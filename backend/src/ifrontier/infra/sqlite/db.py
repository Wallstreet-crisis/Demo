from __future__ import annotations

import sqlite3
import threading
import contextvars
from pathlib import Path
from typing import Optional, Dict

# 房间上下文变量，默认 fallback 到 "default"
room_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("room_id", default="default")

_TLS = threading.local()


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


def get_connection() -> sqlite3.Connection:
    room_id = room_id_var.get()
    
    conns: Optional[Dict[str, sqlite3.Connection]] = getattr(_TLS, "conns", None)
    if conns is None:
        conns = {}
        _TLS.conns = conns

    conn = conns.get(room_id)
    if conn is None:
        path = _get_db_path(room_id)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
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
