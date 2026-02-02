from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.hosting import load_hosting_context, save_hosting_context
from ifrontier.services.user_capabilities import UserCapabilityFacade


class AiHostingActionTakenPayload(BaseModel):
    as_user_id: str
    action_id: str
    action_type: str
    decision: Dict[str, Any] = {}
    taken_at: datetime


@dataclass
class UserHostingAgent:
    """托管用户 Agent（MVP）。

    约束：
    - Agent 只能通过 UserCapabilityFacade 访问系统能力（保证“用户能看见/能做”）。
    - 真实业务动作事件（例如 contract.created）仍由底层服务发出；
      本 Agent 额外发出 hosting 审计事件，用于区分“托管代打”。
    """

    user_id: str
    facade: UserCapabilityFacade

    def tick(self) -> List[EventEnvelopeJson]:
        ctx_rec = load_hosting_context(self.user_id)
        ctx = dict(ctx_rec.context) if ctx_rec is not None else {}

        now = datetime.now(timezone.utc)
        action_id = str(uuid4())

        # MVP：先不做激进决策，避免引入大量策略与副作用。
        # 只维护上下文与画像的入口，后续可在此扩展为交易/聊天/契约/挂单等动作。
        ctx["last_tick_at"] = now.isoformat()
        ctx["ticks"] = int(ctx.get("ticks") or 0) + 1
        save_hosting_context(user_id=self.user_id, context=ctx)

        payload = AiHostingActionTakenPayload(
            as_user_id=str(self.user_id),
            action_id=action_id,
            action_type="IDLE",
            decision={"note": "mvp"},
            taken_at=now,
        )
        env = EventEnvelope(
            event_type=EventType.AI_HOSTING_ACTION_TAKEN,
            correlation_id=uuid4(),
            actor=EventActor(agent_id=f"hosting:{self.user_id}"),
            payload=payload,
        )
        return [EventEnvelopeJson.from_envelope(env)]
