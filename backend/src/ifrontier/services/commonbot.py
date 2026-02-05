from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from ifrontier.domain.assets.profile import get_profile
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    AiCommonBotDecisionPayload,
    TradeIntentSubmittedPayload,
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.llm.openrouter import OpenRouterClient, extract_first_message_text
from ifrontier.core.ai_logger import log_ai_action, log_ai_thought


def _price_trend(price_series: List[float]) -> float:
    if len(price_series) < 2:
        return 0.0
    return (price_series[-1] - price_series[0]) / max(price_series[0], 1e-6)


def _score_decision(
    visual_truth: str,
    symbol: str,
    price_series: List[float],
    news_text: str | None = None,
) -> Tuple[str, float]:
    profile = get_profile(symbol)
    sector = profile.sector if profile else "GENERIC"

    base = 0.0
    vt_upper = visual_truth.upper()
    if vt_upper == "PROFIT":
        base = 0.7
    elif vt_upper == "LOSS":
        base = -0.7
    
    # 增加对新闻文本的简单启发式扫描 (散户机器人逻辑)
    text_impact = 0.0
    if news_text:
        text_upper = news_text.upper()
        # 战争/危机关键词 (支持中英文)
        war_keywords = [
            "WAR", "CONFLICT", "CRISIS", "BATTLE", "MILITARY", "INVASION", "STRIKE", "GLOBAL WAR", "WORLD WAR",
            "战争", "冲突", "危机", "战役", "军事", "入侵", "打击", "全球战争", "世界大战", "不可抗力", "停产"
        ]
        if any(k in text_upper for k in war_keywords):
            # 军工和能源股看涨，金融/消费/技术/物流看跌
            if sector in ["MILITARY", "ENERGY"]:
                text_impact += 0.8  # 强烈看涨
            elif sector in ["FINANCE", "CONSUMER", "TECH", "LOGISTICS", "HEALTHCARE"]:
                text_impact -= 0.7  # 强烈看跌
            else:
                text_impact -= 0.3 # 整体不确定性
        
        # 增长关键词 (支持中英文)
        growth_keywords = [
            "GROWTH", "BOOM", "SUCCESS", "RECOVERY", "PROFIT", "ACQUISITION", "DIVIDEND", "BREAKTHROUGH",
            "增长", "繁荣", "成功", "复苏", "盈利", "收购", "分红", "派息", "突破", "利好"
        ]
        if any(k in text_upper for k in growth_keywords):
            text_impact += 0.4
            
        # 负面/调查关键词 (支持中英文)
        negative_keywords = [
            "INVESTIGATION", "LAWSUIT", "LEAK", "SUSPEND", "LOSS", "STOP", "REGULATION",
            "调查", "诉讼", "泄露", "暂停", "亏损", "停止", "管制", "合规", "禁令"
        ]
        if any(k in text_upper for k in negative_keywords):
            text_impact -= 0.4
            
    sector_adj = 0.0
    if sector == "MILITARY":
        sector_adj = 0.15
    elif sector == "ENERGY":
        sector_adj = 0.1
    elif sector == "FINANCE":
        sector_adj = -0.1

    trend = _price_trend(price_series)
    trend_adj = 0.0
    if trend > 0.05:
        trend_adj = -0.1
    elif trend < -0.05:
        trend_adj = 0.1

    score = max(min(base + text_impact + sector_adj + trend_adj, 1.0), -1.0)

    if score > 0.3:
        action = "BUY"
    elif score < -0.3:
        action = "SELL"
    else:
        action = "HOLD"

    return action, score


