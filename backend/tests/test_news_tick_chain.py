from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.news import claim_scenario_card, get_news, save_news
from ifrontier.services.news import NewsService
from ifrontier.services.news_tick import NewsTickEngine

client = TestClient(app)


def test_news_chain_tick_emits_omen_and_resolves_with_broadcast() -> None:
    u1 = f"user:tick:u1:{uuid4()}"
    u2 = f"user:tick:u2:{uuid4()}"

    # Ensure both users exist in graph
    resp = client.post("/social/follow", json={"follower_id": u2, "followee_id": u1})
    assert resp.status_code == 200

    start = datetime.now(timezone.utc)

    # Start a MAJOR_EVENT chain with deterministic resolve (no abort)
    resp = client.post(
        "/news/chains/start",
        json={
            "kind": "MAJOR_EVENT",
            "actor_id": u1,
            "t0_seconds": 2,
            "omen_interval_seconds": 1,
            "abort_probability": 0.0,
            "grant_count": 1,
            "seed": 123,
        },
    )
    assert resp.status_code == 200

    # Tick before T0 => emits at least one omen and grants it to someone
    resp = client.post(
        "/news/tick",
        json={"now_iso": (start + timedelta(seconds=0.5)).isoformat(), "limit": 10},
    )
    assert resp.status_code == 200

    # Tick at/after T0 => resolves and broadcasts final variant to all known users
    resp = client.post(
        "/news/tick",
        json={"now_iso": (start + timedelta(seconds=3)).isoformat(), "limit": 10},
    )
    assert resp.status_code == 200

    inbox2 = client.get(f"/news/inbox/{u2}?limit=50")
    assert inbox2.status_code == 200

    # We should have received at least one delivery (omen or broadcast)
    assert len(inbox2.json()["items"]) >= 1


def test_news_tick_engine_serializes_concurrent_ticks() -> None:
    engine = NewsTickEngine(event_store=MagicMock(), news_service=MagicMock(), broadcaster=None)

    entered = []
    gate = asyncio.Event()

    async def _fake_periodic_spawn(*, now):
        entered.append("periodic")
        await gate.wait()
        return []

    async def _fake_tick_scenario_cards(*, now, limit):
        return []

    async def _fake_list_active_chains(*, now, limit):
        return []

    engine._periodic_spawn = _fake_periodic_spawn  # type: ignore[method-assign]
    engine._tick_scenario_cards = _fake_tick_scenario_cards  # type: ignore[method-assign]
    engine._list_active_chains = _fake_list_active_chains  # type: ignore[method-assign]

    async def _run_two_ticks() -> None:
        task1 = asyncio.create_task(engine.tick(now=datetime.now(timezone.utc), limit=1))
        await asyncio.sleep(0)
        task2 = asyncio.create_task(engine.tick(now=datetime.now(timezone.utc), limit=1))
        await asyncio.sleep(0.05)
        assert entered == ["periodic"]
        gate.set()
        await task1
        await task2

    asyncio.run(_run_two_ticks())


def test_news_tick_scenario_cards_claim_once(monkeypatch) -> None:
    engine = NewsTickEngine(event_store=MagicMock(), news_service=MagicMock(), broadcaster=None)
    emitted: list[dict[str, str]] = []

    card_id = f"scenario-card:{uuid4()}"
    save_news(
        card_id=card_id,
        kind="EARNINGS",
        publisher_id="system",
        text="scenario trigger",
        symbols=["TEST"],
        tags=[],
        scheduled_at=datetime.now(timezone.utc).isoformat(),
        scenario_id="scenario:test",
    )

    class _FakeNewsService:
        def get_preset_template(self, *, kind, symbols):
            return "scenario trigger"

        def emit_variant(self, *, card_id, author_id, text):
            emitted.append({"card_id": card_id, "author_id": author_id, "text": text})
            return (f"variant:{card_id}", MagicMock(model_dump=lambda mode="json": {"variant_id": f"variant:{card_id}"}))

    monkeypatch.setattr("ifrontier.infra.sqlite.news.list_pending_scenario_cards", lambda limit=50: [get_news(card_id)])
    monkeypatch.setattr("ifrontier.infra.sqlite.news.has_variant", lambda card_id: False)
    monkeypatch.setattr("ifrontier.infra.sqlite.news.claim_scenario_card", lambda card_id: claim_scenario_card(card_id))
    monkeypatch.setattr("ifrontier.infra.sqlite.news.release_scenario_card", lambda card_id: None)
    monkeypatch.setattr(engine, "_news", _FakeNewsService())

    async def _run_twice() -> None:
        now = datetime.now(timezone.utc)
        first = await engine._tick_scenario_cards(now=now, limit=10)
        second = await engine._tick_scenario_cards(now=now, limit=10)
        assert len(first) == 1
        assert second == []

    asyncio.run(_run_twice())
    assert len(emitted) == 1
