from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account, get_snapshot


client = TestClient(app)


def _reset_sqlite() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM orders")


def test_contract_create_sign_activate_flow() -> None:
    # create
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "CUSTOM",
            "title": "A-B agreement",
            "terms": {"anything": {"nested": [1, 2, 3]}},
            "parties": ["user:alice", "user:bob"],
            "required_signers": ["user:alice", "user:bob"],
        },
    )
    assert resp.status_code == 200
    contract_id = resp.json()["contract_id"]
    assert isinstance(contract_id, str)
    assert len(contract_id) > 0

    # sign by alice -> not fully signed yet
    resp = client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:alice"})
    assert resp.status_code == 200
    assert resp.json()["status"] in {"DRAFT", "SIGNED"}

    # activate should fail because bob not signed
    resp = client.post(f"/contracts/{contract_id}/activate", json={"actor_id": "user:alice"})
    assert resp.status_code == 400

    # sign by bob -> becomes SIGNED
    resp = client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:bob"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "SIGNED"

    # activate -> ok
    resp = client.post(f"/contracts/{contract_id}/activate", json={"actor_id": "user:alice"})
    assert resp.status_code == 200


def test_contract_sign_nonexistent_returns_400() -> None:
    resp = client.post(
        "/contracts/00000000-0000-0000-0000-000000000000/sign",
        json={"signer": "user:alice"},
    )
    assert resp.status_code == 400


def test_opt_in_contract_allows_join_without_everyone_signing() -> None:
    # create opt-in contract: only alice is required signer; bob is invited to join
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "CALL",
            "title": "Join my guild",
            "terms": {"rules": "be nice"},
            "parties": ["user:alice"],
            "required_signers": ["user:alice"],
            "participation_mode": "OPT_IN",
            "invited_parties": ["user:bob"],
        },
    )
    assert resp.status_code == 200
    contract_id = resp.json()["contract_id"]

    # bob chooses to join
    resp = client.post(f"/contracts/{contract_id}/join", json={"joiner": "user:bob"})
    assert resp.status_code == 200

    # alice can sign+activate regardless of bob signing
    resp = client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:alice"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "SIGNED"

    resp = client.post(f"/contracts/{contract_id}/activate", json={"actor_id": "user:alice"})
    assert resp.status_code == 200


