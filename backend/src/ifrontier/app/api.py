from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter
from pydantic import BaseModel, RootModel

from ifrontier.app.ws import hub
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.driver import create_driver
from ifrontier.infra.neo4j.event_store import Neo4jEventStore

router = APIRouter()

_driver = create_driver()
_event_store = Neo4jEventStore(_driver)


@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


class DebugEmitEventRequest(BaseModel):
    event_type: EventType
    payload: Dict[str, Any]
    actor_user_id: Optional[str] = None
    actor_agent_id: Optional[str] = None
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None


class DebugEmitEventResponse(BaseModel):
    event_id: UUID
    correlation_id: Optional[UUID]


@router.post("/debug/emit_event")
async def debug_emit_event(req: DebugEmitEventRequest) -> DebugEmitEventResponse:
    envelope = EventEnvelope(
        event_type=req.event_type,
        occurred_at=datetime.now(timezone.utc),
        correlation_id=req.correlation_id or uuid4(),
        causation_id=req.causation_id,
        actor=EventActor(user_id=req.actor_user_id, agent_id=req.actor_agent_id),
        payload=_AnyPayload(req.payload),
    )

    event_json = EventEnvelopeJson.from_envelope(envelope)
    _event_store.append(event_json)

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(req.event_type), event_json.model_dump())

    return DebugEmitEventResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


class _AnyPayload(RootModel[Dict[str, Any]]):
    pass
