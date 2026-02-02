from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ifrontier.infra.sqlite.ledger import AccountSnapshot, get_snapshot
from ifrontier.infra.sqlite.market import get_last_price


@dataclass(frozen=True)
class AccountValuation:
    account_id: str
    cash: float
    positions: Dict[str, float]
    equity_value: float
    total_value: float
    discount_factor: float
    prices: Dict[str, Optional[float]]


def value_account(*, account_id: str, discount_factor: float = 1.0) -> AccountValuation:
    if discount_factor < 0:
        raise ValueError("discount_factor must be >= 0")

    snap: AccountSnapshot = get_snapshot(account_id)

    equity_value = 0.0
    prices: Dict[str, Optional[float]] = {}
    for symbol, qty in (snap.positions or {}).items():
        q = float(qty)
        if abs(q) < 1e-12:
            continue
        px = get_last_price(symbol)
        prices[str(symbol)] = px
        if px is None:
            continue
        equity_value += q * float(px) * float(discount_factor)

    total_value = float(snap.cash) + float(equity_value)

    return AccountValuation(
        account_id=snap.account_id,
        cash=float(snap.cash),
        positions=dict(snap.positions or {}),
        equity_value=float(equity_value),
        total_value=float(total_value),
        discount_factor=float(discount_factor),
        prices=prices,
    )
