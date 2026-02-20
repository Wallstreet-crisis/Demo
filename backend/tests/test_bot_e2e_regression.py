from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.domain.events.envelope import EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.infra.sqlite.ledger import create_account
from ifrontier.services.commonbot_emergency import CommonBotCohortConfig, CommonBotEmergencyRunner
from ifrontier.services import commonbot_emergency as emergency_module


class _FakeNewsService:
    def __init__(self, ctx: dict):
        self._ctx = ctx

    def get_variant_context(self, variant_id: str):
        return dict(self._ctx)

    def list_inbox(self, player_id: str, limit: int = 5):
        return [{"text": self._ctx.get("text", ""), "created_at": datetime.now(timezone.utc).isoformat()}]


def _reset_db() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM ledger_entries")
        conn.execute("DELETE FROM positions")
        conn.execute("DELETE FROM accounts")
        conn.execute("DELETE FROM orders")


def _fake_match_list():
    return [SimpleNamespace(executed_event=SimpleNamespace(model_dump=lambda: {"event_type": "trade.executed"}))]


def _make_broadcast_event(variant_id: str) -> EventEnvelopeJson:
    return EventEnvelopeJson(
        event_id=uuid4(),
        event_type=str(EventType.NEWS_BROADCASTED),
        occurred_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
        causation_id=None,
        actor={"agent_id": "e2e-test"},
        payload={"channel": "GLOBAL_MANDATORY", "variant_id": variant_id},
    )


def test_e2e_forced_news_prefers_market_when_urgent(monkeypatch) -> None:
    _reset_db()
    create_account("bot:ret:1", owner_type="bot", initial_cash=200000.0)

    called = {"market": 0, "limit": 0}

    def _fake_market_order(**kwargs):
        called["market"] += 1
        return _fake_match_list()

    def _fake_limit_order(**kwargs):
        called["limit"] += 1
        return "oid", _fake_match_list()

    async def _fake_broadcast(channel, payload):
        return None

    monkeypatch.setattr(emergency_module, "submit_market_order", _fake_market_order)
    monkeypatch.setattr(emergency_module, "submit_limit_order", _fake_limit_order)
    monkeypatch.setattr(emergency_module.hub, "broadcast_json", _fake_broadcast)

    news = _FakeNewsService(
        {
            "text": "major event impacts bluegold strongly",
            "symbols": ["BLUEGOLD"],
            "truth_payload": {"kind": "MAJOR_EVENT", "impact_map": {"BLUEGOLD": "UP"}},
            "author_id": "system",
            "mutation_depth": 0,
        }
    )

    cohort = CommonBotCohortConfig(
        cohort_id="ret_urgent",
        bot_id="commonbot:ret_urgent",
        account_id="bot:ret:1",
        use_llm=False,
        is_insider=False,
        rumor_sensitivity=1.0,
        risk_appetite=0.0,  # 提升 urgency，触发市价逻辑
        llm_preference=0.0,
    )

    runner = CommonBotEmergencyRunner(news=news, event_store=MagicMock(), cohorts=[cohort])
    ev = _make_broadcast_event("v-e2e-urgent")

    emitted = asyncio.run(runner.maybe_react(broadcast_event=ev, force=True))

    assert len(emitted) >= 2  # decision + trade_intent
    assert called["market"] >= 1
    assert called["limit"] == 0


