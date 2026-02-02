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


def test_suppression_budget_reduces_omen_delivery() -> None:
    u1 = f"user:suppress:u1:{uuid4()}"
    u2 = f"user:suppress:u2:{uuid4()}"

    # Ensure users exist
    resp = client.post("/social/follow", json={"follower_id": u2, "followee_id": u1})
    assert resp.status_code == 200

    start = datetime.now(timezone.utc)

    resp = client.post(
        "/news/chains/start",
        json={
            "kind": "MAJOR_EVENT",
            "actor_id": u1,
            "t0_seconds": 30,
            "omen_interval_seconds": 10,
            "abort_probability": 0.0,
            "grant_count": 1,
            "seed": 42,
        },
    )
    assert resp.status_code == 200
    chain_id = resp.json()["chain_id"]

    # Add suppression budget >= grant_count, so omen should be generated but not delivered
    resp = client.post(
        "/news/suppress",
        json={
            "actor_id": "user:rich",
            "chain_id": chain_id,
            "spend_influence": 1.0,
            "scope": "chain",
        },
    )
    assert resp.status_code == 200

    resp = client.post(
        "/news/tick",
        json={"now_iso": (start + timedelta(seconds=1)).isoformat(), "limit": 10},
    )
    assert resp.status_code == 200

    chains = resp.json()["chains"]
    assert chains

    # At least one omen action exists; its delivered_to should be empty
    delivered_counts = []
    for ch in chains:
        for action in ch.get("actions", []):
            if action.get("type") == "omen_emitted":
                delivered_counts.append(len(action.get("delivered_to") or []))

    assert delivered_counts
    assert all(c == 0 for c in delivered_counts)
