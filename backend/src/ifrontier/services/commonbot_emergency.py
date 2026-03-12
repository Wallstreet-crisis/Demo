from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from ifrontier.domain.events.envelope import EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.event_store import SqliteEventStore
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
from ifrontier.services.matching import submit_limit_order, submit_market_order
from ifrontier.services.news_intelligence import NewsIntelligenceEngine
from ifrontier.app.ws import hub


@dataclass(frozen=True)
class CommonBotCohortConfig:
    cohort_id: str
    bot_id: str
    account_id: str
    use_llm: bool
    is_insider: bool = False
    max_news_items: int = 10
    rumor_sensitivity: float = 1.0
    risk_appetite: float = 1.0
    llm_preference: float = 0.2


@dataclass(frozen=True)
class _PendingMarketOpenReaction:
    correlation_id: UUID
    variant_id: str
    news_text: str
    symbols: List[str]
    truth_payload: Dict[str, Any]


class CommonBotEmergencyRunner:
    def __init__(
        self,
        *,
        news: NewsService,
        event_store: SqliteEventStore,
        cohorts: List[CommonBotCohortConfig] | None = None,
        market_data_provider: Callable[[List[str]], CommonBotMarketTrends] | None = None,
    ) -> None:
        self._news = news
        self._event_store = event_store
        self._cohorts = cohorts or [
            CommonBotCohortConfig(cohort_id="ret_fast_1", bot_id="commonbot:ret_fast_1", account_id="bot:ret:1", use_llm=True, is_insider=False, rumor_sensitivity=1.35, risk_appetite=1.05, llm_preference=0.35),
            CommonBotCohortConfig(cohort_id="ret_fast_2", bot_id="commonbot:ret_fast_2", account_id="bot:ret:2", use_llm=True, is_insider=False, rumor_sensitivity=1.3, risk_appetite=1.0, llm_preference=0.3),
            CommonBotCohortConfig(cohort_id="ret_slow_1", bot_id="commonbot:ret_slow_1", account_id="bot:ret:3", use_llm=False, is_insider=False, rumor_sensitivity=1.1, risk_appetite=0.8, llm_preference=0.1),
            CommonBotCohortConfig(cohort_id="inst_momentum", bot_id="commonbot:inst_momentum", account_id="bot:inst:1", use_llm=True, is_insider=True, rumor_sensitivity=0.65, risk_appetite=1.15, llm_preference=0.25),
            CommonBotCohortConfig(cohort_id="inst_meanrev", bot_id="commonbot:inst_meanrev", account_id="bot:inst:2", use_llm=False, is_insider=True, rumor_sensitivity=0.7, risk_appetite=0.7, llm_preference=0.1),
            CommonBotCohortConfig(cohort_id="insider_sector", bot_id="commonbot:insider_sector", account_id="bot:inst:3", use_llm=True, is_insider=True, rumor_sensitivity=0.55, risk_appetite=0.9, llm_preference=0.2),
        ]
        self._market_data_provider = market_data_provider
        self._pending_market_open: _PendingMarketOpenReaction | None = None
        self._intel = NewsIntelligenceEngine()

    async def maybe_react(
        self,
        *,
        broadcast_event: EventEnvelopeJson,
        force: bool = False,
    ) -> List[EventEnvelopeJson]:
        print(f"[CommonBotEmergency:maybe_react] Triggered by {broadcast_event.event_type}")
        if not self._is_news_broadcasted(broadcast_event.event_type):
            return []

        payload = broadcast_event.payload or {}
        channel = str(payload.get("channel") or "")
        # 放宽限制：除了 GLOBAL_MANDATORY，非强制频道也有概率触发（模拟机器人注意力）
        import random
        if not force and channel != "GLOBAL_MANDATORY" and random.random() > 0.4:
            return []

        variant_id = str(payload.get("variant_id") or "")
        if not variant_id:
            return []

        ctx_news = self._load_variant_context(variant_id)
        variant_text = str(ctx_news.get("text") or "")
        symbols = ctx_news.get("symbols") or []
        truth_payload = ctx_news.get("truth_payload") or {}
        author_id = str(ctx_news.get("author_id") or "system")
        mutation_depth = int(ctx_news.get("mutation_depth") or 0)

        if not symbols:
            # v0.1: 对于 WORLD_EVENT 等可能影响全局的新闻，如果没定义符号，则赋予默认关键证券
            symbols = ["BLUEGOLD", "MARS_GEN", "CIVILBANK", "NEURALINK"]
            print(f"[CommonBotEmergency:maybe_react] News {variant_id} has no symbols, using defaults: {symbols}")

        signal = self._intel.build_signal(
            variant_id=variant_id,
            news_text=variant_text,
            symbols=symbols,
            truth_payload=truth_payload,
            author_id=author_id,
            mutation_depth=mutation_depth,
            force=force or channel == "GLOBAL_MANDATORY",
        )
        self._intel.ingest(signal)

        emitted: List[EventEnvelopeJson] = []
        corr = broadcast_event.correlation_id or uuid4()
        
        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        market_phase = session.phase

        for cohort in self._cohorts:
            # 获取该机器人的新闻窗口（带时间戳）
            recent_news_items = []
            try:
                # 获取机器人收件箱中的最近新闻
                inbox = self._news.list_inbox(player_id=cohort.account_id, limit=5)
                recent_news_items = [
                    {"text": item["text"], "delivered_at": item["created_at"]} 
                    for item in inbox
                ]
            except Exception:
                recent_news_items = []

            ctx = self._build_shared_context(
                cohort=cohort, 
                variant_id=variant_id, 
                news_text=variant_text, 
                symbols=symbols,
                recent_news_items=recent_news_items
            )
            if ctx is None:
                continue
            
            for symbol in symbols:
                outlook = self._intel.symbol_outlook(
                    symbol=symbol,
                    rumor_sensitivity=cohort.rumor_sensitivity,
                    risk_appetite=cohort.risk_appetite,
                )
                decision_json, trade_json = run_commonbot_for_earnings(
                    symbol=symbol,
                    visual_truth="UNKNOWN",
                    price_series=ctx.trends.symbol_price_series.get(symbol, []),
                    bot_id=cohort.bot_id,
                    correlation_id=corr,
                    news_text=variant_text,
                    news_window=ctx.recent_news_items, # 传入新闻序列
                    use_llm=cohort.use_llm,
                    truth_payload=truth_payload,
                    is_insider=cohort.is_insider,
                    author_id=author_id,
                    mutation_depth=mutation_depth,
                    strategy_signal={
                        "net_bias": outlook.net_bias,
                        "confidence": outlook.confidence,
                        "urgency": outlook.urgency,
                        "conflict": outlook.conflict,
                    },
                    llm_policy={
                        "force_level": signal.force_level,
                        "prefer_llm": bool(outlook.conflict >= 0.55 or cohort.llm_preference > 0.22),
                    },
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
                        truth_payload=truth_payload,
                    )
                    continue

                if trade_json is not None:
                    self._event_store.append(trade_json)
                    emitted.append(trade_json)
                    await self._submit_trade_from_intent(
                        account_id=cohort.account_id,
                        symbol=symbol,
                        trade_payload=trade_json.payload,
                        urgency=outlook.urgency,
                        conflict=outlook.conflict,
                        log_prefix="maybe_react",
                    )

        return emitted

    async def maybe_react_on_market_open(self) -> List[EventEnvelopeJson]:
        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        if session.phase != MarketPhase.TRADING:
            return []

        pending = self._pending_market_open
        if pending is None:
            return []
        # 清除 pending，避免反复触发
        self._pending_market_open = None

        ctx_news = self._load_variant_context(pending.variant_id)
        variant_text = str(ctx_news.get("text") or pending.news_text)
        symbols = list(ctx_news.get("symbols") or pending.symbols)
        author_id = str(ctx_news.get("author_id") or "system")
        mutation_depth = int(ctx_news.get("mutation_depth") or 0)

        signal = self._intel.build_signal(
            variant_id=pending.variant_id,
            news_text=variant_text,
            symbols=symbols,
            truth_payload=pending.truth_payload,
            author_id=author_id,
            mutation_depth=mutation_depth,
            force=True,
        )
        self._intel.ingest(signal)

        emitted: List[EventEnvelopeJson] = []
        for cohort in self._cohorts:
            # 获取该机器人的新闻窗口（带时间戳）
            recent_news_items = []
            try:
                inbox = self._news.list_inbox(player_id=cohort.account_id, limit=5)
                recent_news_items = [
                    {"text": item["text"], "delivered_at": item["created_at"]} 
                    for item in inbox
                ]
            except Exception:
                recent_news_items = []

            ctx = self._build_shared_context(
                cohort=cohort,
                variant_id=pending.variant_id,
                news_text=pending.news_text,
                symbols=symbols,
                recent_news_items=recent_news_items
            )
            if ctx is None:
                continue

            for symbol in symbols[:1]:
                outlook = self._intel.symbol_outlook(
                    symbol=symbol,
                    rumor_sensitivity=cohort.rumor_sensitivity,
                    risk_appetite=cohort.risk_appetite,
                )
                decision_json, trade_json = run_commonbot_for_earnings(
                    symbol=symbol,
                    visual_truth="UNKNOWN",
                    price_series=ctx.trends.symbol_price_series.get(symbol, []),
                    bot_id=cohort.bot_id,
                    correlation_id=pending.correlation_id,
                    news_text=pending.news_text,
                    news_window=ctx.recent_news_items,
                    use_llm=cohort.use_llm,
                    truth_payload=pending.truth_payload,
                    is_insider=cohort.is_insider,
                    author_id=author_id,
                    mutation_depth=mutation_depth,
                    strategy_signal={
                        "net_bias": outlook.net_bias,
                        "confidence": outlook.confidence,
                        "urgency": outlook.urgency,
                        "conflict": outlook.conflict,
                    },
                    llm_policy={
                        "force_level": signal.force_level,
                        "prefer_llm": bool(outlook.conflict >= 0.5 or cohort.llm_preference > 0.2),
                    },
                )
                self._event_store.append(decision_json)
                emitted.append(decision_json)

                if trade_json is not None:
                    self._event_store.append(trade_json)
                    emitted.append(trade_json)
                    await self._submit_trade_from_intent(
                        account_id=cohort.account_id,
                        symbol=symbol,
                        trade_payload=trade_json.payload,
                        urgency=outlook.urgency,
                        conflict=outlook.conflict,
                        log_prefix="open",
                    )

        return emitted

    def _build_shared_context(
        self,
        *,
        cohort: CommonBotCohortConfig,
        variant_id: str,
        news_text: str,
        symbols: List[str],
        recent_news_items: List[Dict[str, Any]] | None = None,
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
            recent_news_items=recent_news_items,
            trends=trends,
        )

    def _load_variant_context(self, variant_id: str) -> Dict[str, Any]:
        rec = self._news.get_variant_context(variant_id=variant_id)
        return rec or {}

    async def react_to_delivery(
        self,
        *,
        delivery_event: EventEnvelopeJson,
    ) -> List[EventEnvelopeJson]:
        """让机器人响应直接投递给它们的新闻（如 Omen）"""
        payload = delivery_event.payload or {}
        to_player_id = str(payload.get("to_player_id") or "")
        variant_id = str(payload.get("variant_id") or "")
        
        # 查找该机器人属于哪个 cohort
        target_cohort = next((c for c in self._cohorts if c.account_id == to_player_id), None)
        if not target_cohort or not variant_id:
            return []

        print(f"[CommonBotEmergency:react_to_delivery] Bot {to_player_id} reacting to news {variant_id}")
        
        ctx_news = self._load_variant_context(variant_id)
        variant_text = str(ctx_news.get("text") or "")
        symbols = ctx_news.get("symbols") or []
        truth_payload = ctx_news.get("truth_payload") or {}
        author_id = str(ctx_news.get("author_id") or "system")
        mutation_depth = int(ctx_news.get("mutation_depth") or 0)

        if not symbols:
            symbols = ["BLUEGOLD", "MARS_GEN", "CIVILBANK", "NEURALINK"]

        signal = self._intel.build_signal(
            variant_id=variant_id,
            news_text=variant_text,
            symbols=symbols,
            truth_payload=truth_payload,
            author_id=author_id,
            mutation_depth=mutation_depth,
            force=False,
        )
        self._intel.ingest(signal)

        corr = delivery_event.correlation_id or uuid4()
        emitted: List[EventEnvelopeJson] = []
        
        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        
        # 获取该机器人的新闻窗口（带时间戳）
        recent_news_items = []
        try:
            inbox = self._news.list_inbox(player_id=to_player_id, limit=5)
            recent_news_items = [
                {"text": item["text"], "delivered_at": item["created_at"]} 
                for item in inbox
            ]
        except Exception:
            recent_news_items = []

        ctx = self._build_shared_context(
            cohort=target_cohort, 
            variant_id=variant_id, 
            news_text=variant_text, 
            symbols=symbols,
            recent_news_items=recent_news_items
        )
        if ctx is None:
            return []

        for symbol in symbols:
            outlook = self._intel.symbol_outlook(
                symbol=symbol,
                rumor_sensitivity=target_cohort.rumor_sensitivity,
                risk_appetite=target_cohort.risk_appetite,
            )
            decision_json, trade_json = run_commonbot_for_earnings(
                symbol=symbol,
                visual_truth="UNKNOWN",
                price_series=ctx.trends.symbol_price_series.get(symbol, []),
                bot_id=target_cohort.bot_id,
                correlation_id=corr,
                news_text=variant_text,
                news_window=ctx.recent_news_items,
                use_llm=target_cohort.use_llm,
                truth_payload=truth_payload,
                is_insider=target_cohort.is_insider,
                author_id=author_id,
                mutation_depth=mutation_depth,
                strategy_signal={
                    "net_bias": outlook.net_bias,
                    "confidence": outlook.confidence,
                    "urgency": outlook.urgency,
                    "conflict": outlook.conflict,
                },
                llm_policy={
                    "force_level": signal.force_level,
                    "prefer_llm": bool(outlook.conflict >= 0.5 or target_cohort.llm_preference > 0.2),
                },
            )
            self._event_store.append(decision_json)
            emitted.append(decision_json)

            if session.phase == MarketPhase.TRADING and trade_json is not None:
                self._event_store.append(trade_json)
                emitted.append(trade_json)
                await self._submit_trade_from_intent(
                    account_id=target_cohort.account_id,
                    symbol=symbol,
                    trade_payload=trade_json.payload,
                    urgency=outlook.urgency,
                    conflict=outlook.conflict,
                    log_prefix="delivery",
                )

        return emitted

    @staticmethod
    def _is_news_broadcasted(event_type: str) -> bool:
        et = getattr(event_type, "value", event_type)
        return str(et) in {
            str(EventType.NEWS_BROADCASTED),
            EventType.NEWS_BROADCASTED.value,
        }

    async def _submit_trade_from_intent(
        self,
        *,
        account_id: str,
        symbol: str,
        trade_payload: Dict[str, Any],
        urgency: float,
        conflict: float,
        log_prefix: str,
    ) -> None:
        side = str(trade_payload.get("side") or "").upper()
        if side not in {"BUY", "SELL"}:
            return

        last_price_val = trade_payload.get("price_hint")
        if last_price_val is None:
            from ifrontier.infra.sqlite.market import get_last_price

            last_price = get_last_price(symbol) or 0.0
        else:
            last_price = float(last_price_val)

        if last_price <= 0:
            print(f"[CommonBotEmergency:{log_prefix}] Skipping trade for {symbol}: invalid price {last_price}")
            return

        size = float(trade_payload.get("size") or 1.0)
        confidence = float(trade_payload.get("confidence") or 0.5)
        urgency = max(0.0, min(1.0, float(urgency)))
        conflict = max(0.0, min(1.0, float(conflict)))

        # 急切度越高越倾向市价；冲突越高越保守
        use_market_order = urgency >= 0.75 and conflict <= 0.65

        try:
            if use_market_order:
                print(
                    f"[CommonBotEmergency:{log_prefix}] {account_id} submitting MARKET {side} {symbol} qty={size:.2f} "
                    f"(urgency={urgency:.2f}, conflict={conflict:.2f})"
                )
                matches = submit_market_order(
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    quantity=size,
                )
            else:
                offset = 0.004 + (0.028 * confidence) + (0.018 * urgency)
                offset *= max(0.5, 1.0 - 0.45 * conflict)
                order_price = last_price * (1.0 + offset if side == "BUY" else 1.0 - offset)

                print(
                    f"[CommonBotEmergency:{log_prefix}] {account_id} submitting LIMIT {side} {symbol} px={order_price:.2f} qty={size:.2f} "
                    f"(offset={offset:.2%}, conf={confidence:.2f})"
                )
                _order_id, matches = submit_limit_order(
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    price=float(order_price),
                    quantity=size,
                )

            for m in matches:
                ev = m.executed_event.model_dump()
                await hub.broadcast_json("events", ev)
                ev_type = ev.get("event_type")
                if ev_type:
                    await hub.broadcast_json(str(ev_type), ev)
        except Exception as exc:
            print(f"[CommonBotEmergency:{log_prefix}] Order failed for {account_id}: {exc}")
