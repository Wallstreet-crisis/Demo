from __future__ import annotations

from dataclasses import dataclass

from typing import List
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.market import get_last_price
from ifrontier.infra.sqlite.securities import list_securities
from ifrontier.services.matching import submit_limit_order, MatchResult
from ifrontier.core.ai_logger import log_ai_action


@dataclass(frozen=True)
class MarketMakerConfig:
    account_id: str
    spread_pct: float
    min_qty: float


# ── 做市商资本池基准 ──
# 健康度 = (当前现金 + 持仓市值) / BASELINE_CAPITAL
# 用于动态调整做市参数；归零时停止做市
BASELINE_CAPITAL = 1_000_000_000.0      # 初始总资本基准 (10亿)
DAILY_REGEN_RATE = 0.005                # 每游戏日自然恢复比率 (0.5%)
DAILY_REGEN_CAP = 0.6                   # 恢复上限 (不会超过基准的60%，防止完全回血)
HEALTH_WARN_THRESHOLD = 0.3             # 健康度低于此值时发出警报
HEALTH_CRITICAL_THRESHOLD = 0.1         # 健康度低于此值时进入危机模式
HEALTH_DEAD_THRESHOLD = 0.01            # 低于此值视为破产，停止做市


class MarketMaker:
    def __init__(self, *, cfg: MarketMakerConfig) -> None:
        self._cfg = cfg
        self._last_health: float = 1.0
        self._bankrupt_announced: bool = False

    def compute_health(self) -> float:
        """计算做市商健康度 (0.0 ~ 1.0+)。"""
        snap = get_snapshot(self._cfg.account_id)
        cash = float(snap.cash)

        # 计算持仓市值
        position_value = 0.0
        for sec in list_securities(status="TRADABLE"):
            qty = float(snap.positions.get(sec.symbol.upper(), 0.0))
            if qty > 0:
                price = get_last_price(sec.symbol) or float(sec.seed_price)
                position_value += qty * price

        total = cash + position_value
        health = total / BASELINE_CAPITAL if BASELINE_CAPITAL > 0 else 0.0
        return max(0.0, health)

    def daily_regen(self) -> None:
        """每游戏日开盘时调用：自然恢复少量现金和持仓。"""
        from ifrontier.infra.sqlite.db import get_connection

        health = self.compute_health()
        if health >= DAILY_REGEN_CAP:
            return  # 已经超过恢复上限，不再补

        regen_cash = BASELINE_CAPITAL * DAILY_REGEN_RATE * 0.5  # 一半分给现金
        regen_qty_budget = BASELINE_CAPITAL * DAILY_REGEN_RATE * 0.5  # 一半分给持仓

        conn = get_connection()
        with conn:
            conn.execute(
                "UPDATE accounts SET cash = cash + ? WHERE account_id = ?",
                (regen_cash, self._cfg.account_id),
            )
            securities = list_securities(status="TRADABLE")
            if securities:
                per_symbol_budget = regen_qty_budget / len(securities)
                for sec in securities:
                    price = get_last_price(sec.symbol) or float(sec.seed_price)
                    if price > 0:
                        regen_qty = per_symbol_budget / price
                        conn.execute(
                            "UPDATE positions SET quantity = quantity + ? "
                            "WHERE account_id = ? AND symbol = ?",
                            (regen_qty, self._cfg.account_id, sec.symbol),
                        )

        self._bankrupt_announced = False
        log_ai_action(
            agent_id=self._cfg.account_id,
            action_type="MM_REGEN",
            detail=f"Daily regen applied. Cash +{regen_cash:,.0f}, Health before: {health:.2%}"
        )

    def tick_once(self, *, active_chains_count: int = 0) -> List[MatchResult]:
        create_account(self._cfg.account_id, owner_type="market_maker", initial_cash=0.0)

        from ifrontier.infra.sqlite.orders import cancel_orders_by_account
        cancel_orders_by_account(self._cfg.account_id)

        # ── 健康度检查 ──
        health = self.compute_health()
        self._last_health = health

        if health < HEALTH_DEAD_THRESHOLD:
            if not self._bankrupt_announced:
                log_ai_action(
                    agent_id=self._cfg.account_id,
                    action_type="MM_BANKRUPT",
                    detail=f"Market maker is bankrupt! Health: {health:.4%}. Halting all market making."
                )
                self._bankrupt_announced = True
            return []  # 破产，不做市

        import random

        # ── 健康度影响做市参数 ──
        # 健康度越低 → 点差越大、挂单量越小
        stress_factor = max(0.0, 1.0 - health)  # 0=健康, 1=垂死
        spread_multiplier = 1.0 + stress_factor * 20.0  # 满血1x → 垂死21x
        qty_multiplier = max(0.05, health)  # 满血1x → 垂死0.05x

        volatility_multiplier = 1.0 + (active_chains_count * 1.5)
        panic_factor = min(1.0, active_chains_count / 5.0)

        if health < HEALTH_WARN_THRESHOLD or active_chains_count > 0:
            log_ai_action(
                agent_id=self._cfg.account_id,
                action_type="MM_ADJUST",
                detail=(
                    f"Health: {health:.2%} | Stress: {stress_factor:.2f} | "
                    f"Spread×{spread_multiplier:.1f} | Qty×{qty_multiplier:.2f} | "
                    f"News Chains: {active_chains_count} | Panic: {panic_factor:.2f}"
                )
            )

        snap = get_snapshot(self._cfg.account_id)

        all_matches: List[MatchResult] = []
        for sec in list_securities(status="TRADABLE"):
            mid = get_last_price(sec.symbol) or float(sec.seed_price)
            if mid <= 0:
                continue

            breathing_range = 0.01 * volatility_multiplier
            breathing = 1.0 + random.uniform(-breathing_range, breathing_range)
            mid *= breathing

            spread = 0.002 * (1.0 + panic_factor * 10.0) * volatility_multiplier * spread_multiplier
            bid = float(mid) * (1.0 - spread)
            ask = float(mid) * (1.0 + spread)

            base_qty = float(self._cfg.min_qty) * 5.0
            if panic_factor > 0.8:
                qty = base_qty * 0.2
            else:
                qty = base_qty * volatility_multiplier
            qty *= qty_multiplier  # 健康度衰减

            if bid <= 0 or ask <= 0 or qty < 0.01:
                continue

            # ── 买单 ──
            if float(snap.cash) >= float(bid) * float(qty) - 1e-9:
                try:
                    _, matches = submit_limit_order(
                        account_id=self._cfg.account_id,
                        symbol=sec.symbol,
                        side="BUY",
                        price=float(bid),
                        quantity=float(qty)
                    )
                    all_matches.extend(matches)
                    if matches:
                        snap = get_snapshot(self._cfg.account_id)
                except ValueError:
                    snap = get_snapshot(self._cfg.account_id)

            # ── 噪声成交（仅健康度>10%时才做噪声交易）──
            if health > HEALTH_CRITICAL_THRESHOLD:
                noise_prob = min(0.5 + (active_chains_count * 0.1), 0.8) * qty_multiplier
                if random.random() < noise_prob:
                    side = random.choice(["BUY", "SELL"])
                    noise_qty = float(1.0 + random.uniform(0, 5.0) * volatility_multiplier) * qty_multiplier

                    from ifrontier.services.matching import submit_market_order
                    try:
                        if side == "BUY":
                            est_cost = float(mid) * float(noise_qty)
                            if float(snap.cash) >= est_cost - 1e-9:
                                noise_matches = submit_market_order(
                                    account_id=self._cfg.account_id,
                                    symbol=sec.symbol,
                                    side=side,
                                    quantity=noise_qty,
                                )
                                all_matches.extend(noise_matches)
                                if noise_matches:
                                    snap = get_snapshot(self._cfg.account_id)
                        else:
                            avail = float(snap.positions.get(str(sec.symbol).upper(), 0.0))
                            if avail >= float(noise_qty) + 1e-6:
                                noise_matches = submit_market_order(
                                    account_id=self._cfg.account_id,
                                    symbol=sec.symbol,
                                    side=side,
                                    quantity=noise_qty,
                                )
                                all_matches.extend(noise_matches)
                                if noise_matches:
                                    snap = get_snapshot(self._cfg.account_id)
                    except Exception:
                        snap = get_snapshot(self._cfg.account_id)

            # ── 卖单 ──
            current_pos = float(snap.positions.get(sec.symbol.upper(), 0.0))
            if current_pos >= float(qty) + 1e-6:
                try:
                    _, matches = submit_limit_order(
                        account_id=self._cfg.account_id,
                        symbol=sec.symbol,
                        side="SELL",
                        price=float(ask),
                        quantity=float(qty)
                    )
                    all_matches.extend(matches)
                    if matches:
                        snap = get_snapshot(self._cfg.account_id)
                except ValueError:
                    snap = get_snapshot(self._cfg.account_id)

        return all_matches

    @property
    def last_health(self) -> float:
        return self._last_health
