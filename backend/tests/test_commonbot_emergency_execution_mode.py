from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services import commonbot_emergency as emergency_module
from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner


def _fake_match_list():
    return [SimpleNamespace(executed_event=SimpleNamespace(model_dump=lambda: {"event_type": "trade.executed"}))]


def test_submit_trade_prefers_market_when_urgent_and_low_conflict(monkeypatch) -> None:
    runner = CommonBotEmergencyRunner(news=MagicMock(), event_store=MagicMock(), cohorts=[])

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

    asyncio.run(
        runner._submit_trade_from_intent(
            account_id="bot:ret:1",
            symbol="BLUEGOLD",
            trade_payload={"side": "BUY", "size": 10.0, "price_hint": 10.0, "confidence": 0.8},
            urgency=0.92,
            conflict=0.18,
            log_prefix="test",
        )
    )

    assert called["market"] == 1
    assert called["limit"] == 0


def test_submit_trade_prefers_limit_when_conflicted(monkeypatch) -> None:
    runner = CommonBotEmergencyRunner(news=MagicMock(), event_store=MagicMock(), cohorts=[])

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

    asyncio.run(
        runner._submit_trade_from_intent(
            account_id="bot:inst:1",
            symbol="CIVILBANK",
            trade_payload={"side": "SELL", "size": 15.0, "price_hint": 20.0, "confidence": 0.7},
            urgency=0.84,
            conflict=0.91,
            log_prefix="test",
        )
    )

    assert called["market"] == 0
    assert called["limit"] == 1