def run_commonbot_for_earnings(
    *,
    symbol: str,
    visual_truth: str,
    price_series: List[float],
    bot_id: str,
    correlation_id,
    news_text: str | None = None,
    news_window: List[Dict[str, Any]] | None = None,
    use_llm: bool = False,
    truth_payload: Dict[str, Any] | None = None,
    is_insider: bool = False,
    author_id: str = "system",
    mutation_depth: int = 0,
) -> Tuple[EventEnvelopeJson, EventEnvelopeJson | None]:
    llm_result = None
    
    # --- 核心博弈逻辑：真理与欺骗 ---
    # ... (保持原有的 trust logic) ...
    news_kind = str((truth_payload or {}).get("kind") or "UNKNOWN").upper()
    is_system_fact = (author_id == "system") and (news_kind in ["MAJOR_EVENT", "WORLD_EVENT", "EARNINGS"]) and (not news_kind.startswith("OMEN"))
    
    should_trust_truth = is_system_fact or is_insider
    
    if author_id != "system" or news_kind in ["RUMOR", "LEAK", "OMEN"]:
        mislead_chance = 0.3 + (min(mutation_depth, 5) * 0.1)
        if is_insider and random.random() < mislead_chance:
            should_trust_truth = False
            mode_desc = f"INSIDER_MISLED (Chance: {mislead_chance:.0%})"
        else:
            should_trust_truth = False if not is_insider else True
            mode_desc = "INSIDER_PENETRATION" if should_trust_truth else "RETAIL_SPECULATION (Focus text)"
    else:
        mode_desc = "FACT_TRUST" if should_trust_truth else "TEXT_ANALYSIS"

    # 记录进入决策流
    log_ai_action(
        agent_id=bot_id,
        action_type="DECISION_START",
        detail=f"Symbol: {symbol} | Mode: {mode_desc} | Kind: {news_kind}"
    )

    is_rumor = (author_id != "system") or (news_kind in ["RUMOR", "LEAK", "OMEN"])

    if should_trust_truth and truth_payload:
        direction = truth_payload.get("direction")
        if not direction and truth_payload.get("impact_map"):
            direction = truth_payload["impact_map"].get(symbol)
            
        if direction:
            direction = str(direction).upper()
            if direction == "UP":
                action, score = "BUY", 0.95
            elif direction == "DOWN":
                action, score = "SELL", 0.95
            else:
                action, score = "HOLD", 0.1
            confidence = score
            w_visual, w_text, w_trend = 0.05, 0.05, 0.9 
        elif use_llm:
            llm_result = _llm_decide_from_news(
                symbol=symbol,
                visual_truth=visual_truth,
                news_text=news_text or "",
                news_window=news_window,
                price_series=price_series,
                is_rumor=is_rumor,
            )
    else:
        if use_llm:
            llm_result = _llm_decide_from_news(
                symbol=symbol,
                visual_truth=visual_truth,
                news_text=news_text or "",
                news_window=news_window,
                price_series=price_series,
                is_rumor=is_rumor,
            )

    if llm_result is not None:
        action = str(llm_result.get("action") or "HOLD").upper()
        confidence = float(llm_result.get("confidence") or 0.0)
        w_visual = float(llm_result.get("w_visual") or 0.0)
        w_text = float(llm_result.get("w_text") or 0.0)
        w_trend = float(llm_result.get("w_trend") or 0.0)
        
        # 记录 LLM 决策
        log_ai_thought(
            agent_id=bot_id,
            news_context=f"{symbol} | {news_text[:50]}...",
            decision=f"{action} (Conf: {confidence:.2f}, w_text: {w_text:.2f})"
        )
    else:
        action, score = _score_decision(visual_truth, symbol, price_series, news_text=news_text)
        confidence = abs(float(score))
        w_visual, w_text, w_trend = 0.3, 0.7, 0.0
        
        # 记录启发式决策
        log_ai_action(
            agent_id=bot_id,
            action_type="HEURISTIC_DECISION",
            detail=f"{symbol} -> {action} (Score: {score:.2f})",
            context={"reason": "LLM fallback"}
        )

    now = datetime.now(timezone.utc)
    decision_payload = AiCommonBotDecisionPayload(
        bot_id=bot_id,
        tick_id="debug-tick",
        asset_symbol=symbol,
        action=action,
        confidence=confidence,
        w_visual=w_visual,
        w_text=w_text,
        w_trend=w_trend,
        decided_at=now,
    )
    decision_envelope = EventEnvelope[AiCommonBotDecisionPayload](
        event_type=EventType.AI_COMMONBOT_DECISION,
        correlation_id=correlation_id,
        actor=EventActor(agent_id=bot_id),
        payload=decision_payload,
    )
    decision_json = EventEnvelopeJson.from_envelope(decision_envelope)

    trade_json: EventEnvelopeJson | None = None
    if action in {"BUY", "SELL"}:
        base_size = 10.0
        if "inst" in bot_id:
            base_size = 1000.0
        
        # 随信心指数指数级增长，表现得更具攻击性
        size = base_size * (2 ** (confidence * 4))
        size *= random.uniform(0.8, 1.2)

        intent_payload = TradeIntentSubmittedPayload(
            intent_id=str(uuid4()),
            user_id="commonbot:" + bot_id,
            symbol=symbol,
            side=action,
            size=float(round(size, 2)),
            price_hint=price_series[-1] if price_series else None,
            confidence=confidence,
            created_at=now,
        )
        intent_envelope = EventEnvelope[TradeIntentSubmittedPayload](
            event_type=EventType.TRADE_INTENT_SUBMITTED,
            correlation_id=correlation_id,
            actor=EventActor(agent_id=bot_id),
            payload=intent_payload,
        )
        trade_json = EventEnvelopeJson.from_envelope(intent_envelope)

    return decision_json, trade_json


