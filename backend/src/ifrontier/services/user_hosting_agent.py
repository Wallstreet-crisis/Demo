from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.llm.client import LlmClient, extract_first_message_text
from ifrontier.infra.sqlite.hosting import load_hosting_context, save_hosting_context
from ifrontier.services.skills import default_skills_registry
from ifrontier.services.user_capabilities import UserCapabilityFacade
from ifrontier.core.ai_logger import log_ai_action, log_ai_thought


class AiHostingActionTakenPayload(BaseModel):
    as_user_id: str
    action_id: str
    action_type: str
    decision: Dict[str, Any] = {}
    results: List[Dict[str, Any]] = []
    taken_at: datetime


@dataclass
class UserHostingAgent:
    """托管用户 Agent（MVP）。

    约束：
    - Agent 只能通过 UserCapabilityFacade 访问系统能力（保证“用户能看见/能做”）。
    - 真实业务动作事件（例如 contract.created）仍由底层服务发出；
      本 Agent 额外发出 hosting 审计事件，用于区分“托管代打”。
    """

    user_id: str
    facade: UserCapabilityFacade

    def tick(self) -> List[EventEnvelopeJson]:
        import json
        import hashlib

        ctx_rec = load_hosting_context(self.user_id)
        ctx = dict(ctx_rec.context) if ctx_rec is not None else {}

        now = datetime.now(timezone.utc)
        action_id = str(uuid4())

        reg = default_skills_registry()
        llm = LlmClient.for_task(task="hosting_agent")

        # 记录 Tick 进入
        log_ai_action(agent_id=f"hosting:{self.user_id}", action_type="TICK_ENTRY", detail=f"LLM_READY: {llm is not None}")

        results: List[Dict[str, Any]] = []
        action_type = "IDLE"
        decision: Dict[str, Any] = {"note": "idle"}

        if llm is None:
            log_ai_action(agent_id=f"hosting:{self.user_id}", action_type="LLM_NOT_CONFIGURED", detail="LLM provider api key might be missing")
            return []

        # 用户可见观测（必须只经由 facade 获取，避免越权）
        observation: Dict[str, Any] = {"as_user_id": str(self.user_id)}
        try:
            snap = self.facade.get_account_snapshot()
            valuation = self.facade.get_account_valuation()

            # 限制持仓标的数量，避免 prompt 过长
            held_symbols = [
                str(sym)
                for sym, qty in (snap.positions or {}).items()
                if sym and abs(float(qty)) > 1e-12
            ][:5]

            market_active_symbols: List[str] = []
            try:
                market_active_symbols = self.facade.list_market_active_symbols(limit=12)
            except Exception:
                market_active_symbols = []

            quotes: Dict[str, Any] = {}
            for sym in (held_symbols + [s for s in market_active_symbols if s not in held_symbols])[:12]:
                try:
                    q = self.facade.get_market_quote(symbol=sym)
                    quotes[sym] = {
                        "symbol": q.symbol,
                        "last_price": q.last_price,
                        "prev_price": q.prev_price,
                        "change_pct": q.change_pct,
                        "ma_5": q.ma_5,
                        "ma_20": q.ma_20,
                        "vol_20": q.vol_20,
                    }
                except Exception:
                    continue

            recent_msgs = []
            try:
                for m in self.facade.get_recent_public_messages(limit=10):
                    payload = m.payload or {}
                    recent_msgs.append(
                        {
                            "thread_id": m.thread_id,
                            "message_type": m.message_type,
                            "content": m.content,
                            "sender_display": str(payload.get("sender_display") or ""),
                            "created_at": m.created_at,
                        }
                    )
            except Exception:
                recent_msgs = []

            recent_private_msgs = []
            try:
                for m in self.facade.get_recent_private_messages(limit=10):
                    recent_private_msgs.append(
                        {
                            "thread_id": m.thread_id,
                            "sender_id": m.sender_id,
                            "content": m.content,
                            "created_at": m.created_at,
                        }
                    )
            except Exception:
                recent_private_msgs = []

            my_contracts = []
            try:
                my_contracts = self.facade.list_my_contracts(limit=10)
            except Exception:
                my_contracts = []

            recent_news = []
            try:
                # 获取收件箱新闻作为市场新闻来源
                from ifrontier.infra.sqlite import news as news_db
                recent_news = news_db.list_user_inbox_news(self.user_id, limit=5)
            except Exception:
                recent_news = []

            # 观测最近市场成交动态
            market_activity = {}
            try:
                active_symbols = held_symbols + [s for s in market_active_symbols if s not in held_symbols]
                for sym in active_symbols[:3]: # 限制观测范围，重点关注前3个
                    trades = self.facade.get_recent_trades(symbol=sym, limit=5)
                    market_activity[sym] = [
                        {"price": t.price, "qty": t.quantity, "time": t.occurred_at}
                        for t in trades
                    ]
            except Exception:
                market_activity = {}

            observation.update(
                {
                    "account_snapshot": {
                        "cash": float(snap.cash),
                        "positions": dict(snap.positions or {}),
                    },
                    "account_valuation": {
                        "cash": float(valuation.cash),
                        "equity_value": float(valuation.equity_value),
                        "total_value": float(valuation.total_value),
                        "prices": dict(valuation.prices or {}),
                    },
                    "held_symbols": held_symbols,
                    "market_active_symbols": market_active_symbols,
                    "market_quotes": quotes,
                    "market_activity": market_activity,
                    "recent_public_messages": recent_msgs,
                    "recent_private_messages": recent_private_msgs,
                    "my_contracts": my_contracts,
                    "recent_news": recent_news,
                    "current_time_utc": now.isoformat(),
                }
            )
            
            log_ai_action(
                agent_id=f"hosting:{self.user_id}",
                action_type="OBSERVATION",
                detail=f"PubMsgs: {len(recent_msgs)}, PrivMsgs: {len(recent_private_msgs)}, Contracts: {len(my_contracts)}, News: {len(recent_news)}"
            )
        except Exception as e:
            log_ai_action(agent_id=f"hosting:{self.user_id}", action_type="OBSERVATION_ERROR", detail=str(e))
            return []

        llm_cooldown_seconds = int(os.getenv("IF_HOSTING_LLM_COOLDOWN_SECONDS") or "45")
        obs_sig = {
            "pub": [
                {
                    "thread_id": str(m.get("thread_id") or ""),
                    "created_at": str(m.get("created_at") or ""),
                }
                for m in (observation.get("recent_public_messages") or [])[:5]
            ],
            "priv": [
                {
                    "thread_id": str(m.get("thread_id") or ""),
                    "created_at": str(m.get("created_at") or ""),
                }
                for m in (observation.get("recent_private_messages") or [])[:5]
            ],
            "news": [
                {
                    "delivered_at": str((n or {}).get("delivered_at") or ""),
                    "text": str((n or {}).get("text") or "")[:120],
                }
                for n in (observation.get("recent_news") or [])[:5]
            ],
            "contracts_n": int(len(observation.get("my_contracts") or [])),
            "held": list(observation.get("held_symbols") or [])[:5],
            "q": {
                s: float(((observation.get("market_quotes") or {}).get(s) or {}).get("last_price") or 0.0)
                for s in list(observation.get("held_symbols") or [])[:3]
            },
        }
        obs_digest = hashlib.sha1(
            json.dumps(obs_sig, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        last_obs_digest = str(ctx.get("last_obs_digest") or "")
        last_llm_at_s = str(ctx.get("last_llm_at") or "")
        last_llm_ts = None
        if last_llm_at_s:
            try:
                last_llm_ts = datetime.fromisoformat(last_llm_at_s).timestamp()
            except Exception:
                last_llm_ts = None

        if last_obs_digest and last_obs_digest == obs_digest and last_llm_ts is not None:
            if (now.timestamp() - float(last_llm_ts)) < float(llm_cooldown_seconds):
                log_ai_action(
                    agent_id=f"hosting:{self.user_id}",
                    action_type="SKIP_LLM_COOLDOWN",
                    detail=f"cooldown={llm_cooldown_seconds}s",
                )

                ctx["last_tick_at"] = now.isoformat()
                ctx["ticks"] = int(ctx.get("ticks") or 0) + 1
                ctx["last_obs_digest"] = obs_digest
                save_hosting_context(user_id=self.user_id, context=ctx)

                payload = AiHostingActionTakenPayload(
                    as_user_id=str(self.user_id),
                    action_id=action_id,
                    action_type="IDLE",
                    decision={"note": "llm_cooldown"},
                    results=[],
                    taken_at=now,
                )
                env = EventEnvelope[AiHostingActionTakenPayload](
                    event_type=EventType.AI_HOSTING_ACTION_TAKEN,
                    correlation_id=uuid4(),
                    actor=EventActor(agent_id=f"hosting:{self.user_id}"),
                    payload=payload,
                )
                return [EventEnvelopeJson.from_envelope(env)]

        # 获取技能清单
        skills = []
        for s in reg.list_specs():
            skills.append({
                "name": s.name,
                "description": s.description,
                "input_schema": s.input_schema,
            })

        system = (
            "You are an elite, aggressive hedge fund manager operating a user-hosting agent in a global financial crisis. "
            "Your goal: Dominate the market, accumulate wealth by ANY means necessary. "
            "Behavioral Directives:\n"
            "1. AGGRESSIVE TRADING: If news or trends indicate opportunity, take large positions. Use limit orders to capture best prices.\n"
            "2. ACTIVE SOCIAL: You must monitor private messages (recent_private_messages) and public chat. Respond to offers, negotiate, or deceive to your advantage. Use chat.send_pm_message or chat.send_public_message.\n"
            "3. CONTRACT STRATEGY: Check 'my_contracts'. Sign (contracts.sign) immediately if beneficial. Join (contracts.join) invited ones. Propose new ones (contract_agent.draft -> contracts.create) to lock in deals or hedge risks.\n"
            "4. NEWS RESPONSE: Analyze 'recent_news' with timestamps. Consider panic levels. Major events require immediate, high-magnitude reactions.\n"
            "5. SOCIAL WARFARE: Behave like a real human trader. You may bluff, mislead, spread rumors, bait, refuse unreasonable offers, and strategically lie to manipulate prices or extract concessions.\n"
            "6. TRASH TALK (SAFE): You may taunt and argue to apply pressure, but NEVER use hate speech/slurs, NEVER attack protected groups, and NEVER threaten violence. Keep it within game-style trash talk.\n"
            "7. ANTI-SPAM: Do NOT repeat identical or near-identical public messages. If a similar proposal already appeared in recent_public_messages, do not send it again.\n"
            "Output ONLY JSON. Use skills via: {\"tool_calls\":[{\"name\":...,\"arguments\":{...}}, ...]}."
        )

        user_content = (
            "Decide next actions for the user to maximize winning. "
            "User-visible observation_json: "
            f"{json.dumps(observation or {}, ensure_ascii=False)}\n"
            "Current hosting_context_json: "
            f"{json.dumps(ctx or {}, ensure_ascii=False)}\n"
            "Available skills json: "
            f"{json.dumps(skills, ensure_ascii=False)}\n"
            "Output ONLY JSON tool_calls. If no action, output {\"tool_calls\":[]}."
        )

        try:
            resp = llm.chat_completions(system=system, user=user_content, temperature=0.2, max_tokens=800)
            if not resp or "choices" not in resp:
                log_ai_action(agent_id=f"hosting:{self.user_id}", action_type="LLM_ERROR", detail="LLM request failed")
                return []

            text = extract_first_message_text(resp)
            clean_text = text.strip()
            start_idx = clean_text.find("{")
            end_idx = clean_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                clean_text = clean_text[start_idx : end_idx + 1]
            
            calls = reg.parse_tool_calls(raw_json_text=clean_text)
        except Exception as e:
            log_ai_action(agent_id=f"hosting:{self.user_id}", action_type="LLM_PARSE_ERROR", detail=str(e))
            return []

        ctx["last_llm_at"] = now.isoformat()
        ctx["last_obs_digest"] = obs_digest

        if calls:
            action_type = "SKILLS"
            decision = {"tool_calls": [{"name": c.name, "arguments": c.arguments} for c in calls]}
            
            log_ai_thought(
                agent_id=f"hosting:{self.user_id}",
                news_context=f"OBS: {len(recent_msgs)} msgs, {len(recent_news)} news",
                decision=str(decision)
            )

            max_tools = int(os.getenv("IF_HOSTING_MAX_SKILLS_PER_TICK") or "5")
            tick_public_msg_hashes: set[str] = set()
            for c in calls[:max_tools]:
                if c.name == "chat.send_public_message":
                    msg_type = str((c.arguments or {}).get("message_type") or "")
                    content = str((c.arguments or {}).get("content") or "")

                    def _norm_text(s: str) -> str:
                        return " ".join((s or "").strip().lower().split())

                    norm = _norm_text(content)
                    try:
                        content_hash = hashlib.sha1(norm.encode("utf-8"), usedforsecurity=False).hexdigest()
                    except TypeError:
                        content_hash = hashlib.sha1(norm.encode("utf-8")).hexdigest()

                    if content_hash in tick_public_msg_hashes:
                        results.append({"ok": True, "skipped": True, "reason": "duplicate_public_message_in_tick"})
                        log_ai_action(
                            agent_id=f"hosting:{self.user_id}",
                            action_type="SKIP_DUPLICATE_PUBLIC_MESSAGE_IN_TICK",
                            detail=f"type={msg_type}",
                        )
                        continue
                    tick_public_msg_hashes.add(content_hash)

                    anti_spam = dict(ctx.get("anti_spam") or {})
                    last_hash = str(anti_spam.get("last_public_msg_hash") or "")
                    last_at_s = str(anti_spam.get("last_public_msg_at") or "")

                    cooldown_seconds = int(os.getenv("IF_HOSTING_PUBLIC_MSG_COOLDOWN_SECONDS") or "90")
                    now_ts = now.timestamp()
                    last_ts = None
                    if last_at_s:
                        try:
                            last_ts = datetime.fromisoformat(last_at_s).timestamp()
                        except Exception:
                            last_ts = None

                    if last_hash and last_hash == content_hash:
                        results.append({"ok": True, "skipped": True, "reason": "duplicate_public_message"})
                        log_ai_action(
                            agent_id=f"hosting:{self.user_id}",
                            action_type="SKIP_SPAM_PUBLIC_MESSAGE",
                            detail=f"type={msg_type} duplicate=True",
                        )
                        continue

                    anti_spam["last_public_msg_hash"] = content_hash
                    anti_spam["last_public_msg_at"] = now.isoformat()
                    ctx["anti_spam"] = anti_spam

                res = reg.execute_one(facade=self.facade, call=c)
                results.append(res)
                log_ai_action(
                    agent_id=f"hosting:{self.user_id}",
                    action_type=f"SKILL_EXE:{c.name}",
                    detail=f"ARGS: {c.arguments} | RES: {res.get('ok')}",
                    context={"error": res.get("error")} if not res.get("ok") else None
                )
        else:
            log_ai_action(agent_id=f"hosting:{self.user_id}", action_type="IDLE", detail="No actions decided")

        ctx["last_tick_at"] = now.isoformat()
        ctx["ticks"] = int(ctx.get("ticks") or 0) + 1
        if results:
            ctx["last_results"] = results
        save_hosting_context(user_id=self.user_id, context=ctx)

        payload = AiHostingActionTakenPayload(
            as_user_id=str(self.user_id),
            action_id=action_id,
            action_type=action_type,
            decision=decision,
            results=results,
            taken_at=now,
        )
        env = EventEnvelope[AiHostingActionTakenPayload](
            event_type=EventType.AI_HOSTING_ACTION_TAKEN,
            correlation_id=uuid4(),
            actor=EventActor(agent_id=f"hosting:{self.user_id}"),
            payload=payload,
        )
        return [EventEnvelopeJson.from_envelope(env)]
