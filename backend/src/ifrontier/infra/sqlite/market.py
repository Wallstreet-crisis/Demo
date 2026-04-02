from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from ifrontier.infra.sqlite.db import get_connection


@dataclass(frozen=True)
class TradePrint:
    symbol: str
    price: float
    quantity: float
    occurred_at: str
    event_id: str


@dataclass(frozen=True)
class Candle:
    bucket_start: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float
    trades: int


def init_market_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            occurred_at TEXT NOT NULL,
            event_id TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_market_trades_symbol_time
            ON market_trades(symbol, occurred_at);

        CREATE INDEX IF NOT EXISTS idx_market_trades_event
            ON market_trades(event_id);
        """
    )

    conn.commit()


def record_trade(*, symbol: str, price: float, quantity: float, occurred_at: datetime, event_id: str) -> None:
    if not symbol:
        raise ValueError("symbol is required")
    if price <= 0:
        raise ValueError("price must be positive")
    if quantity < 0:
        raise ValueError("quantity must be non-negative")

    conn = get_connection()
    ts = occurred_at.astimezone(timezone.utc).isoformat()

    with conn:
        conn.execute(
            "INSERT INTO market_trades(symbol, price, quantity, occurred_at, event_id) VALUES (?, ?, ?, ?, ?)",
            (symbol, float(price), float(quantity), ts, str(event_id)),
        )


def list_trades(*, symbol: str, limit: int = 200) -> List[TradePrint]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT symbol, price, quantity, occurred_at, event_id FROM market_trades WHERE symbol = ? ORDER BY occurred_at DESC, trade_id DESC LIMIT ?",
        (symbol, int(limit)),
    ).fetchall()

    return [
        TradePrint(
            symbol=str(r["symbol"]),
            price=float(r["price"]),
            quantity=float(r["quantity"]),
            occurred_at=str(r["occurred_at"]),
            event_id=str(r["event_id"]),
        )
        for r in rows
    ]


def get_last_price(symbol: str) -> Optional[float]:
    conn = get_connection()
    row = conn.execute(
        "SELECT price FROM market_trades WHERE symbol = ? ORDER BY occurred_at DESC, trade_id DESC LIMIT 1",
        (symbol,),
    ).fetchone()
    if row is None:
        return None
    return float(row["price"])


def get_last_price_before(*, symbol: str, before_utc: datetime) -> Optional[float]:
    if before_utc.tzinfo is None:
        before_utc = before_utc.replace(tzinfo=timezone.utc)
    before_utc = before_utc.astimezone(timezone.utc)

    conn = get_connection()
    row = conn.execute(
        "SELECT price FROM market_trades WHERE symbol = ? AND occurred_at < ? ORDER BY occurred_at DESC, trade_id DESC LIMIT 1",
        (symbol, before_utc.isoformat()),
    ).fetchone()
    if row is None:
        return None
    return float(row["price"])


def get_price_series(*, symbol: str, limit: int = 200) -> List[float]:
    conn = get_connection()
    # 获取最新的 N 笔交易价格，并按时间正序排列（最旧到最新）
    rows = conn.execute(
        """
        SELECT price FROM (
            SELECT price, occurred_at, trade_id 
            FROM market_trades 
            WHERE symbol = ? 
            ORDER BY occurred_at DESC, trade_id DESC 
            LIMIT ?
        ) ORDER BY occurred_at ASC, trade_id ASC
        """,
        (symbol, int(limit)),
    ).fetchall()
    return [float(r["price"]) for r in rows]


def list_active_symbols(*, limit: int = 20) -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT symbol, MAX(occurred_at) AS last_at FROM market_trades GROUP BY symbol ORDER BY last_at DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [str(r["symbol"]) for r in rows]


def get_candles(*, symbol: str, interval_seconds: int = 60, limit: int = 200) -> List[Candle]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    conn = get_connection()

    # 仅加载覆盖 limit 个桶所需的时间范围，避免全表扫描
    lookback_seconds = int(interval_seconds) * int(limit) * 2  # 2x 余量
    cutoff = datetime.now(timezone.utc)
    since = (cutoff - timedelta(seconds=lookback_seconds)).isoformat()

    rows = conn.execute(
        "SELECT price, quantity, occurred_at FROM market_trades "
        "WHERE symbol = ? AND occurred_at >= ? "
        "ORDER BY occurred_at ASC, trade_id ASC",
        (symbol, since),
    ).fetchall()

    def _bucket_start_iso(ts_iso: str) -> str:
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        epoch = int(dt.timestamp())
        bucket = epoch - (epoch % int(interval_seconds))
        return datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat()

    buckets: Dict[str, List[Tuple[float, float]]] = {}
    for r in rows:
        b = _bucket_start_iso(str(r["occurred_at"]))
        buckets.setdefault(b, []).append((float(r["price"]), float(r["quantity"])))

    out: List[Candle] = []
    for b in sorted(buckets.keys()):
        pts = buckets[b]
        prices = [p for p, _q in pts]
        qtys = [q for _p, q in pts]
        vol = float(sum(qtys))
        vwap = float(sum(p * q for p, q in pts) / vol) if vol > 0 else float(prices[-1])
        out.append(
            Candle(
                bucket_start=b,
                open=float(prices[0]),
                high=float(max(prices)),
                low=float(min(prices)),
                close=float(prices[-1]),
                volume=vol,
                vwap=vwap,
                trades=int(len(prices)),
            )
        )

    if limit > 0:
        out = out[-int(limit) :]
    return out
