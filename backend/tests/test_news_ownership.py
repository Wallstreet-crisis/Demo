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

client = TestClient(app)


def test_news_ownership_grant_transfer_and_list() -> None:
    u1 = f"user:own:u1:{uuid4()}"
    u2 = f"user:own:u2:{uuid4()}"

    # create card
    resp = client.post(
        "/news/cards",
        json={
            "actor_id": u1,
            "kind": "RUMOR",
            "truth_payload": {"note": "asset"},
        },
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    # grant to u1
    resp = client.post(
        "/news/ownership/grant",
        json={"card_id": card_id, "to_user_id": u1, "granter_id": "system"},
    )
    assert resp.status_code == 200

    resp = client.get(f"/news/ownership/{u1}")
    assert resp.status_code == 200
    assert card_id in resp.json()["cards"]

    # transfer to u2
    resp = client.post(
        "/news/ownership/transfer",
        json={
            "card_id": card_id,
            "from_user_id": u1,
            "to_user_id": u2,
            "transferred_by": u1,
        },
    )
    assert resp.status_code == 200

    resp = client.get(f"/news/ownership/{u1}")
    assert resp.status_code == 200
    assert card_id not in resp.json()["cards"]

    resp = client.get(f"/news/ownership/{u2}")
    assert resp.status_code == 200
    assert card_id in resp.json()["cards"]


def test_news_ownership_transfer_requires_current_owner() -> None:
    u1 = f"user:own2:u1:{uuid4()}"
    u2 = f"user:own2:u2:{uuid4()}"

    resp = client.post(
        "/news/cards",
        json={"actor_id": u1, "kind": "RUMOR", "truth_payload": {"note": "asset2"}},
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    # no grant, so u1 doesn't own it yet
    resp = client.post(
        "/news/ownership/transfer",
        json={
            "card_id": card_id,
            "from_user_id": u1,
            "to_user_id": u2,
            "transferred_by": u1,
        },
    )
    assert resp.status_code == 400
