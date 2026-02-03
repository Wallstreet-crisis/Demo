from __future__ import annotations

import os
from datetime import datetime, timezone
import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.domain.events.envelope import EventEnvelopeJson

from ifrontier.app.main import app

client = TestClient(app)


def test_news_broadcast_triggers_commonbot_emergency(monkeypatch) -> None:
    from ifrontier.app import api as api_module

    called = {"count": 0}

    def _fake_maybe_react(*, broadcast_event, force: bool = False):
        called["count"] += 1
        return []

    monkeypatch.setattr(api_module._commonbot_emergency_runner, "maybe_react", _fake_maybe_react)

    u1 = f"user:cb_emerg:u1:{uuid4()}"
    u2 = f"user:cb_emerg:u2:{uuid4()}"

    resp = client.post(
        "/social/follow",
        json={"follower_id": u2, "followee_id": u1},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/news/cards",
        json={
            "actor_id": "system",
            "kind": "MAJOR_EVENT",
            "truth_payload": {"note": "global"},
            "symbols": ["BLUEGOLD"],
        },
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    resp = client.post(
        "/news/variants/emit",
        json={
            "card_id": card_id,
            "author_id": "system",
            "text": "BREAKING NEWS",
        },
    )
    assert resp.status_code == 200
    variant_id = resp.json()["variant_id"]

    resp = client.post(
        "/news/broadcast",
        json={
            "variant_id": variant_id,
            "actor_id": "system",
            "channel": "GLOBAL_MANDATORY",
            "visibility_level": "NORMAL",
            "limit_users": 5000,
        },
    )
    assert resp.status_code == 200
    assert called["count"] == 1


def test_emergency_does_not_submit_trade_intent_when_market_closed(monkeypatch) -> None:
    monkeypatch.setenv("IF_GAME_TIME_ENABLED", "true")
    monkeypatch.setenv("IF_GAME_EPOCH_UTC", "2026-01-01T00:00:00+00:00")
    monkeypatch.setenv("IF_SECONDS_PER_GAME_DAY", "10")
    monkeypatch.setenv("IF_TRADING_RATIO", "0.5")
    monkeypatch.setenv("IF_CLOSING_BUFFER_RATIO", "0.5")
    monkeypatch.setenv("IF_HOLIDAY_EVERY_DAYS", "0")
    monkeypatch.setenv("IF_HOLIDAY_LENGTH_DAYS", "0")
    monkeypatch.setenv("IF_GAME_NOW_UTC", "2026-01-01T00:00:08+00:00")

    from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
    from ifrontier.domain.events.types import EventType

    from ifrontier.infra.sqlite.ledger import create_account

    create_account("bot:ret:1", owner_type="bot", initial_cash=100000.0)
    create_account("bot:inst:1", owner_type="bot", initial_cash=1000000.0)

    news = MagicMock()
    news.get_variant_context.return_value = {"text": "x", "symbols": ["BLUEGOLD"]}

    store = MagicMock()
    store.append = MagicMock()

    runner = CommonBotEmergencyRunner(news=news, event_store=store)

    ev = EventEnvelopeJson(
        event_id=uuid4(),
        event_type=str(EventType.NEWS_BROADCASTED),
        occurred_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
        causation_id=None,
        actor={"agent_id": "test"},
        payload={"channel": "GLOBAL_MANDATORY", "variant_id": "v1"},
    )

    emitted = runner.maybe_react(broadcast_event=ev)
    types = [getattr(getattr(x, "event_type", ""), "value", getattr(x, "event_type", "")) for x in emitted]
    decision_values = {str(EventType.AI_COMMONBOT_DECISION.value), str(EventType.AI_COMMONBOT_DECISION)}
    trade_values = {str(EventType.TRADE_INTENT_SUBMITTED.value), str(EventType.TRADE_INTENT_SUBMITTED)}
    assert any(str(t) in decision_values for t in types)
    assert not any(str(t) in trade_values for t in types)


def test_market_open_triggers_followup_decision_after_closed_emergency(monkeypatch) -> None:
    monkeypatch.setenv("IF_GAME_TIME_ENABLED", "true")
    monkeypatch.setenv("IF_GAME_EPOCH_UTC", "2026-01-01T00:00:00+00:00")
    monkeypatch.setenv("IF_SECONDS_PER_GAME_DAY", "10")
    monkeypatch.setenv("IF_TRADING_RATIO", "0.5")
    monkeypatch.setenv("IF_CLOSING_BUFFER_RATIO", "0.5")
    monkeypatch.setenv("IF_HOLIDAY_EVERY_DAYS", "0")
    monkeypatch.setenv("IF_HOLIDAY_LENGTH_DAYS", "0")

    from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
    from ifrontier.domain.events.types import EventType
    from ifrontier.infra.sqlite.ledger import create_account

    create_account("bot:ret:1", owner_type="bot", initial_cash=100000.0)
    create_account("bot:inst:1", owner_type="bot", initial_cash=1000000.0)

    news = MagicMock()
    news.get_variant_context.return_value = {"text": "x", "symbols": ["BLUEGOLD"]}
    store = MagicMock()
    store.append = MagicMock()

    runner = CommonBotEmergencyRunner(news=news, event_store=store)

    # 先在休市阶段触发一次 emergency（只产生 decision，不产生 intent，并写入 pending）
    monkeypatch.setenv("IF_GAME_NOW_UTC", "2026-01-01T00:00:08+00:00")
    ev = EventEnvelopeJson(
        event_id=uuid4(),
        event_type=str(EventType.NEWS_BROADCASTED),
        occurred_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
        causation_id=None,
        actor={"agent_id": "test"},
        payload={"channel": "GLOBAL_MANDATORY", "variant_id": "v1"},
    )
    _ = runner.maybe_react(broadcast_event=ev)

    # 切换到开市阶段，触发补决策
    monkeypatch.setenv("IF_GAME_NOW_UTC", "2026-01-01T00:00:01+00:00")
    emitted = runner.maybe_react_on_market_open()
    types = [getattr(getattr(x, "event_type", ""), "value", getattr(x, "event_type", "")) for x in emitted]
    decision_values = {str(EventType.AI_COMMONBOT_DECISION.value), str(EventType.AI_COMMONBOT_DECISION)}
    assert any(str(t) in decision_values for t in types)
