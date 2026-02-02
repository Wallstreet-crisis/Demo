from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict
from uuid import uuid4

from ifrontier.infra.sqlite.db import get_connection


@dataclass
class AccountSnapshot:
    account_id: str
    cash: float
    positions: Dict[str, float]


def create_account(account_id: str, owner_type: str, initial_cash: float = 0.0) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO accounts(account_id, owner_type, cash) VALUES (?, ?, ?)",
            (account_id, owner_type, initial_cash),
        )


def get_snapshot(account_id: str) -> AccountSnapshot:
    conn = get_connection()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT cash FROM accounts WHERE account_id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"account {account_id} does not exist")

    cash = float(row["cash"])
    positions: Dict[str, float] = {}
    for prow in cur.execute(
        "SELECT symbol, quantity FROM positions WHERE account_id = ?", (account_id,)
    ):
        positions[str(prow["symbol"])] = float(prow["quantity"])

    return AccountSnapshot(account_id=account_id, cash=cash, positions=positions)


def apply_trade_executed(
    *,
    buy_account_id: str,
    sell_account_id: str,
    symbol: str,
    price: float,
    quantity: float,
    event_id: str,
) -> None:
    if quantity <= 0 or price <= 0:
        raise ValueError("price and quantity must be positive")

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cost = price * quantity

    with conn:
        cur = conn.cursor()

        # Ensure accounts exist
        for acc_id in (buy_account_id, sell_account_id):
            cur.execute(
                "INSERT OR IGNORE INTO accounts(account_id, owner_type, cash) VALUES (?, ?, 0)",
                (acc_id, "user"),
            )

        # Check balances
        buy_cash = cur.execute(
            "SELECT cash FROM accounts WHERE account_id = ?", (buy_account_id,)
        ).fetchone()["cash"]
        sell_qty_row = cur.execute(
            "SELECT quantity FROM positions WHERE account_id = ? AND symbol = ?",
            (sell_account_id, symbol),
        ).fetchone()
        sell_qty = float(sell_qty_row["quantity"]) if sell_qty_row is not None else 0.0

        if buy_cash < cost - 1e-9:
            raise ValueError("insufficient cash for buyer")
        if sell_qty < quantity - 1e-9:
            raise ValueError("insufficient position for seller")

        # Buyer: -cash, +symbol
        _insert_ledger(cur, buy_account_id, "CASH", "CASH", -cost, event_id, now)
        _insert_ledger(cur, buy_account_id, "EQUITY", symbol, quantity, event_id, now)

        cur.execute(
            "UPDATE accounts SET cash = cash - ? WHERE account_id = ?",
            (cost, buy_account_id),
        )
        cur.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
            (buy_account_id, symbol, quantity),
        )

        # Seller: +cash, -symbol
        _insert_ledger(cur, sell_account_id, "CASH", "CASH", cost, event_id, now)
        _insert_ledger(cur, sell_account_id, "EQUITY", symbol, -quantity, event_id, now)

        cur.execute(
            "UPDATE accounts SET cash = cash + ? WHERE account_id = ?",
            (cost, sell_account_id),
        )
        cur.execute(
            "UPDATE positions SET quantity = quantity - ? WHERE account_id = ? AND symbol = ?",
            (quantity, sell_account_id, symbol),
        )

        # Safety checks: no negative balances
        for acc_id in (buy_account_id, sell_account_id):
            cash_row = cur.execute(
                "SELECT cash FROM accounts WHERE account_id = ?", (acc_id,)
            ).fetchone()
            if cash_row is None or float(cash_row["cash"]) < -1e-9:
                raise ValueError("negative cash balance after trade")

            neg_pos_row = cur.execute(
                "SELECT symbol, quantity FROM positions WHERE account_id = ? AND quantity < 0",
                (acc_id,),
            ).fetchone()
            if neg_pos_row is not None:
                raise ValueError("negative position after trade")


def _insert_ledger(cur, account_id: str, asset_type: str, symbol: str, delta: float, event_id: str, created_at: str) -> None:
    cur.execute(
        "INSERT INTO ledger_entries(entry_id, account_id, asset_type, symbol, delta, event_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid4()), account_id, asset_type, symbol, delta, event_id, created_at),
    )
