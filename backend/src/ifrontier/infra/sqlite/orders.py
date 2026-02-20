from __future__ import annotations

"""SQLite-backed order book.

当前支持：
- 限价单 (LIMIT)：进入订单簿，可被撮合
- 市价单 (MARKET)：由撮合引擎“吃单”实现，不进入订单簿

撮合规则（由 matching.py 实现）：价格优先，其次时间优先。
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from ifrontier.infra.sqlite.db import get_connection


@dataclass
class Order:
    order_id: str
    account_id: str
    symbol: str
    side: str  # BUY / SELL
    order_type: str  # LIMIT / MARKET
    price: float
    quantity_remaining: float
    status: str  # OPEN / PARTIAL_FILLED / FILLED / CANCELLED
    created_at: str


def init_order_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            order_type TEXT NOT NULL DEFAULT 'LIMIT',
            price REAL NOT NULL,
            quantity_remaining REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_orders_symbol_side_price_time
            ON orders(symbol, side, price, created_at);
        """
    )

    conn.commit()


def insert_limit_order(account_id: str, symbol: str, side: str, price: float, quantity: float) -> Order:
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    if price <= 0 or quantity <= 0:
        raise ValueError("price and quantity must be positive")

    conn = get_connection()
    account_id = str(account_id).lower()
    order_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    with conn:
        conn.execute(
            "INSERT INTO orders(order_id, account_id, symbol, side, order_type, price, quantity_remaining, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_id, account_id, symbol, side, "LIMIT", price, quantity, "OPEN", created_at),
        )

    return Order(
        order_id=order_id,
        account_id=account_id,
        symbol=symbol,
        side=side,
        order_type="LIMIT",
        price=price,
        quantity_remaining=quantity,
        status="OPEN",
        created_at=created_at,
    )


def load_order(order_id: str) -> Optional[Order]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if row is None:
        return None

    return Order(
        order_id=row["order_id"],
        account_id=row["account_id"],
        symbol=row["symbol"],
        side=row["side"],
        order_type=row["order_type"],
        price=float(row["price"]),
        quantity_remaining=float(row["quantity_remaining"]),
        status=row["status"],
        created_at=row["created_at"],
    )


def update_order_quantity_and_status(order_id: str, new_quantity: float, new_status: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE orders SET quantity_remaining = ?, status = ? WHERE order_id = ?",
            (new_quantity, new_status, order_id),
        )


def cancel_orders_by_account(account_id: str, symbol: Optional[str] = None) -> int:
    conn = get_connection()
    account_id = str(account_id).lower()
    sql = "UPDATE orders SET status = 'CANCELLED', quantity_remaining = 0 WHERE account_id = ? AND status IN ('OPEN', 'PARTIAL_FILLED')"
    params = [account_id]
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol)
    
    with conn:
        res = conn.execute(sql, params)
        return res.rowcount


def fetch_best_opposite_orders(symbol: str, side: str) -> List[Order]:
    """Return candidate opposite LIMIT orders sorted by price/time.

    For an incoming BUY, we look for SELLs ordered by price ASC, created_at ASC.
    For an incoming SELL, we look for BUYs ordered by price DESC, created_at ASC.

    Note: 市价单不进入 orders 表，因此这里永远只会返回 LIMIT 订单。
    """

    conn = get_connection()

    if side == "BUY":
        opp_side = "SELL"
        sql = (
            "SELECT * FROM orders "
            "WHERE symbol = ? AND side = ? AND order_type = 'LIMIT' AND status IN ('OPEN','PARTIAL_FILLED') "
            "ORDER BY price ASC, created_at ASC"
        )
    elif side == "SELL":
        opp_side = "BUY"
        sql = (
            "SELECT * FROM orders "
            "WHERE symbol = ? AND side = ? AND order_type = 'LIMIT' AND status IN ('OPEN','PARTIAL_FILLED') "
            "ORDER BY price DESC, created_at ASC"
        )
    else:
        raise ValueError("side must be BUY or SELL")

    rows = conn.execute(sql, (symbol, opp_side)).fetchall()

    return [
        Order(
            order_id=r["order_id"],
            account_id=r["account_id"],
            symbol=r["symbol"],
            side=r["side"],
            order_type=r["order_type"],
            price=float(r["price"]),
            quantity_remaining=float(r["quantity_remaining"]),
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def list_open_orders(symbol: str, side: str, limit: int = 20) -> List[Order]:
    conn = get_connection()
    side_u = str(side or "").upper()
    if side_u not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")

    lim = max(1, min(int(limit or 20), 200))
    if side_u == "BUY":
        order_sql = "ORDER BY price DESC, created_at ASC"
    else:
        order_sql = "ORDER BY price ASC, created_at ASC"

    rows = conn.execute(
        (
            "SELECT * FROM orders "
            "WHERE symbol = ? AND side = ? AND order_type = 'LIMIT' AND status IN ('OPEN','PARTIAL_FILLED') "
            f"{order_sql} LIMIT ?"
        ),
        (symbol, side_u, lim),
    ).fetchall()

    return [
        Order(
            order_id=r["order_id"],
            account_id=r["account_id"],
            symbol=r["symbol"],
            side=r["side"],
            order_type=r["order_type"],
            price=float(r["price"]),
            quantity_remaining=float(r["quantity_remaining"]),
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def list_open_orders_by_account(account_id: str, symbol: Optional[str] = None, limit: int = 50) -> List[Order]:
    conn = get_connection()
    account_norm = str(account_id).lower()
    lim = max(1, min(int(limit or 50), 200))

    sql = (
        "SELECT * FROM orders "
        "WHERE account_id = ? AND order_type = 'LIMIT' AND status IN ('OPEN','PARTIAL_FILLED')"
    )
    params: list = [account_norm]
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(lim)

    rows = conn.execute(sql, params).fetchall()
    return [
        Order(
            order_id=r["order_id"],
            account_id=r["account_id"],
            symbol=r["symbol"],
            side=r["side"],
            order_type=r["order_type"],
            price=float(r["price"]),
            quantity_remaining=float(r["quantity_remaining"]),
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def cancel_order(order_id: str, account_id: str) -> bool:
    conn = get_connection()
    account_norm = str(account_id).lower()
    with conn:
        res = conn.execute(
            "UPDATE orders SET status = 'CANCELLED', quantity_remaining = 0 "
            "WHERE order_id = ? AND account_id = ? AND status IN ('OPEN','PARTIAL_FILLED')",
            (order_id, account_norm),
        )
    return (res.rowcount or 0) > 0
