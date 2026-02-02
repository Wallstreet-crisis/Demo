from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from neo4j import Driver

from ifrontier.domain.contracts.models import ContractStatus, ParticipationMode
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    ContractActivatedPayload,
    ContractJoinedPayload,
    ContractCreatedPayload,
    ContractProposalApprovedPayload,
    ContractProposalCreatedPayload,
    ContractSettledPayload,
    ContractSignedPayload,
    ContractRuleExecutedPayload
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.infra.sqlite.ledger import ContractTransfer, apply_contract_transfers
from ifrontier.services.contract_rules import eval_condition, parse_transfers, should_run

class ContractService:

    def __init__(self, driver: Driver, event_store: Neo4jEventStore) -> None:
        self._driver = driver
        self._event_store = event_store

    def create_contract(
        self,
        *,
        kind: str,
        title: str,
        terms: Dict[str, Any],
        parties: List[str],
        required_signers: List[str],
        participation_mode: str | None = None,
        invited_parties: List[str] | None = None,
        actor_id: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        contract_id = str(uuid4())

        has_rules = isinstance(terms.get("rules"), list) and len(terms.get("rules")) > 0

        mode = (participation_mode or ParticipationMode.ALL_SIGNERS.value).upper()
        invited = invited_parties or []

        # Neo4j: 创建 Contract 节点
        with self._driver.session() as session:
            session.execute_write(
                self._create_contract_tx,
                {
                    "contract_id": contract_id,
                    "kind": kind,
                    "title": title,
                    "terms_json": json.dumps(terms, ensure_ascii=False),
                    "status": ContractStatus.DRAFT.value,
                    "has_rules": bool(has_rules),
                    "parties": parties,
                    "required_signers": required_signers,
                    "signatures": [],
                    "participation_mode": mode,
                    "invited_parties": invited,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                },
            )

        payload = ContractCreatedPayload(
            contract_id=contract_id,
            kind=kind,
            title=title,
            terms=terms,
            parties=parties,
            required_signers=required_signers,
            created_at=now,
        )
        env = EventEnvelope(
            event_type=EventType.CONTRACT_CREATED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))
        return contract_id

    def join_contract(self, *, contract_id: str, joiner: str) -> None:
        now = datetime.now(timezone.utc)

        with self._driver.session() as session:
            ok = session.execute_write(
                self._join_contract_tx,
                {"contract_id": contract_id, "joiner": joiner, "joined_at": now.isoformat()},
            )
        if not ok:
            raise ValueError("contract not found or not joinable")

        payload = ContractJoinedPayload(contract_id=contract_id, joiner=joiner, joined_at=now)
        env = EventEnvelope(
            event_type=EventType.CONTRACT_JOINED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=joiner),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def create_proposal(
        self,
        *,
        contract_id: str,
        proposal_type: str,
        proposer: str,
        details: Dict[str, Any],
    ) -> str:
        now = datetime.now(timezone.utc)
        proposal_id = str(uuid4())

        with self._driver.session() as session:
            ok = session.execute_write(
                self._create_proposal_tx,
                {
                    "contract_id": contract_id,
                    "proposal_id": proposal_id,
                    "proposal_type": proposal_type.upper(),
                    "proposer": proposer,
                    "details_json": json.dumps(details, ensure_ascii=False),
                    "created_at": now.isoformat(),
                },
            )
        if not ok:
            raise ValueError("contract not found")

        payload = ContractProposalCreatedPayload(
            contract_id=contract_id,
            proposal_id=proposal_id,
            proposal_type=proposal_type.upper(),
            proposer=proposer,
            details=details,
            created_at=now,
        )
        env = EventEnvelope(
            event_type=EventType.CONTRACT_PROPOSAL_CREATED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=proposer),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))
        return proposal_id

    def approve_proposal(
        self,
        *,
        contract_id: str,
        proposal_id: str,
        approver: str,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)

        with self._driver.session() as session:
            record = session.execute_write(
                self._approve_proposal_tx,
                {
                    "contract_id": contract_id,
                    "proposal_id": proposal_id,
                    "approver": approver,
                    "approved_at": now.isoformat(),
                },
            )

        if record is None:
            raise ValueError("proposal not found")

        payload = ContractProposalApprovedPayload(
            contract_id=contract_id,
            proposal_id=proposal_id,
            approver=approver,
            approved_at=now,
        )
        env = EventEnvelope(
            event_type=EventType.CONTRACT_PROPOSAL_APPROVED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=approver),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

        # record contains final status & applied flag
        return dict(record)

    def sign_contract(self, *, contract_id: str, signer: str) -> ContractStatus:
        now = datetime.now(timezone.utc)

        with self._driver.session() as session:
            record = session.execute_write(
                self._sign_contract_tx,
                {"contract_id": contract_id, "signer": signer, "signed_at": now.isoformat()},
            )

        if record is None:
            raise ValueError("contract not found or not signable")

        status = record["status"]

        payload = ContractSignedPayload(contract_id=contract_id, signer=signer, signed_at=now)
        env = EventEnvelope(
            event_type=EventType.CONTRACT_SIGNED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=signer),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))
        return ContractStatus(status)

    def activate_contract(self, *, contract_id: str, actor_id: str) -> None:
        now = datetime.now(timezone.utc)

        with self._driver.session() as session:
            ok = session.execute_write(
                self._activate_contract_tx,
                {"contract_id": contract_id, "activated_at": now.isoformat()},
            )
        if not ok:
            raise ValueError("contract not found or not signed")

        payload = ContractActivatedPayload(contract_id=contract_id, activated_at=now)
        env = EventEnvelope(
            event_type=EventType.CONTRACT_ACTIVATED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def settle_contract(self, *, contract_id: str, actor_id: str) -> None:
        now = datetime.now(timezone.utc)

        with self._driver.session() as session:
            record = session.execute_read(
                self._load_contract_for_settle_tx,
                {"contract_id": contract_id},
            )

        if record is None:
            raise ValueError("contract not found")

        status = str(record.get("status") or "")
        if status != ContractStatus.ACTIVE.value:
            raise ValueError("contract not active")

        terms_json = str(record.get("terms_json") or "{}")
        try:
            terms = json.loads(terms_json)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid contract terms") from exc

        transfers_raw = terms.get("transfers")
        if not isinstance(transfers_raw, list) or not transfers_raw:
            raise ValueError("contract transfers missing")

        transfers: List[ContractTransfer] = []
        for item in transfers_raw:
            if not isinstance(item, dict):
                raise ValueError("invalid transfer")
            transfers.append(
                ContractTransfer(
                    from_account_id=str(item.get("from")),
                    to_account_id=str(item.get("to")),
                    asset_type=str(item.get("asset_type")),
                    symbol=str(item.get("symbol")),
                    quantity=float(item.get("quantity")),
                )
            )

        settlement_event_id = str(uuid4())
        apply_contract_transfers(transfers=transfers, event_id=settlement_event_id)

        payload = ContractSettledPayload(
            contract_id=contract_id,
            settlement_event_id=settlement_event_id,
            settled_at=now,
        )
        env = EventEnvelope(
            event_type=EventType.CONTRACT_SETTLED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def run_rules(self, *, contract_id: str, actor_id: str) -> None:
        now = datetime.now(timezone.utc)

        with self._driver.session() as session:
            record = session.execute_read(
                self._load_contract_for_rules_tx,
                {"contract_id": contract_id},
            )

        if record is None:
            raise ValueError("contract not found")

        status = str(record.get("status") or "")
        if status != ContractStatus.ACTIVE.value:
            raise ValueError("contract not active")

        terms_json = str(record.get("terms_json") or "{}")
        try:
            terms = json.loads(terms_json)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid contract terms") from exc

        rules_raw = terms.get("rules")
        if rules_raw is None:
            raise ValueError("contract rules missing")
        if not isinstance(rules_raw, list):
            raise ValueError("contract rules invalid")

        rule_state_json = str(record.get("rule_state_json") or "{}")
        try:
            rule_state = json.loads(rule_state_json) if rule_state_json else {}
        except json.JSONDecodeError as exc:
            raise ValueError("invalid contract rule_state") from exc
        if not isinstance(rule_state, dict):
            raise ValueError("invalid contract rule_state")

        state_changed = False
        for rule in rules_raw:
            if not isinstance(rule, dict):
                raise ValueError("invalid rule")
            rule_id = str(rule.get("rule_id") or "")
            if not rule_id:
                raise ValueError("rule_id missing")

            schedule = rule.get("schedule") or {"type": "once"}
            if not isinstance(schedule, dict):
                raise ValueError("invalid schedule")

            st = rule_state.get(rule_id) or {}
            if not isinstance(st, dict):
                raise ValueError("invalid rule_state")

            if not should_run(schedule, st):
                payload = ContractRuleExecutedPayload(
                    contract_id=contract_id,
                    rule_id=rule_id,
                    evaluated=False,
                    executed=False,
                    reason="schedule blocked",
                    settlement_event_id=None,
                    executed_at=now,
                )
                env = EventEnvelope(
                    event_type=EventType.CONTRACT_RULE_EXECUTED,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id=actor_id),
                    payload=payload,
                )
                self._event_store.append(EventEnvelopeJson.from_envelope(env))
                continue

            condition = rule.get("condition", True)
            cond_ok = bool(eval_condition(condition))
            if not cond_ok:
                payload = ContractRuleExecutedPayload(
                    contract_id=contract_id,
                    rule_id=rule_id,
                    evaluated=True,
                    executed=False,
                    reason="condition false",
                    settlement_event_id=None,
                    executed_at=now,
                )
                env = EventEnvelope(
                    event_type=EventType.CONTRACT_RULE_EXECUTED,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id=actor_id),
                    payload=payload,
                )
                self._event_store.append(EventEnvelopeJson.from_envelope(env))
                continue

            actions = rule.get("actions") or {}
            if not isinstance(actions, dict):
                raise ValueError("invalid actions")

            transfers = parse_transfers(actions.get("transfers"))
            settlement_event_id = str(uuid4())
            apply_contract_transfers(transfers=transfers, event_id=settlement_event_id)

            runs = int(st.get("runs") or 0) + 1
            st["runs"] = runs
            st["last_run_at"] = now.isoformat()
            rule_state[rule_id] = st
            state_changed = True

            payload = ContractRuleExecutedPayload(
                contract_id=contract_id,
                rule_id=rule_id,
                evaluated=True,
                executed=True,
                reason=None,
                settlement_event_id=settlement_event_id,
                executed_at=now,
            )
            env = EventEnvelope(
                event_type=EventType.CONTRACT_RULE_EXECUTED,
                correlation_id=uuid4(),
                actor=EventActor(user_id=actor_id),
                payload=payload,
            )
            self._event_store.append(EventEnvelopeJson.from_envelope(env))

        if state_changed:
            with self._driver.session() as session:
                session.execute_write(
                    self._save_contract_rule_state_tx,
                    {
                        "contract_id": contract_id,
                        "rule_state_json": json.dumps(rule_state, ensure_ascii=False),
                        "updated_at": now.isoformat(),
                    },
                )

    @staticmethod
    def _create_contract_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (c:Contract {contract_id: $contract_id})
            SET c.kind = $kind,
                c.title = $title,
                c.terms_json = $terms_json,
                c.status = $status,
                c.has_rules = $has_rules,
                c.parties = $parties,
                c.required_signers = $required_signers,
                c.signatures = $signatures,
                c.participation_mode = $participation_mode,
                c.invited_parties = $invited_parties,
                c.created_at = $created_at,
                c.updated_at = $updated_at
            """,
            **params,
        )

    @staticmethod
    def _join_contract_tx(tx, params: Dict[str, Any]) -> bool:
        record = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            WHERE c.participation_mode = 'OPT_IN'
            WITH c,
                 CASE WHEN c.invited_parties IS NULL THEN [] ELSE c.invited_parties END AS invited,
                 CASE WHEN c.parties IS NULL THEN [] ELSE c.parties END AS parties
            WHERE $joiner IN invited
            WITH c, parties,
                 CASE WHEN $joiner IN parties THEN parties ELSE parties + $joiner END AS new_parties
            SET c.parties = new_parties,
                c.updated_at = $joined_at
            RETURN c.contract_id AS contract_id
            """,
            **params,
        ).single()
        return record is not None

    @staticmethod
    def _create_proposal_tx(tx, params: Dict[str, Any]) -> bool:
        record = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            CREATE (p:ContractProposal {proposal_id: $proposal_id})
            SET p.contract_id = $contract_id,
                p.proposal_type = $proposal_type,
                p.proposer = $proposer,
                p.details_json = $details_json,
                p.approvals = [],
                p.created_at = $created_at
            MERGE (c)-[:HAS_PROPOSAL]->(p)
            RETURN p.proposal_id AS proposal_id
            """,
            **params,
        ).single()
        return record is not None

    @staticmethod
    def _approve_proposal_tx(tx, params: Dict[str, Any]):
        # 当 contract.parties 全员批准时，自动应用提案
        record = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})-[:HAS_PROPOSAL]->(p:ContractProposal {proposal_id: $proposal_id})
            WITH c, p,
                 CASE WHEN p.approvals IS NULL THEN [] ELSE p.approvals END AS approvals,
                 CASE WHEN c.parties IS NULL THEN [] ELSE c.parties END AS parties
            WITH c, p, parties,
                 CASE WHEN $approver IN approvals THEN approvals ELSE approvals + $approver END AS new_approvals
            WITH c, p, parties, new_approvals,
                 ALL(x IN parties WHERE x IN new_approvals) AS all_approved
            SET p.approvals = new_approvals

            SET c.status = CASE
                WHEN all_approved AND p.proposal_type = 'SUSPEND' THEN 'SUSPENDED'
                WHEN all_approved AND p.proposal_type = 'TERMINATE' THEN 'TERMINATED'
                WHEN all_approved AND p.proposal_type = 'FAIL' THEN 'FAILED'
                ELSE c.status
            END,
            c.terms_json = CASE
                WHEN all_approved AND p.proposal_type = 'AMEND' THEN p.details_json
                ELSE c.terms_json
            END,
            c.updated_at = CASE WHEN all_approved THEN $approved_at ELSE c.updated_at END

            RETURN all_approved AS applied, c.status AS contract_status, p.proposal_type AS proposal_type
            """,
            **params,
        ).single()
        return record

    @staticmethod
    def _sign_contract_tx(tx, params: Dict[str, Any]):
        # 规则：只允许 DRAFT/SIGNED 签署；签署集合去重；若 required_signers 全部签完则置 SIGNED
        result = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            WITH c,
                 CASE WHEN c.signatures IS NULL THEN [] ELSE c.signatures END AS sigs,
                 CASE WHEN c.required_signers IS NULL THEN [] ELSE c.required_signers END AS reqs
            WHERE c.status IN ['DRAFT','SIGNED']
            WITH c,
                 CASE WHEN $signer IN sigs THEN sigs ELSE sigs + $signer END AS new_sigs,
                 reqs
            WITH c, new_sigs, reqs,
                 ALL(x IN reqs WHERE x IN new_sigs) AS all_signed
            SET c.signatures = new_sigs,
                c.status = CASE WHEN all_signed THEN 'SIGNED' ELSE c.status END,
                c.updated_at = $signed_at
            RETURN c.status AS status
            """,
            **params,
        )
        return result.single()

    @staticmethod
    def _activate_contract_tx(tx, params: Dict[str, Any]) -> bool:
        record = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            WHERE c.status = 'SIGNED'
            SET c.status = 'ACTIVE',
                c.updated_at = $activated_at,
                c.activated_at = $activated_at
            RETURN c.contract_id AS contract_id
            """,
            **params,
        ).single()
        return record is not None

    @staticmethod
    def _load_contract_for_rules_tx(tx, params):
        rec = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            RETURN c.status AS status,
                   c.terms_json AS terms_json,
                   c.rule_state_json AS rule_state_json
            """,
            **params,
        ).single()
        return dict(rec) if rec else None

    @staticmethod
    def _load_contract_for_settle_tx(tx, params: Dict[str, Any]):
        result = tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            RETURN c.status AS status, c.terms_json AS terms_json
            """,
            **params,
        )
        rec = result.single()
        return dict(rec) if rec is not None else None

    @staticmethod
    def _save_contract_rule_state_tx(tx, params) -> None:
        tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            SET c.rule_state_json = $rule_state_json,
                c.updated_at = $updated_at
            """,
            **params,
        )