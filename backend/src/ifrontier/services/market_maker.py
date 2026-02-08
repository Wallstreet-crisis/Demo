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
        # 每次 Tick 前先清理旧挂单，保持盘口新鲜
        cancel_orders_by_account(self._cfg.account_id)

        import random
        # 基础波动率 0.5%，如果有活跃事件，波动率翻倍甚至更多
        # 模拟做市商对新闻的恐慌反应：活跃事件越多，价差越大，规避风险
        volatility_multiplier = 1.0 + (active_chains_count * 1.5) 
        
        # 恐慌程度影响：当 active_chains_count 很高时，做市商会收缩深度或大幅拉开价差
        panic_factor = min(1.0, active_chains_count / 5.0)

        if active_chains_count > 0:
            log_ai_action(
                agent_id=self._cfg.account_id,
                action_type="MM_ADJUST",
                detail=f"News Chains: {active_chains_count} | Panic: {panic_factor:.2f} | Vol Multiplier: {volatility_multiplier:.2f}"
            )

        all_matches = []
        for sec in list_securities(status="TRADABLE"):
            mid = get_last_price(sec.symbol) or float(sec.seed_price)
            if mid <= 0:
                continue

            # 模拟价格呼吸效应，随事件强度增加
            breathing_range = 0.01 * volatility_multiplier 
            breathing = 1.0 + random.uniform(-breathing_range, breathing_range)
            mid *= breathing

            # 价差随波动率和恐慌感拉开：规避逆向选择风险
            spread = 0.002 * (1.0 + panic_factor * 10.0) * volatility_multiplier 
            bid = float(mid) * (1.0 - spread)
            ask = float(mid) * (1.0 + spread)

            # 动态深度：正常期间提供深度，极端恐慌期间深度收缩，但活跃（非恐慌）期间深度翻倍
            # 这里的逻辑是：如果只是活跃（有新闻但链数不多），增加流动性；如果链数爆炸，说明有极端行情，收缩深度保命
            base_qty = float(self._cfg.min_qty) * 5.0
            if panic_factor > 0.8:
                qty = base_qty * 0.2 # 深度收缩
            else:
                qty = base_qty * volatility_multiplier

            if bid <= 0 or ask <= 0 or qty <= 0:
                continue

            snap = get_snapshot(self._cfg.account_id)
            if float(snap.cash) >= float(bid) * float(qty) - 1e-9:
                # print(f"[MarketMaker] Submitting BUY for {sec.symbol} at {bid:.2f}")
                _, matches = submit_limit_order(
                    account_id=self._cfg.account_id,
                    symbol=sec.symbol,
                    side="BUY",
                    price=float(bid),
                    quantity=float(qty)
                )
                all_matches.extend(matches)

            # --- 增加：做市商主动“跨盘”成交，制造市场底噪和流动性 ---
            # 基础概率 50%，随事件强度增加到 80%
            noise_prob = min(0.5 + (active_chains_count * 0.1), 0.8)
            if random.random() < noise_prob: 
                side = random.choice(["BUY", "SELL"])
                # 噪声成交规模也随波动率放大，制造更大的成交量
                # 基础 1.0，活跃期间放大到 10-100 股
                noise_qty = float(1.0 + random.uniform(0, 5.0) * volatility_multiplier)
                
                from ifrontier.services.matching import submit_market_order
                try:
                    snap = get_snapshot(self._cfg.account_id)
                    if side == "BUY":
                        # 市价单最终成交价来自对手盘，这里用 mid 粗略估算成本做保护。
                        est_cost = float(mid) * float(noise_qty)
                        if float(snap.cash) >= est_cost - 1e-9:
                            noise_matches = submit_market_order(
                                account_id=self._cfg.account_id,
                                symbol=sec.symbol,
                                side=side,
                                quantity=noise_qty,
                            )
                            all_matches.extend(noise_matches)
                    else:
                        avail = float(snap.positions.get(str(sec.symbol).upper(), 0.0))
                        if avail >= float(noise_qty) - 1e-9:
                            noise_matches = submit_market_order(
                                account_id=self._cfg.account_id,
                                symbol=sec.symbol,
                                side=side,
                                quantity=noise_qty,
                            )
                            all_matches.extend(noise_matches)
                except Exception:
                    pass
            # -----------------------------------------------

            snap = get_snapshot(self._cfg.account_id)
            if float(snap.positions.get(sec.symbol, 0.0)) >= float(qty) - 1e-9:
                # print(f"[MarketMaker] Submitting SELL for {sec.symbol} at {ask:.2f}")
                _, matches = submit_limit_order(
                    account_id=self._cfg.account_id,
                    symbol=sec.symbol,
                    side="SELL",
                    price=float(ask),
                    quantity=float(qty)
                )
                all_matches.extend(matches)

        return all_matches
