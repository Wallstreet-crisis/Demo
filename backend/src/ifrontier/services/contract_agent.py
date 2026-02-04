from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ifrontier.infra.sqlite.contract_agent import (
    clear_contract_agent_context,
    load_contract_agent_context,
    save_contract_agent_context,
)
from ifrontier.infra.llm.openrouter import OpenRouterClient, extract_first_message_text


@dataclass(frozen=True)
class ContractDraftResult:
    draft_id: str
    template_id: str
    contract_create: Dict[str, Any]
    explanation: str
    questions: List[str]
    risk_rating: str


@dataclass(frozen=True)
class ContractAuditResult:
    audit_id: str
    contract_id: str
    summary: str
    issues: List[str]
    questions: List[str]
    risk_rating: str


class ContractAgent:
    @staticmethod
    def _ensure_default_policies(terms: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(terms, dict):
            terms = {"transfers": [], "rules": []}

        dp = terms.get("default_policy")
        if not isinstance(dp, dict):
            dp = {}
        dp.setdefault("kind", "DEFAULT_PARTIAL_FILL")
        params = dp.get("params")
        if not isinstance(params, dict):
            params = {}
        params.setdefault("min_fill_ratio", 0.0)
        params.setdefault("penalty_bps", 0)
        dp["params"] = params
        terms["default_policy"] = dp

        reserved = terms.get("reserved_default_policies")
        if not isinstance(reserved, list):
            reserved = []
        if not any(isinstance(x, dict) and x.get("kind") == "DEFAULT_LIQUIDATE_THEN_HAIRCUT" for x in reserved):
            reserved.append({"kind": "DEFAULT_LIQUIDATE_THEN_HAIRCUT", "params": {}})
        terms["reserved_default_policies"] = reserved
        return terms

    def draft(self, *, actor_id: str, natural_language: str) -> ContractDraftResult:
        text = (natural_language or "").strip()
        if not text:
            raise ValueError("natural_language is required")

        ctx_rec = load_contract_agent_context(actor_id)
        ctx = dict(ctx_rec.context) if ctx_rec is not None else {}

        llm = OpenRouterClient.from_env()
        if llm is not None:
            llm_res = self._draft_with_llm(actor_id=actor_id, natural_language=text, context=ctx, llm=llm)
            if llm_res is not None:
                ctx["last_draft"] = {
                    "draft_id": llm_res.draft_id,
                    "template_id": llm_res.template_id,
                    "natural_language": text,
                    "contract": llm_res.contract_create,
                }
                save_contract_agent_context(actor_id=actor_id, context=ctx)
                return llm_res

        template_id = "UNKNOWN"
        contract: Dict[str, Any] | None = None
        questions: List[str] = []
        explanation = ""
        risk = "LOW"

        # Template A: 一对一直接转账（现金）
        # 例："我给 user:b 转 1000 现金" / "给 Bob 转 1000"（需要补充对手方 ID）
        m = re.search(r"(给|向)\s*(?P<to>[^\s]+)\s*(转|支付)\s*(?P<amount>\d+(?:\.\d+)?)\s*(现金|元)?", text)
        if m:
            template_id = "P2P_CASH_TRANSFER"
            to_id = str(m.group("to") or "").strip()
            amount = float(m.group("amount"))
            if not to_id:
                questions.append("请提供收款方的 user_id（例如 user:alice）。")
            if amount <= 0:
                questions.append("转账金额需要大于 0。")

            parties = [actor_id]
            required_signers = [actor_id]
            participation_mode = "OPT_IN"
            invited_parties: List[str] = []
            if to_id:
                invited_parties = [to_id]
                parties = [actor_id, to_id]
                required_signers = [actor_id, to_id]

            terms = {
                "transfers": [
                    {
                        "from": actor_id,
                        "to": to_id or "<TO_BE_CONFIRMED>",
                        "asset_type": "CASH",
                        "symbol": "CASH",
                        "quantity": amount,
                    }
                ],
                "rules": [],
            }
            terms = self._ensure_default_policies(terms)

            contract = {
                "actor_id": actor_id,
                "kind": "P2P_CASH_TRANSFER",
                "title": f"现金转账：{actor_id} -> {to_id or '待确认'}",
                "terms": terms,
                "parties": parties,
                "required_signers": required_signers,
                "participation_mode": participation_mode,
                "invited_parties": invited_parties,
            }

            explanation = (
                "我将你的指令理解为：你希望向对方进行一次性现金转账。\n"
                "这份契约的核心是：在契约结算时，从你的账户扣除约定现金，并增加到对方账户。\n"
                "风险点：请确认收款方身份与金额；转账属于不可逆的资金流出。"
            )
            risk = "LOW" if to_id and amount <= 10000 else "MEDIUM"

        # Template B: 简单一对一股票现货交易（现金换股票）
        # 例："我用 2000 现金向 user:b 买 10 股 BLUEGOLD 单价 200"
        if contract is None:
            m2 = re.search(
                r"(向|跟)\s*(?P<counter>[^\s]+)\s*(买|购买)\s*(?P<qty>\d+(?:\.\d+)?)\s*(股)?\s*(?P<symbol>[A-Z0-9_\-]+)\s*(单价|价格)?\s*(?P<price>\d+(?:\.\d+)?)?",
                text,
            )
            if m2:
                template_id = "P2P_EQUITY_TRADE"
                counter = str(m2.group("counter") or "").strip()
                qty = float(m2.group("qty"))
                symbol = str(m2.group("symbol") or "").strip().upper()
                price_raw = m2.group("price")
                price = float(price_raw) if price_raw else None

                if not counter:
                    questions.append("请提供对手方的 user_id（例如 user:bob）。")
                if qty <= 0:
                    questions.append("数量需要大于 0。")
                if not symbol:
                    questions.append("请提供股票代码（例如 BLUEGOLD）。")
                if price is None:
                    questions.append("请提供单价（例如 单价 12.5）。")
                if price is not None and price <= 0:
                    questions.append("单价需要大于 0。")

                parties = [actor_id]
                required_signers = [actor_id]
                participation_mode = "OPT_IN"
                invited_parties: List[str] = []
                if counter:
                    invited_parties = [counter]
                    parties = [actor_id, counter]
                    required_signers = [actor_id, counter]

                cash_amount = float(price * qty) if (price is not None) else 0.0

                terms = {
                    "transfers": [
                        {
                            "from": actor_id,
                            "to": counter or "<COUNTERPARTY_TO_BE_CONFIRMED>",
                            "asset_type": "CASH",
                            "symbol": "CASH",
                            "quantity": cash_amount,
                        },
                        {
                            "from": counter or "<COUNTERPARTY_TO_BE_CONFIRMED>",
                            "to": actor_id,
                            "asset_type": "EQUITY",
                            "symbol": symbol,
                            "quantity": qty,
                        },
                    ],
                    "rules": [],
                    "pricing": {"price": price, "currency": "CASH"},
                }
                terms = self._ensure_default_policies(terms)

                contract = {
                    "actor_id": actor_id,
                    "kind": "P2P_EQUITY_TRADE",
                    "title": f"现货交易：{actor_id} 买入 {qty} 股 {symbol}",
                    "terms": terms,
                    "parties": parties,
                    "required_signers": required_signers,
                    "participation_mode": participation_mode,
                    "invited_parties": invited_parties,
                }

                explanation = (
                    "我将你的指令理解为：你希望与对手方进行一笔‘现金换股票’的现货交易。\n"
                    "你支付现金，对方交付约定数量的股票。\n"
                    "风险点：需要确认对手方是否真实持有该股票；以及价格是否合理。"
                )
                risk = "MEDIUM"

        # Template C: 对赌/对冲契约 (Bet/Wager)
        # 例："Bet 1000 cash with user:bob on BLUEGOLD > 150"
        if contract is None:
            m3 = re.search(
                r"(?P<bet_type>Bet|对赌|赌)\s*(?P<amount>\d+(?:\.\d+)?)\s*(cash|现金)?\s*(with|跟|向)\s*(?P<counter>[^\s]+)\s*(on|关于|对于)?\s*(?P<symbol>[A-Z0-9_\-]+)\s*(?P<op>>|<|>=|<=|==)\s*(?P<target>\d+(?:\.\d+)?)",
                text,
                re.IGNORECASE
            )
            if m3:
                template_id = "P2P_PRICE_WAGER"
                counter = str(m3.group("counter") or "").strip()
                amount = float(m3.group("amount"))
                symbol = str(m3.group("symbol") or "").strip().upper()
                op_map = {">": "gt", "<": "lt", ">=": "gte", "<=": "lte", "==": "eq"}
                op_raw = m3.group("op")
                op = op_map.get(op_raw, "gt")
                target = float(m3.group("target"))

                invited_parties = [counter] if counter else []
                parties = [actor_id, counter] if counter else [actor_id]
                
                # 构建契约条款：如果触发条件，B 向 A 转账；否则 A 向 B 转账（或者 A 预质押）
                # 这里简化为：结算时根据价格决定 1000 块归谁
                terms = {
                    "transfers": [
                        {
                            "from": counter or "<COUNTERPARTY>",
                            "to": actor_id,
                            "asset_type": "CASH",
                            "symbol": "CASH",
                            "quantity": amount,
                            "condition": {
                                "var": f"price:{symbol}",
                                "op": op,
                                "val": target
                            }
                        },
                        {
                            "from": actor_id,
                            "to": counter or "<COUNTERPARTY>",
                            "asset_type": "CASH",
                            "symbol": "CASH",
                            "quantity": amount,
                            "condition": {
                                "var": f"price:{symbol}",
                                "op": "not_" + op if not op.startswith("not_") else op[4:], # 粗略逻辑
                                "val": target
                            }
                        }
                    ],
                    "rules": []
                }
                terms = self._ensure_default_policies(terms)

                contract = {
                    "actor_id": actor_id,
                    "kind": "P2P_PRICE_WAGER",
                    "title": f"价格对赌：{symbol} {op_raw} {target}",
                    "terms": terms,
                    "parties": parties,
                    "required_signers": parties,
                    "participation_mode": "OPT_IN",
                    "invited_parties": invited_parties,
                }
                explanation = f"这是一个对赌协议：如果 {symbol} 的价格 {op_raw} {target}，你将赢得 {amount} 现金；否则你将输掉同等金额。"
                risk = "HIGH"

        if contract is None:
            template_id = "UNKNOWN"
            questions.extend(
                [
                    "我没能明确识别契约类型。你是要：转账、买卖股票、还是借款/对赌？",
                    "请提供对手方 user_id（例如 user:alice）。",
                ]
            )
            contract = {
                "actor_id": actor_id,
                "kind": "UNKNOWN",
                "title": "待澄清的契约草案",
                "terms": self._ensure_default_policies({"transfers": [], "rules": []}),
                "parties": [actor_id],
                "required_signers": [actor_id],
                "participation_mode": "ALL_SIGNERS",
                "invited_parties": [],
            }
            explanation = "我需要你补充一些关键信息后才能生成可执行的契约草案。"
            risk = "HIGH"

        ctx["last_draft"] = {
            "draft_id": str(uuid4()),
            "template_id": template_id,
            "natural_language": text,
            "contract": contract,
        }
        save_contract_agent_context(actor_id=actor_id, context=ctx)

        return ContractDraftResult(
            draft_id=str(uuid4()),
            template_id=template_id,
            contract_create=contract,
            explanation=explanation,
            questions=questions,
            risk_rating=risk,
        )

    def append_edit_context(
        self,
        *,
        actor_id: str,
        base_contract_create: Dict[str, Any],
        instruction: str,
    ) -> None:
        ctx_rec = load_contract_agent_context(actor_id)
        ctx = dict(ctx_rec.context) if ctx_rec is not None else {}

        edits = ctx.get("edit_history")
        if not isinstance(edits, list):
            edits = []

        edits.append(
            {
                "edit_id": str(uuid4()),
                "instruction": str(instruction or ""),
                "base_contract_create": dict(base_contract_create or {}),
            }
        )

        ctx["edit_history"] = edits
        ctx["working_contract"] = dict(base_contract_create or {})
        save_contract_agent_context(actor_id=actor_id, context=ctx)

    def audit_contract(
        self,
        *,
        actor_id: str,
        contract_id: str,
        contract_snapshot: Dict[str, Any],
        force: bool = False,
    ) -> ContractAuditResult:
        ctx_rec = load_contract_agent_context(actor_id)
        ctx = dict(ctx_rec.context) if ctx_rec is not None else {}

        audits = ctx.get("contract_audits")
        if not isinstance(audits, dict):
            audits = {}

        cached = audits.get(contract_id)
        if (not force) and isinstance(cached, dict):
            return ContractAuditResult(
                audit_id=str(cached.get("audit_id") or ""),
                contract_id=str(cached.get("contract_id") or contract_id),
                summary=str(cached.get("summary") or ""),
                issues=list(cached.get("issues") or []),
                questions=list(cached.get("questions") or []),
                risk_rating=str(cached.get("risk_rating") or "LOW"),
            )

        llm = OpenRouterClient.from_env()
        if llm is None:
            res = ContractAuditResult(
                audit_id=str(uuid4()),
                contract_id=contract_id,
                summary="LLM not configured",
                issues=[],
                questions=[],
                risk_rating="LOW",
            )
            audits[contract_id] = {
                "audit_id": res.audit_id,
                "contract_id": res.contract_id,
                "summary": res.summary,
                "issues": res.issues,
                "questions": res.questions,
                "risk_rating": res.risk_rating,
            }
            ctx["contract_audits"] = audits
            save_contract_agent_context(actor_id=actor_id, context=ctx)
            return res

        llm_res = self._audit_with_llm(actor_id=actor_id, contract_id=contract_id, contract_snapshot=contract_snapshot, llm=llm)
        if llm_res is None:
            raise ValueError("audit failed")

        audits[contract_id] = {
            "audit_id": llm_res.audit_id,
            "contract_id": llm_res.contract_id,
            "summary": llm_res.summary,
            "issues": llm_res.issues,
            "questions": llm_res.questions,
            "risk_rating": llm_res.risk_rating,
        }
        ctx["contract_audits"] = audits
        save_contract_agent_context(actor_id=actor_id, context=ctx)
        return llm_res

    def _audit_with_llm(
        self,
        *,
        actor_id: str,
        contract_id: str,
        contract_snapshot: Dict[str, Any],
        llm: OpenRouterClient,
    ) -> ContractAuditResult | None:
        system = (
            "你是财务审计官(Financial Auditor)，仅输出合规JSON，禁止输出任何额外文字、注释、符号。",
            "目标：对收到的契约进行风险解释与质疑，给出清晰摘要、潜在问题、需要追问的点，并给出风险评级。",
            "输出结构固定：{\"audit_id\":\"...\",\"contract_id\":\"...\",\"summary\":\"...\",\"issues\":[...],\"questions\":[...],\"risk_rating\":\"LOW|MEDIUM|HIGH\"}",
            "issues/questions 必须是字符串数组，可以为空数组。",
            "summary 必须是简明中文段落，优先解释 transfers/触发条件/对我方资金与仓位影响。",
            "禁止输出非JSON内容。",
        )
        system_str = "\n".join(system)

        user = (
            "请输出 JSON，结构如下："
            "{\"audit_id\":\"...\",\"contract_id\":\"...\",\"summary\":\"...\",\"issues\":[...],\"questions\":[...],\"risk_rating\":\"LOW|MEDIUM|HIGH\"}.\n"
            f"actor_id: {actor_id}\n"
            f"contract_id: {contract_id}\n"
            f"contract_snapshot_json: {json.dumps(contract_snapshot or {}, ensure_ascii=False)}\n"
        )

        try:
            resp = llm.chat_completions(system=system_str, user=user, temperature=0.2, max_tokens=800)
            text = extract_first_message_text(resp)
            clean_text = text.strip()
            start_idx = clean_text.find("{")
            end_idx = clean_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                clean_text = clean_text[start_idx : end_idx + 1]
            obj = json.loads(clean_text)
        except Exception as exc:
            print(f"[ContractAgent] Audit LLM failed: {exc}")
            return None

        if not isinstance(obj, dict):
            return None

        audit_id = str(obj.get("audit_id") or uuid4())
        summary = str(obj.get("summary") or "")
        issues_raw = obj.get("issues")
        questions_raw = obj.get("questions")
        issues = [str(x) for x in (issues_raw or [])] if isinstance(issues_raw, list) else []
        questions = [str(x) for x in (questions_raw or [])] if isinstance(questions_raw, list) else []
        risk = str(obj.get("risk_rating") or "LOW").upper()
        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            risk = "LOW"

        return ContractAuditResult(
            audit_id=audit_id,
            contract_id=str(obj.get("contract_id") or contract_id),
            summary=summary,
            issues=issues,
            questions=questions,
            risk_rating=risk,
        )

    def _draft_with_llm(
        self,
        *,
        actor_id: str,
        natural_language: str,
        context: Dict[str, Any],
        llm: OpenRouterClient,
    ) -> ContractDraftResult | None:
        print(f"[ContractAgent] Attempting LLM draft for {actor_id}...")
        system = (
            "你是财务经理(Contract Agent)，仅输出合规JSON，禁止输出任何额外文字、注释、符号。",
            "契约为**纯结构化可执行合约**：所有履约/触发/计算逻辑**仅由transfers与expr表达式承载**，无其他可执行规则字段。",
            "字段规范（强制严格执行）：",
            "1. 顶层结构固定：{\"template_id\":\"...\",\"contract_create\":{...},\"explanation\":\"...\",\"questions\":[],\"risk_rating\":\"LOW|MEDIUM|HIGH\"}",
            "2. contract_create必填：kind/title/terms/parties/required_signers/participation_mode/invited_parties",
            "3. terms必填结构：parties/transfers/rules/default_policy/reserved_default_policies",
            "   3.1 transfers为数组，元素必须包含from/to/asset_type(CASH|EQUITY)/symbol/quantity；quantity为数字或{\"expr\":<expr>}表达式",
            "   3.2 expr仅支持：op(add/sub/mul/div/min/max)、args、变量{\"var\":\"cash:<account_id>\"}/{\"var\":\"pos:<account_id>:<symbol>\"}/{\"var\":\"price:<symbol>\"}",
            "   3.3 【关键规则】rules字段**仅为人类可读文本**，是explanation的核心摘要整合，无任何机器执行逻辑，直接复用给定的条款文本，不修改、不结构化、不嵌套",
            "   3.4 default_policy固定为DEFAULT_PARTIAL_FILL；reserved_default_policies固定包含DEFAULT_LIQUIDATE_THEN_HAIRCUT",
            "4. parties为数组，元素含party_id/role；required_signers为签约方ID数组；invited_parties为受邀方数组",
            "5. 【字段整合规则】explanation为rules所有条款的连贯通顺复述+业务场景简要说明，与rules内容完全对齐，无冲突、无新增信息",
            "6. risk_rating仅可选LOW/MEDIUM/HIGH，questions可为空数组",
            "禁止行为：禁止将rules转为结构化JSON、禁止在rules外新增可执行规则字段、禁止修改给定的rules文本、禁止输出非JSON内容"
        )
        # 将元组转换为单行或多行字符串，具体取决于模型偏好，此处合并
        system_str = "\n".join(system)

        user = (
            "请输出 JSON，结构如下："
            "{\"template_id\":\"...\",\"contract_create\":{...},\"explanation\":\"...\",\"questions\":[...],\"risk_rating\":\"LOW|MEDIUM|HIGH\"}.\n"
            f"actor_id: {actor_id}\n"
            f"natural_language: {natural_language}\n"
            f"context_json: {json.dumps(context or {}, ensure_ascii=False)}\n"
        )

        try:
            resp = llm.chat_completions(system=system_str, user=user, temperature=0.2, max_tokens=1000)
            text = extract_first_message_text(resp)
            print(f"[ContractAgent] LLM Raw Response: {text[:200]}...")
            
            # v0.2: 使用更鲁棒的 JSON 提取方法
            clean_text = text.strip()
            start_idx = clean_text.find("{")
            end_idx = clean_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                clean_text = clean_text[start_idx : end_idx + 1]
            
            obj = json.loads(clean_text)
        except Exception as exc:
            print(f"[ContractAgent] LLM error or parsing failed: {exc}")
            return None

        if not isinstance(obj, dict):
            print("[ContractAgent] LLM returned non-dict object")
            return None

        template_id = str(obj.get("template_id") or "LLM")
        contract_create = obj.get("contract_create")
        if not isinstance(contract_create, dict):
            return None

        # 最小修正：确保 actor_id 写入草案，便于后续对接 /contracts/create
        contract_create.setdefault("actor_id", actor_id)
        contract_create.setdefault("terms", {"transfers": [], "rules": []})
        if not isinstance(contract_create.get("terms"), dict):
            contract_create["terms"] = {"transfers": [], "rules": []}
        contract_create["terms"] = self._ensure_default_policies(dict(contract_create.get("terms") or {}))

        explanation = str(obj.get("explanation") or "")
        questions = obj.get("questions")
        if not isinstance(questions, list):
            questions = []
        questions = [str(x) for x in questions if x]

        risk_rating = str(obj.get("risk_rating") or "MEDIUM").upper()
        if risk_rating not in {"LOW", "MEDIUM", "HIGH"}:
            risk_rating = "MEDIUM"

        return ContractDraftResult(
            draft_id=str(uuid4()),
            template_id=template_id,
            contract_create=contract_create,
            explanation=explanation,
            questions=questions,
            risk_rating=risk_rating,
        )

    def get_context(self, *, actor_id: str) -> Dict[str, Any]:
        rec = load_contract_agent_context(actor_id)
        if rec is None:
            return {}
        return dict(rec.context or {})

    def clear_context(self, *, actor_id: str) -> None:
        clear_contract_agent_context(actor_id)
