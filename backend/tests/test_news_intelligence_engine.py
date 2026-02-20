from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.news_intelligence import NewsIntelligenceEngine


def test_news_intelligence_handles_opposite_impacts_and_stacking() -> None:
    engine = NewsIntelligenceEngine()

    s1 = engine.build_signal(
        variant_id="v-op-1",
        news_text="global shock across sectors",
        symbols=["BLUEGOLD", "CIVILBANK"],
        truth_payload={
            "kind": "WORLD_EVENT",
            "impact_map": {"BLUEGOLD": "UP", "CIVILBANK": "DOWN"},
        },
        author_id="system",
        mutation_depth=0,
        force=True,
    )
    s2 = engine.build_signal(
        variant_id="v-op-2",
        news_text="global shock across sectors",  # same text -> same cluster family
        symbols=["BLUEGOLD", "CIVILBANK"],
        truth_payload={
            "kind": "WORLD_EVENT",
            "impact_map": {"BLUEGOLD": "UP", "CIVILBANK": "DOWN"},
        },
        author_id="system",
        mutation_depth=0,
        force=True,
    )
    engine.ingest(s1)
    engine.ingest(s2)

    bg = engine.symbol_outlook(symbol="BLUEGOLD")
    cb = engine.symbol_outlook(symbol="CIVILBANK")

    assert bg.net_bias > 0.15
    assert cb.net_bias < -0.15
    assert bg.confidence > 0.1
    assert cb.confidence > 0.1


def test_news_intelligence_time_decay_reduces_influence() -> None:
    engine = NewsIntelligenceEngine()
    sig = engine.build_signal(
        variant_id="v-decay-1",
        news_text="rumor spreads quickly",
        symbols=["NEURALINK"],
        truth_payload={"kind": "RUMOR", "direction": "UP"},
        author_id="user:someone",
        mutation_depth=2,
        force=False,
    )
    engine.ingest(sig)

    fresh = engine.symbol_outlook(symbol="NEURALINK")

    # 人工推进时间（修改信号时间戳）模拟时效衰减
    engine._signals[0].created_at = engine._signals[0].created_at - timedelta(hours=3)
    decayed = engine.symbol_outlook(symbol="NEURALINK")

    assert abs(decayed.net_bias) < abs(fresh.net_bias)
    assert decayed.urgency <= fresh.urgency + 1e-9
