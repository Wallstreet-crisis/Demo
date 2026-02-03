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
    ContractDefaultedPayload,
    ContractSettledPayload,
    ContractSignedPayload,
    ContractRuleExecutedPayload
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.infra.sqlite.ledger import ContractTransfer, apply_contract_transfers, get_snapshot
from ifrontier.services.contract_rules import eval_condition, parse_transfers, should_run


class ContractService:

    @staticmethod
    def _apply_default_partial_fill(
        *,
        transfers: List[ContractTransfer],
        default_policy: Dict[str, Any] | None,
    ) -> tuple[List[ContractTransfer], float, Dict[str, Any]]:
        if not transfers:
            raise ValueError("transfers must be non-empty")

        dp = default_policy if isinstance(default_policy, dict) else {}
        params = dp.get("params") if isinstance(dp.get("params"), dict) else {}
        min_fill_ratio = float(params.get("min_fill_ratio") or 0.0)

        required_by_key: Dict[tuple[str, str, str], float] = {}
        required_by_from: Dict[str, Dict[str, float]] = {}
        for t in transfers:
            key = (t.from_account_id, t.asset_type, t.symbol)
            required_by_key[key] = float(required_by_key.get(key) or 0.0) + float(t.quantity)
            from_map = required_by_from.get(t.from_account_id)
            if from_map is None:
                from_map = {}
                required_by_from[t.from_account_id] = from_map
            k2 = f"{t.asset_type}:{t.symbol}"
            from_map[k2] = float(from_map.get(k2) or 0.0) + float(t.quantity)

        ratios: List[float] = []
        for (from_id, asset_type, symbol), req in required_by_key.items():
            if req <= 0:
                continue
            snap = get_snapshot(from_id)
            if asset_type == "CASH":
                avail = float(snap.cash)
            else:
                avail = float(snap.positions.get(symbol, 0.0))
            ratios.append(avail / float(req))

        if not ratios:
            global_ratio = 1.0
        else:
            global_ratio = min(1.0, float(min(ratios)))

        if global_ratio < min_fill_ratio:
            global_ratio = 0.0

        scaled: List[ContractTransfer] = []
        for t in transfers:
            q = float(t.quantity) * float(global_ratio)
            if q <= 1e-9:
                continue
            scaled.append(
                ContractTransfer(
                    from_account_id=t.from_account_id,
                    to_account_id=t.to_account_id,
                    asset_type=t.asset_type,
                    symbol=t.symbol,
                    quantity=float(q),
                )
            )

        shortfall_by_from: Dict[str, Any] = {}
        for from_id, items in required_by_from.items():
            for k2, req in items.items():
                exec_q = float(req) * float(global_ratio)
                short = float(req) - float(exec_q)
                if short <= 1e-9:
                    continue
                m = shortfall_by_from.get(from_id)
                if m is None:
                    m = {}
                    shortfall_by_from[from_id] = m
                m[k2] = float(short)

        return scaled, float(global_ratio), shortfall_by_from

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

    def create_contracts_batch(
        self,
        *,
        actor_id: str,
        contracts: List[Dict[str, Any]],
    ) -> List[str]:
        now = datetime.now(timezone.utc)

        specs: List[Dict[str, Any]] = []
        for c in contracts:
            contract_id = str(uuid4())
            kind = str(c["kind"])
            title = str(c["title"])
            terms = dict(c.get("terms") or {})
            parties = list(c.get("parties") or [])
            required_signers = list(c.get("required_signers") or [])
            participation_mode = (c.get("participation_mode") or ParticipationMode.ALL_SIGNERS.value).upper()
            invited_parties = list(c.get("invited_parties") or [])

            has_rules = isinstance(terms.get("rules"), list) and len(terms.get("rules")) > 0

            specs.append(
                {
                    "contract_id": contract_id,
                    "kind": kind,
                    "title": title,
                    "terms": terms,
                    "terms_json": json.dumps(terms, ensure_ascii=False),
                    "status": ContractStatus.DRAFT.value,
                    "has_rules": bool(has_rules),
                    "parties": parties,
                    "required_signers": required_signers,
                    "signatures": [],
                    "participation_mode": participation_mode,
                    "invited_parties": invited_parties,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )

        with self._driver.session() as session:
            session.execute_write(
                self._create_contracts_batch_tx,
                {"contracts": specs},
            )

        for spec in specs:
            payload = ContractCreatedPayload(
                contract_id=spec["contract_id"],
                kind=spec["kind"],
                title=spec["title"],
                terms=spec["terms"],
                parties=spec["parties"],
                required_signers=spec["required_signers"],
                created_at=now,
            )
            env = EventEnvelope(
                event_type=EventType.CONTRACT_CREATED,
                correlation_id=uuid4(),
                actor=EventActor(user_id=actor_id),
                payload=payload,
            )
            self._event_store.append(EventEnvelopeJson.from_envelope(env))

        return [spec["contract_id"] for spec in specs]

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
        if status == ContractStatus.SETTLED.value:
            return
        if status == ContractStatus.DEFAULTED.value:
            raise ValueError("contract defaulted")
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

        transfers = parse_transfers(transfers_raw)

        default_policy = terms.get("default_policy") if isinstance(terms, dict) else None
        scaled, fill_ratio, shortfall_by_from = self._apply_default_partial_fill(
            transfers=transfers,
            default_policy=default_policy if isinstance(default_policy, dict) else None,
        )

        settlement_event_id = str(uuid4())
        if scaled:
            apply_contract_transfers(transfers=scaled, event_id=settlement_event_id)

        new_status = ContractStatus.SETTLED.value if fill_ratio >= 1.0 - 1e-9 else ContractStatus.DEFAULTED.value
        with self._driver.session() as session:
            session.execute_write(
                self._set_contract_status_tx,
                {"contract_id": contract_id, "status": new_status, "updated_at": now.isoformat()},
            )

        if new_status == ContractStatus.DEFAULTED.value:
            payload = ContractDefaultedPayload(
                contract_id=contract_id,
                settlement_event_id=settlement_event_id,
                fill_ratio=float(fill_ratio),
                shortfall_by_from=shortfall_by_from,
                defaulted_at=now,
            )
            env = EventEnvelope(
                event_type=EventType.CONTRACT_DEFAULTED,
                correlation_id=uuid4(),
                actor=EventActor(user_id=actor_id),
                payload=payload,
            )
            self._event_store.append(EventEnvelopeJson.from_envelope(env))

        payload = ContractSettledPayload(contract_id=contract_id, settlement_event_id=settlement_event_id, settled_at=now)
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
        if status == ContractStatus.SETTLED.value:
            return
        if status == ContractStatus.DEFAULTED.value:
            raise ValueError("contract defaulted")
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
        defaulted = False
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
            default_policy = terms.get("default_policy") if isinstance(terms, dict) else None
            scaled, fill_ratio, shortfall_by_from = self._apply_default_partial_fill(
                transfers=transfers,
                default_policy=default_policy if isinstance(default_policy, dict) else None,
            )

            settlement_event_id = str(uuid4())
            if scaled:
                apply_contract_transfers(transfers=scaled, event_id=settlement_event_id)

            if fill_ratio < 1.0 - 1e-9:
                defaulted = True

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

            if defaulted:
                payload = ContractDefaultedPayload(
                    contract_id=contract_id,
                    settlement_event_id=settlement_event_id,
                    fill_ratio=float(fill_ratio),
                    shortfall_by_from=shortfall_by_from,
                    defaulted_at=now,
                )
                env = EventEnvelope(
                    event_type=EventType.CONTRACT_DEFAULTED,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id=actor_id),
                    payload=payload,
                )
                self._event_store.append(EventEnvelopeJson.from_envelope(env))
                break

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

        if defaulted:
            with self._driver.session() as session:
                session.execute_write(
                    self._set_contract_status_tx,
                    {"contract_id": contract_id, "status": ContractStatus.DEFAULTED.value, "updated_at": now.isoformat()},
                )
            return

        all_exhausted = True
        for rule in rules_raw:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("rule_id") or "")
            if not rule_id:
                all_exhausted = False
                break

            schedule = rule.get("schedule") or {"type": "once"}
            if not isinstance(schedule, dict):
                all_exhausted = False
                break

            st = rule_state.get(rule_id) or {}
            if not isinstance(st, dict):
                all_exhausted = False
                break

            stype = str(schedule.get("type") or "once")
            runs_now = int(st.get("runs") or 0)
            if stype == "once":
                if runs_now < 1:
                    all_exhausted = False
                    break
            elif stype == "interval":
                max_runs = schedule.get("max_runs")
                if max_runs is None:
                    all_exhausted = False
                    break
                if runs_now < int(max_runs):
                    all_exhausted = False
                    break
            else:
                all_exhausted = False
                break

        if all_exhausted:
            with self._driver.session() as session:
                session.execute_write(
                    self._set_contract_status_tx,
                    {"contract_id": contract_id, "status": ContractStatus.SETTLED.value, "updated_at": now.isoformat()},
                )

    @staticmethod
    def _set_contract_status_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            MATCH (c:Contract {contract_id: $contract_id})
            SET c.status = $status,
                c.updated_at = $updated_at
            """,
            **params,
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
    def _create_contracts_batch_tx(tx, params: Dict[str, Any]) -> None:
        tx.run(
            """
            UNWIND $contracts AS c
            MERGE (ct:Contract {contract_id: c.contract_id})
            SET ct.kind = c.kind,
                ct.title = c.title,
                ct.terms_json = c.terms_json,
                ct.status = c.status,
                ct.has_rules = c.has_rules,
                ct.parties = c.parties,
                ct.required_signers = c.required_signers,
                ct.signatures = c.signatures,
                ct.participation_mode = c.participation_mode,
                ct.invited_parties = c.invited_parties,
                ct.created_at = c.created_at,
                ct.updated_at = c.updated_at
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