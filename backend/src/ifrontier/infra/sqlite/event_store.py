from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from ifrontier.domain.events.envelope import EventEnvelopeJson
from ifrontier.infra.sqlite.db import get_connection


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    event_type: str
    occurred_at: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    actor: Optional[Dict[str, Any]]
    payload: Dict[str, Any]


def init_event_store_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            correlation_id TEXT,
            causation_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}',
            actor_json TEXT NOT NULL DEFAULT '{}',
            actor_user_id TEXT,
            actor_agent_id TEXT,
            contract_id TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_events_correlation_id ON events(correlation_id);
        CREATE INDEX IF NOT EXISTS idx_events_contract_id_type ON events(contract_id, event_type);
        CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at);
        """
    )
    conn.commit()


class SqliteEventStore:
    def append(self, event: EventEnvelopeJson) -> None:
        actor_user_id = (event.actor or {}).get("user_id")
        actor_agent_id = (event.actor or {}).get("agent_id")

        contract_id = None
        if isinstance(event.payload, dict):
            contract_id = event.payload.get("contract_id")

        payload_json = json.dumps(event.payload, ensure_ascii=False)
        actor_json = json.dumps(event.actor or {}, ensure_ascii=False)

        conn = get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO events(
                    event_id, event_type, occurred_at, correlation_id, causation_id,
                    payload_json, actor_json, actor_user_id, actor_agent_id, contract_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    event_type = excluded.event_type,
                    occurred_at = excluded.occurred_at,
                    correlation_id = excluded.correlation_id,
                    causation_id = excluded.causation_id,
                    payload_json = excluded.payload_json,
                    actor_json = excluded.actor_json,
                    actor_user_id = excluded.actor_user_id,
                    actor_agent_id = excluded.actor_agent_id,
                    contract_id = excluded.contract_id
                """,
                (
                    str(event.event_id),
                    event.event_type,
                    event.occurred_at.isoformat(),
                    str(event.correlation_id) if event.correlation_id else None,
                    str(event.causation_id) if event.causation_id else None,
                    payload_json,
                    actor_json,
                    actor_user_id,
                    actor_agent_id,
                    str(contract_id) if contract_id else None,
                ),
            )

    def list_by_correlation_id(self, correlation_id: UUID, limit: int = 200) -> List[StoredEvent]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT event_id, event_type, occurred_at, correlation_id, causation_id,
                   actor_json, payload_json
            FROM events
            WHERE correlation_id = ?
            ORDER BY occurred_at ASC
            LIMIT ?
            """,
            (str(correlation_id), int(limit)),
        ).fetchall()

        return [
            StoredEvent(
                event_id=str(r["event_id"]),
                event_type=str(r["event_type"]),
                occurred_at=str(r["occurred_at"]),
                correlation_id=r["correlation_id"],
                causation_id=r["causation_id"],
                actor=json.loads(r["actor_json"]) if r["actor_json"] else None,
                payload=json.loads(r["payload_json"]) if r["payload_json"] else {},
            )
            for r in rows
        ]

    def list_by_contract_id_and_type(
        self, *, contract_id: str, event_type: str, limit: int = 200
    ) -> List[StoredEvent]:
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT event_id, event_type, occurred_at, correlation_id, causation_id,
                   actor_json, payload_json
            FROM events
            WHERE contract_id = ? AND event_type = ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (str(contract_id), str(event_type), int(limit)),
        ).fetchall()

        return [
            StoredEvent(
                event_id=str(r["event_id"]),
                event_type=str(r["event_type"]),
                occurred_at=str(r["occurred_at"]),
                correlation_id=r["correlation_id"],
                causation_id=r["causation_id"],
                actor=json.loads(r["actor_json"]) if r["actor_json"] else None,
                payload=json.loads(r["payload_json"]) if r["payload_json"] else {},
            )
            for r in rows
        ]
