from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.market import record_trade

client = TestClient(app)


def _reset_sqlite() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM market_trades")


def test_contract_rule_transfer_quantity_expr_can_use_price_var() -> None:
    _reset_sqlite()

    create_account("user:alice", owner_type="user", initial_cash=1000.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    symbol = f"BLUEGOLD_{uuid4()}"
    record_trade(symbol=symbol, price=10.0, quantity=1.0, occurred_at=datetime.now(timezone.utc), event_id=str(uuid4()))

    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "RULES",
            "title": "expr-qty",
            "terms": {
                "rules": [
                    {
                        "rule_id": "r1",
                        "schedule": {"type": "once"},
                        "condition": True,
                        "actions": {
                            "transfers": [
                                {
                                    "from": "user:alice",
                                    "to": "user:bob",
                                    "asset_type": "CASH",
                                    "symbol": "CASH",
                                    "quantity": {"expr": {"op": "mul", "args": [{"var": f"price:{symbol}"}, 2]}},
                                }
                            ]
                        },
                    }
                ]
            },
            "parties": ["user:alice", "user:bob"],
            "required_signers": ["user:alice", "user:bob"],
        },
    )
    assert resp.status_code == 200
    contract_id = resp.json()["contract_id"]

    client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{contract_id}/activate", json={"actor_id": "user:alice"})

    resp = client.post(f"/contracts/{contract_id}/run_rules", json={"actor_id": "user:alice"})
    assert resp.status_code == 200

    assert get_snapshot("user:alice").cash == 980.0
    assert get_snapshot("user:bob").cash == 20.0
