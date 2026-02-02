from __future__ import annotations

import json
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


def test_contract_agent_draft_cash_transfer_and_context() -> None:
    # ensure deterministic: do not use LLM in this test
    import os

    os.environ.pop("OPENROUTER_API_KEY", None)

    actor = f"user:agent:{uuid4()}"
    to = f"user:agent:to:{uuid4()}"

    resp = client.post(
        "/contract-agent/draft",
        json={"actor_id": actor, "natural_language": f"给 {to} 转 1000 现金"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_id"] == "P2P_CASH_TRANSFER"
    cc = data["contract_create"]
    assert cc["actor_id"] == actor
    assert cc["kind"] == "P2P_CASH_TRANSFER"
    assert "terms" in cc
    assert len(cc["terms"]["transfers"]) == 1

    resp = client.get(f"/contract-agent/context/{actor}")
    assert resp.status_code == 200
    ctx = resp.json()
    assert ctx["actor_id"] == actor
    assert "last_draft" in ctx["context"]


def test_contract_agent_clear_context() -> None:
    import os

    os.environ.pop("OPENROUTER_API_KEY", None)

    actor = f"user:agent:{uuid4()}"
    resp = client.post(
        "/contract-agent/draft",
        json={"actor_id": actor, "natural_language": "给 user:someone 转 1"},
    )
    assert resp.status_code == 200

    resp = client.post(f"/contract-agent/context/{actor}/clear")
    assert resp.status_code == 200

    resp = client.get(f"/contract-agent/context/{actor}")
    assert resp.status_code == 200
    assert resp.json()["context"] == {}


def test_contract_agent_llm_draft(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    from urllib import request as ureq

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            content_obj = {
                "template_id": "P2P_CASH_TRANSFER",
                "contract_create": {
                    "actor_id": "user:a",
                    "kind": "P2P_CASH_TRANSFER",
                    "title": "LLM转账",
                    "terms": {
                        "transfers": [
                            {
                                "from": "user:a",
                                "to": "user:b",
                                "asset_type": "CASH",
                                "symbol": "CASH",
                                "quantity": 100.0,
                            }
                        ],
                        "rules": [],
                    },
                    "parties": ["user:a", "user:b"],
                    "required_signers": ["user:a", "user:b"],
                    "participation_mode": "OPT_IN",
                    "invited_parties": ["user:b"],
                },
                "explanation": "这是一次现金转账。",
                "questions": [],
                "risk_rating": "LOW",
            }
            resp = {"choices": [{"message": {"content": json.dumps(content_obj, ensure_ascii=False)}}]}
            return json.dumps(resp, ensure_ascii=False).encode("utf-8")

    def _fake_urlopen(req, timeout=0):
        return _FakeResp()

    monkeypatch.setattr(ureq, "urlopen", _fake_urlopen)

    actor = "user:a"
    resp = client.post(
        "/contract-agent/draft",
        json={"actor_id": actor, "natural_language": "给 user:b 转 100 现金"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_id"] == "P2P_CASH_TRANSFER"
    assert data["risk_rating"] == "LOW"
    assert data["contract_create"]["kind"] == "P2P_CASH_TRANSFER"
