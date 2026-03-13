from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ifrontier.infra.sqlite.db import get_connection


@dataclass
class ContractRecord:
    contract_id: str
    kind: str
    title: str
    terms_json: str
    status: str
    created_at: str
    updated_at: str
    parties_json: str
    required_signers_json: str
    participation_mode: str
    has_rules: bool
    rule_state_json: str
    signed_parties_json: str
    invited_parties_json: str
    signed_at: Optional[str]
    signed_by: Optional[str]
    creator_id: Optional[str]
    invited_by: Optional[str]
    invited_at: Optional[str]
    status_changed_at: Optional[str]
    
    # Helper properties to deserialize JSON fields
    @property
    def parties(self) -> List[str]:
        try:
            return json.loads(self.parties_json) if self.parties_json else []
        except json.JSONDecodeError:
            return []

    @property
    def required_signers(self) -> List[str]:
        try:
            return json.loads(self.required_signers_json) if self.required_signers_json else []
        except json.JSONDecodeError:
            return []

    @property
    def invited_parties(self) -> List[str]:
        try:
            return json.loads(self.invited_parties_json) if self.invited_parties_json else []
        except json.JSONDecodeError:
            return []

    @property
    def signed_parties(self) -> List[str]:
        try:
            return json.loads(self.signed_parties_json) if self.signed_parties_json else []
        except json.JSONDecodeError:
            return []

    @property
    def rule_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.rule_state_json) if self.rule_state_json else {}
        except json.JSONDecodeError:
            return {}


@dataclass
class ProposalRecord:
    proposal_id: str
    contract_id: str
    proposal_type: str
    proposer: str
    details_json: str
    approvals_json: str
    created_at: str
    
    @property
    def details(self) -> Dict[str, Any]:
        try:
            return json.loads(self.details_json) if self.details_json else {}
        except json.JSONDecodeError:
            return {}
            
    @property
    def approvals(self) -> List[str]:
        try:
            return json.loads(self.approvals_json) if self.approvals_json else []
        except json.JSONDecodeError:
            return []


def init_contracts_schema() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS contracts (
            contract_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            terms_json TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            parties_json TEXT,
            required_signers_json TEXT,
            participation_mode TEXT,
            has_rules INTEGER NOT NULL DEFAULT 0,
            rule_state_json TEXT,
            signed_parties_json TEXT,
            invited_parties_json TEXT,
            signed_at TEXT,
            signed_by TEXT,
            creator_id TEXT,
            invited_by TEXT,
            invited_at TEXT,
            status_changed_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
        CREATE INDEX IF NOT EXISTS idx_contracts_parties ON contracts(parties_json);

        CREATE TABLE IF NOT EXISTS proposals (
            proposal_id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            proposal_type TEXT NOT NULL,
            proposer TEXT NOT NULL,
            details_json TEXT,
            approvals_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(contract_id) REFERENCES contracts(contract_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_proposals_contract ON proposals(contract_id);
        """
    )

    conn.commit()


def create_contract(
    contract_id: str,
    kind: str,
    title: str,
    terms: Dict[str, Any],
    parties: List[str],
    required_signers: List[str],
    invited_parties: List[str] = None,
    creator_id: str = None,
) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    
    terms_json = json.dumps(terms, ensure_ascii=False)
    parties_json = json.dumps(parties, ensure_ascii=False)
    required_signers_json = json.dumps(required_signers, ensure_ascii=False)
    invited_parties_json = json.dumps(invited_parties or [], ensure_ascii=False)
    
    with conn:
        conn.execute(
            """
            INSERT INTO contracts (
                contract_id, kind, title, terms_json, status, created_at, updated_at,
                parties_json, required_signers_json, participation_mode, has_rules,
                rule_state_json, signed_parties_json, invited_parties_json,
                creator_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contract_id, kind, title, terms_json, "DRAFT", now, now,
                parties_json, required_signers_json, "ALL_SIGNERS", 0,
                "{}", "[]", invited_parties_json,
                creator_id
            ),
        )


def get_contract(contract_id: str) -> Optional[ContractRecord]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)).fetchone()
    if row is None:
        return None

    return ContractRecord(
        contract_id=row["contract_id"],
        kind=row["kind"],
        title=row["title"],
        terms_json=row["terms_json"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        parties_json=row["parties_json"],
        required_signers_json=row["required_signers_json"],
        participation_mode=row["participation_mode"],
        has_rules=bool(row["has_rules"]),
        rule_state_json=row["rule_state_json"],
        signed_parties_json=row["signed_parties_json"],
        invited_parties_json=row["invited_parties_json"],
        signed_at=row["signed_at"],
        signed_by=row["signed_by"],
        creator_id=row["creator_id"],
        invited_by=row["invited_by"],
        invited_at=row["invited_at"],
        status_changed_at=row["status_changed_at"],
    )


def get_contract_as_dict(contract_id: str) -> Optional[Dict[str, Any]]:
    """获取合约详情（字典格式），用于调试端点"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def list_contracts_for_player(player_id: str, limit: int = 50) -> List[ContractRecord]:
    conn = get_connection()
    # Simple search in parties_json or invited_parties_json
    # For better performance, a separate join table is usually better, but this follows existing patterns here
    pattern = f'%"{player_id}"%'
    rows = conn.execute(
        """
        SELECT * FROM contracts
        WHERE parties_json LIKE ? OR invited_parties_json LIKE ? OR creator_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (pattern, pattern, player_id, limit),
    ).fetchall()

    return [
        ContractRecord(
            contract_id=r["contract_id"],
            kind=r["kind"],
            title=r["title"],
            terms_json=r["terms_json"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            parties_json=r["parties_json"],
            required_signers_json=r["required_signers_json"],
            participation_mode=r["participation_mode"],
            has_rules=bool(r["has_rules"]),
            rule_state_json=r["rule_state_json"],
            signed_parties_json=r["signed_parties_json"],
            invited_parties_json=r["invited_parties_json"],
            signed_at=r["signed_at"],
            signed_by=r["signed_by"],
            creator_id=r["creator_id"],
            invited_by=r["invited_by"],
            invited_at=r["invited_at"],
            status_changed_at=r["status_changed_at"],
        )
        for r in rows
    ]


def update_contract_status(contract_id: str, new_status: str) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            "UPDATE contracts SET status = ?, status_changed_at = ?, updated_at = ? WHERE contract_id = ?",
            (new_status, now, now, contract_id),
        )


