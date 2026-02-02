from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.app.main import app


client = TestClient(app)


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
