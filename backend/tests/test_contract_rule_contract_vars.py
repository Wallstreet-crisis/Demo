from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot
from ifrontier.infra.sqlite.db import get_connection

client = TestClient(app)


def _reset_sqlite() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM orders")


def test_rule_condition_can_see_other_contract_status() -> None:
    _reset_sqlite()

    # prepare accounts
    create_account("user:alice", owner_type="user", initial_cash=100.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    # create & activate main contract A (no rules, just for status)
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "MASTER",
            "title": "main",
            "terms": {},
            "parties": ["user:alice", "user:bob"],
            "required_signers": ["user:alice", "user:bob"],
        },
    )
    assert resp.status_code == 200
    main_id = resp.json()["contract_id"]

    client.post(f"/contracts/{main_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{main_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{main_id}/activate", json={"actor_id": "user:alice"})

    # create contract B: its rule checks contract.status:main_id == ACTIVE, then transfers 10 cash
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "DEPENDENT",
            "title": "depends-on-main",
            "terms": {
                "rules": [
                    {
                        "rule_id": "r1",
                        "schedule": {"type": "once"},
                        "condition": {
                            "op": "==",
                            "left": {"var": f"contract.status:{main_id}"},
                            "right": "ACTIVE",
                        },
                        "actions": {
                            "transfers": [
                                {
                                    "from": "user:alice",
                                    "to": "user:bob",
                                    "asset_type": "CASH",
                                    "symbol": "CASH",
                                    "quantity": 10.0,
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
    dep_id = resp.json()["contract_id"]

    client.post(f"/contracts/{dep_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{dep_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{dep_id}/activate", json={"actor_id": "user:alice"})

    before_alice = get_snapshot("user:alice")
    before_bob = get_snapshot("user:bob")

    resp = client.post(f"/contracts/{dep_id}/run_rules", json={"actor_id": "user:alice"})
    assert resp.status_code == 200

    after_alice = get_snapshot("user:alice")
    after_bob = get_snapshot("user:bob")

    assert after_alice.cash == before_alice.cash - 10.0
    assert after_bob.cash == before_bob.cash + 10.0


def test_rule_condition_can_use_contract_runs_of_other_contract() -> None:
    _reset_sqlite()

    create_account("user:alice", owner_type="user", initial_cash=100.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    # contract C: simple rule r1 that always transfers 5 from alice to bob
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "SOURCE",
            "title": "source",
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
                                    "quantity": 5.0,
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
    source_id = resp.json()["contract_id"]

    client.post(f"/contracts/{source_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{source_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{source_id}/activate", json={"actor_id": "user:alice"})

    # run rules once so that source.r1 has runs=1
    client.post(f"/contracts/{source_id}/run_rules", json={"actor_id": "user:alice"})

    # contract D: rule r1 only executes if contract.runs:source_id:r1 >= 1
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "DEPENDENT_RUNS",
            "title": "depends-on-runs",
            "terms": {
                "rules": [
                    {
                        "rule_id": "r1",
                        "schedule": {"type": "once"},
                        "condition": {
                            "op": ">=",
                            "left": {"var": f"contract.runs:{source_id}:r1"},
                            "right": 1,
                        },
                        "actions": {
                            "transfers": [
                                {
                                    "from": "user:alice",
                                    "to": "user:bob",
                                    "asset_type": "CASH",
                                    "symbol": "CASH",
                                    "quantity": 7.0,
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
    dep_id = resp.json()["contract_id"]

    client.post(f"/contracts/{dep_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{dep_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{dep_id}/activate", json={"actor_id": "user:alice"})

    before_alice = get_snapshot("user:alice")
    before_bob = get_snapshot("user:bob")

    resp = client.post(f"/contracts/{dep_id}/run_rules", json={"actor_id": "user:alice"})
    assert resp.status_code == 200

    after_alice = get_snapshot("user:alice")
    after_bob = get_snapshot("user:bob")

    assert after_alice.cash == before_alice.cash - 7.0
    assert after_bob.cash == before_bob.cash + 7.0
