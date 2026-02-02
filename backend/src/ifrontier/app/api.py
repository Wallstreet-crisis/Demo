from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
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
from ifrontier.infra.sqlite.ledger import apply_trade_executed, create_account, get_snapshot
from ifrontier.infra.sqlite.market import get_candles, get_last_price, get_price_series, record_trade
from ifrontier.services.matching import submit_limit_order, submit_market_order
from ifrontier.services.market_analytics import get_quote
from ifrontier.services.valuation import value_account
from ifrontier.domain.players.caste import get_caste_config
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.services.contracts import ContractService
from ifrontier.services.contract_agent import ContractAgent
from ifrontier.services.news import NewsService
from ifrontier.services.news_tick import NewsTickEngine
from ifrontier.services.game_time import load_game_time_config_from_env
from ifrontier.services.market_session import get_market_session
router = APIRouter()

_driver = create_driver()
_event_store = Neo4jEventStore(_driver)
_contract_service = ContractService(_driver, _event_store)
_contract_agent = ContractAgent()
_news_service = NewsService(_driver, _event_store)
_news_tick_engine = NewsTickEngine(_driver, _event_store, _news_service)
_commonbot_emergency_runner = CommonBotEmergencyRunner(news=_news_service, event_store=_event_store)

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

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


class _AnyPayload(RootModel[Dict[str, Any]]):
    pass


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
    order_id, _ = submit_limit_order(
        account_id=account_id,
        symbol=req.symbol,
        side=req.side,
        price=req.price,
        quantity=req.quantity,
    )
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
        order_id, _matches = submit_market_order(
            account_id=account_id,
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

class PlayerAccountResponse(BaseModel):
    account_id: str
    cash: float
    positions: Dict[str, float]


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
    risk_roll: Dict[str, Any] | None = None
    correlation_id: UUID | None = None


class NewsMutateVariantResponse(BaseModel):
    new_variant_id: str
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/variants/mutate")
async def news_mutate_variant(req: NewsMutateVariantRequest) -> NewsMutateVariantResponse:
    try:
        new_variant_id, event_json = _news_service.mutate_variant(
            parent_variant_id=req.parent_variant_id,
            editor_id=req.editor_id,
            new_text=req.new_text,
            influence_cost=req.influence_cost,
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
    limit: int = 50
    correlation_id: UUID | None = None


class NewsPropagateResponse(BaseModel):
    delivered: int
    correlation_id: UUID | None


@router.post("/news/propagate")
async def news_propagate(req: NewsPropagateRequest) -> NewsPropagateResponse:
    try:
        delivered_events = _news_service.propagate_to_followers(
            variant_id=req.variant_id,
            from_actor_id=req.from_actor_id,
            visibility_level=req.visibility_level,
            spend_influence=req.spend_influence,
            limit=req.limit,
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    emergency_events = _commonbot_emergency_runner.maybe_react(broadcast_event=event_json)
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
        result = _news_tick_engine.start_chain(
            kind=req.kind,
            actor_id=req.actor_id,
            t0_seconds=req.t0_seconds,
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
    result = _news_tick_engine.tick(now=now, limit=req.limit)

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