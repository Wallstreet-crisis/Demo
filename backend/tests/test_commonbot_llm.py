from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_commonbot_fallback_without_openrouter_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from ifrontier.services.commonbot import run_commonbot_for_earnings

    decision, trade = run_commonbot_for_earnings(
        symbol="BLUEGOLD",
        visual_truth="PROFIT",
        price_series=[10.0, 10.5],
        bot_id="commonbot:test",
        correlation_id=uuid4(),
        news_text="headline",
        use_llm=True,
    )

    from ifrontier.domain.events.types import EventType

    decision_type = getattr(decision.event_type, "value", None)
    if decision_type is None:
        decision_type = str(decision.event_type)
    assert decision_type in {
        "ai.commonbot.decision",
        "EventType.AI_COMMONBOT_DECISION",
        EventType.AI_COMMONBOT_DECISION.value,
    }
    if trade is not None:
        trade_type = getattr(trade.event_type, "value", None)
        if trade_type is None:
            trade_type = str(trade.event_type)
        assert trade_type in {
            "trade.intent_submitted",
            "EventType.TRADE_INTENT_SUBMITTED",
            EventType.TRADE_INTENT_SUBMITTED.value,
        }


def test_commonbot_llm_parses_openrouter_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

    # mock urllib.request.urlopen used in OpenRouterClient
    import io
    from urllib import request as ureq

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                '{"choices":[{"message":{"content":"{\\"action\\":\\"BUY\\",\\"confidence\\":0.8,\\"w_visual\\":0.6,\\"w_text\\":0.3,\\"w_trend\\":0.1}"}}]}'
            ).encode("utf-8")

    def _fake_urlopen(req, timeout=0):
        return _FakeResp()

    monkeypatch.setattr(ureq, "urlopen", _fake_urlopen)

    from ifrontier.services.commonbot import run_commonbot_for_earnings

    decision, trade = run_commonbot_for_earnings(
        symbol="BLUEGOLD",
        visual_truth="PROFIT",
        price_series=[10.0, 10.5],
        bot_id="commonbot:test",
        correlation_id=uuid4(),
        news_text="headline",
        use_llm=True,
    )

    payload = decision.payload or {}
    assert str(payload.get("action")) == "BUY"
    assert float(payload.get("confidence")) == 0.8
    assert float(payload.get("w_text")) == 0.3
    assert trade is not None
