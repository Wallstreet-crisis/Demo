from __future__ import annotations

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
        # 战争/危机关键词
        war_keywords = ["WAR", "CONFLICT", "CRISIS", "BATTLE", "MILITARY", "INVASION", "STRIKE", "GLOBAL WAR", "WORLD WAR"]
        if any(k in text_upper for k in war_keywords):
            # 军工和能源股看涨，金融/消费/技术/物流看跌
            if sector in ["MILITARY", "ENERGY"]:
                text_impact += 0.8  # 强烈看涨
            elif sector in ["FINANCE", "CONSUMER", "TECH", "LOGISTICS", "HEALTHCARE"]:
                text_impact -= 0.7  # 强烈看跌
            else:
                text_impact -= 0.3 # 整体不确定性
        
        # 增长关键词
        if any(k in text_upper for k in ["GROWTH", "BOOM", "SUCCESS", "RECOVERY"]):
            text_impact += 0.4
            
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
    use_llm: bool = False,
) -> Tuple[EventEnvelopeJson, EventEnvelopeJson | None]:
    llm_result = None
    if use_llm:
        llm_result = _llm_decide_from_news(
            symbol=symbol,
            visual_truth=visual_truth,
            news_text=news_text or "",
            price_series=price_series,
        )

    if llm_result is not None:
        action = str(llm_result.get("action") or "HOLD").upper()
        confidence = float(llm_result.get("confidence") or 0.0)
        w_visual = float(llm_result.get("w_visual") or 0.0)
        w_text = float(llm_result.get("w_text") or 0.0)
        w_trend = float(llm_result.get("w_trend") or 0.0)
    else:
        action, score = _score_decision(visual_truth, symbol, price_series, news_text=news_text)
        confidence = abs(float(score))
        w_visual, w_text, w_trend = 0.3, 0.7, 0.0

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
        # 增加交易规模：不再是固定的 1.0 股
        # 根据信心指数和机器人类型分配规模
        # 散户机器人通常 10-100 股，机构机器人（inst）通常 1000-10000 股
        base_size = 10.0
        if "inst" in bot_id:
            base_size = 1000.0
        
        # 随信心指数指数级增长
        size = base_size * (2 ** (confidence * 3))
        # 增加一些随机性
        import random
        size *= random.uniform(0.8, 1.2)

        intent_payload = TradeIntentSubmittedPayload(
            intent_id=str(uuid4()),
            user_id="commonbot:" + bot_id,
            symbol=symbol,
            side=action,
            size=float(round(size, 2)),
            price_hint=price_series[-1] if price_series else None,
            confidence=confidence, # v0.2: 直接传入信心指数
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
    price_series: List[float],
) -> Dict[str, Any] | None:
    client = OpenRouterClient.from_env()
    if client is None:
        return None

    trend = _price_trend(price_series)

    system = (
        "你是一个在极端金融危机中博弈的市场参与者(common bot)。你的目标是极度贪婪或极度恐惧。不要平庸。"
        "你只能输出 JSON，不要输出其它文字。"
        "根据新闻的视觉真相、文本、以及价格趋势，生成极具攻击性的交易动作。"
        "action 只能是 BUY/SELL/HOLD。confidence 在 0~1 之间。"
        "如果你看到战争、冲突、危机等词汇，且涉及的是军工股，你应该狂热买入；如果是消费或金融，你应该恐慌性抛售。"
        "同时给出权重 w_visual/w_text/w_trend（0~1）。"
    )

    user = (
        "请输出 JSON："
        "{\"action\":\"BUY|SELL|HOLD\",\"confidence\":0.0,"
        "\"w_visual\":0.0,\"w_text\":0.0,\"w_trend\":0.0}.\n"
        f"symbol: {symbol}\n"
        f"visual_truth: {visual_truth}\n"
        f"news_text: {news_text}\n"
        f"price_trend: {trend}\n"
    )

    # v0.2: 增加 max_tokens 防止 JSON 被截断，提升稳定性
    resp = client.chat_completions(system=system, user=user, temperature=0.2, max_tokens=512)
    if not resp or "choices" not in resp:
        print(f"[LLM:CommonBot] LLM Request failed for {symbol}, falling back to heuristics.")
        return None

    text = extract_first_message_text(resp)
    # v0.2: 使用更鲁棒的 JSON 提取方法，解决 Markdown 代码块或 LLM 废话干扰
    clean_text = text.strip()
    try:
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")
        if start_idx != -1 and end_idx != -1:
            clean_text = clean_text[start_idx : end_idx + 1]
        
        obj = __import__("json").loads(clean_text)
    except Exception as e:
        print(f"[LLM:CommonBot] JSON parse error for {symbol}: {e}. Text: {text[:200]}. Falling back to heuristics.")
        return None

    if not isinstance(obj, dict):
        return None
    return obj
