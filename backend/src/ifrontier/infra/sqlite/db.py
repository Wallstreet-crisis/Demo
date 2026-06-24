from __future__ import annotations

import sqlite3
import threading
import contextvars
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict
from uuid import uuid4

# 房间上下文变量，默认 fallback 到 "default"
room_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("room_id", default="default")

# 标记当前是否处于外层统一事务中，供 DB 函数判断是否跳过内部 with conn
_transaction_active: contextvars.ContextVar[bool] = contextvars.ContextVar("transaction_active", default=False)

_TLS = threading.local()


def is_transaction_active() -> bool:
    return _transaction_active.get()


@contextmanager
def transaction():
    """开始一个统一事务。内部 DB 函数可通过 is_transaction_active() 判断并跳过自己的 with conn。"""
    conn = get_connection()
    token = _transaction_active.set(True)
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _transaction_active.reset(token)


@contextmanager
def savepoint(conn: sqlite3.Connection):
    """在已有事务中创建一个 savepoint，失败时回滚到该点。"""
    name = f"sp_{uuid4().hex[:16]}"
    conn.execute(f"SAVEPOINT {name}")
    try:
        yield conn
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise
    else:
        conn.execute(f"RELEASE SAVEPOINT {name}")


def _get_db_path(room_id: str) -> Path:
    base = Path(__file__).resolve().parents[4]
    if room_id == "default":
        # 兼容现有单局数据路径
        data_dir = base / "data"
    else:
        # 按房间隔离的数据路径
        data_dir = base / "data" / "rooms" / room_id
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "ledger.db"


class _TransactionAwareConnection:
    """包装 sqlite3.Connection，当处于外层统一事务时，with conn 不再 commit/rollback。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        if is_transaction_active():
            return self._conn
        return self._conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool | None:
        if is_transaction_active():
            return False
        return self._conn.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def get_connection() -> sqlite3.Connection:
    room_id = room_id_var.get()

    conns: Optional[Dict[str, sqlite3.Connection]] = getattr(_TLS, "conns", None)
    if conns is None:
        conns = {}
        _TLS.conns = conns

    conn = conns.get(room_id)
    if conn is None:
        path = _get_db_path(room_id)
        raw_conn = sqlite3.connect(path, check_same_thread=False)
        raw_conn.row_factory = sqlite3.Row
        raw_conn.execute("PRAGMA journal_mode=WAL;")
        raw_conn.execute("PRAGMA busy_timeout=5000;")
        raw_conn.execute("PRAGMA foreign_keys = ON;")
        conn = _TransactionAwareConnection(raw_conn)
        conns[room_id] = conn
    return conn

def close_connection(room_id: str) -> None:
    conns: Optional[Dict[str, sqlite3.Connection]] = getattr(_TLS, "conns", None)
    if conns is not None:
        conn = conns.pop(room_id, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
