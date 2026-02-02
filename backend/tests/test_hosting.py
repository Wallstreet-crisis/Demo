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
from ifrontier.infra.sqlite.db import get_connection

client = TestClient(app)


def _reset_hosting_tables() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM user_hosting_state")
        conn.execute("DELETE FROM user_hosting_context")


def test_hosting_enable_disable_and_status() -> None:
    _reset_hosting_tables()

    user_id = f"user:host:{uuid4()}"

    st0 = client.get(f"/hosting/{user_id}/status")
    assert st0.status_code == 200
    assert st0.json()["enabled"] is False
    assert st0.json()["status"] == "OFF"

    en = client.post(f"/hosting/{user_id}/enable")
    assert en.status_code == 200
    assert en.json()["state"]["enabled"] is True
    assert en.json()["state"]["status"] == "ON_IDLE"

    st1 = client.get(f"/hosting/{user_id}/status")
    assert st1.status_code == 200
    assert st1.json()["enabled"] is True

    dis = client.post(f"/hosting/{user_id}/disable")
    assert dis.status_code == 200
    assert dis.json()["state"]["enabled"] is False
    assert dis.json()["state"]["status"] == "OFF"


def test_hosting_debug_tick_once_runs() -> None:
    _reset_hosting_tables()

    # enable at least one hosting user so scheduler has something to pick
    user_id = f"user:host:{uuid4()}"
    en = client.post(f"/hosting/{user_id}/enable")
    assert en.status_code == 200

    # scheduler requires app lifespan (it is started by app.main lifespan)
    # TestClient will start lifespan automatically.
    resp = client.post("/hosting/debug/tick_once")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
