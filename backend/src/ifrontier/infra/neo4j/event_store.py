from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from neo4j import Driver

from ifrontier.domain.events.envelope import EventEnvelopeJson


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    event_type: str
    occurred_at: str
    correlation_id: Optional[str]
    causation_id: Optional[str]
    actor: Optional[Dict[str, Any]]
    payload: Dict[str, Any]


class Neo4jEventStore:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def append(self, event: EventEnvelopeJson) -> None:
        actor_user_id = (event.actor or {}).get("user_id")
        actor_agent_id = (event.actor or {}).get("agent_id")

        contract_id = None
        if isinstance(event.payload, dict):
            contract_id = event.payload.get("contract_id")

        payload_json = json.dumps(event.payload, ensure_ascii=False)
        actor_json = json.dumps(event.actor or {}, ensure_ascii=False)

        with self._driver.session() as session:
            session.execute_write(
                self._append_tx,
                {
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "occurred_at": event.occurred_at.isoformat(),
                    "correlation_id": str(event.correlation_id) if event.correlation_id else None,
                    "causation_id": str(event.causation_id) if event.causation_id else None,
                    "payload_json": payload_json,
                    "actor_json": actor_json,
                    "actor_user_id": actor_user_id,
                    "actor_agent_id": actor_agent_id,
                    "contract_id": str(contract_id) if contract_id else None,
                },
            )

    @staticmethod
    def _append_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (e:Event {event_id: $event_id})
            SET e.event_type = $event_type,
                e.occurred_at = $occurred_at,
                e.correlation_id = $correlation_id,
                e.causation_id = $causation_id,
                e.payload_json = $payload_json,
                e.actor_json = $actor_json

            WITH e
            FOREACH (_ IN CASE WHEN $contract_id IS NULL THEN [] ELSE [1] END |
              SET e.contract_id = $contract_id
            )

            WITH e
            FOREACH (_ IN CASE WHEN $actor_user_id IS NULL THEN [] ELSE [1] END |
              MERGE (u:User {user_id: $actor_user_id})
              MERGE (u)-[:EMITTED_EVENT]->(e)
            )

            WITH e
            FOREACH (_ IN CASE WHEN $actor_agent_id IS NULL THEN [] ELSE [1] END |
              MERGE (a:AiAgent {agent_id: $actor_agent_id})
              MERGE (a)-[:EMITTED_EVENT]->(e)
            )
            """,
            **params,
        )

    def list_by_correlation_id(self, correlation_id: UUID, limit: int = 200) -> List[StoredEvent]:
        with self._driver.session() as session:
            records = session.execute_read(
                self._list_by_correlation_id_tx,
                {"correlation_id": str(correlation_id), "limit": limit},
            )

        return [
            StoredEvent(
                event_id=r["event_id"],
                event_type=r["event_type"],
                occurred_at=r["occurred_at"],
                correlation_id=r.get("correlation_id"),
                causation_id=r.get("causation_id"),
                actor=json.loads(r.get("actor_json") or "{}") or None,
                payload=json.loads(r.get("payload_json") or "{}"),
            )
            for r in records
        ]

    @staticmethod
    def _list_by_correlation_id_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (e:Event {correlation_id: $correlation_id})
            RETURN e.event_id AS event_id,
                   e.event_type AS event_type,
                   e.occurred_at AS occurred_at,
                   e.correlation_id AS correlation_id,
                   e.causation_id AS causation_id,
                   e.actor_json AS actor_json,
                   e.payload_json AS payload_json
            ORDER BY e.occurred_at ASC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    def list_by_contract_id_and_type(self, *, contract_id: str, event_type: str, limit: int = 200) -> List[StoredEvent]:
        with self._driver.session() as session:
            records = session.execute_read(
                self._list_by_contract_id_and_type_tx,
                {"contract_id": str(contract_id), "event_type": str(event_type), "limit": int(limit)},
            )

        return [
            StoredEvent(
                event_id=r["event_id"],
                event_type=r["event_type"],
                occurred_at=r["occurred_at"],
                correlation_id=r.get("correlation_id"),
                causation_id=r.get("causation_id"),
                actor=json.loads(r.get("actor_json") or "{}") or None,
                payload=json.loads(r.get("payload_json") or "{}"),
            )
            for r in records
        ]

    @staticmethod
    def _list_by_contract_id_and_type_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (e:Event {contract_id: $contract_id, event_type: $event_type})
            RETURN e.event_id AS event_id,
                   e.event_type AS event_type,
                   e.occurred_at AS occurred_at,
                   e.correlation_id AS correlation_id,
                   e.causation_id AS causation_id,
                   e.actor_json AS actor_json,
                   e.payload_json AS payload_json
            ORDER BY e.occurred_at DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]
