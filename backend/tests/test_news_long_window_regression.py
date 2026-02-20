from __future__ import annotations

from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifrontier.services.news import NewsService


def _sample_direction_score(weights: dict[str, float], rnd: random.Random) -> float:
    d = rnd.choices(
        ["UP", "DOWN", "STABLE"],
        weights=[float(weights.get("UP", 0.34)), float(weights.get("DOWN", 0.34)), float(weights.get("STABLE", 0.32))],
        k=1,
    )[0]
    if d == "UP":
        return 1.0
    if d == "DOWN":
        return -1.0
    return 0.0


def test_long_window_small_news_direction_is_not_bearish_dominated() -> None:
    """长窗口统计回归：小新闻方向不应长期偏空。"""
    svc = NewsService.__new__(NewsService)
    rnd = random.Random(20260220)

    kinds = ["RUMOR", "LEAK", "ANALYST_REPORT"]
    kind_weights = [0.34, 0.28, 0.38]

    total = 4000
    scores: list[float] = []
    downs = 0

    for _ in range(total):
        kind = rnd.choices(kinds, weights=kind_weights, k=1)[0]
        params = svc.get_preset_news_params(kind=kind)
        w = params.get("direction_weights") or {}
        score = _sample_direction_score(w, rnd)
        scores.append(score)
        if score < 0:
            downs += 1

    mean_score = sum(scores) / len(scores)
    down_ratio = downs / float(total)

    # 宽松阈值：允许随机波动，但不能显著偏空
    assert mean_score > -0.08
    assert down_ratio < 0.46


def test_long_window_theme_market_bias_is_balanced() -> None:
    """长窗口统计回归：重大主题的市场偏置长期应接近中性略偏多。"""
    svc = NewsService.__new__(NewsService)
    rnd = random.Random(20260221)

    themes = [
        "WAR",
        "FINANCIAL_CRISIS",
        "ENERGY_SHORTAGE",
        "BIO_HAZARD",
        "TECH_BREAKTHROUGH",
        "PEACE_DIVIDEND",
        "TRADE_PACT",
        "INFRA_RECOVERY",
    ]
    weights = [0.12, 0.12, 0.11, 0.10, 0.18, 0.13, 0.12, 0.12]

    total = 4000
    biases: list[float] = []

    for _ in range(total):
        theme = rnd.choices(themes, weights=weights, k=1)[0]
        params = svc.get_preset_news_params(kind="WORLD_EVENT", theme=theme)
        biases.append(float(params.get("market_bias") or 0.0))

    avg_bias = sum(biases) / len(biases)

    # 宽松阈值：不要求强偏多，但禁止显著偏空漂移
    assert avg_bias > -0.02
    assert avg_bias < 0.08