def test_e2e_conflicting_news_falls_back_to_limit(monkeypatch) -> None:
    _reset_db()
    create_account("bot:ret:1", owner_type="bot", initial_cash=200000.0)

    called = {"market": 0, "limit": 0}

    def _fake_market_order(**kwargs):
        called["market"] += 1
        return _fake_match_list()

    def _fake_limit_order(**kwargs):
        called["limit"] += 1
        return "oid", _fake_match_list()

    async def _fake_broadcast(channel, payload):
        return None

    monkeypatch.setattr(emergency_module, "submit_market_order", _fake_market_order)
    monkeypatch.setattr(emergency_module, "submit_limit_order", _fake_limit_order)
    monkeypatch.setattr(emergency_module.hub, "broadcast_json", _fake_broadcast)

    news = _FakeNewsService(
        {
            "text": "major event says bluegold up",
            "symbols": ["BLUEGOLD"],
            "truth_payload": {"kind": "MAJOR_EVENT", "impact_map": {"BLUEGOLD": "UP"}},
            "author_id": "system",
            "mutation_depth": 0,
        }
    )

    cohort = CommonBotCohortConfig(
        cohort_id="ret_conflict",
        bot_id="commonbot:ret_conflict",
        account_id="bot:ret:1",
        use_llm=False,
        is_insider=False,
        rumor_sensitivity=1.0,
        risk_appetite=0.0,
        llm_preference=0.0,
    )

    runner = CommonBotEmergencyRunner(news=news, event_store=MagicMock(), cohorts=[cohort])

    # 为了稳定复现执行层分支，这里固定 high-conflict outlook。
    # 聚合引擎叠加/冲突行为已在 test_news_intelligence_engine.py 覆盖。
    monkeypatch.setattr(
        runner._intel,
        "symbol_outlook",
        lambda **kwargs: SimpleNamespace(
            symbol="BLUEGOLD",
            net_bias=0.72,
            confidence=0.85,
            urgency=0.91,
            conflict=0.92,
            corroboration=0.4,
        ),
    )

    ev = _make_broadcast_event("v-e2e-conflict")
    emitted = asyncio.run(runner.maybe_react(broadcast_event=ev, force=True))

    assert len(emitted) >= 2
    assert called["limit"] >= 1
    assert called["market"] == 0


def test_e2e_real_aggregation_loose_assertions(monkeypatch) -> None:
    """不 mock 聚合结果，仅做宽松回归断言。

    目标：在真实聚合参数驱动下，确认 bot 至少会选择一种执行路径，
    且执行路径与当下聚合出的 urgency/conflict 保持一致。
    """
    _reset_db()
    create_account("bot:ret:1", owner_type="bot", initial_cash=200000.0)

    called = {"market": 0, "limit": 0}

    def _fake_market_order(**kwargs):
        called["market"] += 1
        return _fake_match_list()

    def _fake_limit_order(**kwargs):
        called["limit"] += 1
        return "oid", _fake_match_list()

    async def _fake_broadcast(channel, payload):
        return None

    monkeypatch.setattr(emergency_module, "submit_market_order", _fake_market_order)
    monkeypatch.setattr(emergency_module, "submit_limit_order", _fake_limit_order)
    monkeypatch.setattr(emergency_module.hub, "broadcast_json", _fake_broadcast)

    news = _FakeNewsService(
        {
            "text": "market uncertainty with mixed impact on bluegold",
            "symbols": ["BLUEGOLD"],
            "truth_payload": {"kind": "MAJOR_EVENT", "impact_map": {"BLUEGOLD": "UP"}},
            "author_id": "system",
            "mutation_depth": 0,
        }
    )

    cohort = CommonBotCohortConfig(
        cohort_id="ret_real_agg",
        bot_id="commonbot:ret_real_agg",
        account_id="bot:ret:1",
        use_llm=False,
        is_insider=False,
        rumor_sensitivity=1.0,
        risk_appetite=0.0,
        llm_preference=0.0,
    )

    runner = CommonBotEmergencyRunner(news=news, event_store=MagicMock(), cohorts=[cohort])

    # 注入一条反向弱信号，形成“真实聚合”的混合态（非强制覆盖）
    opposite = runner._intel.build_signal(
        variant_id="v-real-opposite",
        news_text="rumor says bluegold down slightly",
        symbols=["BLUEGOLD"],
        truth_payload={"kind": "RUMOR", "impact_map": {"BLUEGOLD": "DOWN"}},
        author_id="user:alice",
        mutation_depth=2,
        force=False,
    )
    runner._intel.ingest(opposite)

    ev = _make_broadcast_event("v-e2e-real-agg")
    emitted = asyncio.run(runner.maybe_react(broadcast_event=ev, force=True))

    assert len(emitted) >= 2
    assert called["market"] + called["limit"] == 1

    # 用同一聚合引擎复算当前展望，做“宽松一致性”校验。
    outlook = runner._intel.symbol_outlook(symbol="BLUEGOLD", rumor_sensitivity=1.0, risk_appetite=0.0)
    if outlook.urgency >= 0.75 and outlook.conflict <= 0.65:
        assert called["market"] == 1
    else:
        assert called["limit"] == 1
