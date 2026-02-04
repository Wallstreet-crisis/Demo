from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, RootModel

from ifrontier.app.ws import hub
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.neo4j.driver import create_driver
from ifrontier.infra.neo4j.event_store import Neo4jEventStore
from ifrontier.services.commonbot import run_commonbot_for_earnings
from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
from ifrontier.infra.sqlite.ledger import apply_trade_executed, create_account, get_snapshot, spend_cash
from ifrontier.infra.sqlite.market import get_candles, get_last_price, get_price_series, record_trade
from ifrontier.services.matching import submit_limit_order, submit_market_order
from ifrontier.services.market_analytics import get_quote
from ifrontier.services.valuation import value_account
from ifrontier.domain.players.caste import get_caste_config
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.services.contracts import ContractService
from ifrontier.services.contract_agent import ContractAgent
from ifrontier.services.chat import ChatService
from ifrontier.services.news import NewsService
from ifrontier.services.news_tick import NewsTickEngine
from ifrontier.services.game_time import load_game_time_config_from_env
from ifrontier.services.market_session import get_market_session
from ifrontier.infra.sqlite.hosting import get_hosting_state, upsert_hosting_state
from ifrontier.services.hosting_scheduler import HostingScheduler
from ifrontier.services.user_capabilities import UserCapabilityFacade
from ifrontier.infra.sqlite.securities import load_securities_pool_from_env, set_status
from ifrontier.services.market_maker import MarketMaker, MarketMakerConfig

router = APIRouter()

_driver = create_driver()
_event_store = Neo4jEventStore(_driver)
_contract_service = ContractService(_driver, _event_store)
_contract_agent = ContractAgent()
_chat_service = ChatService(event_store=_event_store)
_news_service = NewsService(_driver, _event_store)
_news_tick_engine = NewsTickEngine(_driver, _event_store, _news_service)
_commonbot_emergency_runner = CommonBotEmergencyRunner(news=_news_service, event_store=_event_store)

_hosting_scheduler: HostingScheduler | None = None

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

class DebugSecuritiesSetStatusRequest(BaseModel):
    symbol: str
    status: str

class DebugMarketMakerTickResponse(BaseModel):
    placed: int

@router.post("/debug/securities/load_pool")
async def debug_securities_load_pool() -> Dict[str, Any]:
    try:
        load_securities_pool_from_env()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}

@router.post("/debug/securities/set_status")
async def debug_securities_set_status(req: DebugSecuritiesSetStatusRequest) -> Dict[str, Any]:
    try:
        set_status(symbol=req.symbol, status=req.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}

@router.post("/debug/market_maker/tick_once")
async def debug_market_maker_tick_once() -> DebugMarketMakerTickResponse:
    cfg = MarketMakerConfig(
        account_id=str(os.getenv("IF_MARKET_MAKER_ACCOUNT_ID") or "mm:1"),
        spread_pct=float(os.getenv("IF_MARKET_MAKER_SPREAD_PCT") or "0.02"),
        min_qty=float(os.getenv("IF_MARKET_MAKER_MIN_QTY") or "1.0"),
    )
    mm = MarketMaker(cfg=cfg)
    matches = mm.tick_once()
    return DebugMarketMakerTickResponse(placed=int(len(matches or [])))

class DebugEmitEventRequest(BaseModel):
    event_type: EventType
    payload: Dict[str, Any]
    actor_user_id: Optional[str] = None
    actor_agent_id: Optional[str] = None
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None

class DebugEmitEventResponse(BaseModel):
    event_id: UUID
    correlation_id: Optional[UUID]

@router.post("/debug/emit_event")
async def debug_emit_event(req: DebugEmitEventRequest) -> DebugEmitEventResponse:
    envelope = EventEnvelope(
        event_type=req.event_type,
        occurred_at=datetime.now(timezone.utc),
        correlation_id=req.correlation_id or uuid4(),
        causation_id=req.causation_id,
        actor=EventActor(user_id=req.actor_user_id, agent_id=req.actor_agent_id),
        payload=_AnyPayload(req.payload),
    )

    event_json = EventEnvelopeJson.from_envelope(envelope)
    _event_store.append(event_json)

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(req.event_type), event_json.model_dump())

    return DebugEmitEventResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)

class NewsStoreCatalogPreset(BaseModel):
    preset_id: str
    text: str

class NewsStoreCatalogItem(BaseModel):
    kind: str
    price_cash: float
    requires_symbols: bool = False
    preview_text: str
    presets: List[NewsStoreCatalogPreset]

class NewsStoreCatalogResponse(BaseModel):
    items: List[NewsStoreCatalogItem]

@router.get("/news/store/catalog")
async def news_store_catalog() -> NewsStoreCatalogResponse:
    items_cfg: List[Dict[str, Any]] = [
        {"kind": "RUMOR", "price_cash": 50.0, "requires_symbols": False},
        {"kind": "LEAK", "price_cash": 120.0, "requires_symbols": True},
        {"kind": "ANALYST_REPORT", "price_cash": 80.0, "requires_symbols": True},
        {"kind": "OMEN", "price_cash": 100.0, "requires_symbols": True},
        {"kind": "DISCLOSURE", "price_cash": 180.0, "requires_symbols": True},
        {"kind": "EARNINGS", "price_cash": 150.0, "requires_symbols": True},
        {"kind": "MAJOR_EVENT", "price_cash": 300.0, "requires_symbols": True},
    ]

    out: List[NewsStoreCatalogItem] = []
    for it in items_cfg:
        kind = str(it["kind"])
        requires_symbols = bool(it.get("requires_symbols") or False)
        symbols = ["BLUEGOLD"] if requires_symbols else []
        presets_texts = _news_service.get_preset_templates(kind=kind, symbols=symbols)
        preview = presets_texts[0] if presets_texts else _news_service.get_preset_template(kind=kind, symbols=symbols)
        out.append(
            NewsStoreCatalogItem(
                kind=kind,
                price_cash=float(it["price_cash"]),
                requires_symbols=requires_symbols,
                preview_text=str(preview),
                presets=[
                    NewsStoreCatalogPreset(preset_id=f"{kind}:{idx}", text=str(t))
                    for idx, t in enumerate(presets_texts)
                ],
            )
        )

    return NewsStoreCatalogResponse(items=out)

def _news_debug_enabled() -> bool:
    return str(os.getenv("IF_NEWS_DEBUG") or "0").strip().lower() in {"1", "true", "yes"}

class DebugNewsChainsResponse(BaseModel):
    items: List[Dict[str, Any]]

@router.get("/debug/news/chains")
async def debug_news_chains(limit: int = 50) -> DebugNewsChainsResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    def _tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (ch:NewsChain)
            RETURN ch.chain_id AS chain_id,
                   ch.major_card_id AS major_card_id,
                   ch.kind AS kind,
                   ch.phase AS phase,
                   ch.created_at AS created_at,
                   ch.t0_at AS t0_at,
                   ch.next_omen_at AS next_omen_at,
                   ch.omen_interval_seconds AS omen_interval_seconds,
                   ch.abort_probability AS abort_probability,
                   ch.grant_count AS grant_count,
                   ch.seed AS seed,
                   ch.symbols AS symbols
            ORDER BY ch.created_at DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    with _driver.session() as session:
        rows = session.execute_read(_tx, {"limit": int(limit)})
    return DebugNewsChainsResponse(items=rows)

class DebugNewsChainResponse(BaseModel):
    chain: Dict[str, Any] | None = None
    major_card: Dict[str, Any] | None = None
    variants: List[Dict[str, Any]] = []

