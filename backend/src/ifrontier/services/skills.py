from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel

from ifrontier.services.user_capabilities import UserCapabilityFacade


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Dict[str, Any]


class SkillsRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, Tuple[SkillSpec, Callable[[UserCapabilityFacade, Dict[str, Any]], Any]]] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[[UserCapabilityFacade, Dict[str, Any]], Any],
    ) -> None:
        self._handlers[name] = (SkillSpec(name=name, description=description, input_schema=input_schema), handler)

    def list_specs(self) -> List[SkillSpec]:
        return [spec for spec, _h in self._handlers.values()]

    def parse_tool_calls(self, *, raw_json_text: str) -> List[ToolCall]:
        """Parse model output.

        Expected JSON formats:
        - {"tool_calls":[{"name":"...","arguments":{...}}, ...]}
        - {"name":"...","arguments":{...}}  (single)
        """
        try:
            obj = json.loads(raw_json_text)
        except Exception:
            return []

        if isinstance(obj, dict) and "tool_calls" in obj:
            calls = obj.get("tool_calls")
            if not isinstance(calls, list):
                return []
            out: List[ToolCall] = []
            for c in calls:
                if not isinstance(c, dict):
                    continue
                name = str(c.get("name") or "").strip()
                args = c.get("arguments")
                if not name or not isinstance(args, dict):
                    continue
                out.append(ToolCall(name=name, arguments=dict(args)))
            return out

        if isinstance(obj, dict) and obj.get("name") and isinstance(obj.get("arguments"), dict):
            return [ToolCall(name=str(obj["name"]), arguments=dict(obj["arguments"]))]

        return []

    def execute_one(self, *, facade: UserCapabilityFacade, call: ToolCall) -> Dict[str, Any]:
        if call.name not in self._handlers:
            return {"ok": False, "error": f"unknown skill: {call.name}"}

        spec, handler = self._handlers[call.name]
        try:
            result = handler(facade, call.arguments)
        except Exception as exc:
            return {"ok": False, "error": str(exc), "skill": spec.name}

        return {"ok": True, "skill": spec.name, "result": _to_jsonable(result)}


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(x) for x in list(obj)]
    if isinstance(obj, BaseModel):
        return _to_jsonable(obj.model_dump(mode="json"))
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return _to_jsonable(obj.model_dump(mode="json"))
        except TypeError:
            return _to_jsonable(obj.model_dump())
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if hasattr(obj, "__dict__"):
        return _to_jsonable(dict(obj.__dict__))
    return str(obj)


