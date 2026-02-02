from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.llm.openrouter import OpenRouterClient, extract_first_message_text
from ifrontier.infra.sqlite.hosting import load_hosting_context, save_hosting_context
from ifrontier.services.skills import default_skills_registry
from ifrontier.services.user_capabilities import UserCapabilityFacade


class AiHostingActionTakenPayload(BaseModel):
    as_user_id: str
    action_id: str
    action_type: str
    decision: Dict[str, Any] = {}
    results: List[Dict[str, Any]] = []
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

        reg = default_skills_registry()
        llm = OpenRouterClient.from_env()

        results: List[Dict[str, Any]] = []
        action_type = "IDLE"
        decision: Dict[str, Any] = {"note": "mvp"}

        if llm is not None:
            # 用户可见观测（必须只经由 facade 获取，避免越权）
            observation: Dict[str, Any] = {"as_user_id": str(self.user_id)}
            try:
                snap = self.facade.get_account_snapshot()
                valuation = self.facade.get_account_valuation()

                # 限制持仓标的数量，避免 prompt 过长
                held_symbols = [
                    str(sym)
                    for sym, qty in (snap.positions or {}).items()
                    if sym and abs(float(qty)) > 1e-12
                ][:5]

                quotes: Dict[str, Any] = {}
                for sym in held_symbols:
                    try:
                        q = self.facade.get_market_quote(symbol=sym)
                        quotes[sym] = {
                            "symbol": q.symbol,
                            "last_price": q.last_price,
                            "prev_price": q.prev_price,
                            "change_pct": q.change_pct,
                            "ma_5": q.ma_5,
                            "ma_20": q.ma_20,
                            "vol_20": q.vol_20,
                        }
                    except Exception:
                        continue

                recent_msgs = []
                try:
                    for m in self.facade.get_recent_public_messages(limit=5):
                        payload = m.payload or {}
                        recent_msgs.append(
                            {
                                "thread_id": m.thread_id,
                                "message_type": m.message_type,
                                "content": m.content,
                                "sender_display": str(payload.get("sender_display") or ""),
                                "created_at": m.created_at,
                            }
                        )
                except Exception:
                    recent_msgs = []

                observation.update(
                    {
                        "account_snapshot": {
                            "cash": float(snap.cash),
                            "positions": dict(snap.positions or {}),
                        },
                        "account_valuation": {
                            "cash": float(valuation.cash),
                            "equity_value": float(valuation.equity_value),
                            "total_value": float(valuation.total_value),
                            "prices": dict(valuation.prices or {}),
                        },
                        "held_symbols": held_symbols,
                        "market_quotes": quotes,
                        "recent_public_messages": recent_msgs,
                    }
                )
            except Exception:
                # 观测失败不应阻断托管 tick
                pass

            # 只给出“用户视角可见”的上下文（避免越权）：
            # - hosting context（本模块维护）
            # - skills 清单（白名单）
            skills = [
                {
                    "name": s.name,
                    "description": s.description,
                    "input_schema": s.input_schema,
                }
                for s in reg.list_specs()
            ]

            system = (
                "You are a rational and aggressive user-hosting agent. "
                "You MUST ONLY output JSON. No extra text. "
                "You can only act via the provided skills. "
                "Return tool calls as: {\"tool_calls\":[{\"name\":...,\"arguments\":{...}}, ...]}."
            )

            user = (
                "Decide next actions for the user to maximize winning. "
                "User-visible observation_json: "
                f"{__import__('json').dumps(observation or {}, ensure_ascii=False)}\n"
                "Current hosting_context_json: "
                f"{__import__('json').dumps(ctx or {}, ensure_ascii=False)}\n"
                "Available skills json: "
                f"{__import__('json').dumps(skills, ensure_ascii=False)}\n"
                "Output ONLY JSON tool_calls. If no action, output {\"tool_calls\":[]}."
            )

            resp = llm.chat_completions(system=system, user=user, temperature=0.2, max_tokens=800)
            text = extract_first_message_text(resp)
            calls = reg.parse_tool_calls(raw_json_text=text)
            if calls:
                action_type = "SKILLS"
                decision = {"tool_calls": [{"name": c.name, "arguments": c.arguments} for c in calls]}
            for c in calls[:3]:
                # 单 tick 限制最多执行 3 个动作，避免过度激进
                results.append(reg.execute_one(facade=self.facade, call=c))

        ctx["last_tick_at"] = now.isoformat()
        ctx["ticks"] = int(ctx.get("ticks") or 0) + 1
        if results:
            ctx["last_results"] = results
        save_hosting_context(user_id=self.user_id, context=ctx)

        payload = AiHostingActionTakenPayload(
            as_user_id=str(self.user_id),
            action_id=action_id,
            action_type=action_type,
            decision=decision,
            results=results,
            taken_at=now,
        )
        env = EventEnvelope(
            event_type=EventType.AI_HOSTING_ACTION_TAKEN,
            correlation_id=uuid4(),
            actor=EventActor(agent_id=f"hosting:{self.user_id}"),
            payload=payload,
        )
        return [EventEnvelopeJson.from_envelope(env)]
