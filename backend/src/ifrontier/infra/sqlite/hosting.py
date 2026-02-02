from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ifrontier.infra.sqlite.db import get_connection


def init_hosting_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_hosting_state (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'OFF',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_hosting_context (
            user_id TEXT PRIMARY KEY,
            context_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class UserHostingState:
    user_id: str
    enabled: bool
    status: str
    updated_at: str


@dataclass(frozen=True)
class UserHostingContext:
    user_id: str
    context: Dict[str, Any]
    updated_at: str


def upsert_hosting_state(*, user_id: str, enabled: bool, status: str) -> UserHostingState:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO user_hosting_state(user_id, enabled, status, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled, status=excluded.status, updated_at=excluded.updated_at",
            (str(user_id), 1 if enabled else 0, str(status), now),
        )

    return UserHostingState(user_id=str(user_id), enabled=bool(enabled), status=str(status), updated_at=now)


def get_hosting_state(user_id: str) -> Optional[UserHostingState]:
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, enabled, status, updated_at FROM user_hosting_state WHERE user_id = ?",
        (str(user_id),),
    ).fetchone()
    if row is None:
        return None
    return UserHostingState(
        user_id=str(row["user_id"]),
        enabled=bool(int(row["enabled"])) if row["enabled"] is not None else False,
        status=str(row["status"]),
        updated_at=str(row["updated_at"]),
    )


def list_enabled_hosting_users(*, limit: int = 200) -> List[UserHostingState]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT user_id, enabled, status, updated_at FROM user_hosting_state WHERE enabled = 1 ORDER BY updated_at ASC LIMIT ?",
        (int(limit),),
    ).fetchall()
    out: List[UserHostingState] = []
    for r in rows:
        out.append(
            UserHostingState(
                user_id=str(r["user_id"]),
                enabled=bool(int(r["enabled"])) if r["enabled"] is not None else False,
                status=str(r["status"]),
                updated_at=str(r["updated_at"]),
            )
        )
    return out


def load_hosting_context(user_id: str) -> Optional[UserHostingContext]:
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, context_json, updated_at FROM user_hosting_context WHERE user_id = ?",
        (str(user_id),),
    ).fetchone()
    if row is None:
        return None

    raw = str(row["context_json"])
    try:
        ctx = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        ctx = {}

    if not isinstance(ctx, dict):
        ctx = {}

    return UserHostingContext(user_id=str(row["user_id"]), context=ctx, updated_at=str(row["updated_at"]))


def save_hosting_context(*, user_id: str, context: Dict[str, Any]) -> UserHostingContext:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(context or {}, ensure_ascii=False)

    with conn:
        conn.execute(
            "INSERT INTO user_hosting_context(user_id, context_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET context_json=excluded.context_json, updated_at=excluded.updated_at",
            (str(user_id), payload, now),
        )

    return UserHostingContext(user_id=str(user_id), context=dict(context or {}), updated_at=now)
