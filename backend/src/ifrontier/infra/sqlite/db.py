from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

_DB_PATH: Optional[Path] = None
_CONNECTION: Optional[sqlite3.Connection] = None


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        base = Path(__file__).resolve().parents[3]
        data_dir = base / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        _DB_PATH = data_dir / "ledger.db"
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    global _CONNECTION
    if _CONNECTION is None:
        path = _get_db_path()
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        _CONNECTION = conn
    return _CONNECTION
