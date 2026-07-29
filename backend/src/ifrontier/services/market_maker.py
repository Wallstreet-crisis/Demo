from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List

from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.market import get_last_price, get_price_series, list_trades
from ifrontier.infra.sqlite.securities import list_securities, SecuritySpec
from ifrontier.services.matching import submit_limit_order, MatchResult
from ifrontier.core.ai_logger import log_ai_action
from ifrontier.services.flow_detector import FlowDetector


@dataclass(frozen=True)
class MarketMakerConfig:
    account_id: str
    spread_pct: float
    min_qty: float


# ── 做市商资本池基准 ──
BASELINE_CAPITAL = 1_000_000_000.0
DAILY_REGEN_CAP = 0.6

# ── 广播事件阈值（与模式阈值独立，用于 scheduler 事件广播）──
HEALTH_WARN_THRESHOLD = 0.3
HEALTH_CRITICAL_THRESHOLD = 0.1

# ── 仓位硬约束 ──
MAX_POSITION_PCT = 0.25
MIN_CASH_RESERVE = 0.05
MAX_SYMBOLS_SIMULTANEOUS = 5
QUOTE_PCT = 0.005  # 每单占目标仓位的比例

# ── 健康度阈值 ──
HEALTH_NORMAL_THRESHOLD = 0.5
HEALTH_YELLOW_THRESHOLD = 0.2
HEALTH_RED_THRESHOLD = 0.1
HEALTH_DEAD_THRESHOLD = 0.01


class MarketMakerMode(Enum):
    NORMAL = "normal"
    YELLOW = "yellow"
    RED = "red"
    PAUSED = "paused"


def _determine_mode(health: float) -> MarketMakerMode:
    if health < HEALTH_DEAD_THRESHOLD:
        return MarketMakerMode.PAUSED
    if health < HEALTH_RED_THRESHOLD:
        return MarketMakerMode.PAUSED
    if health < HEALTH_YELLOW_THRESHOLD:
        return MarketMakerMode.RED
    if health < HEALTH_NORMAL_THRESHOLD:
        return MarketMakerMode.YELLOW
    return MarketMakerMode.NORMAL


def _vwap(trades) -> float:
    if not trades:
        return 0.0
    total_value = sum(t.price * t.quantity for t in trades)
    total_qty = sum(t.quantity for t in trades)
    if total_qty <= 0:
        return trades[-1].price
    return total_value / total_qty


def _inventory_skew(current_position: float, target_position: float) -> float:
    if target_position <= 0:
        return 0.0
    deviation = (current_position - target_position) / target_position
    return -math.tanh(deviation * 2.0)


def _regen_rate(health: float) -> float:
    if health < 0.1:
        return 0.0
    if health < 0.3:
        return 0.02
    if health < 0.6:
        return 0.01
    return 0.005


