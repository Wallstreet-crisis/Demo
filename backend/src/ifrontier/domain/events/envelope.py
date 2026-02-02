from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Generic, Optional, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ifrontier.domain.events.types import EventType

PayloadT = TypeVar("PayloadT", bound=BaseModel)


class EventActor(BaseModel):
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    caste: Optional[str] = None


class EventEnvelope(BaseModel, Generic[PayloadT]):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None

    actor: Optional[EventActor] = None
    payload: PayloadT


class EventEnvelopeJson(BaseModel):
    event_id: UUID
    event_type: str
    occurred_at: datetime
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None
    actor: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any]

    @staticmethod
    def from_envelope(envelope: EventEnvelope[BaseModel]) -> "EventEnvelopeJson":
        return EventEnvelopeJson(
            event_id=envelope.event_id,
            event_type=str(envelope.event_type),
            occurred_at=envelope.occurred_at,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            actor=envelope.actor.model_dump(mode="json") if envelope.actor else None,
            payload=envelope.payload.model_dump(mode="json"),
        )
