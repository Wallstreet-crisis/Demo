from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from pydantic import RootModel

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.event_store import SqliteEventStore
from ifrontier.infra.sqlite.chat import (
    ChatMessage,
    ChatThread,
    create_thread_if_not_exists,
    get_intro_fee_quote,
    get_public_wealth,
    get_thread,
    insert_message,
    list_messages,
    list_threads_for_user,
    replace_public_wealth_cache,
    upsert_intro_fee_quote,
)
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import ContractTransfer, apply_contract_transfers, create_account
from ifrontier.services.valuation import value_account


DEFAULT_INTRO_FEE_CASH = 1000.0
WEALTH_RATIO_THRESHOLD = 5.0
PUBLIC_WEALTH_MIN_THRESHOLD = 1_000_000.0


@dataclass(frozen=True)
class OpenPmResult:
    thread_id: str
    rich_user_id: str
    poor_user_id: str
    paid_intro_fee: bool
    intro_fee_cash: float


_caste_cache: Dict[str, Tuple[str, float]] = {}  # account_id -> (caste, timestamp)
_CASTE_CACHE_TTL = 60.0  # 缓存 60 秒


def _lookup_caste(sender_id: str) -> str:
    """查询发送者阶级，带内存缓存避免高频 DB 查询。"""
    import time
    now = time.monotonic()
    cached = _caste_cache.get(sender_id)
    if cached and (now - cached[1]) < _CASTE_CACHE_TTL:
        return cached[0]
    conn = get_connection()
    row = conn.execute("SELECT owner_type FROM accounts WHERE account_id = ?", (sender_id,)).fetchone()
    caste = str(row["owner_type"]).upper() if row else "UNKNOWN"
    _caste_cache[sender_id] = (caste, now)
    return caste


