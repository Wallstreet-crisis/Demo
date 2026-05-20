from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

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
    ContractRuleExecutedPayload,
    ContractInvitedPayload,
    ContractTerminatedPayload
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.contracts import (
    ContractRecord,
    create_contract as sqlite_create_contract,
    get_contract as sqlite_get_contract,
    list_contracts_for_player as sqlite_list_contracts_for_player,
    update_contract_status as sqlite_update_contract_status,
    set_contract_has_rules as sqlite_set_contract_has_rules,
    save_contract_rule_state as sqlite_save_contract_rule_state,
    save_contract_terms as sqlite_save_contract_terms,
    join_contract as sqlite_join_contract,
    sign_contract as sqlite_sign_contract,
    create_proposal as sqlite_create_proposal,
    get_proposal as sqlite_get_proposal,
    add_proposal_approval as sqlite_add_proposal_approval,
)
from ifrontier.infra.sqlite.event_store import SqliteEventStore
from ifrontier.infra.sqlite.ledger import ContractTransfer, apply_contract_transfers, get_snapshot
from ifrontier.core.logger import get_logger
from ifrontier.services.victory import VictoryService
from ifrontier.services.contract_rules import eval_condition, parse_transfers, should_run


_log = get_logger(__name__)


class ContractService:
    _VALID_TRIGGER_SCOPES = {"ANY_PARTY", "ANY_SIGNER", "CREATOR_ONLY", "SYSTEM_ONLY"}
    _VALID_TRIGGER_EXECUTION_MODES = {"MANUAL", "SCHEDULED", "MANUAL_OR_SCHEDULED"}
    _TRIGGER_ACTIONS = ("activate", "settle", "run_rules")
    _SYSTEM_ACTORS = {"system", "system:tick"}

    def __init__(self, event_store: SqliteEventStore) -> None:
        self._event_store = event_store
        self._victory_service = VictoryService()

    def _get_victory_service(self) -> VictoryService:
        victory_service = getattr(self, "_victory_service", None)
        if victory_service is None:
            victory_service = VictoryService()
            self._victory_service = victory_service
        return victory_service

    @staticmethod
    def _normalize_account_id(value: str) -> str:
        return str(value or "").strip().lower()

    def _refresh_settlement_for_accounts(self, account_ids: List[str]) -> None:
        """合同资产变动后，立即刷新相关账户的状态与总估值。

        这里不主动广播事件，避免资产高频波动导致消息风暴；广播仍由
        VictoryScheduler 在检测到状态变化时统一处理。
        """
        seen = set()
        for acc_id in account_ids:
            nid = self._normalize_account_id(acc_id)
            if not nid or nid in seen:
                continue
            seen.add(nid)
            try:
                self._get_victory_service().update_player_settlement(nid)
            except Exception as exc:
                # 合同已成功落账，不因单个结算刷新失败阻断主流程；
                # 但必须记录下来，避免状态刷新问题被静默吞掉而难以排查。
                _log.exception("Failed to refresh settlement for account %s after contract mutation: %s", nid, exc)

    @classmethod
    def _default_trigger_policy(cls, *, kind: str, has_rules: bool) -> Dict[str, Dict[str, str]]:
        kind_u = str(kind or "").upper()
        return {
            "activate": {"actor_scope": "CREATOR_ONLY" if kind_u == "CALL" else "ANY_PARTY"},
            "settle": {"actor_scope": "ANY_PARTY"},
            "run_rules": {
                "actor_scope": "ANY_PARTY",
                "execution_mode": "MANUAL_OR_SCHEDULED" if has_rules else "MANUAL",
            },
        }

    @classmethod
    def _normalize_trigger_policy(
        cls,
        *,
        kind: str,
        has_rules: bool,
        trigger_policy: Any | None,
    ) -> Dict[str, Dict[str, str]]:
        policy = cls._default_trigger_policy(kind=kind, has_rules=has_rules)
        if trigger_policy is None:
            return policy

        if isinstance(trigger_policy, str):
            scope = str(trigger_policy or "").upper()
            if scope in cls._VALID_TRIGGER_SCOPES:
                for action in cls._TRIGGER_ACTIONS:
                    policy[action]["actor_scope"] = scope
                if scope == "SYSTEM_ONLY":
                    policy["run_rules"]["execution_mode"] = "SCHEDULED"
                elif scope:
                    policy["run_rules"]["execution_mode"] = "MANUAL"
            return policy

        if not isinstance(trigger_policy, dict):
            return policy

        for action in cls._TRIGGER_ACTIONS:
            raw_action = trigger_policy.get(action)
            if isinstance(raw_action, str):
                scope = str(raw_action or "").upper()
                if scope in cls._VALID_TRIGGER_SCOPES:
                    policy[action]["actor_scope"] = scope
            elif isinstance(raw_action, dict):
                scope = str(raw_action.get("actor_scope") or raw_action.get("scope") or "").upper()
                if action == "run_rules":
                    mode = str(raw_action.get("execution_mode") or raw_action.get("mode") or "").upper()
                    if mode in cls._VALID_TRIGGER_EXECUTION_MODES:
                        policy[action]["execution_mode"] = mode
                    elif scope == "SYSTEM_ONLY":
                        policy[action]["execution_mode"] = "SCHEDULED"
                    elif scope:
                        policy[action]["execution_mode"] = "MANUAL"
                if scope in cls._VALID_TRIGGER_SCOPES:
                    policy[action]["actor_scope"] = scope

        return policy

    @classmethod
    def _normalize_trigger_policy_from_record(cls, contract: ContractRecord) -> Dict[str, Dict[str, str]]:
        raw = contract.trigger_policy
        if raw:
            return cls._normalize_trigger_policy(kind=contract.kind, has_rules=contract.has_rules, trigger_policy=raw)
        return cls._default_trigger_policy(kind=contract.kind, has_rules=contract.has_rules)

    def _actor_matches_scope(self, *, actor_id: str, contract: ContractRecord, scope: str) -> bool:
        actor_norm = self._normalize_account_id(actor_id)
        creator_norm = self._normalize_account_id(contract.creator_id or "")

        if scope == "SYSTEM_ONLY":
            return actor_norm in self._SYSTEM_ACTORS or actor_norm.startswith("system:")

        if scope == "CREATOR_ONLY":
            return bool(actor_norm) and bool(creator_norm) and actor_norm == creator_norm

        if scope == "ANY_SIGNER":
            signed = {self._normalize_account_id(x) for x in (contract.signed_parties or [])}
            required = {self._normalize_account_id(x) for x in (contract.required_signers or [])}
            return bool(actor_norm) and (actor_norm in signed or actor_norm in required or actor_norm == creator_norm)

        # ANY_PARTY
        parties = {self._normalize_account_id(x) for x in (contract.parties or [])}
        invited = {self._normalize_account_id(x) for x in (contract.invited_parties or [])}
        required = {self._normalize_account_id(x) for x in (contract.required_signers or [])}
        return bool(actor_norm) and (actor_norm in parties or actor_norm in invited or actor_norm in required or actor_norm == creator_norm)

    def _is_system_actor(self, actor_id: str) -> bool:
        actor_norm = self._normalize_account_id(actor_id)
        return actor_norm in self._SYSTEM_ACTORS or actor_norm.startswith("system:")

    def _assert_trigger_authorized(self, contract: ContractRecord, *, actor_id: str, action: str) -> None:
        policy = self._normalize_trigger_policy_from_record(contract)
        action_key = str(action or "").strip().lower()
        if action_key not in self._TRIGGER_ACTIONS:
            raise ValueError("unsupported trigger action")

        action_policy = policy.get(action_key, {}) if isinstance(policy, dict) else {}
        scope = str(action_policy.get("actor_scope") or "ANY_PARTY").upper()
        if scope not in self._VALID_TRIGGER_SCOPES:
            scope = "ANY_PARTY"

        if action_key == "run_rules":
            execution_mode = str(action_policy.get("execution_mode") or "MANUAL_OR_SCHEDULED").upper()
            if execution_mode not in self._VALID_TRIGGER_EXECUTION_MODES:
                execution_mode = "MANUAL_OR_SCHEDULED"

            if self._is_system_actor(actor_id):
                if execution_mode in {"SCHEDULED", "MANUAL_OR_SCHEDULED"}:
                    return
                raise ValueError("this contract is not scheduled for automatic execution")

            if execution_mode == "SCHEDULED":
                raise ValueError("this contract is scheduled-only")

        if not self._actor_matches_scope(actor_id=actor_id, contract=contract, scope=scope):
            if scope == "SYSTEM_ONLY":
                raise ValueError("this action is reserved for the scheduler")
            if scope == "CREATOR_ONLY":
                raise ValueError("only contract creator can trigger this action")
            if scope == "ANY_SIGNER":
                raise ValueError("only a required signer can trigger this action")
            raise ValueError("you are not allowed to trigger this action")

    @staticmethod
    def _normalize_var_in_expr(v: Any, *, contract_id: str) -> Any:
        if not isinstance(v, str):
            return v
        vv = str(v)
        if vv == "contract.status" or (vv.startswith("contract.status") and ":" not in vv):
            return f"contract.status:{contract_id}"
        if vv.startswith("contract.runs:"):
            parts = vv.split(":")
            if len(parts) == 2 and parts[1]:
                return f"contract.runs:{contract_id}:{parts[1]}"
        return vv

    @classmethod
    def _normalize_condition_expr(cls, expr: Any, *, contract_id: str) -> Any:
        if isinstance(expr, list):
            return [cls._normalize_condition_expr(x, contract_id=contract_id) for x in expr]

        if not isinstance(expr, dict):
            return expr

        if "var" in expr:
            out = dict(expr)
            out["var"] = cls._normalize_var_in_expr(out.get("var"), contract_id=contract_id)
            return out

        if "op" in expr:
            op = str(expr.get("op") or "")
            if op in {"and", "or"}:
                args = cls._normalize_condition_expr(expr.get("args"), contract_id=contract_id)
                return {"op": op, "args": args}
            if op == "not":
                arg = cls._normalize_condition_expr(expr.get("arg"), contract_id=contract_id)
                return {"op": "not", "arg": arg}
            if op in {"==", "!=", ">", ">=", "<", "<="}:
                left = cls._normalize_condition_expr(expr.get("left"), contract_id=contract_id)
                right = cls._normalize_condition_expr(expr.get("right"), contract_id=contract_id)
                if op in {"==", "!="}:
                    if isinstance(left, dict) and str(left.get("var") or "").startswith("contract.status:") and right == "SIGNED":
                        right = "ACTIVE"
                    if isinstance(right, dict) and str(right.get("var") or "").startswith("contract.status:") and left == "SIGNED":
                        left = "ACTIVE"
                return {"op": op, "left": left, "right": right}
            return dict(expr)

        if len(expr) == 1:
            k = next(iter(expr.keys()))
            v = expr.get(k)
            if k in {"and", "or"} and isinstance(v, list):
                return {"op": k, "args": [cls._normalize_condition_expr(x, contract_id=contract_id) for x in v]}
            if k == "not":
                return {"op": "not", "arg": cls._normalize_condition_expr(v, contract_id=contract_id)}
            if k in {"==", "!=", ">", ">=", "<", "<="} and isinstance(v, list) and len(v) == 2:
                left = cls._normalize_condition_expr(v[0], contract_id=contract_id)
                right = cls._normalize_condition_expr(v[1], contract_id=contract_id)
                if k in {"==", "!="}:
                    if isinstance(left, dict) and str(left.get("var") or "").startswith("contract.status:") and right == "SIGNED":
                        right = "ACTIVE"
                    if isinstance(right, dict) and str(right.get("var") or "").startswith("contract.status:") and left == "SIGNED":
                        left = "ACTIVE"
                return {"op": k, "left": left, "right": right}

        return {kk: cls._normalize_condition_expr(vv, contract_id=contract_id) for kk, vv in expr.items()}

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

    def __init__(self, event_store: SqliteEventStore) -> None:
        self._event_store = event_store

    def list_contracts(self, *, player_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """列出与特定玩家相关的合约：参与的、受邀的、作为签署者的。"""
        pid = str(player_id).lower()
        records = sqlite_list_contracts_for_player(pid, limit=int(limit))

        out = []
        for r in records:
            d = {
                "contract_id": r.contract_id,
                "kind": r.kind,
                "title": r.title,
                "terms_json": r.terms_json,
                "status": r.status,
                "parties": r.parties,
                "required_signers": r.required_signers,
                "signatures": r.signed_parties,  # 正确返回已签署者
                "participation_mode": r.participation_mode or "ALL_SIGNERS",
                "invited_parties": r.invited_parties,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            try:
                d["terms"] = json.loads(d.get("terms_json") or "{}")
            except Exception:
                d["terms"] = {}
            out.append(d)
        return out

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
        trigger_policy: Any | None = None,
        actor_id: str,
    ) -> str:
        now = datetime.now(timezone.utc)
        contract_id = str(uuid4())

        rules_raw = terms.get("rules") if isinstance(terms, dict) else None
        has_rules = isinstance(rules_raw, list) and any(isinstance(x, dict) for x in rules_raw)

        mode = (participation_mode or ParticipationMode.ALL_SIGNERS.value).upper()
        normalized_trigger_policy = self._normalize_trigger_policy(
            kind=kind,
            has_rules=has_rules,
            trigger_policy=trigger_policy,
        )

        # ID 归一化
        parties = [str(p).lower() for p in (parties or [])]
        required_signers = [str(s).lower() for s in (required_signers or [])]
        invited = [str(i).lower() for i in (invited_parties or [])]
        aid = str(actor_id).lower()

        sqlite_create_contract(
            contract_id=contract_id,
            kind=kind,
            title=title,
            terms=terms,
            parties=parties,
            required_signers=required_signers,
            invited_parties=invited,
            creator_id=aid,  # 正确记录创建者
            participation_mode=mode,
            has_rules=has_rules,
            trigger_policy=normalized_trigger_policy,
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
        env = EventEnvelope[ContractCreatedPayload](
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
            parties = [str(p).lower() for p in list(c.get("parties") or [])]
            required_signers = [str(s).lower() for s in list(c.get("required_signers") or [])]
            participation_mode = (c.get("participation_mode") or ParticipationMode.ALL_SIGNERS.value).upper()
            invited_parties = [str(i).lower() for i in list(c.get("invited_parties") or [])]

            rules_raw = terms.get("rules") if isinstance(terms, dict) else None
            has_rules = isinstance(rules_raw, list) and any(isinstance(x, dict) for x in rules_raw)
            normalized_trigger_policy = self._normalize_trigger_policy(
                kind=kind,
                has_rules=has_rules,
                trigger_policy=c.get("trigger_policy"),
            )

            specs.append(
                {
                    "contract_id": contract_id,
                    "kind": kind,
                    "title": title,
                    "terms": terms,
                    "terms_json": json.dumps(terms, ensure_ascii=False),
                    "status": ContractStatus.DRAFT.value,
                    "has_rules": bool(has_rules),
                    "trigger_policy": normalized_trigger_policy,
                    "parties": parties,
                    "required_signers": required_signers,
                    "signatures": [],
                    "participation_mode": participation_mode,
                    "invited_parties": invited_parties,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )

        for spec in specs:
            sqlite_create_contract(
                contract_id=spec["contract_id"],
                kind=spec["kind"],
                title=spec["title"],
                terms=spec["terms"],
                parties=spec["parties"],
                required_signers=spec["required_signers"],
                invited_parties=spec["invited_parties"],
                creator_id=str(actor_id).lower(),
                participation_mode=spec["participation_mode"],
                has_rules=bool(spec["has_rules"]),
                trigger_policy=spec["trigger_policy"],
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
            env = EventEnvelope[ContractCreatedPayload](
                event_type=EventType.CONTRACT_CREATED,
                correlation_id=uuid4(),
                actor=EventActor(user_id=actor_id),
                payload=payload,
            )
            self._event_store.append(EventEnvelopeJson.from_envelope(env))

        return [spec["contract_id"] for spec in specs]

    def join_contract(self, *, contract_id: str, joiner: str) -> None:
        now = datetime.now(timezone.utc)

        ok = sqlite_join_contract(contract_id, str(joiner).lower())
        if not ok:
            raise ValueError("contract not found or not joinable")

        payload = ContractJoinedPayload(contract_id=contract_id, joiner=joiner, joined_at=now)
        env = EventEnvelope[ContractJoinedPayload](
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

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        sqlite_create_proposal(
            proposal_id=proposal_id,
            contract_id=contract_id,
            proposal_type=proposal_type.upper(),
            proposer=str(proposer).lower(),
            details=details,
        )

        payload = ContractProposalCreatedPayload(
            contract_id=contract_id,
            proposal_id=proposal_id,
            proposal_type=proposal_type.upper(),
            proposer=proposer,
            details=details,
            created_at=now,
        )
        env = EventEnvelope[ContractProposalCreatedPayload](
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

        proposal = sqlite_get_proposal(proposal_id)
        if proposal is None or proposal.contract_id != contract_id:
            raise ValueError("proposal not found")

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        updated_proposal = sqlite_add_proposal_approval(proposal_id, str(approver).lower())
        if updated_proposal is None:
            raise ValueError("proposal not found")

        all_approved = set(contract.parties).issubset(set(updated_proposal.approvals))

        new_status = contract.status
        if all_approved:
            proposal_type = proposal.proposal_type.upper()
            if proposal_type == "SUSPEND":
                new_status = "SUSPENDED"
            elif proposal_type == "TERMINATE":
                new_status = "TERMINATED"
            elif proposal_type == "FAIL":
                new_status = "FAILED"
            elif proposal_type == "AMEND":
                try:
                    details = json.loads(proposal.details_json)
                    new_terms = details.get("terms", {})
                    new_status = contract.status
                    if new_terms:
                        sqlite_save_contract_terms(contract_id, new_terms)
                except Exception:
                    pass

            if new_status != contract.status:
                sqlite_update_contract_status(contract_id, new_status)

        payload = ContractProposalApprovedPayload(
            contract_id=contract_id,
            proposal_id=proposal_id,
            approver=approver,
            approved_at=now,
        )
        env = EventEnvelope[ContractProposalApprovedPayload](
            event_type=EventType.CONTRACT_PROPOSAL_APPROVED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=approver),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

        return {"applied": all_approved, "contract_status": new_status, "proposal_type": proposal.proposal_type}

    def sign_contract(self, *, contract_id: str, signer: str) -> ContractStatus:
        now = datetime.now(timezone.utc)

        contract_id = str(contract_id).strip()
        signer = str(signer).lower()

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found or not signable")

        if contract.status not in ("DRAFT", "SIGNED"):
            raise ValueError("contract not in signable state")

        ok = sqlite_sign_contract(contract_id, signer)
        if not ok:
            raise ValueError("contract not found or not signable")

        required = set(contract.required_signers)
        signed_parties = set((sqlite_get_contract(contract_id) or contract).signed_parties)
        all_signed = required.issubset(signed_parties)

        if all_signed:
            sqlite_update_contract_status(contract_id, ContractStatus.SIGNED.value)

        contract = sqlite_get_contract(contract_id)
        status = contract.status if contract else "DRAFT"

        payload = ContractSignedPayload(contract_id=contract_id, signer=signer, signed_at=now)
        env = EventEnvelope[ContractSignedPayload](
            event_type=EventType.CONTRACT_SIGNED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=signer),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))
        return ContractStatus(status)

    def activate_contract(self, *, contract_id: str, actor_id: str) -> None:
        now = datetime.now(timezone.utc)

        contract = sqlite_get_contract(contract_id)
        if contract is None or contract.status != "SIGNED":
            raise ValueError("contract not found or not signed")
        self._assert_trigger_authorized(contract, actor_id=actor_id, action="activate")

        sqlite_update_contract_status(contract_id, "ACTIVE")

        payload = ContractActivatedPayload(contract_id=contract_id, activated_at=now)
        env = EventEnvelope[ContractActivatedPayload](
            event_type=EventType.CONTRACT_ACTIVATED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def settle_contract(self, *, contract_id: str, actor_id: str) -> None:
        now = datetime.now(timezone.utc)

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")
        self._assert_trigger_authorized(contract, actor_id=actor_id, action="settle")

        status = contract.status
        if status == ContractStatus.SETTLED.value:
            return
        if status == ContractStatus.DEFAULTED.value:
            raise ValueError("contract defaulted")
        if status != ContractStatus.ACTIVE.value:
            raise ValueError("contract not active")

        terms_json = contract.terms_json
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

        affected_accounts = [actor_id]
        for t in scaled:
            affected_accounts.append(t.from_account_id)
            affected_accounts.append(t.to_account_id)
        self._refresh_settlement_for_accounts(affected_accounts)

        new_status = ContractStatus.SETTLED.value if fill_ratio >= 1.0 - 1e-9 else ContractStatus.DEFAULTED.value
        sqlite_update_contract_status(contract_id, new_status)

        if new_status == ContractStatus.DEFAULTED.value:
            payload = ContractDefaultedPayload(
                contract_id=contract_id,
                settlement_event_id=settlement_event_id,
                fill_ratio=float(fill_ratio),
                shortfall_by_from=shortfall_by_from,
                defaulted_at=now,
            )
            env = EventEnvelope[ContractDefaultedPayload](
                event_type=EventType.CONTRACT_DEFAULTED,
                correlation_id=uuid4(),
                actor=EventActor(user_id=actor_id),
                payload=payload,
            )
            self._event_store.append(EventEnvelopeJson.from_envelope(env))

        payload = ContractSettledPayload(contract_id=contract_id, settlement_event_id=settlement_event_id, settled_at=now)
        env = EventEnvelope[ContractSettledPayload](
            event_type=EventType.CONTRACT_SETTLED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def run_rules(self, *, contract_id: str, actor_id: str) -> None:
        now = datetime.now(timezone.utc)

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")
        self._assert_trigger_authorized(contract, actor_id=actor_id, action="run_rules")

        status = contract.status
        if status == ContractStatus.SETTLED.value:
            return
        if status == ContractStatus.DEFAULTED.value:
            raise ValueError("contract defaulted")
        if status != ContractStatus.ACTIVE.value:
            raise ValueError("contract not active")

        terms_json = contract.terms_json
        try:
            terms = json.loads(terms_json)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid contract terms") from exc

        rules_raw = terms.get("rules")
        if rules_raw is None:
            raise ValueError("contract rules missing")
        if not isinstance(rules_raw, list):
            raise ValueError("contract rules invalid")

        has_exec_rules = any(isinstance(x, dict) for x in rules_raw)
        if not has_exec_rules:
            sqlite_set_contract_has_rules(contract_id, False)
            return

        rule_state_json = contract.rule_state_json
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
                env = EventEnvelope[ContractRuleExecutedPayload](
                    event_type=EventType.CONTRACT_RULE_EXECUTED,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id=actor_id),
                    payload=payload,
                )
                self._event_store.append(EventEnvelopeJson.from_envelope(env))
                continue

            condition = rule.get("condition", True)
            condition_norm = self._normalize_condition_expr(condition, contract_id=contract_id)
            cond_ok = bool(eval_condition(condition_norm))
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
                env = EventEnvelope[ContractRuleExecutedPayload](
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

            affected_accounts = [actor_id]
            for t in scaled:
                affected_accounts.append(t.from_account_id)
                affected_accounts.append(t.to_account_id)
            self._refresh_settlement_for_accounts(affected_accounts)

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
            env = EventEnvelope[ContractRuleExecutedPayload](
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
                env = EventEnvelope[ContractDefaultedPayload](
                    event_type=EventType.CONTRACT_DEFAULTED,
                    correlation_id=uuid4(),
                    actor=EventActor(user_id=actor_id),
                    payload=payload,
                )
                self._event_store.append(EventEnvelopeJson.from_envelope(env))
                break

        if state_changed:
            sqlite_save_contract_rule_state(contract_id, rule_state)

        if defaulted:
            sqlite_update_contract_status(contract_id, ContractStatus.DEFAULTED.value)
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
            sqlite_update_contract_status(contract_id, ContractStatus.SETTLED.value)

    def get_contract(self, *, contract_id: str) -> Dict[str, Any]:
        """获取单个合约的详细信息"""
        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        return {
            "contract_id": contract.contract_id,
            "kind": contract.kind,
            "title": contract.title,
            "terms": json.loads(contract.terms_json) if contract.terms_json else {},
            "status": contract.status,
            "parties": contract.parties,
            "required_signers": contract.required_signers,
            "invited_parties": contract.invited_parties,
            "has_rules": contract.has_rules,
            "rule_state": json.loads(contract.rule_state_json) if contract.rule_state_json else {},
            "created_at": contract.created_at,
            "activated_at": contract.activated_at,
            "settled_at": contract.settled_at,
        }

    def update_contract_terms(self, *, contract_id: str, terms: Dict[str, Any], actor_id: str) -> None:
        """更新合约条款"""
        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        if contract.status not in (ContractStatus.DRAFT.value, ContractStatus.SIGNED.value):
            raise ValueError("contract cannot be modified in current status")

        sqlite_save_contract_terms(contract_id, terms)

    def invite_to_contract(self, *, contract_id: str, invitee: str, actor_id: str) -> None:
        """邀请玩家加入合约"""
        from ifrontier.domain.events.payloads import ContractInvitedPayload

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        from ifrontier.infra.sqlite.contracts import invite_to_contract as sqlite_invite_to_contract
        ok = sqlite_invite_to_contract(contract_id, str(invitee).lower())
        if not ok:
            raise ValueError("failed to invite to contract")

        now = datetime.now(timezone.utc)
        payload = ContractInvitedPayload(
            contract_id=contract_id,
            invitee=invitee,
            invited_by=actor_id,
            invited_at=now,
        )
        env = EventEnvelope[ContractInvitedPayload](
            event_type=EventType.CONTRACT_INVITED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def list_pending_contracts(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        """列出所有待处理的合约（DRAFT, SIGNED, ACTIVE 状态）"""
        from ifrontier.infra.sqlite.contracts import list_pending_contracts as sqlite_list_pending_contracts

        records = sqlite_list_pending_contracts(limit=int(limit))
        out = []
        for r in records:
            out.append({
                "contract_id": r.contract_id,
                "kind": r.kind,
                "title": r.title,
                "terms": json.loads(r.terms_json) if r.terms_json else {},
                "status": r.status,
                "parties": r.parties,
                "required_signers": r.required_signers,
                "invited_parties": r.invited_parties,
                "has_rules": r.has_rules,
                "created_at": r.created_at,
                "activated_at": r.activated_at,
                "settled_at": r.settled_at,
            })
        return out

    def terminate_contract(self, *, contract_id: str, actor_id: str, reason: str = "") -> None:
        """强制终止合约"""
        from ifrontier.domain.events.payloads import ContractTerminatedPayload

        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        if contract.status not in (ContractStatus.ACTIVE.value, ContractStatus.SIGNED.value, ContractStatus.DRAFT.value):
            raise ValueError("contract cannot be terminated in current status")

        new_status = ContractStatus.TERMINATED.value
        sqlite_update_contract_status(contract_id, new_status)

        now = datetime.now(timezone.utc)
        payload = ContractTerminatedPayload(
            contract_id=contract_id,
            terminated_by=actor_id,
            reason=reason,
            terminated_at=now,
        )
        env = EventEnvelope[ContractTerminatedPayload](
            event_type=EventType.CONTRACT_TERMINATED,
            correlation_id=uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        self._event_store.append(EventEnvelopeJson.from_envelope(env))

    def get_contract_rule_state(self, *, contract_id: str) -> Dict[str, Any]:
        """获取合约规则执行状态"""
        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        try:
            rule_state = json.loads(contract.rule_state_json) if contract.rule_state_json else {}
        except json.JSONDecodeError:
            rule_state = {}

        return rule_state

    def reset_contract_rule_state(self, *, contract_id: str, actor_id: str) -> None:
        """重置合约规则执行状态"""
        contract = sqlite_get_contract(contract_id)
        if contract is None:
            raise ValueError("contract not found")

        if contract.status != ContractStatus.DRAFT.value:
            raise ValueError("can only reset rule state in DRAFT status")

        sqlite_save_contract_rule_state(contract_id, {})