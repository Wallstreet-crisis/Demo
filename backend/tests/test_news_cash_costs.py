from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot

client = TestClient(app)


def test_news_mutate_spends_cash_by_char_count(monkeypatch) -> None:
    monkeypatch.setenv("IF_NEWS_MUTATE_CASH_PER_CHAR", "0.5")

    editor = f"user:mutate:editor:{uuid4()}"
    create_account(editor, owner_type="user", initial_cash=10.0)

    # Create a card + initial variant (GM/system-only endpoint)
    resp = client.post(
        "/news/cards",
        json={"actor_id": "system", "kind": "RUMOR", "symbols": [], "tags": []},
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    resp = client.post(
        "/news/variants/emit",
        json={"card_id": card_id, "author_id": "system", "text": "base"},
    )
    assert resp.status_code == 200
    parent_variant_id = resp.json()["variant_id"]

    # mutate: 4 chars => cost 2.0
    resp = client.post(
        "/news/variants/mutate",
        json={"parent_variant_id": parent_variant_id, "editor_id": editor, "new_text": "abcd"},
    )
    assert resp.status_code == 200

    snap = get_snapshot(editor)
    assert abs(float(snap.cash) - 8.0) < 1e-6


def test_news_propagate_cost_increases_with_mutation_depth(monkeypatch) -> None:
    # base per delivery = 1.0, mutation_mult = 0.5
    monkeypatch.setenv("IF_NEWS_PROPAGATE_CASH_PER_DELIVERY", "1.0")
    monkeypatch.setenv("IF_NEWS_PROPAGATE_MUTATION_MULT", "0.5")

    actor = f"user:prop:actor:{uuid4()}"
    f1 = f"user:prop:f1:{uuid4()}"
    f2 = f"user:prop:f2:{uuid4()}"

    create_account(actor, owner_type="user", initial_cash=10.0)

    # Build follower graph
    r = client.post("/social/follow", json={"follower_id": f1, "followee_id": actor})
    assert r.status_code == 200
    r = client.post("/social/follow", json={"follower_id": f2, "followee_id": actor})
    assert r.status_code == 200

    # Create a card + initial variant (GM/system-only endpoint)
    resp = client.post(
        "/news/cards",
        json={"actor_id": "system", "kind": "RUMOR", "symbols": [], "tags": []},
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    resp = client.post(
        "/news/variants/emit",
        json={"card_id": card_id, "author_id": "system", "text": "base"},
    )
    assert resp.status_code == 200
    parent_variant_id = resp.json()["variant_id"]

    # One mutation => depth=1
    resp = client.post(
        "/news/variants/mutate",
        json={"parent_variant_id": parent_variant_id, "editor_id": actor, "new_text": "m1", "spend_cash": 0.01},
    )
    assert resp.status_code == 200
    mutated_variant_id = resp.json()["new_variant_id"]

    # depth=1 => per_delivery_cost = 1.0 * (1 + 1*0.5) = 1.5
    # budget=2.9 => affordable=1 => should deliver to only 1 follower
    resp = client.post(
        "/news/propagate",
        json={
            "variant_id": mutated_variant_id,
            "from_actor_id": actor,
            "visibility_level": "NORMAL",
            "spend_cash": 2.9,
            "limit": 50,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["delivered"] == 1

    snap = get_snapshot(actor)
    # 10 - 0.01(mutate) - 1.5(propagate) = 8.49
    assert abs(float(snap.cash) - 8.49) < 1e-6
