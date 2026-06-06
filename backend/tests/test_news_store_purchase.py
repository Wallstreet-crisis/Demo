from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.domain.news.prototypes import StoreTriggerMode, prototype_registry
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.news import get_main_card

client = TestClient(app)


class _FakeEvent:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, object]:
        return dict(self._payload)


def test_news_store_purchase_delivers_only_to_buyer_and_spends_cash() -> None:
    buyer = f"user:purchase:buyer:{uuid4()}"
    other = f"user:purchase:other:{uuid4()}"

    create_account(buyer, owner_type="user", initial_cash=100.0)

    # Ensure other user exists in graph
    resp = client.post("/social/follow", json={"follower_id": other, "followee_id": buyer})
    assert resp.status_code == 200

    resp = client.post(
        "/news/store/purchase",
        json={
            "buyer_user_id": buyer,
            "kind": "RUMOR",
            "price_cash": 30.0,
            "symbols": ["ABC"],
            "tags": ["purchased"],
            "initial_text": "hello",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["card_id"]
    assert body["variant_id"]

    snap = get_snapshot(buyer)
    assert abs(float(snap.cash) - 70.0) < 1e-6

    inbox_buyer = client.get(f"/news/inbox/{buyer}?limit=50")
    assert inbox_buyer.status_code == 200
    items = inbox_buyer.json()["items"]
    assert items
    assert any(i["delivery_reason"] == "PURCHASED" for i in items)
    assert any(i["variant_id"] == body["variant_id"] for i in items)

    inbox_other = client.get(f"/news/inbox/{other}?limit=50")
    assert inbox_other.status_code == 200
    assert inbox_other.json()["items"] == []


def test_news_store_purchase_fails_when_insufficient_cash() -> None:
    buyer = f"user:purchase:poor:{uuid4()}"
    create_account(buyer, owner_type="user", initial_cash=0.0)

    resp = client.post(
        "/news/store/purchase",
        json={
            "buyer_user_id": buyer,
            "kind": "RUMOR",
            "price_cash": 10.0,
            "initial_text": "hello",
        },
    )
    assert resp.status_code == 400


def test_news_store_purchase_rejects_missing_symbols_for_symbol_required_kind() -> None:
    buyer = f"user:purchase:symbols:{uuid4()}"
    create_account(buyer, owner_type="user", initial_cash=100000.0)

    resp = client.post(
        "/news/store/purchase",
        json={
            "buyer_user_id": buyer,
            "kind": "LEAK",
            "price_cash": 15000.0,
            "initial_text": "hello",
        },
    )
    assert resp.status_code == 400
    assert "symbols required" in resp.json()["detail"]


def test_news_store_purchase_major_event_broadcasts_chain_events(monkeypatch) -> None:
    from ifrontier.app import api as api_module

    buyer = f"user:purchase:major:{uuid4()}"
    create_account(buyer, owner_type="user", initial_cash=200000.0)

    calls: list[tuple[list[str], dict[str, object]]] = []

    async def _fake_broadcast_many(channel: list[str], payload: dict[str, object]) -> None:
        calls.append((list(channel), dict(payload)))

    def _fake_start_chain(**kwargs):
        return {
            "chain_id": f"chain:{uuid4()}",
            "major_card_id": f"card:{uuid4()}",
            "card_created_event": _FakeEvent({"event_type": "news.card_created", "source": "test"}),
            "chain_started_event": _FakeEvent({"event_type": "news.chain_started", "source": "test"}),
            "t0_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(api_module._news_tick_engine, "start_chain", _fake_start_chain)
    monkeypatch.setattr(api_module.hub, "broadcast_many", _fake_broadcast_many)

    resp = client.post(
        "/news/store/purchase",
        json={
            "buyer_user_id": buyer,
            "kind": "MAJOR_EVENT",
            "price_cash": 100000.0,
            "symbols": ["BLUEGOLD"],
            "initial_text": "breaking",
        },
    )
    assert resp.status_code == 200

    event_types = [payload.get("event_type") for _channel, payload in calls]
    assert "news.card_created" in event_types
    assert "news.chain_started" in event_types


def test_news_store_purchase_manual_item_activates_only_when_requested() -> None:
    buyer = f"user:purchase:manual:{uuid4()}"
    create_account(buyer, owner_type="user", initial_cash=100000.0)

    rumor_bp = prototype_registry.find_by_kind("RUMOR")[0]
    original_trigger_mode = rumor_bp.store_trigger_mode
    try:
        rumor_bp.store_trigger_mode = StoreTriggerMode.MANUAL

        resp = client.post(
            "/news/store/purchase",
            json={
                "buyer_user_id": buyer,
                "kind": "RUMOR",
                "price_cash": 2000.0,
                "symbols": ["ABC"],
                "initial_text": "manual item",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["card_id"]
        assert body["variant_id"] is None
        assert body["chain_id"] is None

        activated = client.post(
            f"/news/cards/{body['card_id']}/activate",
            json={"actor_id": buyer, "text": "manual activation text"},
        )
        assert activated.status_code == 200, activated.text
        activated_body = activated.json()
        assert activated_body["variant_id"]
        assert activated_body["delivery_id"]
    finally:
        rumor_bp.store_trigger_mode = original_trigger_mode


def test_studio_news_update_card_rewrites_tree_fields() -> None:
    actor = "author"
    card_resp = client.post(
        "/news/cards",
        json={
            "actor_id": actor,
            "kind": "RUMOR",
            "symbols": ["TREE"],
            "tags": ["old"],
            "scenario_id": "scenario:tree-a",
        },
    )
    assert card_resp.status_code == 200, card_resp.text
    card_id = card_resp.json()["card_id"]

    update_resp = client.patch(
        f"/studio/news/cards/{card_id}",
        json={
            "actor_id": actor,
            "kind": "LEAK",
            "symbols": ["TREE", "ROOT"],
            "tags": ["updated", "branch"],
            "parent_card_id": f"parent:{uuid4()}",
            "activation_prob": 0.5,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "scenario_id": "scenario:tree-b",
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    card = get_main_card(card_id)
    assert card is not None
    assert card.kind == "LEAK"
    assert card.symbols == ["TREE", "ROOT"]
    assert card.tags == ["updated", "branch"]
    assert card.parent_card_id is not None
    assert abs(float(card.activation_prob) - 0.5) < 1e-6
    assert card.scenario_id == "scenario:tree-b"


def test_news_store_purchase_auto_chain_can_bind_other_chain_kind(monkeypatch) -> None:
    from ifrontier.app import api as api_module

    buyer = f"user:purchase:auto-chain:{uuid4()}"
    create_account(buyer, owner_type="user", initial_cash=200000.0)

    rumor_bp = prototype_registry.find_by_kind("RUMOR")[0]
    original_trigger_mode = rumor_bp.store_trigger_mode
    original_chain_kind = rumor_bp.store_chain_kind
    calls: list[dict[str, object]] = []

    def _fake_start_chain(**kwargs):
        calls.append(dict(kwargs))
        return {
            "chain_id": f"chain:{uuid4()}",
            "major_card_id": f"card:{uuid4()}",
            "card_created_event": _FakeEvent({"event_type": "news.card_created"}),
            "chain_started_event": _FakeEvent({"event_type": "news.chain_started"}),
            "t0_at": datetime.now(timezone.utc),
        }

    async def _fake_broadcast_many(*args, **kwargs):
        return None

    monkeypatch.setattr(api_module._news_tick_engine, "start_chain", _fake_start_chain)
    monkeypatch.setattr(api_module.hub, "broadcast_many", _fake_broadcast_many)

    try:
        rumor_bp.store_trigger_mode = StoreTriggerMode.AUTO_CHAIN
        rumor_bp.store_chain_kind = "WORLD_EVENT"

        resp = client.post(
            "/news/store/purchase",
            json={
                "buyer_user_id": buyer,
                "kind": "RUMOR",
                "price_cash": 2000.0,
                "symbols": ["ABC"],
                "initial_text": "auto chain bind",
            },
        )
        assert resp.status_code == 200, resp.text
        assert calls, "expected start_chain to be called"
        assert calls[0]["kind"] == "WORLD_EVENT"
    finally:
        rumor_bp.store_trigger_mode = original_trigger_mode
        rumor_bp.store_chain_kind = original_chain_kind
