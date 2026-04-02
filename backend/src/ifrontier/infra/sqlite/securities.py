from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Optional

from ifrontier.core.logger import get_logger
from ifrontier.infra.sqlite.db import get_connection

_log = get_logger(__name__)


@dataclass(frozen=True)
class SecuritySpec:
    symbol: str
    sector: str
    status: str
    seed_price: float


def init_securities_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS securities (
            symbol TEXT PRIMARY KEY,
            sector TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'TRADABLE',
            seed_price REAL NOT NULL DEFAULT 1.0
        );

        CREATE INDEX IF NOT EXISTS idx_securities_status ON securities(status);
        CREATE INDEX IF NOT EXISTS idx_securities_sector ON securities(sector);
        """
    )
    conn.commit()

    # 初始化种子数据
    default_symbols = [
        ("BLUEGOLD", "MILITARY", 150.0),
        ("CIVILBANK", "FINANCE", 80.0),
        ("FOODMART", "CONSUMER", 45.0),
        ("NEURALINK", "TECH", 210.0),
        ("MARS_GEN", "ENERGY", 120.0),
        ("BIO_SYNTH", "HEALTHCARE", 95.0),
        ("ORBIT_LOG", "LOGISTICS", 65.0),
    ]
    from ifrontier.infra.sqlite.market import record_trade
    from datetime import datetime, timezone
    from uuid import uuid4

    with conn:
        for sym, sec, price in default_symbols:
            # 1) 插入证券定义
            conn.execute(
                "INSERT OR IGNORE INTO securities(symbol, sector, seed_price) VALUES (?, ?, ?)",
                (sym, sec, float(price))
            )
            
            # 2) 检查是否已经有成交记录
            row = conn.execute("SELECT 1 FROM market_trades WHERE symbol = ? LIMIT 1", (sym,)).fetchone()
            if row is None:
                # 如果没有成交记录，记录一笔创世交易用于定标
                _log.info("Recording genesis trade for %s at %s", sym, price)
                record_trade(
                    symbol=sym,
                    price=float(price),
                    quantity=0.0,
                    occurred_at=datetime.now(timezone.utc),
                    event_id=f"genesis:{uuid4()}"
                )


def upsert_security(*, symbol: str, sector: str = "", status: str = "TRADABLE", seed_price: float = 1.0) -> None:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    if seed_price <= 0:
        raise ValueError("seed_price must be > 0")

    st = str(status or "TRADABLE").strip().upper()
    if st not in {"TRADABLE", "HALTED"}:
        raise ValueError("invalid status")

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO securities(symbol, sector, status, seed_price) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(symbol) DO UPDATE SET sector = excluded.sector, status = excluded.status, seed_price = excluded.seed_price",
            (sym, str(sector or ""), st, float(seed_price)),
        )


def list_securities(*, status: str | None = None) -> List[SecuritySpec]:
    conn = get_connection()
    if status is None:
        rows = conn.execute("SELECT symbol, sector, status, seed_price FROM securities ORDER BY symbol ASC").fetchall()
    else:
        st = str(status).strip().upper()
        rows = conn.execute(
            "SELECT symbol, sector, status, seed_price FROM securities WHERE status = ? ORDER BY symbol ASC",
            (st,),
        ).fetchall()

    return [
        SecuritySpec(
            symbol=str(r["symbol"]),
            sector=str(r["sector"] or ""),
            status=str(r["status"]),
            seed_price=float(r["seed_price"]),
        )
        for r in rows
    ]


def get_security(symbol: str) -> Optional[SecuritySpec]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None

    conn = get_connection()
    row = conn.execute(
        "SELECT symbol, sector, status, seed_price FROM securities WHERE symbol = ?",
        (sym,),
    ).fetchone()
    if row is None:
        return None

    return SecuritySpec(
        symbol=str(row["symbol"]),
        sector=str(row["sector"] or ""),
        status=str(row["status"]),
        seed_price=float(row["seed_price"]),
    )


def set_status(*, symbol: str, status: str) -> None:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")

    st = str(status or "").strip().upper()
    if st not in {"TRADABLE", "HALTED"}:
        raise ValueError("invalid status")

    conn = get_connection()
    with conn:
        cur = conn.execute("UPDATE securities SET status = ? WHERE symbol = ?", (st, sym))
        if cur.rowcount == 0:
            raise ValueError("symbol not found")


def any_securities_configured() -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM securities LIMIT 1").fetchone()
    return row is not None


def assert_symbol_tradable(symbol: str) -> None:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")

    if not any_securities_configured():
        return

    sec = get_security(sym)
    if sec is None:
        raise ValueError("symbol not in securities pool")
    if sec.status != "TRADABLE":
        raise ValueError("symbol halted")


def load_securities_pool_from_env() -> None:
    path = os.getenv("IF_SECURITIES_POOL_JSON")
    if not path:
        return

    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)

    symbols = obj.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError("invalid securities pool config")

    for item in symbols:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        sector = str(item.get("sector") or "")
        status = str(item.get("status") or "TRADABLE")
        seed_price = float(item.get("seed_price") or 1.0)
        upsert_security(symbol=symbol, sector=sector, status=status, seed_price=seed_price)
