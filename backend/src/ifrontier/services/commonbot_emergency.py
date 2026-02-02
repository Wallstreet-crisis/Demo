from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from ifrontier.domain.events.envelope import EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.services.commonbot import run_commonbot_for_earnings
from ifrontier.services.commonbot_context import (
    CommonBotMarketTrends,
    CommonBotSharedContext,
    build_context_from_account_snapshot,
    load_account_snapshot,
)
from ifrontier.services.market_analytics import get_quote
from ifrontier.services.game_time import load_game_time_config_from_env
from ifrontier.services.market_session import MarketPhase, get_market_session
from ifrontier.infra.sqlite.market import get_price_series
from ifrontier.services.news import NewsService


@dataclass(frozen=True)
class CommonBotCohortConfig:
    cohort_id: str
    bot_id: str
    account_id: str
    use_llm: bool
    max_news_items: int = 10


@dataclass(frozen=True)
class _PendingMarketOpenReaction:
    correlation_id: UUID
    variant_id: str
    news_text: str
    symbols: List[str]


class CommonBotEmergencyRunner:
    def __init__(
        self,
        *,
        news: NewsService,
        event_store: Neo4jEventStore,
        cohorts: List[CommonBotCohortConfig] | None = None,
        market_data_provider: Callable[[List[str]], CommonBotMarketTrends] | None = None,
    ) -> None:
        self._news = news
        self._event_store = event_store
        self._cohorts = cohorts or [
            CommonBotCohortConfig(
                cohort_id="retail",
                bot_id="commonbot:retail:cohort",
                account_id="bot:ret:1",
                use_llm=False,
            ),
            CommonBotCohortConfig(
                cohort_id="institutional",
                bot_id="commonbot:institutional:cohort",
                account_id="bot:inst:1",
                use_llm=True,
            ),
        ]
        self._market_data_provider = market_data_provider
        self._pending_market_open: _PendingMarketOpenReaction | None = None

    def maybe_react(
        self,
        *,
        broadcast_event: EventEnvelopeJson,
        force: bool = False,
    ) -> List[EventEnvelopeJson]:
        if not self._is_news_broadcasted(broadcast_event.event_type):
            return []

        payload = broadcast_event.payload or {}
        channel = str(payload.get("channel") or "")
        if not force and channel != "GLOBAL_MANDATORY":
            return []

        variant_id = str(payload.get("variant_id") or "")
        if not variant_id:
            return []

        variant_text, symbols = self._load_variant_text_and_symbols(variant_id)
        if not symbols:
            return []

        emitted: List[EventEnvelopeJson] = []
        corr = broadcast_event.correlation_id or uuid4()

        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        market_phase = session.phase

        for cohort in self._cohorts:
            ctx = self._build_shared_context(cohort=cohort, variant_id=variant_id, news_text=variant_text, symbols=symbols)
            if ctx is None:
                continue
            for symbol in symbols[:1]:
                decision_json, trade_json = run_commonbot_for_earnings(
                    symbol=symbol,
                    visual_truth="UNKNOWN",
                    price_series=ctx.trends.symbol_price_series.get(symbol, []),
                    bot_id=cohort.bot_id,
                    correlation_id=corr,
                    news_text="\n".join(ctx.recent_news_texts),
                    use_llm=cohort.use_llm,
                )

                self._event_store.append(decision_json)
                emitted.append(decision_json)

                if market_phase != MarketPhase.TRADING:
                    # 休市期间仅产生可观测的决策事件，且记录“开市补决策”状态。
                    self._pending_market_open = _PendingMarketOpenReaction(
                        correlation_id=corr,
                        variant_id=variant_id,
                        news_text=variant_text,
                        symbols=list(symbols),
                    )
                    continue

                if trade_json is not None:
                    self._event_store.append(trade_json)
                    emitted.append(trade_json)

        return emitted

    def maybe_react_on_market_open(self) -> List[EventEnvelopeJson]:
        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        if session.phase != MarketPhase.TRADING:
            return []

        pending = self._pending_market_open
        if pending is None:
            return []
        # 清除 pending，避免反复触发
        self._pending_market_open = None

        emitted: List[EventEnvelopeJson] = []
        for cohort in self._cohorts:
            ctx = self._build_shared_context(
                cohort=cohort,
                variant_id=pending.variant_id,
                news_text=pending.news_text,
                symbols=pending.symbols,
            )
            if ctx is None:
                continue

            for symbol in pending.symbols[:1]:
                decision_json, trade_json = run_commonbot_for_earnings(
                    symbol=symbol,
                    visual_truth="UNKNOWN",
                    price_series=ctx.trends.symbol_price_series.get(symbol, []),
                    bot_id=cohort.bot_id,
                    correlation_id=pending.correlation_id,
                    news_text="\n".join(ctx.recent_news_texts),
                    use_llm=cohort.use_llm,
                )
                self._event_store.append(decision_json)
                emitted.append(decision_json)

                if trade_json is not None:
                    self._event_store.append(trade_json)
                    emitted.append(trade_json)

        return emitted

    def _build_shared_context(
        self,
        *,
        cohort: CommonBotCohortConfig,
        variant_id: str,
        news_text: str,
        symbols: List[str],
    ) -> CommonBotSharedContext | None:
        try:
            snap = load_account_snapshot(cohort.account_id)
        except ValueError:
            return None

        recent_variant_ids = [variant_id]
        recent_news_texts = [news_text] if news_text else []

        trends = CommonBotMarketTrends()
        if self._market_data_provider is not None:
            trends = self._market_data_provider(symbols)
        else:
            cfg = load_game_time_config_from_env()
            session = get_market_session(cfg=cfg)
            trends.market_phase = session.phase.value
            for s in symbols:
                q = get_quote(s)
                trends.market_quotes[s] = {
                    "symbol": q.symbol,
                    "last_price": q.last_price,
                    "prev_price": q.prev_price,
                    "change_pct": q.change_pct,
                    "ma_5": q.ma_5,
                    "ma_20": q.ma_20,
                    "vol_20": q.vol_20,
                }
                trends.symbol_price_series[s] = get_price_series(symbol=s, limit=200)

        return build_context_from_account_snapshot(
            cohort_id=cohort.cohort_id,
            account_snapshot=snap,
            recent_news_texts=recent_news_texts[: cohort.max_news_items],
            recent_variant_ids=recent_variant_ids[: cohort.max_news_items],
            trends=trends,
        )

    def _load_variant_text_and_symbols(self, variant_id: str) -> Tuple[str, List[str]]:
        rec = self._news.get_variant_context(variant_id=variant_id)
        text = str((rec or {}).get("text") or "")
        symbols = rec.get("symbols") if isinstance(rec, dict) else None
        if not isinstance(symbols, list):
            symbols = []
        symbols = [str(s) for s in symbols if s]
        return text, symbols

    @staticmethod
    def _is_news_broadcasted(event_type: str) -> bool:
        et = getattr(event_type, "value", event_type)
        return str(et) in {
            str(EventType.NEWS_BROADCASTED),
            EventType.NEWS_BROADCASTED.value,
        }
