from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Tuple


@dataclass
class NewsSignal:
    signal_id: str
    variant_id: str
    created_at: datetime
    source_type: str
    news_kind: str
    author_id: str
    mutation_depth: int
    force_level: str
    reliability_prior: float
    deception_risk: float
    intensity: float
    direction_map: Dict[str, float] = field(default_factory=dict)
    sector_map: Dict[str, float] = field(default_factory=dict)
    market_bias: float = 0.0
    ttl_seconds: int = 1800
    cluster_id: str = ""
    # 新增行为绑定相关字段
    behavior_bindings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SymbolOutlook:
    symbol: str
    net_bias: float
    confidence: float
    urgency: float
    conflict: float
    corroboration: float


class NewsIntelligenceEngine:
    """Lightweight news aggregation engine.

    目标：
    1) 聚合同类新闻并做饱和叠加，避免无限放大；
    2) 支持时效衰减；
    3) 支持同一新闻对多标的相反影响。
    """

    def __init__(self) -> None:
        self._signals: List[NewsSignal] = []

    def build_signal(
        self,
        *,
        variant_id: str,
        news_text: str,
        symbols: List[str],
        truth_payload: Dict[str, Any],
        author_id: str,
        mutation_depth: int,
        force: bool,
        now: datetime | None = None,
    ) -> NewsSignal:
        now = now or datetime.now(timezone.utc)
        payload = truth_payload or {}
        news_kind = str(payload.get("kind") or "UNKNOWN").upper()

        source_type = "system" if author_id == "system" else "player"
        if str(author_id).startswith("bot:"):
            source_type = "bot"

        force_level = "HARD" if force else ("SOFT" if str(payload.get("system_spawn") or "").lower() in {"1", "true"} else "NONE")

        direction_map: Dict[str, float] = {}
        impact_map = payload.get("impact_map") or {}
        if isinstance(impact_map, dict) and impact_map:
            for sym, direction in impact_map.items():
                direction_map[str(sym).upper()] = self._direction_to_score(direction)

        # 回退：若没给 impact_map，使用 direction 应用于显式 symbols
        if not direction_map:
            base_dir = self._direction_to_score(payload.get("direction"))
            for s in symbols:
                direction_map[str(s).upper()] = base_dir

        # 多层影响：允许 market bias，且优先使用 truth_payload 的预置参数
        market_bias = 0.0
        if news_kind in {"WORLD_EVENT", "MAJOR_EVENT"}:
            market_bias = 0.2 if sum(direction_map.values()) >= 0 else -0.2
        market_bias = float(payload.get("market_bias", market_bias) or 0.0)

        reliability_prior = float(
            payload.get("reliability_prior", self._source_reliability(source_type=source_type, news_kind=news_kind))
            or self._source_reliability(source_type=source_type, news_kind=news_kind)
        )
        deception_risk = float(
            payload.get(
                "deception_risk",
                self._deception_risk(source_type=source_type, news_kind=news_kind, mutation_depth=mutation_depth),
            )
            or self._deception_risk(source_type=source_type, news_kind=news_kind, mutation_depth=mutation_depth)
        )
        intensity = float(
            payload.get("intensity", self._intensity(news_kind=news_kind, force_level=force_level, news_text=news_text))
            or self._intensity(news_kind=news_kind, force_level=force_level, news_text=news_text)
        )
        ttl_seconds = int(payload.get("ttl_seconds", self._ttl_by_kind(news_kind)) or self._ttl_by_kind(news_kind))

        cluster_id = self._build_cluster_id(
            variant_id=variant_id,
            news_kind=news_kind,
            direction_map=direction_map,
            text=news_text,
        )

        # 提取 behavior_bindings
        # 已经在 NewsService.create_card 中合并到了 truth_payload
        bindings = {}
        for k, v in payload.items():
            if k in {
                "market_volatility", "sentiment_shift", "price_impact", 
                "insider_trading_signal", "institutional_bias", 
                "target_price_modifier", "sector_wide_impact", 
                "fundamental_shift", "macro_regime_change", "global_liquidity_delta"
            }:
                bindings[k] = v

        return NewsSignal(
            signal_id=f"sig:{variant_id}",
            variant_id=variant_id,
            created_at=now,
            source_type=source_type,
            news_kind=news_kind,
            author_id=author_id,
            mutation_depth=int(mutation_depth),
            force_level=force_level,
            reliability_prior=float(reliability_prior),
            deception_risk=float(deception_risk),
            intensity=float(intensity),
            direction_map=direction_map,
            sector_map={},
            market_bias=float(market_bias),
            ttl_seconds=int(ttl_seconds),
            cluster_id=cluster_id,
            behavior_bindings=bindings,
        )

    def ingest(self, signal: NewsSignal) -> None:
        self._signals.append(signal)
        # 控制内存，保留最近 300 条信号足够驱动短中期行为
        if len(self._signals) > 300:
            self._signals = self._signals[-300:]

    def symbol_outlook(
        self,
        *,
        symbol: str,
        now: datetime | None = None,
        rumor_sensitivity: float = 1.0,
        risk_appetite: float = 1.0,
    ) -> SymbolOutlook:
        now = now or datetime.now(timezone.utc)
        sym = str(symbol).upper()

        signed = 0.0
        absolute = 0.0
        corroboration = 0.0
        by_cluster: Dict[str, float] = {}

        for s in self._signals:
            if sym not in s.direction_map and abs(float(s.market_bias)) < 1e-9:
                continue

            age_seconds = max((now - s.created_at).total_seconds(), 0.0)
            if age_seconds > float(s.ttl_seconds):
                continue

            decay = self._decay(age_seconds=age_seconds, ttl_seconds=s.ttl_seconds)
            force_boost = 2.0 if s.force_level == "HARD" else (1.2 if s.force_level == "SOFT" else 1.0)

            reliability = float(s.reliability_prior) * (1.0 - float(s.deception_risk) * max(0.2, 1.1 - rumor_sensitivity))
            weight = float(s.intensity) * float(decay) * float(force_boost) * max(0.05, reliability)

            bindings = dict(s.behavior_bindings or {})

            market_volatility = float(bindings.get("market_volatility") or 0.0)
            if abs(market_volatility) > 1e-9:
                weight *= max(0.5, min(2.0, 1.0 + market_volatility))

            institutional_bias = float(bindings.get("institutional_bias") or 0.0)
            if abs(institutional_bias) > 1e-9:
                weight *= max(0.7, min(1.8, 1.0 + institutional_bias))

            sym_bias = float(s.direction_map.get(sym, 0.0)) + float(s.market_bias)

            price_impact = float(bindings.get("price_impact") or 0.0)
            if abs(price_impact) > 1e-9:
                sym_bias *= max(0.6, min(2.2, 1.0 + price_impact))

            tpm = float(bindings.get("target_price_modifier") or 1.0)
            if abs(tpm - 1.0) > 1e-9:
                sym_bias *= max(0.6, min(2.5, tpm))

            liquidity_delta = float(bindings.get("global_liquidity_delta") or 0.0)
            if abs(liquidity_delta) > 1e-9:
                sym_bias += max(-0.5, min(0.5, liquidity_delta))

            if bool(bindings.get("macro_regime_change")):
                weight *= 1.1

            contribution = weight * sym_bias

            # 同簇饱和累加，避免重复新闻无限放大
            by_cluster[s.cluster_id] = by_cluster.get(s.cluster_id, 0.0) + contribution

        if by_cluster:
            saturated_values = [1.4 * math.tanh(v / 1.1) for v in by_cluster.values()]
            signed = float(sum(saturated_values))
            absolute = float(sum(abs(v) for v in saturated_values))
            corroboration = float(sum(1.0 for v in saturated_values if abs(v) > 0.2) / max(len(saturated_values), 1))

        conflict = 0.0
        if absolute > 1e-9:
            conflict = max(0.0, min(1.0, (absolute - abs(signed)) / absolute))

        net_bias = max(-1.0, min(1.0, signed))
        confidence = max(0.05, min(1.0, abs(net_bias) * (1.0 - 0.55 * conflict) + 0.1 * corroboration))

        urgency = max(0.0, min(1.0, 0.65 * abs(net_bias) + 0.25 * conflict + 0.2 * (1.0 - risk_appetite)))
        if abs(net_bias) >= 0.35 and confidence >= 0.55:
            urgency = max(urgency, 0.45)

        if any(bool((s.behavior_bindings or {}).get("insider_trading_signal")) for s in self._signals):
            urgency = max(urgency, 0.55)

        return SymbolOutlook(
            symbol=sym,
            net_bias=float(net_bias),
            confidence=float(confidence),
            urgency=float(urgency),
            conflict=float(conflict),
            corroboration=float(corroboration),
        )

    @staticmethod
    def _direction_to_score(direction: Any) -> float:
        d = str(direction or "").upper()
        if d in {"UP", "BULL", "BULLISH", "BUY"}:
            return 1.0
        if d in {"DOWN", "BEAR", "BEARISH", "SELL"}:
            return -1.0
        if d in {"STABLE", "NEUTRAL", "HOLD"}:
            return 0.0
        try:
            return max(-1.0, min(1.0, float(direction)))
        except Exception:
            return 0.0

    @staticmethod
    def _source_reliability(*, source_type: str, news_kind: str) -> float:
        if source_type == "system" and news_kind in {"WORLD_EVENT", "MAJOR_EVENT", "EARNINGS", "DISCLOSURE"}:
            return 0.92
        if news_kind in {"RUMOR", "LEAK", "OMEN"}:
            return 0.42
        if source_type == "player":
            return 0.55
        return 0.65

    @staticmethod
    def _deception_risk(*, source_type: str, news_kind: str, mutation_depth: int) -> float:
        base = 0.1
        if news_kind in {"RUMOR", "LEAK", "OMEN"}:
            base = 0.45
        if source_type == "player":
            base += 0.15
        base += min(max(mutation_depth, 0), 5) * 0.06
        return max(0.0, min(0.95, base))

    @staticmethod
    def _intensity(*, news_kind: str, force_level: str, news_text: str) -> float:
        base = 0.45
        if news_kind in {"WORLD_EVENT", "MAJOR_EVENT"}:
            base = 0.9
        elif news_kind in {"EARNINGS", "DISCLOSURE"}:
            base = 0.7
        elif news_kind in {"RUMOR", "LEAK", "OMEN"}:
            base = 0.5

        text_up = str(news_text or "").upper()
        if any(k in text_up for k in ["WAR", "CRISIS", "停产", "挤兑", "崩盘", "禁令"]):
            base += 0.12
        if force_level == "HARD":
            base += 0.2
        return max(0.1, min(1.0, base))

    @staticmethod
    def _ttl_by_kind(news_kind: str) -> int:
        if news_kind in {"WORLD_EVENT", "MAJOR_EVENT"}:
            return 4 * 3600
        if news_kind in {"EARNINGS", "DISCLOSURE"}:
            return 2 * 3600
        if news_kind in {"RUMOR", "LEAK", "OMEN"}:
            return 20 * 60
        return 45 * 60

    @staticmethod
    def _decay(*, age_seconds: float, ttl_seconds: int) -> float:
        half_life = max(float(ttl_seconds) * 0.5, 60.0)
        return math.pow(2.0, -float(age_seconds) / half_life)

    @staticmethod
    def _build_cluster_id(*, variant_id: str, news_kind: str, direction_map: Dict[str, float], text: str) -> str:
        # 相似新闻聚类：按 kind + 目标集合 + 方向签名 + 文本前缀
        target_sig = ",".join(sorted(f"{k}:{round(v, 2)}" for k, v in direction_map.items()))
        prefix = str(text or "").strip().lower()[:80]
        if not prefix:
            prefix = variant_id
        return f"{news_kind}|{target_sig}|{prefix}"
