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


def test_news_card_variant_mutate_propagate_and_inbox() -> None:
    # Use unique ids to avoid cross-test pollution in shared Neo4j
    u_author = f"user:author:{uuid4()}"
    u_follower = f"user:follower:{uuid4()}"

    # follower follows author, so author can propagate to follower
    resp = client.post(
        "/social/follow",
        json={"follower_id": u_follower, "followee_id": u_author},
    )
    assert resp.status_code == 200

    # create card (placeholder / no image)
    resp = client.post(
        "/news/cards",
        json={
            "actor_id": u_author,
            "kind": "RUMOR",
            "image_anchor_id": None,
            "image_uri": None,
            "truth_payload": {"chain_id": f"chain:{uuid4()}"},
            "symbols": ["BLUEGOLD"],
            "tags": ["test"],
        },
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    # emit first variant
    resp = client.post(
        "/news/variants/emit",
        json={
            "card_id": card_id,
            "author_id": u_author,
            "text": "Diplomacy downgraded.",
        },
    )
    assert resp.status_code == 200
    root_variant_id = resp.json()["variant_id"]

    # mutate (fork)
    resp = client.post(
        "/news/variants/mutate",
        json={
            "parent_variant_id": root_variant_id,
            "editor_id": u_author,
            "new_text": "This is totally fine.",
            "influence_cost": 1.0,
        },
    )
    assert resp.status_code == 200
    new_variant_id = resp.json()["new_variant_id"]

    # propagate mutated variant to followers
    resp = client.post(
        "/news/propagate",
        json={
            "variant_id": new_variant_id,
            "from_actor_id": u_author,
            "visibility_level": "NORMAL",
            "limit": 10,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["delivered"] == 1

    # follower inbox should contain the message
    resp = client.get(f"/news/inbox/{u_follower}?limit=10")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert any(x["variant_id"] == new_variant_id and "totally fine" in x["text"] for x in items)


def test_news_broadcast_delivers_to_all_known_users() -> None:
    u1 = f"user:broadcast:u1:{uuid4()}"
    u2 = f"user:broadcast:u2:{uuid4()}"

    # Create two users in graph via follow (ensures :User nodes exist)
    resp = client.post(
        "/social/follow",
        json={"follower_id": u2, "followee_id": u1},
    )
    assert resp.status_code == 200

    resp = client.post(
        "/news/cards",
        json={
            "actor_id": u1,
            "kind": "MAJOR_EVENT",
            "truth_payload": {"note": "global"},
        },
    )
    assert resp.status_code == 200
    card_id = resp.json()["card_id"]

    resp = client.post(
        "/news/variants/emit",
        json={
            "card_id": card_id,
            "author_id": u1,
            "text": "EARNINGS REPORT RELEASED.",
        },
    )
    assert resp.status_code == 200
    variant_id = resp.json()["variant_id"]

    resp = client.post(
        "/news/broadcast",
        json={
            "variant_id": variant_id,
            "actor_id": u1,
            "channel": "GLOBAL_MANDATORY",
            "visibility_level": "NORMAL",
            "limit_users": 5000,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["delivered"] >= 2

    resp = client.get(f"/news/inbox/{u2}?limit=20")
    assert resp.status_code == 200
    assert any(x["variant_id"] == variant_id for x in resp.json()["items"])