def _llm_decide_from_news(
    *,
    symbol: str,
    visual_truth: str,
    news_text: str,
    news_window: List[Dict[str, Any]] | None = None,
    price_series: List[float],
    is_rumor: bool = False,
) -> Dict[str, Any] | None:
    client = OpenRouterClient.from_env()
    if client is None:
        log_ai_action(
            agent_id=f"commonbot:{symbol}",
            action_type="LLM_NOT_CONFIGURED",
            detail="OPENROUTER_API_KEY missing",
        )
        return None

    trend = _price_trend(price_series)
    news_context = news_text
    if news_window:
        # 构建带时间戳的新闻窗口描述
        window_lines = []
        for i, item in enumerate(news_window):
            window_lines.append(f"[{item.get('delivered_at', 'unknown')}] {item.get('text')}")
        news_context = "Current event: " + news_text + "\nRecent history:\n" + "\n".join(window_lines)

    if is_rumor:
        system = (
            "你是一个在极端金融危机中博弈的散户(retail bot)。你对传闻和泄密非常敏感。"
            "你会观察最近的新闻序列来判断恐慌程度。"
            "如果连续出现负面消息，你的恐慌感会呈指数级上升。"
            "你只能输出 JSON，不要输出其它文字。"
            "action 只能是 BUY/SELL/HOLD。confidence 在 0~1 之间。请给出权重 w_visual/w_text/w_trend。"
        )
    else:
        system = (
            "你是一个专业的市场参与者。你会分析新闻序列的时间戳和内容来判断市场趋势。"
            "考虑事件的紧迫性和潜在的系统性风险。"
            "你只能输出 JSON，不要输出其它文字。"
            "action 只能是 BUY/SELL/HOLD。confidence 在 0~1 之间。请给出权重 w_visual/w_text/w_trend。"
        )

    user = (
        "请输出 JSON："
        "{\"action\":\"BUY|SELL|HOLD\",\"confidence\":0.0,"
        "\"w_visual\":0.0,\"w_text\":0.0,\"w_trend\":0.0}.\n"
        f"symbol: {symbol}\n"
        f"visual_truth: {visual_truth}\n"
        f"news_context: {news_context}\n"
        f"price_trend: {trend}\n"
    )

    try:
        resp = client.chat_completions(system=system, user=user, temperature=0.2, max_tokens=512)
    except Exception as exc:
        log_ai_action(
            agent_id=f"commonbot:{symbol}",
            action_type="LLM_CALL_ERROR",
            detail=str(exc),
        )
        return None
    if not resp or "choices" not in resp:
        log_ai_action(
            agent_id=f"commonbot:{symbol}",
            action_type="LLM_EMPTY_RESPONSE",
            detail="missing choices",
        )
        return None

    text = extract_first_message_text(resp)
    clean_text = str(text or "").strip()
    if clean_text.startswith("```"):
        lines = [ln for ln in clean_text.splitlines() if not ln.strip().startswith("```")]
        clean_text = "\n".join(lines).strip()

    try:
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            clean_text = clean_text[start_idx : end_idx + 1]
        obj = __import__("json").loads(clean_text)
    except Exception as exc:
        log_ai_action(
            agent_id=f"commonbot:{symbol}",
            action_type="LLM_PARSE_ERROR",
            detail=str(exc),
            context={"raw": str(text or "")[:400]},
        )
        return None

    return obj
