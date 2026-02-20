from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.news import NewsService
from ifrontier.services.news_intelligence import NewsIntelligenceEngine


def test_preset_params_include_balanced_direction_weights() -> None:
    svc = NewsService.__new__(NewsService)
    rumor = svc.get_preset_news_params(kind="RUMOR")
    major = svc.get_preset_news_params(kind="MAJOR_EVENT")
    peace = svc.get_preset_news_params(kind="WORLD_EVENT", theme="PEACE_DIVIDEND")

    rw = rumor.get("direction_weights") or {}
    mw = major.get("direction_weights") or {}

    assert abs(float(rw.get("UP", 0.0)) - float(rw.get("DOWN", 0.0))) <= 0.02
    assert abs(float(mw.get("UP", 0.0)) - float(mw.get("DOWN", 0.0))) <= 0.02
    assert float(peace.get("market_bias") or 0.0) > 0.0


def test_news_intelligence_prefers_truth_payload_overrides() -> None:
    engine = NewsIntelligenceEngine()
    signal = engine.build_signal(
        variant_id="v-override-1",
        news_text="policy uplift",
        symbols=["CIVILBANK"],
        truth_payload={
            "kind": "ANALYST_REPORT",
            "direction": "UP",
            "ttl_seconds": 9999,
            "intensity": 0.77,
            "reliability_prior": 0.81,
            "deception_risk": 0.11,
            "market_bias": 0.07,
        },
        author_id="system",
        mutation_depth=0,
        force=False,
    )

    assert signal.ttl_seconds == 9999
    assert abs(signal.intensity - 0.77) < 1e-9
    assert abs(signal.reliability_prior - 0.81) < 1e-9
    assert abs(signal.deception_risk - 0.11) < 1e-9
    assert abs(signal.market_bias - 0.07) < 1e-9
