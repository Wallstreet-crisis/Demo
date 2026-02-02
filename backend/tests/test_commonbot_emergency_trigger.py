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
            "actor_id": u1,
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
            "author_id": u1,
            "text": "BREAKING NEWS",
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
    assert called["count"] == 1
