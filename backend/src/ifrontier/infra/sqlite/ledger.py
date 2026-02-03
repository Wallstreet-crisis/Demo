from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List
from uuid import uuid4

from ifrontier.infra.sqlite.db import get_connection


@dataclass
class AccountSnapshot:
    account_id: str
    cash: float
    positions: Dict[str, float]


@dataclass
class ContractTransfer:
    from_account_id: str
    to_account_id: str
    asset_type: str  # CASH / EQUITY
    symbol: str  # CASH / 股票代码
    quantity: float


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


def spend_cash(*, account_id: str, amount: float, event_id: str) -> None:
    if amount <= 0:
        raise ValueError("amount must be positive")

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    with conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO accounts(account_id, owner_type, cash) VALUES (?, ?, 0)",
            (account_id, "user"),
        )
        row = cur.execute(
            "SELECT cash FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        cash = float(row["cash"]) if row is not None else 0.0
        if cash < float(amount) - 1e-9:
            raise ValueError("insufficient cash")

        _insert_ledger(cur, account_id, "CASH", "CASH", -float(amount), str(event_id), now)
        cur.execute(
            "UPDATE accounts SET cash = cash - ? WHERE account_id = ?",
            (float(amount), account_id),
        )


def _insert_ledger(cur, account_id: str, asset_type: str, symbol: str, delta: float, event_id: str, created_at: str) -> None:
    cur.execute(
        "INSERT INTO ledger_entries(entry_id, account_id, asset_type, symbol, delta, event_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid4()), account_id, asset_type, symbol, delta, event_id, created_at),
    )


def apply_contract_transfers(*, transfers: List[ContractTransfer], event_id: str) -> None:
    if not transfers:
        raise ValueError("transfers must be non-empty")

    for t in transfers:
        if t.quantity <= 0:
            raise ValueError("transfer quantity must be positive")
        if t.asset_type not in {"CASH", "EQUITY"}:
            raise ValueError("unsupported asset_type")
        if not t.symbol:
            raise ValueError("symbol is required")
        if not t.from_account_id or not t.to_account_id:
            raise ValueError("from_account_id and to_account_id are required")

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()

    with conn:
        cur = conn.cursor()

        # Ensure accounts exist
        account_ids = set()
        for t in transfers:
            account_ids.add(t.from_account_id)
            account_ids.add(t.to_account_id)
        for acc_id in account_ids:
            cur.execute(
                "INSERT OR IGNORE INTO accounts(account_id, owner_type, cash) VALUES (?, ?, 0)",
                (acc_id, "user"),
            )

        # Pre-check: no overdraft / no negative positions
        for t in transfers:
            if t.asset_type == "CASH":
                cash_row = cur.execute(
                    "SELECT cash FROM accounts WHERE account_id = ?",
                    (t.from_account_id,),
                ).fetchone()
                from_cash = float(cash_row["cash"]) if cash_row is not None else 0.0
                if from_cash < t.quantity - 1e-9:
                    raise ValueError("insufficient cash")
            else:
                pos_row = cur.execute(
                    "SELECT quantity FROM positions WHERE account_id = ? AND symbol = ?",
                    (t.from_account_id, t.symbol),
                ).fetchone()
                from_qty = float(pos_row["quantity"]) if pos_row is not None else 0.0
                if from_qty < t.quantity - 1e-9:
                    raise ValueError("insufficient position")

        # Apply transfers
        for t in transfers:
            # from: -quantity
            _insert_ledger(cur, t.from_account_id, t.asset_type, t.symbol, -t.quantity, event_id, now)
            # to: +quantity
            _insert_ledger(cur, t.to_account_id, t.asset_type, t.symbol, t.quantity, event_id, now)

            if t.asset_type == "CASH":
                cur.execute(
                    "UPDATE accounts SET cash = cash - ? WHERE account_id = ?",
                    (t.quantity, t.from_account_id),
                )
                cur.execute(
                    "UPDATE accounts SET cash = cash + ? WHERE account_id = ?",
                    (t.quantity, t.to_account_id),
                )
            else:
                cur.execute(
                    "UPDATE positions SET quantity = quantity - ? WHERE account_id = ? AND symbol = ?",
                    (t.quantity, t.from_account_id, t.symbol),
                )
                cur.execute(
                    "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
                    (t.to_account_id, t.symbol, t.quantity),
                )

        # Safety: no negative cash / positions
        for acc_id in account_ids:
            cash_row = cur.execute(
                "SELECT cash FROM accounts WHERE account_id = ?",
                (acc_id,),
            ).fetchone()
            if cash_row is None or float(cash_row["cash"]) < -1e-9:
                raise ValueError("negative cash balance after transfer")

            neg_pos_row = cur.execute(
                "SELECT symbol, quantity FROM positions WHERE account_id = ? AND quantity < 0",
                (acc_id,),
            ).fetchone()
            if neg_pos_row is not None:
                raise ValueError("negative position after transfer")
