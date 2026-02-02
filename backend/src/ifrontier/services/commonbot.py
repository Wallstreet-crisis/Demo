from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple
from uuid import uuid4

from ifrontier.domain.assets.profile import get_profile
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    AiCommonBotDecisionPayload,
    TradeIntentSubmittedPayload,
)
from ifrontier.domain.events.types import EventType


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
) -> Tuple[EventEnvelopeJson, EventEnvelopeJson | None]:
    action, score = _score_decision(visual_truth, symbol, price_series)

    now = datetime.now(timezone.utc)

    decision_payload = AiCommonBotDecisionPayload(
        bot_id=bot_id,
        tick_id="debug-tick",
        asset_symbol=symbol,
        action=action,
        confidence=abs(score),
        w_visual=1.0,
        w_text=0.0,
        w_trend=0.0,
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