@router.get("/debug/news/chains/{chain_id}")
async def debug_news_chain(chain_id: str, variants_limit: int = 50) -> DebugNewsChainResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    def _tx(tx, params: Dict[str, Any]) -> Dict[str, Any]:
        rec = tx.run(
            """
            MATCH (ch:NewsChain {chain_id: $chain_id})
            OPTIONAL MATCH (c:NewsCard {card_id: ch.major_card_id})
            RETURN properties(ch) AS chain_props, properties(c) AS card_props
            """,
            **params,
        ).single()
        if rec is None:
            return {"chain": None, "major_card": None}
        return {"chain": rec.get("chain_props"), "major_card": rec.get("card_props")}

    def _variants_tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (ch:NewsChain {chain_id: $chain_id})
            MATCH (c:NewsCard {card_id: ch.major_card_id})-[:HAS_VARIANT]->(v:NewsVariant)
            RETURN v.variant_id AS variant_id,
                   v.text AS text,
                   v.author_id AS author_id,
                   v.mutation_depth AS mutation_depth,
                   v.influence_cost AS influence_cost,
                   v.created_at AS created_at
            ORDER BY v.created_at DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    with _driver.session() as session:
        base = session.execute_read(_tx, {"chain_id": str(chain_id)})
        vars_rows = session.execute_read(_variants_tx, {"chain_id": str(chain_id), "limit": int(variants_limit)})

    return DebugNewsChainResponse(chain=base.get("chain"), major_card=base.get("major_card"), variants=vars_rows)

class DebugNewsDeliveriesResponse(BaseModel):
    items: List[Dict[str, Any]]

@router.get("/debug/news/deliveries")
async def debug_news_deliveries(variant_id: str, limit: int = 200) -> DebugNewsDeliveriesResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    def _tx(tx, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = tx.run(
            """
            MATCH (d:NewsDelivery {variant_id: $variant_id})
            RETURN d.delivery_id AS delivery_id,
                   d.card_id AS card_id,
                   d.variant_id AS variant_id,
                   d.to_player_id AS to_player_id,
                   d.from_actor_id AS from_actor_id,
                   d.visibility_level AS visibility_level,
                   d.delivery_reason AS delivery_reason,
                   d.delivered_at AS delivered_at
            ORDER BY d.delivered_at DESC
            LIMIT $limit
            """,
            **params,
        )
        return [dict(r) for r in result]

    with _driver.session() as session:
        rows = session.execute_read(_tx, {"variant_id": str(variant_id), "limit": int(limit)})
    return DebugNewsDeliveriesResponse(items=rows)

class DebugEventsByCorrelationResponse(BaseModel):
    items: List[Dict[str, Any]]

@router.get("/debug/events/by_correlation/{correlation_id}")
async def debug_events_by_correlation(correlation_id: str, limit: int = 200) -> DebugEventsByCorrelationResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    try:
        corr = UUID(str(correlation_id))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid correlation_id") from exc

    events = _event_store.list_by_correlation_id(corr, limit=int(limit))
    return DebugEventsByCorrelationResponse(
        items=[
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at,
                "correlation_id": e.correlation_id,
                "causation_id": e.causation_id,
                "actor": e.actor,
                "payload": e.payload,
            }
            for e in events
        ]
    )

class _AnyPayload(RootModel[Dict[str, Any]]):
    pass

class HostingStatusResponse(BaseModel):
    user_id: str
    enabled: bool
    status: str
    updated_at: str

class HostingEnableResponse(BaseModel):
    state: HostingStatusResponse
    event_id: UUID
    correlation_id: UUID | None

class HostingDisableResponse(BaseModel):
    state: HostingStatusResponse
    event_id: UUID
    correlation_id: UUID | None

@router.post("/hosting/{user_id}/enable")
async def hosting_enable(user_id: str) -> HostingEnableResponse:
    st = upsert_hosting_state(user_id=user_id, enabled=True, status="ON_IDLE")
    payload = _AnyPayload(
        {
            "as_user_id": str(user_id),
            "enabled": True,
            "status": st.status,
            "changed_at": datetime.now(timezone.utc),
        }
    )
    env = EventEnvelope(
        event_type=EventType.AI_HOSTING_STATE_CHANGED,
        correlation_id=uuid4(),
        actor=EventActor(agent_id=f"hosting:{user_id}"),
        payload=payload,
    )
    ev = EventEnvelopeJson.from_envelope(env)
    _event_store.append(ev)
    await hub.broadcast_json("events", ev.model_dump())
    await hub.broadcast_json(str(EventType.AI_HOSTING_STATE_CHANGED), ev.model_dump())

    return HostingEnableResponse(
        state=HostingStatusResponse(
            user_id=st.user_id,
            enabled=bool(st.enabled),
            status=str(st.status),
            updated_at=str(st.updated_at),
        ),
        event_id=ev.event_id,
        correlation_id=ev.correlation_id,
    )

@router.post("/hosting/{user_id}/disable")
async def hosting_disable(user_id: str) -> HostingDisableResponse:
    st = upsert_hosting_state(user_id=user_id, enabled=False, status="OFF")
    payload = _AnyPayload(
        {
            "as_user_id": str(user_id),
            "enabled": False,
            "status": st.status,
            "changed_at": datetime.now(timezone.utc),
        }
    )
    env = EventEnvelope(
        event_type=EventType.AI_HOSTING_STATE_CHANGED,
        correlation_id=uuid4(),
        actor=EventActor(agent_id=f"hosting:{user_id}"),
        payload=payload,
    )
    ev = EventEnvelopeJson.from_envelope(env)
    _event_store.append(ev)
    await hub.broadcast_json("events", ev.model_dump())
    await hub.broadcast_json(str(EventType.AI_HOSTING_STATE_CHANGED), ev.model_dump())

    return HostingDisableResponse(
        state=HostingStatusResponse(
            user_id=st.user_id,
            enabled=bool(st.enabled),
            status=str(st.status),
            updated_at=str(st.updated_at),
        ),
        event_id=ev.event_id,
        correlation_id=ev.correlation_id,
    )

@router.get("/hosting/{user_id}/status")
async def hosting_status(user_id: str) -> HostingStatusResponse:
    st = get_hosting_state(user_id)
    if st is None:
        st = upsert_hosting_state(user_id=user_id, enabled=False, status="OFF")
    return HostingStatusResponse(
        user_id=st.user_id,
        enabled=bool(st.enabled),
        status=str(st.status),
        updated_at=str(st.updated_at),
    )

class HostingDebugTickResponse(BaseModel):
    ok: bool

@router.post("/hosting/debug/tick_once")
async def hosting_debug_tick_once() -> HostingDebugTickResponse:
    sched = _hosting_scheduler
    if sched is None:
        # 测试环境中 TestClient 可能不会触发 lifespan，从而导致 scheduler 未启动。
        # debug 接口允许临时构造 scheduler 并执行一次 tick。
        sched = HostingScheduler(
            min_players=8,
            tick_interval_seconds=1.0,
            max_per_tick=2,
            channel_for_online_stats="events",
            get_channel_size=hub.get_channel_size,
            broadcaster=_make_broadcaster_for_events(),
            make_facade=make_user_facade,
        )
    await sched.tick_once()
    return HostingDebugTickResponse(ok=True)

def _make_broadcaster_for_events():
    async def _broadcast(ev: dict) -> None:
        await hub.broadcast_json("events", ev)
        ev_type = ev.get("event_type")
        if ev_type:
            await hub.broadcast_json(str(ev_type), ev)

    return _broadcast

def make_user_facade(user_id: str) -> UserCapabilityFacade:
    return UserCapabilityFacade(
        user_id=user_id,
        contract_service=_contract_service,
        contract_agent=_contract_agent,
        chat_service=_chat_service,
    )

class DebugEarningsNewsRequest(BaseModel):
    symbol: str
    visual_truth: str
    headline_text: str | None = None
    price_series: list[float] = []


class DebugEarningsNewsResponse(BaseModel):
    news_event_id: UUID
    ai_decision_event_id: UUID
    trade_intent_event_id: UUID | None = None
    correlation_id: UUID


