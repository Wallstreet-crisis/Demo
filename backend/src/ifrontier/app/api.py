from __future__ import annotations

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
from ifrontier.infra.sqlite.ledger import apply_trade_executed, create_account, get_snapshot
from ifrontier.services.matching import submit_limit_order, submit_market_order
from ifrontier.domain.players.caste import get_caste_config
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.services.contracts import ContractService
router = APIRouter()

_driver = create_driver()
_event_store = Neo4jEventStore(_driver)
_contract_service = ContractService(_driver, _event_store)

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

    _event_store.append(event_json)
    await hub.broadcast_json("events", event_json.model_dump())
    await hub.broadcast_json(str(EventType.TRADE_EXECUTED), event_json.model_dump())

    return DebugExecuteTradeResponse(event_id=event_json.event_id, correlation_id=correlation_id)


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
    order_id, _matches = submit_limit_order(
        account_id=req.account_id,
        symbol=req.symbol,
        side=req.side,
        price=req.price,
        quantity=req.quantity,
    )

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
    submit_market_order(
        account_id=account_id,
        symbol=req.symbol,
        side=req.side,
        quantity=req.quantity,
    )


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