def set_contract_has_rules(contract_id: str, has_rules: bool) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            "UPDATE contracts SET has_rules = ? WHERE contract_id = ?",
            (1 if has_rules else 0, contract_id),
        )


def save_contract_rule_state(contract_id: str, rule_state: Dict[str, Any]) -> None:
    conn = get_connection()
    rule_state_json = json.dumps(rule_state, ensure_ascii=False)
    with conn:
        conn.execute(
            "UPDATE contracts SET rule_state_json = ? WHERE contract_id = ?",
            (rule_state_json, contract_id),
        )


def save_contract_terms(contract_id: str, terms: Dict[str, Any]) -> None:
    conn = get_connection()
    terms_json = json.dumps(terms, ensure_ascii=False)
    with conn:
        conn.execute(
            "UPDATE contracts SET terms_json = ?, updated_at = ? WHERE contract_id = ?",
            (terms_json, datetime.now(timezone.utc).isoformat(), contract_id),
        )


def join_contract(contract_id: str, joiner: str) -> bool:
    conn = get_connection()
    contract = get_contract(contract_id)
    if contract is None:
        return False
    
    parties = contract.parties
    if joiner not in parties:
        parties.append(joiner)
        parties_json = json.dumps(parties, ensure_ascii=False)
        
        with conn:
            conn.execute(
                "UPDATE contracts SET parties_json = ? WHERE contract_id = ?",
                (parties_json, contract_id),
            )
    return True