class ChatService:
    def __init__(self, *, event_store: SqliteEventStore) -> None:
        self._event_store = event_store

    @staticmethod
    def _pm_thread_id(user_a: str, user_b: str) -> str:
        a, b = sorted([str(user_a), str(user_b)])
        return f"pm:{a}|{b}"

    @staticmethod
    def _public_thread_id() -> str:
        return "public:global"

    def set_intro_fee_quote(self, *, rich_user_id: str, fee_cash: float, actor_id: str) -> EventEnvelopeJson:
        upsert_intro_fee_quote(rich_user_id=rich_user_id, fee_cash=fee_cash)
        payload = {
            "rich_user_id": rich_user_id,
            "fee_cash": float(fee_cash),
            "quoted_at": datetime.now(timezone.utc),
        }
        env = EventEnvelope[_AnyPayload](
            event_type=EventType.CHAT_INTRO_FEE_QUOTED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=_AnyPayload(payload),
        )
        event_json = EventEnvelopeJson.from_envelope(env)
        self._event_store.append(event_json)
        return event_json

    def open_pm(self, *, requester_id: str, target_id: str) -> Tuple[OpenPmResult, List[EventEnvelopeJson]]:
        if not requester_id or not target_id:
            raise ValueError("requester_id and target_id are required")
        if requester_id == target_id:
            raise ValueError("cannot open pm with self")

        thread_id = self._pm_thread_id(requester_id, target_id)
        existing = get_thread(thread_id)
        if existing is not None:
            return (
                OpenPmResult(
                    thread_id=thread_id,
                    rich_user_id="",
                    poor_user_id="",
                    paid_intro_fee=False,
                    intro_fee_cash=0.0,
                ),
                [],
            )

        v_req = value_account(account_id=requester_id)
        v_tar = value_account(account_id=target_id)
        total_req = float(v_req.total_value)
        total_tar = float(v_tar.total_value)

        hi_total, hi_user = (total_req, requester_id) if total_req >= total_tar else (total_tar, target_id)
        lo_total, lo_user = (total_tar, target_id) if total_req >= total_tar else (total_req, requester_id)

        lo_eff = max(lo_total, 1.0)
        ratio = hi_total / lo_eff

        needs_barrier = ratio >= WEALTH_RATIO_THRESHOLD
        paid = False
        fee_cash = 0.0
        events: List[EventEnvelopeJson] = []

        if needs_barrier and requester_id == lo_user:
            fee_cash = float(get_intro_fee_quote(rich_user_id=hi_user) or DEFAULT_INTRO_FEE_CASH)
            if fee_cash > 0:
                create_account(requester_id, owner_type="user")
                create_account(hi_user, owner_type="user")
                try:
                    apply_contract_transfers(
                        transfers=[
                            ContractTransfer(
                                from_account_id=requester_id,
                                to_account_id=hi_user,
                                asset_type="CASH",
                                symbol="CASH",
                                quantity=float(fee_cash),
                            )
                        ],
                        event_id=str(uuid4()),
                    )
                except ValueError:
                    raise ValueError(
                        f"你当前资产差距过大，需要向 {hi_user} 支付引荐费 {fee_cash} CASH 才能建立私聊；但你的现金不足。"
                    )

                paid = True
                payload_paid = {
                    "thread_id": thread_id,
                    "rich_user_id": hi_user,
                    "poor_user_id": lo_user,
                    "fee_cash": float(fee_cash),
                    "paid_at": datetime.now(timezone.utc),
                }
                env_paid = EventEnvelope[_AnyPayload](
                    event_type=EventType.CHAT_INTRO_FEE_PAID,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id=requester_id),
                    payload=_AnyPayload(payload_paid),
                )
                event_paid = EventEnvelopeJson.from_envelope(env_paid)
                self._event_store.append(event_paid)
                events.append(event_paid)

        create_thread_if_not_exists(
            thread_id=thread_id,
            kind="PM",
            participant_a=min(requester_id, target_id),
            participant_b=max(requester_id, target_id),
            status="OPEN",
        )

        payload_opened = {
            "thread_id": thread_id,
            "participant_a": min(requester_id, target_id),
            "participant_b": max(requester_id, target_id),
            "opened_at": datetime.now(timezone.utc),
        }
        env_opened = EventEnvelope[_AnyPayload](
            event_type=EventType.CHAT_THREAD_OPENED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=requester_id),
            payload=_AnyPayload(payload_opened),
        )
        event_opened = EventEnvelopeJson.from_envelope(env_opened)
        self._event_store.append(event_opened)
        events.append(event_opened)

        return (
            OpenPmResult(
                thread_id=thread_id,
                rich_user_id=hi_user,
                poor_user_id=lo_user,
                paid_intro_fee=paid,
                intro_fee_cash=float(fee_cash),
            ),
            events,
        )

    def send_public_message(
        self,
        *,
        sender_id: str,
        message_type: str,
        content: str = "",
        payload: Optional[Dict[str, Any]] = None,
        anonymous: bool = False,
        alias: str | None = None,
    ) -> EventEnvelopeJson:
        thread_id = self._public_thread_id()
        create_thread_if_not_exists(
            thread_id=thread_id,
            kind="PUBLIC",
            participant_a="*",
            participant_b="*",
            status="OPEN",
        )

        message_id = str(uuid4())
        sender_display = self._compute_sender_display(sender_id=sender_id, anonymous=anonymous, alias=alias)
        
        sender_caste = "UNKNOWN" if anonymous else _lookup_caste(sender_id)

        stored_payload = dict(payload or {})
        stored_payload["anonymous"] = bool(anonymous)
        stored_payload["sender_display"] = sender_display
        stored_payload["sender_caste"] = sender_caste
        
        insert_message(
            message_id=message_id,
            thread_id=thread_id,
            sender_id=sender_id,
            message_type=message_type,
            content=content,
            payload=stored_payload,
        )

        ev_payload = {
            "message_id": message_id,
            "thread_id": thread_id,
            "sender_id": None if anonymous else sender_id,
            "sender_display": sender_display,
            "sender_caste": sender_caste,
            "message_type": message_type,
            "content": content,
            "payload": stored_payload,
            "sent_at": datetime.now(timezone.utc),
        }
        env = EventEnvelope[_AnyPayload](
            event_type=EventType.CHAT_MESSAGE_SENT,
            correlation_id=uuid4(),
            actor=EventActor(user_id=sender_id),
            payload=_AnyPayload(ev_payload),
        )
        event_json = EventEnvelopeJson.from_envelope(env)
        self._event_store.append(event_json)
        return event_json

    def send_pm_message(
        self,
        *,
        thread_id: str,
        sender_id: str,
        message_type: str,
        content: str = "",
        payload: Optional[Dict[str, Any]] = None,
        anonymous: bool = False,
        alias: str | None = None,
    ) -> EventEnvelopeJson:
        th = get_thread(thread_id)
        if th is None or th.kind != "PM":
            raise ValueError("pm thread not found")

        if sender_id not in {th.participant_a, th.participant_b}:
            raise ValueError("sender is not a participant of this thread")

        message_id = str(uuid4())
        sender_display = self._compute_sender_display(sender_id=sender_id, anonymous=anonymous, alias=alias)
        
        sender_caste = "UNKNOWN" if anonymous else _lookup_caste(sender_id)

        stored_payload = dict(payload or {})
        stored_payload["anonymous"] = bool(anonymous)
        stored_payload["sender_display"] = sender_display
        stored_payload["sender_caste"] = sender_caste

        insert_message(
            message_id=message_id,
            thread_id=thread_id,
            sender_id=sender_id,
            message_type=message_type,
            content=content,
            payload=stored_payload,
        )

        ev_payload = {
            "message_id": message_id,
            "thread_id": thread_id,
            "sender_id": None if anonymous else sender_id,
            "sender_display": sender_display,
            "sender_caste": sender_caste,
            "message_type": message_type,
            "content": content,
            "payload": stored_payload,
            "sent_at": datetime.now(timezone.utc),
        }
        env = EventEnvelope[_AnyPayload](
            event_type=EventType.CHAT_MESSAGE_SENT,
            correlation_id=uuid4(),
            actor=EventActor(user_id=sender_id),
            payload=_AnyPayload(ev_payload),
        )
        event_json = EventEnvelopeJson.from_envelope(env)
        self._event_store.append(event_json)
        return event_json

    def list_public_messages(self, *, limit: int = 50, before: str | None = None) -> List[ChatMessage]:
        return list_messages(thread_id=self._public_thread_id(), limit=limit, before=before)

    def list_pm_messages(self, *, thread_id: str, limit: int = 50, before: str | None = None) -> List[ChatMessage]:
        return list_messages(thread_id=thread_id, limit=limit, before=before)

    def list_threads(self, *, user_id: str, limit: int = 200) -> List[ChatThread]:
        return list_threads_for_user(user_id=user_id, limit=limit)

    def refresh_public_wealth_top10(self) -> Tuple[int, EventEnvelopeJson]:
        conn = get_connection()
        rows = conn.execute("SELECT account_id FROM accounts").fetchall()
        user_ids = [str(r["account_id"]) for r in rows]

        valuations: List[Tuple[str, float]] = []
        for uid in user_ids:
            try:
                v = value_account(account_id=uid)
            except Exception:
                continue
            valuations.append((uid, float(v.total_value)))

        if not valuations:
            replace_public_wealth_cache(items=[])
        else:
            valuations.sort(key=lambda x: x[1], reverse=True)
            n = len(valuations)
            topn = max(1, int(ceil(n * 0.1)))
            top = [(uid, tv) for uid, tv in valuations[:topn] if tv >= PUBLIC_WEALTH_MIN_THRESHOLD]
            replace_public_wealth_cache(items=top)

        payload = {
            "refreshed_at": datetime.now(timezone.utc),
            "total_accounts": int(len(valuations)),
            "public_count": int(
                len(conn.execute("SELECT user_id FROM wealth_public_cache").fetchall())
            ),
        }
        env = EventEnvelope[_AnyPayload](
            event_type=EventType.WEALTH_PUBLIC_REFRESHED,
            correlation_id=uuid4(),
            actor=EventActor(agent_id="system"),
            payload=_AnyPayload(payload),
        )
        event_json = EventEnvelopeJson.from_envelope(env)
        self._event_store.append(event_json)
        return payload["public_count"], event_json

    def get_public_total_value(self, *, user_id: str) -> Optional[float]:
        return get_public_wealth(user_id)

    @staticmethod
    def _compute_sender_display(*, sender_id: str, anonymous: bool, alias: str | None) -> str:
        if not anonymous:
            return str(sender_id)
        if alias:
            return str(alias)
        return f"Anonymous-{str(uuid4()).replace('-', '')[:6].upper()}"

class _AnyPayload(RootModel[Dict[str, Any]]):
    pass
