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
from ifrontier.services.matching import submit_limit_order
from ifrontier.app.ws import hub


@dataclass(frozen=True)
class CommonBotCohortConfig:
    cohort_id: str
    bot_id: str
    account_id: str
    use_llm: bool
    is_insider: bool = False
    max_news_items: int = 10


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
        event_store: Neo4jEventStore,
        cohorts: List[CommonBotCohortConfig] | None = None,
        market_data_provider: Callable[[List[str]], CommonBotMarketTrends] | None = None,
    ) -> None:
        self._news = news
        self._event_store = event_store
        self._cohorts = cohorts or [
            CommonBotCohortConfig(cohort_id=f"ret:{i}", bot_id=f"commonbot:ret:{i}", account_id=f"bot:ret:{i}", use_llm=True, is_insider=False)
            for i in range(1, 11)
        ] + [
            CommonBotCohortConfig(cohort_id=f"inst:{i}", bot_id=f"commonbot:inst:{i}", account_id=f"bot:inst:{i}", use_llm=True, is_insider=True)
            for i in range(1, 4)
        ]
        self._market_data_provider = market_data_provider
        self._pending_market_open: _PendingMarketOpenReaction | None = None

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
        if not force and channel != "GLOBAL_MANDATORY":
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
            # 确保 CommonBot 能够对重大新闻产生市场反应
            symbols = ["BLUEGOLD", "MARS_GEN", "CIVILBANK", "NEURALINK"]
            print(f"[CommonBotEmergency:maybe_react] News {variant_id} has no symbols, using defaults: {symbols}")

        emitted: List[EventEnvelopeJson] = []
        corr = broadcast_event.correlation_id or uuid4()
        print(f"[CommonBotEmergency:maybe_react] Reacting to {variant_id} for {len(self._cohorts)} cohorts. Symbols: {symbols}")

        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        market_phase = session.phase

        for cohort in self._cohorts:
            ctx = self._build_shared_context(cohort=cohort, variant_id=variant_id, news_text=variant_text, symbols=symbols)
            if ctx is None:
                continue
            for symbol in symbols:
                decision_json, trade_json = run_commonbot_for_earnings(
                    symbol=symbol,
                    visual_truth="UNKNOWN",
                    price_series=ctx.trends.symbol_price_series.get(symbol, []),
                    bot_id=cohort.bot_id,
                    correlation_id=corr,
                    news_text="\n".join(ctx.recent_news_texts),
                    use_llm=cohort.use_llm,
                    truth_payload=truth_payload,
                    is_insider=cohort.is_insider,
                    author_id=author_id,
                    mutation_depth=mutation_depth,
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
                    
                    # 真正提交订单进入撮合引擎
                    try:
                        side = str(trade_json.payload.get("side"))
                        # 从 trade_json 获取由 run_commonbot_for_earnings 计算出的动态规模和价格
                        last_price_val = trade_json.payload.get("price_hint")
                        if last_price_val is None:
                            from ifrontier.infra.sqlite.market import get_last_price
                            last_price = get_last_price(symbol) or 0.0
                        else:
                            last_price = float(last_price_val)
                            
                        if last_price <= 0:
                            print(f"[CommonBotEmergency:maybe_react] Skipping trade for {symbol}: invalid price {last_price}")
                            continue

                        size = float(trade_json.payload.get("size") or 1.0)
                        confidence = float(trade_json.payload.get("confidence") or 0.5)

                        # 使用相同的激进报价逻辑
                        offset = 0.01 + (confidence * 0.04)
                        if side == "BUY":
                            order_price = last_price * (1.0 + offset)
                        else:
                            order_price = last_price * (1.0 - offset)

                        print(f"[CommonBotEmergency:maybe_react] Bot {cohort.account_id} submitting {side} for {symbol} at {order_price:.2f} (size: {size}, offset: {offset:.2%})")
                        
                        _order_id, matches = submit_limit_order(
                            account_id=cohort.account_id,
                            symbol=symbol,
                            side=side,
                            price=float(order_price),
                            quantity=size,
                        )
                        # 广播成交事件
                        for m in matches:
                            ev = m.executed_event.model_dump()
                            await hub.broadcast_json("events", ev)
                            ev_type = ev.get("event_type")
                            if ev_type:
                                await hub.broadcast_json(str(ev_type), ev)
                    except Exception as e:
                        print(f"[CommonBotEmergency:maybe_react] Order failed for {cohort.bot_id}: {e}")

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
        author_id = str(ctx_news.get("author_id") or "system")
        mutation_depth = int(ctx_news.get("mutation_depth") or 0)

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
                    truth_payload=pending.truth_payload,
                    is_insider=cohort.is_insider,
                    author_id=author_id,
                    mutation_depth=mutation_depth,
                )
                self._event_store.append(decision_json)
                emitted.append(decision_json)

                if trade_json is not None:
                    self._event_store.append(trade_json)
                    emitted.append(trade_json)

                    # 真正提交订单进入撮合引擎
                    try:
                        side = str(trade_json.payload.get("side"))
                        last_price_val = trade_json.payload.get("price_hint")
                        if last_price_val is None:
                            from ifrontier.infra.sqlite.market import get_last_price
                            last_price = get_last_price(symbol) or 0.0
                        else:
                            last_price = float(last_price_val)
                            
                        if last_price <= 0:
                            print(f"[CommonBotEmergency:open] Skipping trade for {symbol}: invalid price {last_price}")
                            continue

                        size = float(trade_json.payload.get("size") or 1.0)
                        confidence = float(trade_json.payload.get("confidence") or 0.5)

                        # 使用相同的激进报价逻辑
                        offset = 0.01 + (confidence * 0.04)
                        if side == "BUY":
                            order_price = last_price * (1.0 + offset)
                        else:
                            order_price = last_price * (1.0 - offset)

                        print(f"[CommonBotEmergency:open] Bot {cohort.account_id} submitting {side} for {symbol} at {order_price:.2f} (size: {size}, offset: {offset:.2%})")

                        _order_id, matches = submit_limit_order(
                            account_id=cohort.account_id,
                            symbol=symbol,
                            side=side,
                            price=float(order_price),
                            quantity=size,
                        )
                        # 广播成交事件
                        for m in matches:
                            ev = m.executed_event.model_dump()
                            await hub.broadcast_json("events", ev)
                            ev_type = ev.get("event_type")
                            if ev_type:
                                await hub.broadcast_json(str(ev_type), ev)
                    except Exception as e:
                        print(f"[CommonBotEmergency:open] Order failed for {cohort.bot_id}: {e}")

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

        corr = delivery_event.correlation_id or uuid4()
        emitted: List[EventEnvelopeJson] = []
        
        cfg = load_game_time_config_from_env()
        session = get_market_session(cfg=cfg)
        
        ctx = self._build_shared_context(cohort=target_cohort, variant_id=variant_id, news_text=variant_text, symbols=symbols)
        if ctx is None:
            return []

        for symbol in symbols:
            decision_json, trade_json = run_commonbot_for_earnings(
                symbol=symbol,
                visual_truth="UNKNOWN",
                price_series=ctx.trends.symbol_price_series.get(symbol, []),
                bot_id=target_cohort.bot_id,
                correlation_id=corr,
                news_text="\n".join(ctx.recent_news_texts),
                use_llm=target_cohort.use_llm,
                truth_payload=truth_payload,
                is_insider=target_cohort.is_insider,
                author_id=author_id,
                mutation_depth=mutation_depth,
            )
            self._event_store.append(decision_json)
            emitted.append(decision_json)

            if session.phase == MarketPhase.TRADING and trade_json is not None:
                self._event_store.append(trade_json)
                emitted.append(trade_json)
                try:
                    side = str(trade_json.payload.get("side"))
                    last_price_val = trade_json.payload.get("price_hint")
                    if last_price_val is None:
                        from ifrontier.infra.sqlite.market import get_last_price
                        last_price = get_last_price(symbol) or 0.0
                    else:
                        last_price = float(last_price_val)
                        
                    if last_price <= 0:
                        print(f"[CommonBotEmergency:delivery] Skipping trade for {symbol}: invalid price {last_price}")
                        continue
                    
                    # 让机器人更具攻击性以促成成交：
                    # 根据信心指数动态调整价格偏移，最高可达 5%
                    # 这将确保能穿透做市商的盘口并直接拉升/砸盘
                    confidence = float(trade_json.payload.get("confidence") or 0.5)
                    # 基础偏移 1%，根据信心最高加成到 5%
                    offset = 0.01 + (confidence * 0.04)
                    
                    if side == "BUY":
                        order_price = last_price * (1.0 + offset)
                    else:
                        order_price = last_price * (1.0 - offset)

                    print(f"[CommonBotEmergency:delivery] Bot {target_cohort.account_id} submitting {side} at {order_price:.2f} (last: {last_price:.2f}, offset: {offset:.2%}, conf: {confidence:.2f})")
                    
                    _order_id, matches = submit_limit_order(
                        account_id=target_cohort.account_id,
                        symbol=symbol,
                        side=side,
                        price=float(order_price),
                        quantity=float(trade_json.payload.get("size") or 1.0),
                    )
                    for m in matches:
                        ev = m.executed_event.model_dump()
                        await hub.broadcast_json("events", ev)
                except Exception as e:
                    print(f"[CommonBotEmergency:delivery] Order failed: {e}")

        return emitted

    @staticmethod
    def _is_news_broadcasted(event_type: str) -> bool:
        et = getattr(event_type, "value", event_type)
        return str(et) in {
            str(EventType.NEWS_BROADCASTED),
            EventType.NEWS_BROADCASTED.value,
        }
