from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ifrontier.infra.sqlite.db import get_connection


def init_contract_agent_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS contract_agent_context (
            actor_id TEXT PRIMARY KEY,
            context_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class ContractAgentContext:
    actor_id: str
    context: Dict[str, Any]
    updated_at: str


def load_contract_agent_context(actor_id: str) -> Optional[ContractAgentContext]:
    conn = get_connection()
    row = conn.execute(
        "SELECT actor_id, context_json, updated_at FROM contract_agent_context WHERE actor_id = ?",
        (actor_id,),
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
    return ContractAgentContext(actor_id=str(row["actor_id"]), context=ctx, updated_at=str(row["updated_at"]))


def save_contract_agent_context(*, actor_id: str, context: Dict[str, Any]) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(context or {}, ensure_ascii=False)
    with conn:
        conn.execute(
            "INSERT INTO contract_agent_context(actor_id, context_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(actor_id) DO UPDATE SET context_json = excluded.context_json, updated_at = excluded.updated_at",
            (actor_id, payload, now),
        )


def clear_contract_agent_context(actor_id: str) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM contract_agent_context WHERE actor_id = ?", (actor_id,))
