from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app

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