class MarketMaker:
    def __init__(self, *, cfg: MarketMakerConfig) -> None:
        self._cfg = cfg
        self._last_health: float = 1.0
        self._bankrupt_announced: bool = False
        self._flow_detector = FlowDetector()

    def compute_health(self) -> float:
        snap = get_snapshot(self._cfg.account_id)
        cash = float(snap.cash)

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
        from ifrontier.infra.sqlite.db import get_connection

        health = self.compute_health()
        if health >= DAILY_REGEN_CAP:
            return

        rate = _regen_rate(health)
        if rate <= 0:
            return

        regen_cash = BASELINE_CAPITAL * rate * 0.5
        regen_qty_budget = BASELINE_CAPITAL * rate * 0.5

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
            detail=f"Daily regen applied. Cash +{regen_cash:,.0f}, Health before: {health:.2%}, Rate: {rate:.2%}"
        )

    def _mode_params(self, mode: MarketMakerMode) -> tuple:
        if mode == MarketMakerMode.NORMAL:
            return (0.005, 0.01, 1.0, 7)
        if mode == MarketMakerMode.YELLOW:
            return (0.01, 0.015, 0.5, 5)
        if mode == MarketMakerMode.RED:
            return (0.015, 0.02, 0.2, 3)
        return (0.0, 0.0, 0.0, 0)

    def _fair_value(self, symbol: str, seed_price: float) -> float:
        short_limit = 20
        long_limit = 100

        short_trades = list_trades(symbol=symbol, limit=short_limit)
        long_trades = list_trades(symbol=symbol, limit=long_limit)

        short_vwap = _vwap(short_trades) if short_trades else seed_price
        long_vwap = _vwap(long_trades) if len(long_trades) >= long_limit else seed_price

        prices = get_price_series(symbol=symbol, limit=30)
        if len(prices) >= 5:
            mean = sum(prices) / len(prices)
            cv = (max(prices) - min(prices)) / mean if mean > 0 else 0
            market_is_calm = cv < 0.10
        else:
            market_is_calm = True

        if market_is_calm:
            return short_vwap * 0.5 + long_vwap * 0.3 + seed_price * 0.2
        return seed_price * 0.4 + long_vwap * 0.4 + short_vwap * 0.2

    def _volume_ranked_symbols(self) -> List[str]:
        from ifrontier.infra.sqlite.db import get_connection
        conn = get_connection()
        rows = conn.execute(
            "SELECT symbol, SUM(quantity) AS vol FROM market_trades GROUP BY symbol ORDER BY vol DESC"
        ).fetchall()
        return [str(r["symbol"]) for r in rows]

    def _select_active_symbols(self, mode: MarketMakerMode) -> List[SecuritySpec]:
        all_tradable = list_securities(status="TRADABLE")
        if not all_tradable:
            return []

        _, _, _, max_symbols = self._mode_params(mode)
        if max_symbols >= len(all_tradable):
            return all_tradable

        volume_ranking = self._volume_ranked_symbols()
        symbol_rank = {sym: i for i, sym in enumerate(volume_ranking)}
        sorted_tradable = sorted(all_tradable, key=lambda s: symbol_rank.get(s.symbol, 999))
        return sorted_tradable[:max_symbols]

    def tick_once(self, *, active_chains_count: int = 0) -> List[MatchResult]:
        create_account(self._cfg.account_id, owner_type="market_maker", initial_cash=0.0)

        from ifrontier.infra.sqlite.orders import cancel_orders_by_account
        cancel_orders_by_account(self._cfg.account_id)

        health = self.compute_health()
        self._last_health = health

        mode = _determine_mode(health)

        if mode == MarketMakerMode.PAUSED:
            if not self._bankrupt_announced:
                log_ai_action(
                    agent_id=self._cfg.account_id,
                    action_type="MM_BANKRUPT",
                    detail=f"Market maker is bankrupt! Health: {health:.4%}. Halting all market making."
                )
                self._bankrupt_announced = True
            return []

        snap = get_snapshot(self._cfg.account_id)
        total_capital = float(snap.cash) + sum(
            float(snap.positions.get(sec.symbol.upper(), 0.0)) * (
                get_last_price(sec.symbol) or float(sec.seed_price)
            )
            for sec in list_securities(status="TRADABLE")
        )

        min_spread, max_spread, qty_mult, _ = self._mode_params(mode)
        spread = min_spread + (max_spread - min_spread) * (1.0 - health)

        active_symbols = self._select_active_symbols(mode)
        symbol_count = len(active_symbols)
        target_value_per_symbol = total_capital * (0.15 / max(symbol_count, 1))

        min_cash_reserve = total_capital * MIN_CASH_RESERVE
        max_position_per_symbol = total_capital * MAX_POSITION_PCT

        attack_side = self._flow_detector.attack_side()

        log_ai_action(
            agent_id=self._cfg.account_id,
            action_type="MM_TICK",
            detail=(
                f"Mode: {mode.value} | Health: {health:.2%} | "
                f"Spread: {spread:.2%} | QtyMult: {qty_mult:.2f} | "
                f"ActiveSymbols: {len(active_symbols)}/{len(list_securities(status='TRADABLE'))} | "
                f"AttackSide: {attack_side or 'none'}"
            )
        )

        all_matches: List[MatchResult] = []
        for sec in active_symbols:
            seed_price = float(sec.seed_price)
            fair = self._fair_value(sec.symbol, seed_price)
            if fair <= 0:
                continue

            current_pos = float(snap.positions.get(sec.symbol.upper(), 0.0))
            target_pos = target_value_per_symbol / fair
            raw_skew = _inventory_skew(current_pos, target_pos)
            skew = raw_skew * spread

            bid_price = fair * (1.0 - spread / 2.0 + skew)
            ask_price = fair * (1.0 + spread / 2.0 + skew)
            qty = max(target_pos * QUOTE_PCT * qty_mult, float(self._cfg.min_qty))

            if bid_price <= 0 or ask_price <= 0 or qty < 0.01:
                continue

            cash = float(snap.cash)
            pos = float(snap.positions.get(sec.symbol.upper(), 0.0))

            # ── BUY ──
            can_buy = True
            if attack_side == "SELL":
                can_buy = False
            if cash - bid_price * qty < min_cash_reserve:
                can_buy = False
            if pos + qty > max_position_per_symbol / fair:
                qty_buy = max_position_per_symbol / fair - pos
                if qty_buy < float(self._cfg.min_qty):
                    can_buy = False
                else:
                    buy_qty = qty_buy
            else:
                buy_qty = qty
            if can_buy and buy_qty >= float(self._cfg.min_qty):
                try:
                    _, matches = submit_limit_order(
                        account_id=self._cfg.account_id,
                        symbol=sec.symbol,
                        side="BUY",
                        price=float(bid_price),
                        quantity=float(buy_qty),
                    )
                    for m in matches:
                        self._flow_detector.record_trade("SELL", 0)
                    all_matches.extend(matches)
                    if matches:
                        snap = get_snapshot(self._cfg.account_id)
                except ValueError:
                    snap = get_snapshot(self._cfg.account_id)

            # ── SELL ──
            can_sell = True
            if attack_side == "BUY":
                can_sell = False
            if pos <= 0:
                can_sell = False
            if pos < float(self._cfg.min_qty):
                can_sell = False
            sell_qty = min(qty, pos)
            if can_sell and sell_qty >= float(self._cfg.min_qty):
                try:
                    _, matches = submit_limit_order(
                        account_id=self._cfg.account_id,
                        symbol=sec.symbol,
                        side="SELL",
                        price=float(ask_price),
                        quantity=float(sell_qty),
                    )
                    for m in matches:
                        self._flow_detector.record_trade("BUY", 0)
                    all_matches.extend(matches)
                    if matches:
                        snap = get_snapshot(self._cfg.account_id)
                except ValueError:
                    snap = get_snapshot(self._cfg.account_id)

        return all_matches

    @property
    def last_health(self) -> float:
        return self._last_health
