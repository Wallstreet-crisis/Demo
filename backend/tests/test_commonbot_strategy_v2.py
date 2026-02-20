from __future__ import annotations

from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from ifrontier.services import commonbot as commonbot_module


def test_strategy_signal_can_override_single_news_noise() -> None:
    decision, trade = commonbot_module.run_commonbot_for_earnings(
        symbol="CIVILBANK",
        visual_truth="UNKNOWN",
        price_series=[10.0, 9.9, 9.8],
        bot_id="commonbot:test",
        correlation_id=uuid4(),
        news_text="mixed headline",
        use_llm=False,
        truth_payload={"kind": "RUMOR"},
        strategy_signal={
            "net_bias": 0.7,
            "confidence": 0.8,
            "urgency": 0.6,
            "conflict": 0.1,
        },
    )

    payload = decision.payload or {}
    assert str(payload.get("action")) == "BUY"
    assert float(payload.get("confidence") or 0.0) > 0.6
    assert trade is not None


def test_template_news_default_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    class _FakeClient:
        def chat_completions(self, **kwargs):
            called["n"] += 1
            return {"choices": [{"message": {"content": '{"action":"SELL","confidence":0.9,"w_visual":0.2,"w_text":0.7,"w_trend":0.1}'}}]}

    monkeypatch.setattr(commonbot_module.OpenRouterClient, "from_env", staticmethod(lambda: _FakeClient()))
    monkeypatch.setenv("IF_COMMONBOT_LLM_MAX_CALLS_PER_MIN", "100")

    # 模板新闻 + 低冲突，策略应默认跳过 LLM
    _d, _t = commonbot_module.run_commonbot_for_earnings(
        symbol="BLUEGOLD",
        visual_truth="UNKNOWN",
        price_series=[20.0, 20.1],
        bot_id="commonbot:test",
        correlation_id=uuid4(),
        news_text="system major event",
        use_llm=True,
        truth_payload={"kind": "MAJOR_EVENT"},
        llm_policy={"force_level": "NONE", "prefer_llm": False},
        strategy_signal={"net_bias": 0.0, "confidence": 0.0, "urgency": 0.0, "conflict": 0.2},
    )

    assert called["n"] == 0


def test_llm_cache_reuses_same_news_result(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    class _FakeClient:
        def chat_completions(self, **kwargs):
            called["n"] += 1
            return {"choices": [{"message": {"content": '{"action":"BUY","confidence":0.77,"w_visual":0.1,"w_text":0.8,"w_trend":0.1}'}}]}

    commonbot_module._LLM_ANALYSIS_CACHE.clear()
    commonbot_module._LLM_CALL_WINDOW.clear()

    monkeypatch.setattr(commonbot_module.OpenRouterClient, "from_env", staticmethod(lambda: _FakeClient()))
    monkeypatch.setenv("IF_COMMONBOT_LLM_MAX_CALLS_PER_MIN", "100")
    monkeypatch.setenv("IF_COMMONBOT_LLM_CACHE_TTL_SECONDS", "3600")

    kwargs = dict(
        symbol="NEURALINK",
        visual_truth="UNKNOWN",
        price_series=[8.0, 8.1, 8.3],
        bot_id="commonbot:test",
        correlation_id=uuid4(),
        news_text="custom rumor about chip export",
        use_llm=True,
        truth_payload={"kind": "RUMOR"},
        llm_policy={"force_level": "NONE", "prefer_llm": True},
        strategy_signal={"net_bias": 0.0, "confidence": 0.0, "urgency": 0.0, "conflict": 0.8},
    )

    d1, _ = commonbot_module.run_commonbot_for_earnings(**kwargs)
    d2, _ = commonbot_module.run_commonbot_for_earnings(**kwargs)

    assert called["n"] == 1
    assert str((d1.payload or {}).get("action")) == "BUY"
    assert str((d2.payload or {}).get("action")) == "BUY"