@router.post("/debug/earnings_news")
async def debug_earnings_news(req: DebugEarningsNewsRequest) -> DebugEarningsNewsResponse:
    correlation_id = uuid4()

    news_payload = _AnyPayload(
        {
            "news_id": f"EARN_{req.symbol}_{int(datetime.now(timezone.utc).timestamp())}",
            "variant_id": "root",
            "kind": "EARNINGS",
            "visual_truth": req.visual_truth,
            "original_image_uri": "debug://earnings",
            "initial_text": req.headline_text or "",
            "created_at": datetime.now(timezone.utc),
        }
    )

    news_envelope = EventEnvelope[
        _AnyPayload
    ](
        event_type=EventType.NEWS_CREATED,
        correlation_id=correlation_id,
        actor=EventActor(agent_id="debug"),
        payload=news_payload,
    )
    news_json = EventEnvelopeJson.from_envelope(news_envelope)
    _event_store.append(news_json)
    await hub.broadcast_json("events", news_json.model_dump())

    decision_json, trade_json = run_commonbot_for_earnings(
        symbol=req.symbol,
        visual_truth=req.visual_truth,
        price_series=req.price_series,
        bot_id="commonbot:baseline",
        correlation_id=correlation_id,
    )

    _event_store.append(decision_json)
    await hub.broadcast_json("events", decision_json.model_dump())
    await hub.broadcast_json(str(EventType.AI_COMMONBOT_DECISION), decision_json.model_dump())

    trade_event_id: UUID | None = None
    if trade_json is not None:
        _event_store.append(trade_json)
        await hub.broadcast_json("events", trade_json.model_dump())
        await hub.broadcast_json(str(EventType.TRADE_INTENT_SUBMITTED), trade_json.model_dump())
        trade_event_id = trade_json.event_id

    # Bot 真实下单：对于 BUY/SELL 决策，用 bot 账户提交限价单进入撮合
    action = (decision_json.payload or {}).get("action")
    confidence = float((decision_json.payload or {}).get("confidence") or 0.0)
    if action in {"BUY", "SELL"} and req.price_series:
        last_price = req.price_series[-1]
        eps = 0.001
        order_price = last_price * (1 + eps) if action == "BUY" else last_price * (1 - eps)

        # 简单规则：高置信度用机构账户，低置信度用散户代表
        bot_account = "bot:inst:1" if confidence >= 0.7 else "bot:ret:1"
        qty = 50.0 if bot_account.startswith("bot:inst") else 5.0

        try:
            submit_limit_order(
                account_id=bot_account,
                symbol=req.symbol,
                side=action,
                price=float(order_price),
                quantity=float(qty),
            )
        except ValueError:
            # 资产不足（例如 SELL 无持仓）时忽略，不影响接口返回
            pass

    return DebugEarningsNewsResponse(
        news_event_id=news_json.event_id,
        ai_decision_event_id=decision_json.event_id,
        trade_intent_event_id=trade_event_id,
        correlation_id=correlation_id,
    )


class DebugExecuteTradeRequest(BaseModel):
    buy_account_id: str
    sell_account_id: str
    symbol: str
    price: float
    quantity: float


class DebugExecuteTradeResponse(BaseModel):
    event_id: UUID
    correlation_id: UUID


@router.post("/debug/execute_trade")
async def debug_execute_trade(req: DebugExecuteTradeRequest) -> DebugExecuteTradeResponse:
    correlation_id = uuid4()
    now = datetime.now(timezone.utc)

    # Ensure accounts exist (as user accounts by default)
    create_account(req.buy_account_id, owner_type="user")
    create_account(req.sell_account_id, owner_type="user")

    payload = _AnyPayload(
        {
            "buy_account_id": req.buy_account_id,
            "sell_account_id": req.sell_account_id,
            "symbol": req.symbol,
            "price": req.price,
            "quantity": req.quantity,
            "executed_at": now,
        }
    )

    envelope = EventEnvelope[
        _AnyPayload
    ](
        event_type=EventType.TRADE_EXECUTED,
        correlation_id=correlation_id,
        actor=EventActor(agent_id="debug:settlement"),
        payload=payload,
    )
    event_json = EventEnvelopeJson.from_envelope(envelope)

    # Apply ledger update; 账本校验失败时返回 400，而不是 500
    try:
        apply_trade_executed(
            buy_account_id=req.buy_account_id,
            sell_account_id=req.sell_account_id,
            symbol=req.symbol,
            price=req.price,
            quantity=req.quantity,
            event_id=str(event_json.event_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record_trade(
        symbol=req.symbol,
        price=float(req.price),
        quantity=float(req.quantity),
        occurred_at=now,
        event_id=str(event_json.event_id),
    )

    _event_store.append(event_json)
    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.TRADE_EXECUTED), event_json.model_dump())

    return DebugExecuteTradeResponse(event_id=event_json.event_id, correlation_id=correlation_id)


class MarketQuoteResponse(BaseModel):
    symbol: str
    last_price: float | None
    prev_price: float | None
    change_pct: float | None
    ma_5: float | None
    ma_20: float | None
    vol_20: float | None


@router.get("/market/symbols")
async def get_market_symbols() -> list[str]:
    from ifrontier.infra.sqlite.securities import list_securities
    secs = list_securities()
    return [s.symbol for s in secs]


@router.get("/market/quote/{symbol}")
async def market_quote(symbol: str) -> MarketQuoteResponse:
    q = get_quote(symbol)
    return MarketQuoteResponse(
        symbol=q.symbol,
        last_price=q.last_price,
        prev_price=q.prev_price,
        change_pct=q.change_pct,
        ma_5=q.ma_5,
        ma_20=q.ma_20,
        vol_20=q.vol_20,
    )


class MarketSeriesResponse(BaseModel):
    symbol: str
    prices: list[float]


@router.get("/market/series/{symbol}")
async def market_series(symbol: str, limit: int = 200) -> MarketSeriesResponse:
    prices = get_price_series(symbol=symbol, limit=limit)
    return MarketSeriesResponse(symbol=symbol, prices=prices)


class MarketCandleItem(BaseModel):
    bucket_start: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float
    trades: int


class MarketCandlesResponse(BaseModel):
    symbol: str
    interval_seconds: int
    candles: list[MarketCandleItem]