def sign_contract(contract_id: str, signer: str) -> bool:
    conn = get_connection()
    contract = get_contract(contract_id)
    if contract is None:
        return False
        
    signed_parties = contract.signed_parties
    if signer not in signed_parties:
        signed_parties.append(signer)
        signed_parties_json = json.dumps(signed_parties, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        
        with conn:
            conn.execute(
                "UPDATE contracts SET signed_parties_json = ?, signed_at = ?, signed_by = ?, updated_at = ? WHERE contract_id = ?",
                (signed_parties_json, now, signer, now, contract_id),
            )
    return True


def invite_to_contract(contract_id: str, invitee: str) -> bool:
    conn = get_connection()
    contract = get_contract(contract_id)
    if contract is None:
        return False
        
    invited = contract.invited_parties
    if invitee not in invited:
        invited.append(invitee)
        invited_parties_json = json.dumps(invited, ensure_ascii=False)
        
        with conn:
            conn.execute(
                "UPDATE contracts SET invited_parties_json = ?, invited_at = ? WHERE contract_id = ?",
                (invited_parties_json, datetime.now(timezone.utc).isoformat(), contract_id),
            )
    return True


def list_pending_contracts(limit: int = 50) -> List[ContractRecord]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM contracts 
        WHERE status IN ('DRAFT', 'SIGNED', 'ACTIVE')
        ORDER BY created_at DESC 
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [
        ContractRecord(
            contract_id=r["contract_id"],
            kind=r["kind"],
            title=r["title"],
            terms_json=r["terms_json"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            parties_json=r["parties_json"],
            required_signers_json=r["required_signers_json"],
            participation_mode=r["participation_mode"],
            has_rules=bool(r["has_rules"]),
            rule_state_json=r["rule_state_json"],
            signed_parties_json=r["signed_parties_json"],
            invited_parties_json=r["invited_parties_json"],
            signed_at=r["signed_at"],
            signed_by=r["signed_by"],
            creator_id=r["creator_id"],
            invited_by=r["invited_by"],
            invited_at=r["invited_at"],
            status_changed_at=r["status_changed_at"],
        )
        for r in rows
    ]


def list_contracts_with_rules(limit: int = 50) -> List[ContractRecord]:
    """获取所有处于 ACTIVE 状态且有规则的合约，用于规则引擎调度"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM contracts 
        WHERE status = 'ACTIVE' AND has_rules = 1
        ORDER BY updated_at DESC 
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [
        ContractRecord(
            contract_id=r["contract_id"],
            kind=r["kind"],
            title=r["title"],
            terms_json=r["terms_json"],
            status=r["status"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            parties_json=r["parties_json"],
            required_signers_json=r["required_signers_json"],
            participation_mode=r["participation_mode"],
            has_rules=bool(r["has_rules"]),
            rule_state_json=r["rule_state_json"],
            signed_parties_json=r["signed_parties_json"],
            invited_parties_json=r["invited_parties_json"],
            signed_at=r["signed_at"],
            signed_by=r["signed_by"],
            creator_id=r["creator_id"],
            invited_by=r["invited_by"],
            invited_at=r["invited_at"],
            status_changed_at=r["status_changed_at"],
        )
        for r in rows
    ]


# Proposal related functions - also imported in services/contracts.py

def create_proposal(
    proposal_id: str,
    contract_id: str,
    proposal_type: str,
    proposer: str,
    details: Dict[str, Any],
) -> None:
    conn = get_connection()
    details_json = json.dumps(details, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO proposals (proposal_id, contract_id, proposal_type, proposer, details_json, approvals_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (proposal_id, contract_id, proposal_type, proposer, details_json, "[]", now),
        )

def get_proposal(proposal_id: str) -> Optional[ProposalRecord]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
    if row is None:
        return None

    return ProposalRecord(
        proposal_id=row["proposal_id"],
        contract_id=row["contract_id"],
        proposal_type=row["proposal_type"],
        proposer=row["proposer"],
        details_json=row["details_json"],
        approvals_json=row["approvals_json"],
        created_at=row["created_at"],
    )

def add_proposal_approval(proposal_id: str, approver: str) -> Optional[ProposalRecord]:
    conn = get_connection()
    proposal = get_proposal(proposal_id)
    if proposal is None:
        return None
    
    approvals = proposal.approvals
    if approver not in approvals:
        approvals.append(approver)
        approvals_json = json.dumps(approvals, ensure_ascii=False)
        
        with conn:
            conn.execute(
                "UPDATE proposals SET approvals_json = ? WHERE proposal_id = ?",
                (approvals_json, proposal_id),
            )
            
    return get_proposal(proposal_id)


def list_contracts_by_actor(
    actor_id: str | None = None,
    actor_id_plain: str | None = None,
    status: str | None = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """根据 actor_id 查询合约列表，用于 API 端点"""
    conn = get_connection()
    
    # 构建查询条件
    conditions = []
    params = []
    
    if actor_id is not None:
        conditions.append("(parties_json LIKE ? OR invited_parters_json LIKE ? OR creator_id = ?)")
        pattern = f'%"{actor_id}"%'
        params.extend([pattern, pattern, actor_id])
    
    if actor_id_plain is not None:
        conditions.append("(parties_json LIKE ? OR invited_parties_json LIKE ? OR creator_id = ?)")
        pattern = f'%"{actor_id_plain}"%'
        params.extend([pattern, pattern, actor_id_plain])
    
    where_clause = " OR ".join(conditions) if conditions else "1=1"
    
    if status is not None:
        where_clause += f" AND status = ?"
        params.append(status.upper())
    
    params.append(limit)
    
    rows = conn.execute(
        f"""
        SELECT contract_id, title, kind, status, created_at,
               parties_json, required_signers_json, signatures_json
        FROM contracts
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        params
    ).fetchall()
    
    result = []
    for r in rows:
        import json
        result.append({
            "contract_id": r["contract_id"],
            "title": r["title"],
            "kind": r["kind"],
            "status": r["status"],
            "created_at": r["created_at"],
            "parties": json.loads(r["parties_json"] or "[]"),
            "required_signers": json.loads(r["required_signers_json"] or "[]"),
            "signatures": json.loads(r["signatures_json"] or "[]"),
        })
    return result
