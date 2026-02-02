from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ifrontier.infra.sqlite.db import get_connection


def init_chat_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS chat_threads (
            thread_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL, -- PUBLIC / PM
            participant_a TEXT NOT NULL,
            participant_b TEXT NOT NULL,
            status TEXT NOT NULL, -- OPEN
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_chat_threads_participants
        ON chat_threads(participant_a, participant_b);

        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            message_type TEXT NOT NULL, -- TEXT / CONTRACT_DRAFT / CONTRACT_LINK / CALL_TO_CONTRACT
            content TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_time
        ON chat_messages(thread_id, created_at);

        CREATE TABLE IF NOT EXISTS chat_intro_fee_quotes (
            rich_user_id TEXT PRIMARY KEY,
            fee_cash REAL NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS wealth_public_cache (
            user_id TEXT PRIMARY KEY,
            public_total_value REAL NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class ChatThread:
    thread_id: str
    kind: str
    participant_a: str
    participant_b: str
    status: str
    created_at: str


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    thread_id: str
    sender_id: str
    message_type: str
    content: str
    payload: Dict[str, Any]
    created_at: str


def upsert_intro_fee_quote(*, rich_user_id: str, fee_cash: float) -> None:
    if fee_cash < 0:
        raise ValueError("fee_cash must be >= 0")
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO chat_intro_fee_quotes(rich_user_id, fee_cash, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(rich_user_id) DO UPDATE SET fee_cash = excluded.fee_cash, updated_at = excluded.updated_at",
            (rich_user_id, float(fee_cash), now),
        )


def get_intro_fee_quote(*, rich_user_id: str) -> Optional[float]:
    conn = get_connection()
    row = conn.execute(
        "SELECT fee_cash FROM chat_intro_fee_quotes WHERE rich_user_id = ?",
        (rich_user_id,),
    ).fetchone()
    if row is None:
        return None
    return float(row["fee_cash"])


def create_thread_if_not_exists(
    *,
    thread_id: str,
    kind: str,
    participant_a: str,
    participant_b: str,
    status: str = "OPEN",
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO chat_threads(thread_id, kind, participant_a, participant_b, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (thread_id, kind, participant_a, participant_b, status, now),
        )


def get_thread(thread_id: str) -> Optional[ChatThread]:
    conn = get_connection()
    row = conn.execute(
        "SELECT thread_id, kind, participant_a, participant_b, status, created_at FROM chat_threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    return ChatThread(
        thread_id=str(row["thread_id"]),
        kind=str(row["kind"]),
        participant_a=str(row["participant_a"]),
        participant_b=str(row["participant_b"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
    )


def list_threads_for_user(*, user_id: str, limit: int = 200) -> List[ChatThread]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT thread_id, kind, participant_a, participant_b, status, created_at "
        "FROM chat_threads "
        "WHERE participant_a = ? OR participant_b = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, user_id, int(limit)),
    ).fetchall()

    return [
        ChatThread(
            thread_id=str(r["thread_id"]),
            kind=str(r["kind"]),
            participant_a=str(r["participant_a"]),
            participant_b=str(r["participant_b"]),
            status=str(r["status"]),
            created_at=str(r["created_at"]),
        )
        for r in rows
    ]


def insert_message(
    *,
    message_id: str,
    thread_id: str,
    sender_id: str,
    message_type: str,
    content: str = "",
    payload: Dict[str, Any] | None = None,
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO chat_messages(message_id, thread_id, sender_id, message_type, content, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, thread_id, sender_id, message_type, content or "", payload_json, now),
        )


def list_messages(*, thread_id: str, limit: int = 50, before: str | None = None) -> List[ChatMessage]:
    conn = get_connection()
    if before:
        rows = conn.execute(
            "SELECT message_id, thread_id, sender_id, message_type, content, payload_json, created_at "
            "FROM chat_messages WHERE thread_id = ? AND created_at < ? "
            "ORDER BY created_at DESC LIMIT ?",
            (thread_id, before, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT message_id, thread_id, sender_id, message_type, content, payload_json, created_at "
            "FROM chat_messages WHERE thread_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (thread_id, int(limit)),
        ).fetchall()

    out: List[ChatMessage] = []
    for r in rows:
        raw = str(r["payload_json"])
        try:
            obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            obj = {}
        if not isinstance(obj, dict):
            obj = {}
        out.append(
            ChatMessage(
                message_id=str(r["message_id"]),
                thread_id=str(r["thread_id"]),
                sender_id=str(r["sender_id"]),
                message_type=str(r["message_type"]),
                content=str(r["content"]),
                payload=obj,
                created_at=str(r["created_at"]),
            )
        )
    return out


def upsert_public_wealth(*, user_id: str, public_total_value: float) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "INSERT INTO wealth_public_cache(user_id, public_total_value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET public_total_value = excluded.public_total_value, updated_at = excluded.updated_at",
            (user_id, float(public_total_value), now),
        )


def get_public_wealth(user_id: str) -> Optional[float]:
    conn = get_connection()
    row = conn.execute(
        "SELECT public_total_value FROM wealth_public_cache WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return float(row["public_total_value"])


def replace_public_wealth_cache(*, items: List[Tuple[str, float]]) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute("DELETE FROM wealth_public_cache")
        for user_id, total_value in items:
            conn.execute(
                "INSERT INTO wealth_public_cache(user_id, public_total_value, updated_at) VALUES (?, ?, ?)",
                (str(user_id), float(total_value), now),
            )