@router.get("/market/candles/{symbol}")
async def market_candles(
    symbol: str, interval_seconds: int = 60, limit: int = 200
) -> MarketCandlesResponse:
    try:
        candles = get_candles(symbol=symbol, interval_seconds=interval_seconds, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MarketCandlesResponse(
        symbol=symbol,
        interval_seconds=int(interval_seconds),
        candles=[
            MarketCandleItem(
                bucket_start=c.bucket_start,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                vwap=c.vwap,
                trades=c.trades,
            )
            for c in candles
        ],
    )


class AccountValuationResponse(BaseModel):
    account_id: str
    cash: float
    positions: Dict[str, float]
    equity_value: float
    total_value: float
    discount_factor: float
    prices: Dict[str, float | None]


@router.get("/accounts/{account_id}/valuation")
async def account_valuation(account_id: str, discount_factor: float = 1.0) -> AccountValuationResponse:
    try:
        v = value_account(account_id=account_id, discount_factor=discount_factor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccountValuationResponse(
        account_id=v.account_id,
        cash=v.cash,
        positions=v.positions,
        equity_value=v.equity_value,
        total_value=v.total_value,
        discount_factor=v.discount_factor,
        prices=v.prices,
    )


class MarketSessionResponse(BaseModel):
    enabled: bool
    phase: str
    game_day_index: int
    seconds_into_day: int
    seconds_per_game_day: int
    trading_seconds: int
    closing_buffer_seconds: int


@router.get("/market/session")
async def market_session() -> MarketSessionResponse:
    cfg = load_game_time_config_from_env()
    snap = get_market_session(cfg=cfg)
    return MarketSessionResponse(
        enabled=bool(snap.enabled),
        phase=snap.phase.value,
        game_day_index=int(snap.game_day_index),
        seconds_into_day=int(snap.seconds_into_day),
        seconds_per_game_day=int(snap.seconds_per_game_day),
        trading_seconds=int(snap.trading_seconds),
        closing_buffer_seconds=int(snap.closing_buffer_seconds),
    )


class DebugSubmitOrderRequest(BaseModel):
    account_id: str
    symbol: str
    side: str
    price: float
    quantity: float


class DebugSubmitOrderResponse(BaseModel):
    order_id: str


@router.post("/debug/submit_order")
async def debug_submit_order(req: DebugSubmitOrderRequest) -> DebugSubmitOrderResponse:
    # 这里只是限价单提交入口，实际撮合和记账由 MatchingEngine + SQLite 账本处理
    try:
        order_id, _matches = submit_limit_order(
        account_id=req.account_id,
        symbol=req.symbol,
        side=req.side,
        price=req.price,
        quantity=req.quantity,
    )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DebugSubmitOrderResponse(order_id=order_id)


class CreatePlayerRequest(BaseModel):
    player_id: str
    initial_cash: float | None = None
    caste_id: str | None = None


class CreatePlayerResponse(BaseModel):
    account_id: str
    cash: float


@router.post("/debug/create_player")
async def create_player(req: CreatePlayerRequest) -> CreatePlayerResponse:
    account_id = f"user:{req.player_id}"
    # 如果提供 caste_id, 优先使用阶级配置; 否则回退到显式 initial_cash 或 0
    initial_cash = 0.0
    positions: Dict[str, float] = {}

    if req.caste_id is not None:
        cfg = get_caste_config(req.caste_id)
        if cfg is not None:
            initial_cash = cfg.initial_cash
            positions = cfg.initial_positions
    if req.initial_cash is not None:
        initial_cash = req.initial_cash

    create_account(account_id, owner_type="user", initial_cash=initial_cash)

    if positions:
        conn = get_connection()
        with conn:
            for symbol, qty in positions.items():
                conn.execute(
                    "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
                    (account_id, symbol, qty),
                )
    snap = get_snapshot(account_id)
    return CreatePlayerResponse(account_id=snap.account_id, cash=snap.cash)


class PlayerLimitOrderRequest(BaseModel):
    player_id: str
    symbol: str
    side: str
    price: float
    quantity: float


class PlayerOrderResponse(BaseModel):
    order_id: str


@router.post("/orders/limit")
async def submit_player_limit_order(req: PlayerLimitOrderRequest) -> PlayerOrderResponse:
    account_id = f"user:{req.player_id}"
    order_id, matches = submit_limit_order(
        account_id=account_id,
        symbol=req.symbol,
        side=req.side,
        price=req.price,
        quantity=req.quantity,
    )
    # 广播成交事件
    for m in matches:
        ev = m.executed_event.model_dump()
        await hub.broadcast_json("events", ev)
        await hub.broadcast_json(str(ev.get("event_type")), ev)

    return PlayerOrderResponse(order_id=order_id)


class PlayerMarketOrderRequest(BaseModel):
    player_id: str
    symbol: str
    side: str
    quantity: float


@router.post("/orders/market")
async def submit_player_market_order(req: PlayerMarketOrderRequest) -> None:
    account_id = f"user:{req.player_id}"
    try:
        matches = submit_market_order(
            account_id=account_id,
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
        )
        # 广播成交事件
        for m in matches:
            ev = m.executed_event.model_dump()
            await hub.broadcast_json("events", ev)
            await hub.broadcast_json(str(ev.get("event_type")), ev)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PlayerAccountResponse(BaseModel):
    account_id: str
    cash: float
    positions: Dict[str, float]


class PlayerBootstrapRequest(BaseModel):
    player_id: str
    initial_cash: float | None = None
    caste_id: str | None = None


@router.post("/players/bootstrap")
async def players_bootstrap(req: PlayerBootstrapRequest) -> PlayerAccountResponse:
    # 幂等：如果已存在则返回现有数据，不报错也不重复发放初始资产
    account_id = f"user:{req.player_id}"
    conn = get_connection()

    row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
    if not row:
        initial_cash = float(req.initial_cash) if req.initial_cash is not None else 10000.0
        positions: Dict[str, float] = {}

        if req.caste_id is not None:
            cfg = get_caste_config(req.caste_id)
            if cfg is not None:
                initial_cash = float(cfg.initial_cash)
                positions = dict(cfg.initial_positions)

        create_account(account_id, owner_type="user", initial_cash=float(initial_cash))

        if positions:
            with conn:
                for symbol, qty in positions.items():
                    conn.execute(
                        "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) "
                        "ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
                        (account_id, symbol, qty),
                    )

    # 确保 Neo4j 中存在该玩家 User 节点（供新闻传播/调试使用）
    try:
        with _driver.session() as session:
            session.execute_write(lambda tx, params: tx.run("MERGE (u:User {user_id: $user_id}) RETURN u.user_id AS user_id", **params), {"user_id": account_id})
    except Exception:
        pass

    snap = get_snapshot(account_id)
    return PlayerAccountResponse(account_id=snap.account_id, cash=snap.cash, positions=snap.positions)


@router.get("/players/{player_id}/account")
async def get_player_account(player_id: str) -> PlayerAccountResponse:
    account_id = f"user:{player_id}"
    snap = get_snapshot(account_id)
    return PlayerAccountResponse(account_id=snap.account_id, cash=snap.cash, positions=snap.positions)


class ContractCreateRequest(BaseModel):
    actor_id: str
    kind: str
    title: str
    terms: Dict[str, Any]
    parties: list[str]
    required_signers: list[str]
    participation_mode: str | None = None
    invited_parties: list[str] | None = None


class ContractCreateResponse(BaseModel):
    contract_id: str


class ContractAgentDraftRequest(BaseModel):
    actor_id: str
    natural_language: str


class ContractAgentDraftResponse(BaseModel):
    draft_id: str
    template_id: str
    contract_create: Dict[str, Any]
    explanation: str
    questions: list[str]
    risk_rating: str


@router.post("/contract-agent/draft")
async def contract_agent_draft(req: ContractAgentDraftRequest) -> ContractAgentDraftResponse:
    try:
        res = _contract_agent.draft(actor_id=req.actor_id, natural_language=req.natural_language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from ifrontier.domain.events.payloads import AiContractDraftedPayload

    payload = AiContractDraftedPayload(
        draft_id=str(res.draft_id),
        requester_user_id=str(req.actor_id),
        natural_language=str(req.natural_language),
        python_preview=json.dumps(res.contract_create, ensure_ascii=False),
        risk_rating=str(res.risk_rating),
        drafted_at=datetime.now(timezone.utc),
    )
    env = EventEnvelope(
        event_type=EventType.AI_CONTRACT_DRAFTED,
        correlation_id=uuid4(),
        actor=EventActor(user_id=req.actor_id),
        payload=payload,
    )
    ev_json = EventEnvelopeJson.from_envelope(env)
    _event_store.append(ev_json)
    await hub.broadcast_json("events", ev_json.model_dump())
    await hub.broadcast_json(str(EventType.AI_CONTRACT_DRAFTED), ev_json.model_dump())

    return ContractAgentDraftResponse(
        draft_id=str(res.draft_id),
        template_id=str(res.template_id),
        contract_create=dict(res.contract_create),
        explanation=str(res.explanation),
        questions=list(res.questions),
        risk_rating=str(res.risk_rating),
    )


class ContractAgentContextResponse(BaseModel):
    actor_id: str
    context: Dict[str, Any]


@router.get("/contract-agent/context/{actor_id}")
async def contract_agent_get_context(actor_id: str) -> ContractAgentContextResponse:
    ctx = _contract_agent.get_context(actor_id=actor_id)
    return ContractAgentContextResponse(actor_id=actor_id, context=ctx)


@router.post("/contract-agent/context/{actor_id}/clear")
async def contract_agent_clear_context(actor_id: str) -> None:
    _contract_agent.clear_context(actor_id=actor_id)


class ChatIntroFeeQuoteRequest(BaseModel):
    rich_user_id: str
    fee_cash: float = 1000.0
    actor_id: str


class ChatIntroFeeQuoteResponse(BaseModel):
    event_id: UUID
    correlation_id: UUID | None


@router.post("/chat/intro-fee/quote")
async def chat_intro_fee_quote(req: ChatIntroFeeQuoteRequest) -> ChatIntroFeeQuoteResponse:
    try:
        event_json = _chat_service.set_intro_fee_quote(
            rich_user_id=req.rich_user_id,
            fee_cash=req.fee_cash,
            actor_id=req.actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(event_json.event_type), event_json.model_dump())
    return ChatIntroFeeQuoteResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


class ChatOpenPmRequest(BaseModel):
    requester_id: str
    target_id: str


class ChatOpenPmResponse(BaseModel):
    thread_id: str
    paid_intro_fee: bool
    intro_fee_cash: float


@router.post("/chat/pm/open")
async def chat_open_pm(req: ChatOpenPmRequest) -> ChatOpenPmResponse:
    try:
        result, events = _chat_service.open_pm(requester_id=req.requester_id, target_id=req.target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    for ev in events:
        await hub.broadcast_json("events", ev.model_dump())
        await hub.broadcast_json(str(ev.event_type), ev.model_dump())
        await hub.broadcast_json(f"chat.pm.{result.thread_id}", ev.model_dump())

    return ChatOpenPmResponse(
        thread_id=result.thread_id,
        paid_intro_fee=bool(result.paid_intro_fee),
        intro_fee_cash=float(result.intro_fee_cash),
    )


class ChatSendMessageRequest(BaseModel):
    sender_id: str
    message_type: str = "TEXT"
    content: str = ""
    payload: Dict[str, Any] = {}
    anonymous: bool = False
    alias: str | None = None


class ChatSendMessageResponse(BaseModel):
    event_id: UUID
    correlation_id: UUID | None


@router.post("/chat/public/send")
async def chat_public_send(req: ChatSendMessageRequest) -> ChatSendMessageResponse:
    try:
        event_json = _chat_service.send_public_message(
            sender_id=req.sender_id,
            message_type=req.message_type,
            content=req.content,
            payload=req.payload,
            anonymous=bool(req.anonymous),
            alias=req.alias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(event_json.event_type), event_json.model_dump())
    await hub.broadcast_json("chat.public.global", event_json.model_dump())
    return ChatSendMessageResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


class ChatSendPmMessageRequest(ChatSendMessageRequest):
    thread_id: str


@router.post("/chat/pm/send")
async def chat_pm_send(req: ChatSendPmMessageRequest) -> ChatSendMessageResponse:
    try:
        event_json = _chat_service.send_pm_message(
            thread_id=req.thread_id,
            sender_id=req.sender_id,
            message_type=req.message_type,
            content=req.content,
            payload=req.payload,
            anonymous=bool(req.anonymous),
            alias=req.alias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(event_json.event_type), event_json.model_dump())
    await hub.broadcast_json(f"chat.pm.{req.thread_id}", event_json.model_dump())
    return ChatSendMessageResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


class ChatMessageResponse(BaseModel):
    message_id: str
    thread_id: str
    sender_id: str | None
    sender_display: str
    message_type: str
    content: str
    payload: Dict[str, Any]
    created_at: str


class ChatListMessagesResponse(BaseModel):
    items: list[ChatMessageResponse]


@router.get("/chat/public/messages")
async def chat_public_messages(limit: int = 50, before: str | None = None) -> ChatListMessagesResponse:
    items = _chat_service.list_public_messages(limit=limit, before=before)
    out: list[ChatMessageResponse] = []
    for m in items:
        anon = bool((m.payload or {}).get("anonymous"))
        sender_display = str((m.payload or {}).get("sender_display") or (m.sender_id if not anon else "Anonymous"))
        out.append(
            ChatMessageResponse(
                message_id=m.message_id,
                thread_id=m.thread_id,
                sender_id=None if anon else m.sender_id,
                sender_display=sender_display,
                message_type=m.message_type,
                content=m.content,
                payload=m.payload,
                created_at=m.created_at,
            )
        )
    return ChatListMessagesResponse(items=out)


@router.get("/chat/pm/{thread_id}/messages")
async def chat_pm_messages(thread_id: str, limit: int = 50, before: str | None = None) -> ChatListMessagesResponse:
    items = _chat_service.list_pm_messages(thread_id=thread_id, limit=limit, before=before)
    out: list[ChatMessageResponse] = []
    for m in items:
        anon = bool((m.payload or {}).get("anonymous"))
        sender_display = str((m.payload or {}).get("sender_display") or (m.sender_id if not anon else "Anonymous"))
        out.append(
            ChatMessageResponse(
                message_id=m.message_id,
                thread_id=m.thread_id,
                sender_id=None if anon else m.sender_id,
                sender_display=sender_display,
                message_type=m.message_type,
                content=m.content,
                payload=m.payload,
                created_at=m.created_at,
            )
        )
    return ChatListMessagesResponse(items=out)


class ChatThreadResponse(BaseModel):
    thread_id: str
    kind: str
    participant_a: str
    participant_b: str
    status: str
    created_at: str


class ChatListThreadsResponse(BaseModel):
    items: list[ChatThreadResponse]


@router.get("/chat/threads/{user_id}")
async def chat_list_threads(user_id: str, limit: int = 200) -> ChatListThreadsResponse:
    items = _chat_service.list_threads(user_id=user_id, limit=limit)
    return ChatListThreadsResponse(items=[ChatThreadResponse(**t.__dict__) for t in items])


class WealthPublicRefreshResponse(BaseModel):
    public_count: int
    event_id: UUID
    correlation_id: UUID | None


@router.post("/wealth/public/refresh")
async def wealth_public_refresh() -> WealthPublicRefreshResponse:
    public_count, event_json = _chat_service.refresh_public_wealth_top10()
    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(event_json.event_type), event_json.model_dump())
    return WealthPublicRefreshResponse(
        public_count=int(public_count),
        event_id=event_json.event_id,
        correlation_id=event_json.correlation_id,
    )


class WealthPublicResponse(BaseModel):
    user_id: str
    public_total_value: float | None


@router.get("/wealth/public/{user_id}")
async def wealth_public_get(user_id: str) -> WealthPublicResponse:
    v = _chat_service.get_public_total_value(user_id=user_id)
    return WealthPublicResponse(user_id=user_id, public_total_value=v)


@router.post("/contracts/create")
async def contract_create(req: ContractCreateRequest) -> ContractCreateResponse:
    try:
        contract_id = _contract_service.create_contract(
            kind=req.kind,
            title=req.title,
            terms=req.terms,
            parties=req.parties,
            required_signers=req.required_signers,
            participation_mode=req.participation_mode,
            invited_parties=req.invited_parties,
            actor_id=req.actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContractCreateResponse(contract_id=contract_id)


class ContractBatchItem(BaseModel):
    kind: str
    title: str
    terms: Dict[str, Any]
    parties: list[str]
    required_signers: list[str]
    participation_mode: str | None = None
    invited_parties: list[str] | None = None


class ContractBatchCreateRequest(BaseModel):
    actor_id: str
    contracts: list[ContractBatchItem]


class ContractBatchCreateResponseItem(BaseModel):
    index: int
    contract_id: str


class ContractBatchCreateResponse(BaseModel):
    contracts: list[ContractBatchCreateResponseItem]


@router.post("/contracts/batch_create")
async def contract_batch_create(req: ContractBatchCreateRequest) -> ContractBatchCreateResponse:
    try:
        contract_dicts = [
            {
                "kind": c.kind,
                "title": c.title,
                "terms": c.terms,
                "parties": c.parties,
                "required_signers": c.required_signers,
                "participation_mode": c.participation_mode,
                "invited_parties": c.invited_parties,
            }
            for c in req.contracts
        ]
        ids = _contract_service.create_contracts_batch(
            actor_id=req.actor_id,
            contracts=contract_dicts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items: list[ContractBatchCreateResponseItem] = [
        ContractBatchCreateResponseItem(index=idx, contract_id=cid)
        for idx, cid in enumerate(ids)
    ]
    return ContractBatchCreateResponse(contracts=items)


class ContractJoinRequest(BaseModel):
    joiner: str


@router.post("/contracts/{contract_id}/join")
async def contract_join(contract_id: str, req: ContractJoinRequest) -> None:
    try:
        _contract_service.join_contract(contract_id=contract_id, joiner=req.joiner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ContractSignRequest(BaseModel):
    signer: str


class ContractSignResponse(BaseModel):
    status: str


@router.post("/contracts/{contract_id}/sign")
async def contract_sign(contract_id: str, req: ContractSignRequest) -> ContractSignResponse:
    try:
        status = _contract_service.sign_contract(contract_id=contract_id, signer=req.signer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContractSignResponse(status=status.value)


class ContractActivateRequest(BaseModel):
    actor_id: str


@router.post("/contracts/{contract_id}/activate")
async def contract_activate(contract_id: str, req: ContractActivateRequest) -> None:
    try:
        _contract_service.activate_contract(contract_id=contract_id, actor_id=req.actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ContractProposalCreateRequest(BaseModel):
    proposer: str
    proposal_type: str
    details: Dict[str, Any] = {}


class ContractProposalCreateResponse(BaseModel):
    proposal_id: str


@router.post("/contracts/{contract_id}/proposals/create")
async def contract_proposal_create(
    contract_id: str, req: ContractProposalCreateRequest
) -> ContractProposalCreateResponse:
    try:
        proposal_id = _contract_service.create_proposal(
            contract_id=contract_id,
            proposal_type=req.proposal_type,
            proposer=req.proposer,
            details=req.details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ContractProposalCreateResponse(proposal_id=proposal_id)


class ContractProposalApproveRequest(BaseModel):
    approver: str


class ContractProposalApproveResponse(BaseModel):
    applied: bool
    contract_status: str
    proposal_type: str


@router.post("/contracts/{contract_id}/proposals/{proposal_id}/approve")
async def contract_proposal_approve(
    contract_id: str, proposal_id: str, req: ContractProposalApproveRequest
) -> ContractProposalApproveResponse:
    try:
        result = _contract_service.approve_proposal(
            contract_id=contract_id,
            proposal_id=proposal_id,
            approver=req.approver,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ContractProposalApproveResponse(
        applied=bool(result.get("applied")),
        contract_status=str(result.get("contract_status")),
        proposal_type=str(result.get("proposal_type")),
    )


class ContractSettleRequest(BaseModel):
    actor_id: str


@router.post("/contracts/{contract_id}/settle")
async def contract_settle(contract_id: str, req: ContractSettleRequest) -> None:
    try:
        _contract_service.settle_contract(contract_id=contract_id, actor_id=req.actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ContractRunRulesRequest(BaseModel):
    actor_id: str


@router.post("/contracts/{contract_id}/run_rules")
async def contract_run_rules(contract_id: str, req: ContractRunRulesRequest) -> None:
    try:
        _contract_service.run_rules(contract_id=contract_id, actor_id=req.actor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SocialFollowRequest(BaseModel):
    follower_id: str
    followee_id: str


@router.post("/social/follow")
async def social_follow(req: SocialFollowRequest) -> None:
    try:
        _news_service.follow(follower_id=req.follower_id, followee_id=req.followee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class NewsCreateCardRequest(BaseModel):
    actor_id: str
    kind: str
    image_anchor_id: str | None = None
    image_uri: str | None = None
    truth_payload: Dict[str, Any] | None = None
    symbols: list[str] = []
    tags: list[str] = []
    correlation_id: UUID | None = None


class NewsCreateCardResponse(BaseModel):
    card_id: str
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/cards")
async def news_create_card(req: NewsCreateCardRequest) -> NewsCreateCardResponse:
    # 该端点用于 GM/脚本/调试直接铸造卡牌。
    # 正式玩法中，玩家应通过 /news/store/purchase 购买获得卡牌，而不是自行创建。
    allow_direct_create = str(os.getenv("IF_NEWS_ALLOW_DIRECT_CREATE") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    is_privileged_actor = req.actor_id == "system" or str(req.actor_id).startswith("gm:")
    if not allow_direct_create and not is_privileged_actor:
        raise HTTPException(status_code=403, detail="direct news card creation is GM-only")

    try:
        card_id, event_json = _news_service.create_card(
            kind=req.kind,
            image_anchor_id=req.image_anchor_id,
            image_uri=req.image_uri,
            truth_payload=req.truth_payload,
            symbols=req.symbols,
            tags=req.tags,
            actor_id=req.actor_id,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_CARD_CREATED), event_json.model_dump())

    return NewsCreateCardResponse(
        card_id=card_id,
        event_id=event_json.event_id,
        correlation_id=event_json.correlation_id,
    )


class NewsEmitVariantRequest(BaseModel):
    card_id: str
    author_id: str
    text: str
    parent_variant_id: str | None = None
    influence_cost: float = 0.0
    risk_roll: Dict[str, Any] | None = None
    correlation_id: UUID | None = None


class NewsEmitVariantResponse(BaseModel):
    variant_id: str
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/variants/emit")
async def news_emit_variant(req: NewsEmitVariantRequest) -> NewsEmitVariantResponse:
    try:
        variant_id, event_json = _news_service.emit_variant(
            card_id=req.card_id,
            author_id=req.author_id,
            text=req.text,
            parent_variant_id=req.parent_variant_id,
            influence_cost=req.influence_cost,
            risk_roll=req.risk_roll,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_VARIANT_EMITTED), event_json.model_dump())

    return NewsEmitVariantResponse(
        variant_id=variant_id,
        event_id=event_json.event_id,
        correlation_id=event_json.correlation_id,
    )


class NewsMutateVariantRequest(BaseModel):
    parent_variant_id: str
    editor_id: str
    new_text: str
    influence_cost: float = 0.0
    spend_cash: float | None = None
    risk_roll: Dict[str, Any] | None = None
    correlation_id: UUID | None = None


class NewsMutateVariantResponse(BaseModel):
    new_variant_id: str
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/variants/mutate")
async def news_mutate_variant(req: NewsMutateVariantRequest) -> NewsMutateVariantResponse:
    # v0.1：按字计费（现金），并把成本写入 influence_cost 做审计。
    # 可用 spend_cash 覆盖（策划/脚本显式指定花费）。
    unit_cash = float(os.getenv("IF_NEWS_MUTATE_CASH_PER_CHAR") or "0.1")
    char_count = len(req.new_text or "")
    cash_cost = float(req.spend_cash) if req.spend_cash is not None else float(char_count) * float(unit_cash)

    if cash_cost > 0:
        try:
            spend_cash(account_id=req.editor_id, amount=float(cash_cost), event_id=str(uuid4()))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        new_variant_id, event_json = _news_service.mutate_variant(
            parent_variant_id=req.parent_variant_id,
            editor_id=req.editor_id,
            new_text=req.new_text,
            influence_cost=float(cash_cost),
            risk_roll=req.risk_roll,
            correlation_id=req.correlation_id,
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_VARIANT_MUTATED), event_json.model_dump())

    return NewsMutateVariantResponse(
        new_variant_id=new_variant_id,
        event_id=event_json.event_id,
        correlation_id=event_json.correlation_id,
    )


class NewsPropagateRequest(BaseModel):
    variant_id: str
    from_actor_id: str
    visibility_level: str = "NORMAL"
    spend_influence: float = 0.0
    spend_cash: float | None = None
    limit: int = 50
    correlation_id: UUID | None = None


class NewsPropagateResponse(BaseModel):
    delivered: int
    correlation_id: UUID | None


@router.post("/news/propagate")
async def news_propagate(req: NewsPropagateRequest) -> NewsPropagateResponse:
    requested_limit = int(req.limit)
    if requested_limit <= 0:
        return NewsPropagateResponse(delivered=0, correlation_id=req.correlation_id)

    limit = requested_limit
    per_delivery_cost: float | None = None

    # 若提供 spend_cash，则按 mutation_depth 提高单次投递成本，并用预算限制可投递人数。
    if req.spend_cash is not None:
        ctx = _news_service.get_variant_context(variant_id=req.variant_id) or {}
        depth = int(ctx.get("mutation_depth") or 0)

        unit_per_delivery = float(os.getenv("IF_NEWS_PROPAGATE_CASH_PER_DELIVERY") or "1.0")
        depth_multiplier = float(os.getenv("IF_NEWS_PROPAGATE_MUTATION_MULT") or "0.5")
        multiplier = 1.0 + float(depth) * float(depth_multiplier)

        per_delivery_cost = float(unit_per_delivery) * float(multiplier)
        budget = float(req.spend_cash)
        if budget <= 0:
            raise HTTPException(status_code=400, detail="spend_cash must be > 0")
        if per_delivery_cost <= 0:
            raise HTTPException(status_code=400, detail="invalid propagate cost config")

        affordable = int(budget // per_delivery_cost)
        if affordable < 0:
            affordable = 0
        if affordable < limit:
            limit = affordable

        if limit <= 0:
            return NewsPropagateResponse(delivered=0, correlation_id=req.correlation_id)

    recipients: list[str] = []
    try:
        with _driver.session() as session:
            follower_rows = session.execute_read(
                _news_service._list_followers_tx,
                {"followee_id": req.from_actor_id, "limit": int(limit)},
            )
        recipients = [str(r["user_id"]) for r in follower_rows if str(r.get("user_id")) != str(req.from_actor_id)]
    except Exception:
        recipients = []

    if req.spend_cash is not None and len(recipients) < limit:
        users = _news_service.list_users(limit=5000)
        seen = set(recipients)
        candidates = [u for u in users if u not in seen and str(u) != str(req.from_actor_id)]
        random.shuffle(candidates)
        recipients.extend(candidates[: max(0, int(limit - len(recipients)))])

    if not recipients:
        return NewsPropagateResponse(delivered=0, correlation_id=req.correlation_id)

    if req.spend_cash is not None and per_delivery_cost is not None:
        total_cost = per_delivery_cost * float(len(recipients))
        if total_cost > 0:
            try:
                spend_cash(account_id=req.from_actor_id, amount=float(total_cost), event_id=str(uuid4()))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    delivered_events: list[EventEnvelopeJson] = []
    delivery_reason = "PAID_PROMOTION" if req.spend_cash is not None else "SOCIAL_PROPAGATION"
    for to_player_id in recipients:
        try:
            _delivery_id, ev = _news_service.deliver_variant(
                variant_id=req.variant_id,
                to_player_id=to_player_id,
                from_actor_id=req.from_actor_id,
                visibility_level=req.visibility_level,
                delivery_reason=delivery_reason,
                correlation_id=req.correlation_id,
            )
            delivered_events.append(ev)
        except ValueError:
            continue

    for ev in delivered_events:
        await hub.broadcast_json("events", ev.model_dump())
        await hub.broadcast_json(str(EventType.NEWS_DELIVERED), ev.model_dump())

    correlation_id = delivered_events[0].correlation_id if delivered_events else req.correlation_id
    return NewsPropagateResponse(delivered=len(delivered_events), correlation_id=correlation_id)


class NewsInboxResponseItem(BaseModel):
    delivery_id: str
    card_id: str
    variant_id: str
    from_actor_id: str
    visibility_level: str
    delivery_reason: str
    delivered_at: str
    text: str


class NewsInboxResponse(BaseModel):
    items: list[NewsInboxResponseItem]


@router.get("/news/inbox/{player_id}")
async def news_inbox(player_id: str, limit: int = 50) -> NewsInboxResponse:
    items = _news_service.list_inbox(player_id=player_id, limit=limit)
    return NewsInboxResponse(items=[NewsInboxResponseItem(**x) for x in items])


class NewsBroadcastRequest(BaseModel):
    variant_id: str
    actor_id: str
    channel: str = "GLOBAL_MANDATORY"
    visibility_level: str = "NORMAL"
    limit_users: int = 5000
    correlation_id: UUID | None = None


class NewsBroadcastResponse(BaseModel):
    delivered: int
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/broadcast")
async def news_broadcast(req: NewsBroadcastRequest) -> NewsBroadcastResponse:
    try:
        delivered, event_json = _news_service.broadcast_variant(
            variant_id=req.variant_id,
            channel=req.channel,
            visibility_level=req.visibility_level,
            actor_id=req.actor_id,
            limit_users=req.limit_users,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_BROADCASTED), event_json.model_dump())

    emergency_events = await _commonbot_emergency_runner.maybe_react(broadcast_event=event_json)
    for ev in emergency_events:
        await hub.broadcast_json("events", ev.model_dump())
        await hub.broadcast_json(str(ev.event_type), ev.model_dump())

    return NewsBroadcastResponse(
        delivered=delivered,
        event_id=event_json.event_id,
        correlation_id=event_json.correlation_id,
    )


class NewsChainStartRequest(BaseModel):
    kind: str
    actor_id: str
    t0_seconds: int = 60
    t0_at: str | None = None
    omen_interval_seconds: int = 10
    abort_probability: float = 0.3
    grant_count: int = 2
    seed: int = 1
    correlation_id: UUID | None = None


class NewsChainStartResponse(BaseModel):
    chain_id: str
    major_card_id: str
    t0_at: str


@router.post("/news/chains/start")
async def news_chain_start(req: NewsChainStartRequest) -> NewsChainStartResponse:
    try:
        t0_at = None
        if req.t0_at is not None:
            t0_at = datetime.fromisoformat(req.t0_at)
        result = _news_tick_engine.start_chain(
            kind=req.kind,
            actor_id=req.actor_id,
            t0_seconds=req.t0_seconds,
            t0_at=t0_at,
            omen_interval_seconds=req.omen_interval_seconds,
            abort_probability=req.abort_probability,
            grant_count=req.grant_count,
            seed=req.seed,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 广播链启动相关事件（card_created + chain_started）
    await hub.broadcast_json("events", result["card_created_event"].model_dump())
    await hub.broadcast_json(str(EventType.NEWS_CARD_CREATED), result["card_created_event"].model_dump())
    await hub.broadcast_json("events", result["chain_started_event"].model_dump())
    await hub.broadcast_json(str(EventType.NEWS_CHAIN_STARTED), result["chain_started_event"].model_dump())

    return NewsChainStartResponse(
        chain_id=str(result["chain_id"]),
        major_card_id=str(result["major_card_id"]),
        t0_at=str(result["t0_at"].isoformat()),
    )


class NewsTickRequest(BaseModel):
    now_iso: str | None = None
    limit: int = 50


class NewsTickResponse(BaseModel):
    now: str
    chains: list[Dict[str, Any]]


@router.post("/news/tick")
async def news_tick(req: NewsTickRequest) -> NewsTickResponse:
    now = None
    if req.now_iso is not None:
        now = datetime.fromisoformat(req.now_iso)
    result = await _news_tick_engine.tick(now=now, limit=req.limit)

    # 将 tick 内产生的事件推送到 WS
    for chain in result.get("chains", []):
        for action in (chain or {}).get("actions", []):
            for ev in (action or {}).get("events", []) or []:
                if not ev:
                    continue
                if isinstance(ev, dict):
                    await hub.broadcast_json("events", ev)
                    ev_type = ev.get("event_type")
                    if ev_type:
                        await hub.broadcast_json(str(ev_type), ev)
            for ev in (action or {}).get("emergency_events", []) or []:
                if not ev:
                    continue
                if isinstance(ev, dict):
                    await hub.broadcast_json("events", ev)
                    ev_type = ev.get("event_type")
                    if ev_type:
                        await hub.broadcast_json(str(ev_type), ev)
    return NewsTickResponse(now=str(result["now"]), chains=list(result["chains"]))


class NewsSuppressRequest(BaseModel):
    actor_id: str
    chain_id: str
    spend_influence: float
    signal_class: str | None = None
    scope: str = "chain"
    correlation_id: UUID | None = None


class NewsSuppressResponse(BaseModel):
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/suppress")
async def news_suppress(req: NewsSuppressRequest) -> NewsSuppressResponse:
    try:
        event_json = _news_tick_engine.suppress_propagation(
            actor_id=req.actor_id,
            chain_id=req.chain_id,
            spend_influence=req.spend_influence,
            signal_class=req.signal_class,
            scope=req.scope,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_PROPAGATION_SUPPRESSED), event_json.model_dump())
    return NewsSuppressResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


class NewsOwnershipGrantRequest(BaseModel):
    card_id: str
    to_user_id: str
    granter_id: str
    correlation_id: UUID | None = None


class NewsOwnershipTransferRequest(BaseModel):
    card_id: str
    from_user_id: str
    to_user_id: str
    transferred_by: str
    correlation_id: UUID | None = None


class NewsOwnershipEventResponse(BaseModel):
    event_id: UUID
    correlation_id: UUID | None


class NewsOwnedCardsResponse(BaseModel):
    cards: list[str]


@router.post("/news/ownership/grant")
async def news_ownership_grant(req: NewsOwnershipGrantRequest) -> NewsOwnershipEventResponse:
    try:
        event_json = _news_service.grant_ownership(
            card_id=req.card_id,
            to_user_id=req.to_user_id,
            granter_id=req.granter_id,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_OWNERSHIP_GRANTED), event_json.model_dump())
    return NewsOwnershipEventResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


@router.post("/news/ownership/transfer")
async def news_ownership_transfer(req: NewsOwnershipTransferRequest) -> NewsOwnershipEventResponse:
    try:
        event_json = _news_service.transfer_ownership(
            card_id=req.card_id,
            from_user_id=req.from_user_id,
            to_user_id=req.to_user_id,
            transferred_by=req.transferred_by,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_OWNERSHIP_TRANSFERRED), event_json.model_dump())
    return NewsOwnershipEventResponse(event_id=event_json.event_id, correlation_id=event_json.correlation_id)


@router.get("/news/ownership/{user_id}")
async def news_ownership_list(user_id: str, limit: int = 200) -> NewsOwnedCardsResponse:
    cards = _news_service.list_owned_cards(user_id=user_id, limit=limit)
    return NewsOwnedCardsResponse(cards=cards)


class NewsStorePurchaseRequest(BaseModel):
    buyer_user_id: str
    kind: str
    preset_id: str | None = None
    image_anchor_id: str | None = None
    image_uri: str | None = None
    truth_payload: Dict[str, Any] | None = None
    symbols: list[str] = []
    tags: list[str] = []
    initial_text: str = ""

    # Only used for MAJOR_EVENT
    t0_seconds: int = 60
    t0_at: str | None = None
    omen_interval_seconds: int = 10
    abort_probability: float = 0.3
    grant_count: int = 2
    seed: int = 1
    correlation_id: UUID | None = None

@router.post("/news/store/purchase")
async def news_store_purchase(req: NewsStorePurchaseRequest) -> NewsStorePurchaseResponse:
    items_cfg: List[Dict[str, Any]] = [
        {"kind": "RUMOR", "price_cash": 50.0, "requires_symbols": False},
        {"kind": "LEAK", "price_cash": 120.0, "requires_symbols": True},
        {"kind": "ANALYST_REPORT", "price_cash": 80.0, "requires_symbols": True},
        {"kind": "OMEN", "price_cash": 100.0, "requires_symbols": True},
        {"kind": "DISCLOSURE", "price_cash": 180.0, "requires_symbols": True},
        {"kind": "EARNINGS", "price_cash": 150.0, "requires_symbols": True},
        {"kind": "MAJOR_EVENT", "price_cash": 300.0, "requires_symbols": True},
    ]
    kind_key = str(req.kind)
    cfg = next((x for x in items_cfg if str(x.get("kind")) == kind_key), None)
    if cfg is None:
        raise HTTPException(status_code=400, detail="unknown kind")

    system_price = float(cfg.get("price_cash") or 0.0)
    if system_price <= 0:
        raise HTTPException(status_code=400, detail="invalid system price")

    requires_symbols = bool(cfg.get("requires_symbols") or False)
    if requires_symbols and not (req.symbols or []):
        raise HTTPException(status_code=400, detail="symbols required for this kind")

    purchase_event_id = str(uuid4())
    try:
        spend_cash(account_id=req.buyer_user_id, amount=float(system_price), event_id=purchase_event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # MAJOR_EVENT：购买即创建事件链，T0 延迟广播；不立即投递给所有人
    if str(req.kind) == "MAJOR_EVENT":
        try:
            t0_at = None
            if req.t0_at is not None:
                t0_at = datetime.fromisoformat(req.t0_at)
            result = _news_tick_engine.start_chain(
                kind=req.kind,
                actor_id=req.buyer_user_id,
                t0_seconds=req.t0_seconds,
                t0_at=t0_at,
                omen_interval_seconds=req.omen_interval_seconds,
                abort_probability=req.abort_probability,
                grant_count=req.grant_count,
                seed=req.seed,
                symbols=req.symbols or [],
                correlation_id=req.correlation_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        major_card_id = str(result["major_card_id"])
        # 购买者获得主事件卡所有权
        try:
            _news_service.grant_ownership(
                card_id=major_card_id,
                to_user_id=req.buyer_user_id,
                granter_id="system",
                correlation_id=req.correlation_id,
            )
        except ValueError:
            pass

        return NewsStorePurchaseResponse(
            kind=str(req.kind),
            buyer_user_id=str(req.buyer_user_id),
            chain_id=str(result["chain_id"]),
            card_id=major_card_id,
            variant_id=None,
        )

    # 普通卡：等效“随机拾到”，只投递给购买者，后续靠其手动助推传播
    symbols = req.symbols or []
    presets = _news_service.get_preset_templates(kind=str(req.kind), symbols=symbols)
    preset_id = str(req.preset_id) if req.preset_id is not None else ""
    initial_text = ""
    if preset_id:
        prefix = f"{str(req.kind)}:"
        if not preset_id.startswith(prefix):
            raise HTTPException(status_code=400, detail="invalid preset_id")
        try:
            idx = int(preset_id.split(":", 1)[1])
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid preset_id") from exc
        if idx < 0 or idx >= len(presets):
            raise HTTPException(status_code=400, detail="preset_id out of range")
        initial_text = str(presets[idx])
    else:
        # default preset
        initial_text = str(presets[0]) if presets else _news_service.get_preset_template(kind=str(req.kind), symbols=symbols)

    card_id, card_event = _news_service.create_card(
        kind=req.kind,
        image_anchor_id=req.image_anchor_id,
        image_uri=req.image_uri,
        truth_payload=req.truth_payload,
        symbols=symbols,
        tags=req.tags,
        actor_id=req.buyer_user_id,
        correlation_id=req.correlation_id,
    )
    await hub.broadcast_json("events", card_event.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_CARD_CREATED), card_event.model_dump())

    variant_id, variant_event = _news_service.emit_variant(
        card_id=card_id,
        author_id=req.buyer_user_id,
        text=initial_text,
        parent_variant_id=None,
        influence_cost=0.0,
        risk_roll=None,
        correlation_id=req.correlation_id,
    )
    await hub.broadcast_json("events", variant_event.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_VARIANT_EMITTED), variant_event.model_dump())

    try:
        ownership_event = _news_service.grant_ownership(
            card_id=card_id,
            to_user_id=req.buyer_user_id,
            granter_id="system",
            correlation_id=req.correlation_id,
        )
        await hub.broadcast_json("events", ownership_event.model_dump())
        await hub.broadcast_json(str(EventType.NEWS_OWNERSHIP_GRANTED), ownership_event.model_dump())
    except ValueError:
        pass

    try:
        _delivery_id, delivered_event = _news_service.deliver_variant(
            variant_id=variant_id,
            to_player_id=req.buyer_user_id,
            from_actor_id="system",
            visibility_level="NORMAL",
            delivery_reason="PURCHASED",
            correlation_id=req.correlation_id,
        )
        await hub.broadcast_json("events", delivered_event.model_dump())
        await hub.broadcast_json(str(EventType.NEWS_DELIVERED), delivered_event.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return NewsStorePurchaseResponse(
        kind=str(req.kind),
        buyer_user_id=str(req.buyer_user_id),
        card_id=str(card_id),
        variant_id=str(variant_id),
        chain_id=None,
    )