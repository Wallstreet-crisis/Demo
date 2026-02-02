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
from ifrontier.infra.sqlite.ledger import create_account

client = TestClient(app)


def _reset_chat_tables() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM chat_threads")
        conn.execute("DELETE FROM chat_intro_fee_quotes")
        conn.execute("DELETE FROM wealth_public_cache")


def _set_cash(account_id: str, cash: float) -> None:
    create_account(account_id, owner_type="user", initial_cash=float(cash))
    conn = get_connection()
    with conn:
        conn.execute("UPDATE accounts SET cash = ? WHERE account_id = ?", (float(cash), account_id))


def test_pm_open_requires_intro_fee_when_gap_is_large_and_requester_is_poor() -> None:
    _reset_chat_tables()

    rich = f"user:rich:{uuid4()}"
    poor = f"user:poor:{uuid4()}"

    _set_cash(rich, 10_000_000.0)
    _set_cash(poor, 500.0)

    resp = client.post("/chat/pm/open", json={"requester_id": poor, "target_id": rich})
    assert resp.status_code == 400
    detail = str(resp.json().get("detail") or "")
    assert "引荐费" in detail
    assert "现金不足" in detail


def test_pm_open_allows_rich_to_contact_poor_directly_even_when_gap_is_large() -> None:
    _reset_chat_tables()

    rich = f"user:rich:{uuid4()}"
    poor = f"user:poor:{uuid4()}"

    _set_cash(rich, 10_000_000.0)
    _set_cash(poor, 0.0)

    resp = client.post("/chat/pm/open", json={"requester_id": rich, "target_id": poor})
    assert resp.status_code == 200
    data = resp.json()
    assert str(data.get("thread_id") or "").startswith("pm:")
    assert bool(data.get("paid_intro_fee")) is False


def test_pm_open_no_barrier_when_gap_ratio_is_small() -> None:
    _reset_chat_tables()

    a = f"user:a:{uuid4()}"
    b = f"user:b:{uuid4()}"

    # ratio = 4000/1000 = 4 < 5
    _set_cash(a, 4000.0)
    _set_cash(b, 1000.0)

    resp = client.post("/chat/pm/open", json={"requester_id": b, "target_id": a})
    assert resp.status_code == 200
    data = resp.json()
    assert bool(data.get("paid_intro_fee")) is False


def test_public_messages_order_and_pagination() -> None:
    _reset_chat_tables()

    u = f"user:msg:{uuid4()}"
    _set_cash(u, 100.0)

    for txt in ["m1", "m2", "m3"]:
        resp = client.post(
            "/chat/public/send",
            json={"sender_id": u, "message_type": "TEXT", "content": txt, "payload": {}},
        )
        assert resp.status_code == 200

    resp = client.get("/chat/public/messages", params={"limit": 2})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["content"] == "m3"
    assert items[1]["content"] == "m2"

    before = items[1]["created_at"]
    resp2 = client.get("/chat/public/messages", params={"limit": 2, "before": before})
    assert resp2.status_code == 200
    items2 = resp2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["content"] == "m1"


def test_public_message_anonymous_does_not_leak_sender_id() -> None:
    _reset_chat_tables()

    u = f"user:anon:{uuid4()}"
    _set_cash(u, 100.0)

    resp = client.post(
        "/chat/public/send",
        json={
            "sender_id": u,
            "message_type": "TEXT",
            "content": "secret",
            "payload": {},
            "anonymous": True,
            "alias": "路人甲",
        },
    )
    assert resp.status_code == 200

    resp2 = client.get("/chat/public/messages", params={"limit": 10})
    assert resp2.status_code == 200
    items = resp2.json()["items"]
    assert items[0]["content"] == "secret"
    assert items[0]["sender_id"] is None
    assert items[0]["sender_display"] == "路人甲"


def test_pm_messages_order_and_pagination() -> None:
    _reset_chat_tables()

    a = f"user:pma:{uuid4()}"
    b = f"user:pmb:{uuid4()}"

    _set_cash(a, 10_000_000.0)
    _set_cash(b, 0.0)

    open_resp = client.post("/chat/pm/open", json={"requester_id": a, "target_id": b})
    assert open_resp.status_code == 200
    thread_id = open_resp.json()["thread_id"]

    for txt in ["p1", "p2", "p3"]:
        resp = client.post(
            "/chat/pm/send",
            json={"thread_id": thread_id, "sender_id": a, "message_type": "TEXT", "content": txt, "payload": {}},
        )
        assert resp.status_code == 200

    resp = client.get(f"/chat/pm/{thread_id}/messages", params={"limit": 2})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["content"] == "p3"
    assert items[1]["content"] == "p2"

    before = items[1]["created_at"]
    resp2 = client.get(f"/chat/pm/{thread_id}/messages", params={"limit": 2, "before": before})
    assert resp2.status_code == 200
    items2 = resp2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["content"] == "p1"


def test_pm_message_anonymous_does_not_leak_sender_id() -> None:
    _reset_chat_tables()

    a = f"user:pma:{uuid4()}"
    b = f"user:pmb:{uuid4()}"

    _set_cash(a, 10_000_000.0)
    _set_cash(b, 0.0)

    open_resp = client.post("/chat/pm/open", json={"requester_id": a, "target_id": b})
    assert open_resp.status_code == 200
    thread_id = open_resp.json()["thread_id"]

    resp = client.post(
        "/chat/pm/send",
        json={
            "thread_id": thread_id,
            "sender_id": a,
            "message_type": "TEXT",
            "content": "pm-secret",
            "payload": {},
            "anonymous": True,
        },
    )
    assert resp.status_code == 200

    resp2 = client.get(f"/chat/pm/{thread_id}/messages", params={"limit": 10})
    assert resp2.status_code == 200
    items = resp2.json()["items"]
    assert items[0]["content"] == "pm-secret"
    assert items[0]["sender_id"] is None
    assert str(items[0]["sender_display"]).startswith("Anonymous-")
