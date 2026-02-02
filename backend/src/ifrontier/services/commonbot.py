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
) -> Tuple[str, float]:
    profile = get_profile(symbol)
    sector = profile.sector if profile else "GENERIC"

    base = 0.0
    if visual_truth.upper() == "PROFIT":
        base = 0.7
    elif visual_truth.upper() == "LOSS":
        base = -0.7

    sector_adj = 0.0
    if sector == "MILITARY":
        sector_adj = 0.1
    elif sector == "FINANCE":
        sector_adj = -0.05

    trend = _price_trend(price_series)
    trend_adj = 0.0
    if trend > 0.05:
        trend_adj = -0.1
    elif trend < -0.05:
        trend_adj = 0.1

    score = max(min(base + sector_adj + trend_adj, 1.0), -1.0)

    if score > 0.4:
        action = "BUY"
    elif score < -0.4:
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
        action, score = _score_decision(visual_truth, symbol, price_series)
        confidence = abs(float(score))
        w_visual, w_text, w_trend = 1.0, 0.0, 0.0

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

    decision_envelope = EventEnvelope(
        event_type=EventType.AI_COMMONBOT_DECISION,
        correlation_id=correlation_id,
        actor=EventActor(agent_id=bot_id),
        payload=decision_payload,
    )

    decision_json = EventEnvelopeJson.from_envelope(decision_envelope)

    trade_json: EventEnvelopeJson | None = None
    if action in {"BUY", "SELL"}:
        intent_payload = TradeIntentSubmittedPayload(
            intent_id=str(uuid4()),
            user_id="commonbot:" + bot_id,
            symbol=symbol,
            side=action,
            size=1.0,
            price_hint=price_series[-1] if price_series else None,
            created_at=now,
        )

        intent_envelope = EventEnvelope(
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
        "你是一个市场做市机器人(common bot)。你只能输出 JSON，不要输出其它文字。"
        "根据新闻的视觉真相、文本、以及价格趋势，生成交易动作。"
        "action 只能是 BUY/SELL/HOLD。confidence 在 0~1 之间。"
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

    resp = client.chat_completions(system=system, user=user, temperature=0.2, max_tokens=200)
    text = extract_first_message_text(resp)
    try:
        obj = __import__("json").loads(text)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None
    return obj
