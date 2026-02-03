from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
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


def test_hosting_agent_skills_calls_are_executed(monkeypatch) -> None:
    _reset_hosting_tables()

    # Force LLM path
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    # Mock OpenRouter response: one tool call to send a public message
    tool_calls = {
        "tool_calls": [
            {
                "name": "chat.send_public_message",
                "arguments": {"message_type": "TEXT", "content": "hello-from-hosting", "payload": {}},
            }
        ]
    }

    resp_obj = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(tool_calls, ensure_ascii=False),
                }
            }
        ]
    }

    class _FakeResp:
        def __init__(self, s: str):
            self._s = s

        def read(self):
            return self._s.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=20):
        return _FakeResp(json.dumps(resp_obj, ensure_ascii=False))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    user_id = f"user:host:{uuid4()}"
    en = client.post(f"/hosting/{user_id}/enable")
    assert en.status_code == 200

    # Execute one tick: should call LLM -> tool -> chat send
    resp = client.post("/hosting/debug/tick_once")
    assert resp.status_code == 200

    msgs = client.get("/chat/public/messages", params={"limit": 10})
    assert msgs.status_code == 200
    items = msgs.json()["items"]
    assert items
    assert items[0]["content"] == "hello-from-hosting"

    # Cleanup env
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


def test_hosting_agent_respects_max_tools_per_tick(monkeypatch) -> None:
    _reset_hosting_tables()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
    monkeypatch.setenv("IF_HOSTING_MAX_SKILLS_PER_TICK", "2")

    tool_calls = {
        "tool_calls": [
            {
                "name": "chat.send_public_message",
                "arguments": {"message_type": "TEXT", "content": "m1", "payload": {}},
            },
            {
                "name": "chat.send_public_message",
                "arguments": {"message_type": "TEXT", "content": "m2", "payload": {}},
            },
            {
                "name": "chat.send_public_message",
                "arguments": {"message_type": "TEXT", "content": "m3", "payload": {}},
            },
            {
                "name": "chat.send_public_message",
                "arguments": {"message_type": "TEXT", "content": "m4", "payload": {}},
            },
        ]
    }

    resp_obj = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(tool_calls, ensure_ascii=False),
                }
            }
        ]
    }

    class _FakeResp:
        def __init__(self, s: str):
            self._s = s

        def read(self):
            return self._s.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=20):
        return _FakeResp(json.dumps(resp_obj, ensure_ascii=False))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    user_id = f"user:host:{uuid4()}"
    en = client.post(f"/hosting/{user_id}/enable")
    assert en.status_code == 200

    resp = client.post("/hosting/debug/tick_once")
    assert resp.status_code == 200

    msgs = client.get("/chat/public/messages", params={"limit": 10})
    assert msgs.status_code == 200
    items = msgs.json()["items"]
    contents = [m["content"] for m in items]
    assert "m1" in contents
    assert "m2" in contents
    assert "m3" not in contents
    assert "m4" not in contents

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("IF_HOSTING_MAX_SKILLS_PER_TICK", raising=False)
