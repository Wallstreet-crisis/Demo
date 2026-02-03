from __future__ import annotations

from dataclasses import dataclass

from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.market import get_last_price
from ifrontier.infra.sqlite.orders import insert_limit_order
from ifrontier.infra.sqlite.securities import list_securities


@dataclass(frozen=True)
class MarketMakerConfig:
    account_id: str
    spread_pct: float
    min_qty: float


class MarketMaker:
    def __init__(self, *, cfg: MarketMakerConfig) -> None:
        self._cfg = cfg

    def tick_once(self) -> int:
        create_account(self._cfg.account_id, owner_type="bot_institution", initial_cash=0.0)

        placed = 0
        for sec in list_securities(status="TRADABLE"):
            mid = get_last_price(sec.symbol) or float(sec.seed_price)
            if mid <= 0:
                continue

            bid = float(mid) * (1.0 - float(self._cfg.spread_pct) / 2.0)
            ask = float(mid) * (1.0 + float(self._cfg.spread_pct) / 2.0)
            qty = float(self._cfg.min_qty)
            if bid <= 0 or ask <= 0 or qty <= 0:
                continue

            snap = get_snapshot(self._cfg.account_id)
            if float(snap.cash) >= float(bid) * float(qty) - 1e-9:
                insert_limit_order(self._cfg.account_id, sec.symbol, "BUY", float(bid), float(qty))
                placed += 1

            snap = get_snapshot(self._cfg.account_id)
            if float(snap.positions.get(sec.symbol, 0.0)) >= float(qty) - 1e-9:
                insert_limit_order(self._cfg.account_id, sec.symbol, "SELL", float(ask), float(qty))
                placed += 1

        return placed
