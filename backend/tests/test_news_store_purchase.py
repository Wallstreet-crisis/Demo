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