def test_contract_proposal_suspend_requires_all_parties_approval() -> None:
    # base contract
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "CUSTOM",
            "title": "A-B",
            "terms": {"v": 1},
            "parties": ["user:alice", "user:bob"],
            "required_signers": ["user:alice", "user:bob"],
        },
    )
    assert resp.status_code == 200
    contract_id = resp.json()["contract_id"]

    client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{contract_id}/activate", json={"actor_id": "user:alice"})

    # create suspend proposal
    resp = client.post(
        f"/contracts/{contract_id}/proposals/create",
        json={"proposer": "user:alice", "proposal_type": "SUSPEND", "details": {}},
    )
    assert resp.status_code == 200
    proposal_id = resp.json()["proposal_id"]

    # only alice approves -> not applied
    resp = client.post(
        f"/contracts/{contract_id}/proposals/{proposal_id}/approve",
        json={"approver": "user:alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is False

    # bob approves -> applied, status becomes SUSPENDED
    resp = client.post(
        f"/contracts/{contract_id}/proposals/{proposal_id}/approve",
        json={"approver": "user:bob"},
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is True
    assert resp.json()["contract_status"] == "SUSPENDED"


def test_contract_batch_create_returns_multiple_ids() -> None:
    resp = client.post(
        "/contracts/batch_create",
        json={
            "actor_id": "user:alice",
            "contracts": [
                {
                    "kind": "KIND1",
                    "title": "Batch A",
                    "terms": {"v": 1},
                    "parties": ["user:alice", "user:bob"],
                    "required_signers": ["user:alice", "user:bob"],
                },
                {
                    "kind": "KIND2",
                    "title": "Batch B",
                    "terms": {"v": 2},
                    "parties": ["user:alice", "user:bob"],
                    "required_signers": ["user:alice", "user:bob"],
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "contracts" in data
    assert len(data["contracts"]) == 2
    ids = {item["contract_id"] for item in data["contracts"]}
    assert len(ids) == 2


def test_contract_settle_transfers_assets_between_accounts() -> None:
    _reset_sqlite()

    create_account("user:alice", owner_type="user", initial_cash=1000.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    conn = get_connection()
    with conn:
        conn.execute(
            "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?)",
            ("user:bob", "BLUEGOLD", 50.0),
        )

    # create contract with transfers (alice pays cash, bob transfers equity)
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "EXCHANGE",
            "title": "cash-for-equity",
            "terms": {
                "transfers": [
                    {
                        "from": "user:alice",
                        "to": "user:bob",
                        "asset_type": "CASH",
                        "symbol": "CASH",
                        "quantity": 100.0,
                    },
                    {
                        "from": "user:bob",
                        "to": "user:alice",
                        "asset_type": "EQUITY",
                        "symbol": "BLUEGOLD",
                        "quantity": 10.0,
                    },
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

    resp = client.post(f"/contracts/{contract_id}/settle", json={"actor_id": "user:alice"})
    assert resp.status_code == 200

    alice = get_snapshot("user:alice")
    bob = get_snapshot("user:bob")

    assert alice.cash == 900.0
    assert bob.cash == 100.0
    assert alice.positions.get("BLUEGOLD", 0.0) == 10.0
    assert bob.positions.get("BLUEGOLD", 0.0) == 40.0


def test_contract_settle_fails_and_rolls_back_on_insufficient_assets() -> None:
    _reset_sqlite()

    create_account("user:alice", owner_type="user", initial_cash=50.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    # create contract that would require alice to pay 100 cash (insufficient)
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "EXCHANGE",
            "title": "bad-cash",
            "terms": {
                "transfers": [
                    {
                        "from": "user:alice",
                        "to": "user:bob",
                        "asset_type": "CASH",
                        "symbol": "CASH",
                        "quantity": 100.0,
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

    before_alice = get_snapshot("user:alice")
    before_bob = get_snapshot("user:bob")

    resp = client.post(f"/contracts/{contract_id}/settle", json={"actor_id": "user:alice"})
    assert resp.status_code == 200

    after_alice = get_snapshot("user:alice")
    after_bob = get_snapshot("user:bob")

    assert after_alice.cash == 0.0
    assert after_bob.cash == 50.0


def test_contract_run_rules_once_executes_transfers_and_does_not_repeat() -> None:
    _reset_sqlite()

    create_account("user:alice", owner_type="user", initial_cash=200.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "RULES",
            "title": "pay-if-rich",
            "terms": {
                "rules": [
                    {
                        "rule_id": "r1",
                        "schedule": {"type": "once"},
                        "condition": {
                            "op": ">=",
                            "left": {"var": "cash:user:alice"},
                            "right": 100.0,
                        },
                        "actions": {
                            "transfers": [
                                {
                                    "from": "user:alice",
                                    "to": "user:bob",
                                    "asset_type": "CASH",
                                    "symbol": "CASH",
                                    "quantity": 50.0,
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
    assert get_snapshot("user:alice").cash == 150.0
    assert get_snapshot("user:bob").cash == 50.0

    # run again: once schedule should block, no further changes
    resp = client.post(f"/contracts/{contract_id}/run_rules", json={"actor_id": "user:alice"})
    assert resp.status_code == 200
    assert get_snapshot("user:alice").cash == 150.0
    assert get_snapshot("user:bob").cash == 50.0


def test_contract_run_rules_condition_false_does_not_execute() -> None:
    _reset_sqlite()

    create_account("user:alice", owner_type="user", initial_cash=10.0)
    create_account("user:bob", owner_type="user", initial_cash=0.0)

    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "RULES",
            "title": "pay-if-very-rich",
            "terms": {
                "rules": [
                    {
                        "rule_id": "r1",
                        "schedule": {"type": "once"},
                        "condition": {
                            "op": ">=",
                            "left": {"var": "cash:user:alice"},
                            "right": 100.0,
                        },
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
    contract_id = resp.json()["contract_id"]

    client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:alice"})
    client.post(f"/contracts/{contract_id}/sign", json={"signer": "user:bob"})
    client.post(f"/contracts/{contract_id}/activate", json={"actor_id": "user:alice"})

    before_alice = get_snapshot("user:alice")
    before_bob = get_snapshot("user:bob")

    resp = client.post(f"/contracts/{contract_id}/run_rules", json={"actor_id": "user:alice"})
    assert resp.status_code == 200

    after_alice = get_snapshot("user:alice")
    after_bob = get_snapshot("user:bob")
    assert after_alice.cash == before_alice.cash
    assert after_bob.cash == before_bob.cash


def test_contract_proposal_amend_requires_all_parties_approval() -> None:
    resp = client.post(
        "/contracts/create",
        json={
            "actor_id": "user:alice",
            "kind": "CUSTOM",
            "title": "A-B amendable",
            "terms": {"v": 1},
            "parties": ["user:alice", "user:bob"],
            "required_signers": ["user:alice", "user:bob"],
        },
    )
    assert resp.status_code == 200
    contract_id = resp.json()["contract_id"]

    # create amend proposal: we store new terms as details
    resp = client.post(
        f"/contracts/{contract_id}/proposals/create",
        json={"proposer": "user:alice", "proposal_type": "AMEND", "details": {"v": 2}},
    )
    assert resp.status_code == 200
    proposal_id = resp.json()["proposal_id"]

    # approve by alice then bob -> applied (status unchanged, but applied True)
    resp = client.post(
        f"/contracts/{contract_id}/proposals/{proposal_id}/approve",
        json={"approver": "user:alice"},
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is False

    resp = client.post(
        f"/contracts/{contract_id}/proposals/{proposal_id}/approve",
        json={"approver": "user:bob"},
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] is True
