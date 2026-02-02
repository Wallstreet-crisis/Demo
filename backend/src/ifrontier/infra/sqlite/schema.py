from __future__ import annotations

from ifrontier.infra.sqlite.db import get_connection


def init_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            owner_type TEXT NOT NULL,
            cash REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS positions (
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (account_id, symbol),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ledger_entries (
            entry_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            delta REAL NOT NULL,
            event_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        );
        """
    )

    conn.commit()
