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


class ContractAgent:
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
                "terms": {"transfers": [], "rules": []},
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

    def _draft_with_llm(
        self,
        *,
        actor_id: str,
        natural_language: str,
        context: Dict[str, Any],
        llm: OpenRouterClient,
    ) -> ContractDraftResult | None:
        system = (
            "你是一个财务经理(Contract Agent)。你的任务是把用户自然语言指令翻译为可执行的契约草案。"
            "你必须只输出 JSON，不要输出其它任何文字。"
            "契约草案需要是可编辑模块：kind/title/terms(parties/transfers/rules)/parties/required_signers/participation_mode/invited_parties。"
            "terms.transfers 是列表，元素包含 from/to/asset_type(CASH|EQUITY)/symbol/quantity。"
            "risk_rating 只能是 LOW/MEDIUM/HIGH。"
        )

        user = (
            "请输出 JSON，结构如下："
            "{\"template_id\":\"...\",\"contract_create\":{...},\"explanation\":\"...\",\"questions\":[...],\"risk_rating\":\"LOW|MEDIUM|HIGH\"}.\n"
            f"actor_id: {actor_id}\n"
            f"natural_language: {natural_language}\n"
            f"context_json: {json.dumps(context or {}, ensure_ascii=False)}\n"
        )

        try:
            resp = llm.chat_completions(system=system, user=user, temperature=0.2, max_tokens=800)
            text = extract_first_message_text(resp)
            obj = json.loads(text)
        except Exception:
            return None

        if not isinstance(obj, dict):
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
