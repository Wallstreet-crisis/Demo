from __future__ import annotations

from dataclasses import dataclass

from typing import List, Dict, Any
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


class MarketMaker:
    def __init__(self, *, cfg: MarketMakerConfig) -> None:
        self._cfg = cfg

    def tick_once(self, *, active_chains_count: int = 0) -> List[MatchResult]:
        create_account(self._cfg.account_id, owner_type="market_maker", initial_cash=0.0)

        from ifrontier.infra.sqlite.orders import cancel_orders_by_account
        cancel_orders_by_account(self._cfg.account_id)

        import random
        volatility_multiplier = 1.0 + (active_chains_count * 1.5) 
        panic_factor = min(1.0, active_chains_count / 5.0)

        if active_chains_count > 0:
            log_ai_action(
                agent_id=self._cfg.account_id,
                action_type="MM_ADJUST",
                detail=f"News Chains: {active_chains_count} | Panic: {panic_factor:.2f} | Vol Multiplier: {volatility_multiplier:.2f}"
            )

        # 在循环外获取一次快照，减少 DB 读取次数
        snap = get_snapshot(self._cfg.account_id)

        all_matches = []
        for sec in list_securities(status="TRADABLE"):
            mid = get_last_price(sec.symbol) or float(sec.seed_price)
            if mid <= 0:
                continue

            breathing_range = 0.01 * volatility_multiplier 
            breathing = 1.0 + random.uniform(-breathing_range, breathing_range)
            mid *= breathing

            spread = 0.002 * (1.0 + panic_factor * 10.0) * volatility_multiplier 
            bid = float(mid) * (1.0 - spread)
            ask = float(mid) * (1.0 + spread)

            base_qty = float(self._cfg.min_qty) * 5.0
            if panic_factor > 0.8:
                qty = base_qty * 0.2
            else:
                qty = base_qty * volatility_multiplier

            if bid <= 0 or ask <= 0 or qty <= 0:
                continue

            if float(snap.cash) >= float(bid) * float(qty) - 1e-9:
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

            # --- 噪声成交 ---
            noise_prob = min(0.5 + (active_chains_count * 0.1), 0.8)
            if random.random() < noise_prob: 
                side = random.choice(["BUY", "SELL"])
                noise_qty = float(1.0 + random.uniform(0, 5.0) * volatility_multiplier)
                
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
                        # 留一点 Buffer 避免浮点误差
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
                    pass

            # 再次检查持仓，留出 Buffer 避免 apply_trade_executed 报错
            current_pos = float(snap.positions.get(sec.symbol.upper(), 0.0))
            if current_pos >= float(qty) + 1e-6:
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

        return all_matches