def default_skills_registry() -> SkillsRegistry:
    reg = SkillsRegistry()

    reg.register(
        name="chat.send_public_message",
        description="Send a public chat message as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "message_type": {"type": "string"},
                "content": {"type": "string"},
                "payload": {"type": "object"},
                "anonymous": {"type": "boolean"},
                "alias": {"type": ["string", "null"]},
            },
            "required": ["message_type", "content"],
        },
        handler=lambda f, a: f.send_public_message(
            message_type=str(a.get("message_type") or "TEXT"),
            content=str(a.get("content") or ""),
            payload=a.get("payload") if isinstance(a.get("payload"), dict) else {},
            anonymous=bool(a.get("anonymous") or False),
            alias=(str(a.get("alias")) if a.get("alias") is not None else None),
        ),
    )

    reg.register(
        name="chat.send_pm_message",
        description="Send a private message in an existing PM thread as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string"},
                "message_type": {"type": "string"},
                "content": {"type": "string"},
                "payload": {"type": "object"},
                "anonymous": {"type": "boolean"},
                "alias": {"type": ["string", "null"]},
            },
            "required": ["thread_id", "message_type", "content"],
        },
        handler=lambda f, a: f.send_pm_message(
            thread_id=str(a.get("thread_id") or ""),
            message_type=str(a.get("message_type") or "TEXT"),
            content=str(a.get("content") or ""),
            payload=a.get("payload") if isinstance(a.get("payload"), dict) else {},
            anonymous=bool(a.get("anonymous") or False),
            alias=(str(a.get("alias")) if a.get("alias") is not None else None),
        ),
    )

    reg.register(
        name="chat.open_pm",
        description="Open a new private message thread with another user.",
        input_schema={
            "type": "object",
            "properties": {
                "target_id": {"type": "string"},
            },
            "required": ["target_id"],
        },
        handler=lambda f, a: f.chat_service.open_pm(
            requester_id=f.user_id,
            target_id=str(a.get("target_id") or ""),
        ),
    )

    reg.register(
        name="contract_agent.draft",
        description="Draft a contract from natural language as the user.",
        input_schema={
            "type": "object",
            "properties": {"natural_language": {"type": "string"}},
            "required": ["natural_language"],
        },
        handler=lambda f, a: f.draft_contract(natural_language=str(a.get("natural_language") or "")),
    )

    reg.register(
        name="contracts.create",
        description="Create a contract as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "title": {"type": "string"},
                "terms": {"type": "object"},
                "parties": {"type": "array"},
                "required_signers": {"type": "array"},
                "participation_mode": {"type": ["string", "null"]},
                "invited_parties": {"type": ["array", "null"]},
                "trigger_policy": {"type": ["object", "string", "null"]},
            },
            "required": ["kind", "title", "terms", "parties", "required_signers"],
        },
        handler=lambda f, a: f.create_contract(
            kind=str(a.get("kind") or ""),
            title=str(a.get("title") or ""),
            terms=a.get("terms") if isinstance(a.get("terms"), dict) else {},
            parties=[str(x) for x in (a.get("parties") or []) if x],
            required_signers=[str(x) for x in (a.get("required_signers") or []) if x],
            participation_mode=(str(a.get("participation_mode")) if a.get("participation_mode") is not None else None),
            invited_parties=[str(x) for x in (a.get("invited_parties") or []) if x]
            if isinstance(a.get("invited_parties"), list)
            else None,
            trigger_policy=a.get("trigger_policy") if isinstance(a.get("trigger_policy"), (dict, str)) else None,
        ),
    )

    reg.register(
        name="contracts.sign",
        description="Sign a contract as the user.",
        input_schema={
            "type": "object",
            "properties": {"contract_id": {"type": "string"}},
            "required": ["contract_id"],
        },
        handler=lambda f, a: f.sign_contract(contract_id=str(a.get("contract_id") or "")),
    )

    reg.register(
        name="contracts.activate",
        description="Activate a contract as the user.",
        input_schema={
            "type": "object",
            "properties": {"contract_id": {"type": "string"}},
            "required": ["contract_id"],
        },
        handler=lambda f, a: f.activate_contract(contract_id=str(a.get("contract_id") or "")),
    )

    reg.register(
        name="contracts.join",
        description="Join a contract as the user.",
        input_schema={
            "type": "object",
            "properties": {"contract_id": {"type": "string"}},
            "required": ["contract_id"],
        },
        handler=lambda f, a: f.join_contract(contract_id=str(a.get("contract_id") or "")),
    )

    reg.register(
        name="contracts.create_proposal",
        description="Create a proposal on a contract as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "contract_id": {"type": "string"},
                "proposal_type": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["contract_id", "proposal_type"],
        },
        handler=lambda f, a: f.create_proposal(
            contract_id=str(a.get("contract_id") or ""),
            proposal_type=str(a.get("proposal_type") or ""),
            details=a.get("details") if isinstance(a.get("details"), dict) else {},
        ),
    )

    reg.register(
        name="contracts.approve_proposal",
        description="Approve a proposal on a contract as the user.",
        input_schema={
            "type": "object",
            "properties": {"contract_id": {"type": "string"}, "proposal_id": {"type": "string"}},
            "required": ["contract_id", "proposal_id"],
        },
        handler=lambda f, a: f.approve_proposal(
            contract_id=str(a.get("contract_id") or ""),
            proposal_id=str(a.get("proposal_id") or ""),
        ),
    )

    reg.register(
        name="trading.submit_limit_order",
        description="Submit a limit order as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "price": {"type": "number"},
                "quantity": {"type": "number"},
            },
            "required": ["symbol", "side", "price", "quantity"],
        },
        handler=lambda f, a: f.submit_limit_order(
            symbol=str(a.get("symbol") or ""),
            side=str(a.get("side") or ""),
            price=float(a.get("price") or 0.0),
            quantity=float(a.get("quantity") or 0.0),
        ),
    )

    reg.register(
        name="trading.submit_market_order",
        description="Submit a market order as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string"},
                "quantity": {"type": "number"},
            },
            "required": ["symbol", "side", "quantity"],
        },
        handler=lambda f, a: f.submit_market_order(
            symbol=str(a.get("symbol") or ""),
            side=str(a.get("side") or ""),
            quantity=float(a.get("quantity") or 0.0),
        ),
    )

    reg.register(
        name="trading.cancel_order",
        description="Cancel an open limit order by order_id as the user.",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        handler=lambda f, a: f.cancel_limit_order(order_id=str(a.get("order_id") or "")),
    )

    reg.register(
        name="trading.list_my_open_orders",
        description="List open orders for the user, optionally filtered by symbol.",
        input_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": ["string", "null"]},
                "limit": {"type": "number"},
            },
        },
        handler=lambda f, a: f.list_my_open_orders(
            symbol=a.get("symbol"),
            limit=int(a.get("limit") or 50),
        ),
    )

    reg.register(
        name="news.list_inbox",
        description="List news in the user's inbox.",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "number"}},
        },
        handler=lambda f, a: f.get_news_inbox(limit=int(a.get("limit") or 20)),
    )

    reg.register(
        name="news.list_public_feed",
        description="List public news feed.",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "number"}},
        },
        handler=lambda f, a: f.get_news_public_feed(limit=int(a.get("limit") or 20)),
    )

    reg.register(
        name="news.create_card",
        description="Create a new news card as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "text": {"type": "string"},
                "symbols": {"type": "array", "items": {"type": "string"}},
                "truth_payload": {"type": "object"},
            },
            "required": ["kind"],
        },
        handler=lambda f, a: f.create_news_card(
            kind=str(a.get("kind") or ""),
            text=str(a.get("text") or ""),
            symbols=a.get("symbols"),
            truth_payload=a.get("truth_payload"),
        ),
    )

    reg.register(
        name="news.emit_variant",
        description="Emit a variant of a news card as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "card_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["card_id", "text"],
        },
        handler=lambda f, a: f.emit_news_variant(
            card_id=str(a.get("card_id") or ""),
            text=str(a.get("text") or ""),
        ),
    )

    reg.register(
        name="news.propagate",
        description="Propagate a news variant to other users as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "variant_id": {"type": "string"},
                "limit": {"type": "number"},
            },
            "required": ["variant_id"],
        },
        handler=lambda f, a: f.propagate_news(
            variant_id=str(a.get("variant_id") or ""),
            limit=int(a.get("limit") or 10),
        ),
    )

    reg.register(
        name="news.broadcast",
        description="Broadcast a news variant to all users or a channel as the user.",
        input_schema={
            "type": "object",
            "properties": {
                "variant_id": {"type": "string"},
                "channel": {"type": "string"},
            },
            "required": ["variant_id"],
        },
        handler=lambda f, a: f.broadcast_news(
            variant_id=str(a.get("variant_id") or ""),
            channel=str(a.get("channel") or "GLOBAL"),
        ),
    )

    return reg
