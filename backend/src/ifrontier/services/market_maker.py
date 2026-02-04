from __future__ import annotations

from dataclasses import dataclass

from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.market import get_last_price
from ifrontier.infra.sqlite.securities import list_securities
from ifrontier.services.matching import submit_limit_order


@dataclass(frozen=True)
class MarketMakerConfig:
    account_id: str
    spread_pct: float
    min_qty: float


class MarketMaker:
    def __init__(self, *, cfg: MarketMakerConfig) -> None:
        self._cfg = cfg

    def tick_once(self) -> List[MatchResult]:
        create_account(self._cfg.account_id, owner_type="bot_institution", initial_cash=0.0)

        from ifrontier.infra.sqlite.orders import cancel_orders_by_account
        # 每次 Tick 前先清理旧挂单，保持盘口新鲜
        cancel_orders_by_account(self._cfg.account_id)

        import random
        # 检查是否有活跃的新闻链，如果有，大幅增加波动率
        from ifrontier.infra.sqlite.db import get_connection
        conn = get_connection()
        active_chains = conn.execute("SELECT COUNT(*) FROM news_chains WHERE status = 'ACTIVE'").fetchone()[0]

        # 基础波动率 0.5%，如果有活跃事件，波动率翻倍甚至更多
        # 同时大幅提高成交深度，确保大额订单也能成交
        volatility_multiplier = 1.0 + (active_chains * 1.5) 

        all_matches = []
        for sec in list_securities(status="TRADABLE"):
            mid = get_last_price(sec.symbol) or float(sec.seed_price)
            if mid <= 0:
                continue

            # 模拟价格呼吸效应，随事件强度增加
            breathing_range = 0.01 * volatility_multiplier # 提升基础呼吸到 1%
            breathing = 1.0 + random.uniform(-breathing_range, breathing_range)
            mid *= breathing

            # 价差随波动率扩大
            spread = 0.002 * volatility_multiplier # 缩小基础价差到 0.2%，增加竞争性
            bid = float(mid) * (1.0 - spread)
            ask = float(mid) * (1.0 + spread)

            # 动态深度：活跃期间深度翻倍，机构做市商提供更深盘口
            qty = float(self._cfg.min_qty) * volatility_multiplier * 5.0 

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
            noise_prob = min(0.5 + (active_chains * 0.1), 0.8)
            if random.random() < noise_prob: 
                side = random.choice(["BUY", "SELL"])
                # 噪声成交规模也随波动率放大，制造更大的成交量
                # 基础 1.0，活跃期间放大到 10-100 股
                noise_qty = float(1.0 + random.uniform(0, 5.0) * volatility_multiplier)
                
                from ifrontier.services.matching import submit_market_order
                try:
                    noise_matches = submit_market_order(
                        account_id=self._cfg.account_id,
                        symbol=sec.symbol,
                        side=side,
                        quantity=noise_qty
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
