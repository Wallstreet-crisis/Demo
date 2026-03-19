from __future__ import annotations

import asyncio
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, RootModel

from ifrontier.app.ws import hub
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.event_store import SqliteEventStore
from ifrontier.services.commonbot import run_commonbot_for_earnings
from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
from ifrontier.infra.sqlite.ledger import apply_trade_executed, create_account, get_snapshot, list_ledger_entries, spend_cash
from ifrontier.infra.sqlite.market import get_candles, get_last_price, get_price_series, record_trade
from ifrontier.infra.sqlite.orders import cancel_order, list_open_orders, list_open_orders_by_account
from ifrontier.services.matching import submit_limit_order, submit_market_order
from ifrontier.services.market_analytics import get_market_trends, get_quote
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
from ifrontier.infra.llm.client import LlmClient, LlmConfig, LlmError, extract_first_message_text
from ifrontier.services.app_settings import (
    get_llm_settings_view,
    get_user_preferences,
    load_secure_llm_config,
    save_llm_settings_layered,
    save_llm_settings,
    save_user_preferences,
)

router = APIRouter()

_event_store = SqliteEventStore()
_contract_service = ContractService(_event_store)
_contract_agent = ContractAgent()
_chat_service = ChatService(event_store=_event_store)
_news_service = NewsService(_event_store)
_news_tick_engine = NewsTickEngine(_event_store, _news_service)
_commonbot_emergency_runner = CommonBotEmergencyRunner(
    news=_news_service,
    event_store=_event_store,
    market_data_provider=lambda symbols: get_market_trends(symbols=symbols)
)

def _news_debug_enabled() -> bool:
    """检查是否开启新闻调试。"""
    return str(os.getenv("IF_NEWS_DEBUG") or "0").strip().lower() in {"1", "true", "yes"}

# ==========================================
# 房间管理 (Rooms API)
# ==========================================

from ifrontier.app.room_engine import room_manager
from ifrontier.app.room_meta import get_local_rooms, create_or_update_room_meta

class CreateRoomRequest(BaseModel):
    room_id: Optional[str] = None
    player_id: str
    name: Optional[str] = None

@router.post("/rooms")
async def create_room(req: CreateRoomRequest) -> Dict[str, Any]:
    """创建并拉起一个新的房间引擎"""
    new_room_id = req.room_id
    if not new_room_id:
        import uuid
        new_room_id = f"room_{uuid.uuid4().hex[:8]}"
        
    await room_manager.start_room(new_room_id)
    create_or_update_room_meta(room_id=new_room_id, player_id=req.player_id, name=req.name)
    return {"ok": True, "room_id": new_room_id}

@router.get("/rooms")
async def list_rooms() -> Dict[str, Any]:
    """列出当前运行中的房间"""
    return {"rooms": room_manager.get_active_rooms()}

@router.get("/rooms/local")
async def list_local_rooms() -> Dict[str, Any]:
    """列出本地所有的存档记录"""
    return {"rooms": [r.model_dump() for r in get_local_rooms()]}

class UpdateRoomMetaRequest(BaseModel):
    name: str

@router.post("/rooms/{room_id}/meta")
async def update_room_meta(room_id: str, req: UpdateRoomMetaRequest) -> Dict[str, Any]:
    # player_id 不重要，仅用于更新名称
    meta = create_or_update_room_meta(room_id=room_id, player_id="UNKNOWN", name=req.name)
    return {"ok": True, "meta": meta.model_dump()}

@router.post("/rooms/{room_id}/close")
async def close_room(room_id: str) -> Dict[str, Any]:
    """关闭指定的房间并停止其所有调度器"""
    await room_manager.stop_room(room_id)
    return {"ok": True}

# ==========================================

@router.post("/debug/bots/reset_balances")
async def debug_bots_reset_balances() -> Dict[str, Any]:
    """强制刷新全服 Bot 的资金和持仓。"""
    try:
        from ifrontier.infra.sqlite.bots import init_bot_accounts
        init_bot_accounts()
        return {"ok": True, "message": "Bot balances and positions reset to aggressive levels."}
    except Exception as exc:
        print(f"[API:Debug] Failed to reset bot balances: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


class AppDisplaySettings(BaseModel):
    price_color_scheme: str = "cn_red_up"
    compact_quotes: bool = False
    show_market_phase_badge: bool = True


class AppPreferencesResponse(BaseModel):
    actor_id: str
    language: str
    rise_color: str
    display: AppDisplaySettings
    updated_at: Optional[str] = None


class AppPreferencesUpdateRequest(BaseModel):
    actor_id: str
    language: Optional[str] = None
    rise_color: Optional[str] = None
    display: Optional[Dict[str, Any]] = None


class LlmSettingsResponse(BaseModel):
    actor_id: str
    can_manage: bool
    provider: str
    model: str
    base_url: str
    timeout_seconds: float
    profiles: Dict[str, Any] = {}
    routing: Dict[str, str] = {}
    providers_supported: List[str] = []
    provider_api_key_masks: Dict[str, Optional[str]] = {}
    has_api_key: bool
    api_key_masked: Optional[str] = None


class LlmSettingsUpdateRequest(BaseModel):
    actor_id: str
    provider: str = "openrouter"
    model: str = "google/gemini-2.5-flash"
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 20.0
    profiles: Optional[Dict[str, Any]] = None
    routing: Optional[Dict[str, str]] = None
    api_key: Optional[str] = None
    api_keys: Optional[Dict[str, str]] = None


class LlmConnectionTestRequest(BaseModel):
    actor_id: str
    provider: str = "openrouter"
    model: str = "google/gemini-2.5-flash"
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 20.0
    api_key: Optional[str] = None


class LlmConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model: str
    base_url: str
    message: str
    model_count: int = 0
    first_model: Optional[str] = None


class LlmNetworkDiagnosticRequest(BaseModel):
    actor_id: str
    providers: Optional[List[str]] = None
    api_keys: Optional[Dict[str, str]] = None
    timeout_seconds: float = 12.0


class LlmNetworkDiagnosticItem(BaseModel):
    provider: str
    base_url: str
    ok: bool
    latency_ms: float
    message: str
    model_count: int = 0
    first_model: Optional[str] = None


class LlmNetworkDiagnosticResponse(BaseModel):
    items: List[LlmNetworkDiagnosticItem]


@router.get("/settings/preferences/{actor_id}")
async def settings_get_preferences(actor_id: str) -> AppPreferencesResponse:
    prefs = get_user_preferences(actor_id)
    return AppPreferencesResponse(
        actor_id=str(actor_id),
        language=str(prefs.get("language") or "zh-CN"),
        rise_color=str(prefs.get("rise_color") or "red_up"),
        display=AppDisplaySettings(**dict(prefs.get("display") or {})),
        updated_at=prefs.get("updated_at"),
    )


@router.post("/settings/preferences")
async def settings_save_preferences(req: AppPreferencesUpdateRequest) -> AppPreferencesResponse:
    prefs = save_user_preferences(
        actor_id=req.actor_id,
        language=req.language,
        rise_color=req.rise_color,
        display=dict(req.display or {}),
    )
    return AppPreferencesResponse(
        actor_id=str(req.actor_id),
        language=str(prefs.get("language") or "zh-CN"),
        rise_color=str(prefs.get("rise_color") or "red_up"),
        display=AppDisplaySettings(**dict(prefs.get("display") or {})),
        updated_at=prefs.get("updated_at"),
    )


@router.get("/settings/llm/{actor_id}")
async def settings_get_llm(actor_id: str) -> LlmSettingsResponse:
    cfg = get_llm_settings_view(actor_id=actor_id)
    return LlmSettingsResponse(actor_id=str(actor_id), **cfg)


@router.post("/settings/llm")
async def settings_save_llm(req: LlmSettingsUpdateRequest) -> LlmSettingsResponse:
    try:
        if req.profiles is not None or req.routing is not None:
            cfg = save_llm_settings_layered(
                actor_id=req.actor_id,
                provider=req.provider,
                api_key=req.api_key,
                api_keys=dict(req.api_keys or {}),
                profiles=dict(req.profiles or {}),
                routing=dict(req.routing or {}),
            )
        else:
            cfg = save_llm_settings(
                actor_id=req.actor_id,
                provider=req.provider,
                model=req.model,
                base_url=req.base_url,
                timeout_seconds=float(req.timeout_seconds),
                api_key=req.api_key,
            )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return LlmSettingsResponse(actor_id=str(req.actor_id), **cfg)


@router.post("/settings/llm/test")
async def settings_test_llm(req: LlmConnectionTestRequest) -> LlmConnectionTestResponse:
    view = get_llm_settings_view(actor_id=req.actor_id)
    if not bool(view.get("can_manage")):
        raise HTTPException(status_code=403, detail="actor is not allowed to manage llm settings")

    provider = str(req.provider or "openrouter").strip().lower()
    current = load_secure_llm_config()
    current_keys = current.get("api_keys") or {}
    legacy_provider = str(current.get("provider") or provider or "openrouter").strip().lower()
    legacy_api_key = str(current.get("api_key") or "").strip()
    if legacy_api_key and legacy_provider not in current_keys:
        current_keys = {**dict(current_keys), legacy_provider: legacy_api_key}
    api_key = str(req.api_key).strip() if req.api_key is not None and str(req.api_key).strip() else str(current_keys.get(provider) or "")
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key is required for connection test")

    client = LlmClient(
        LlmConfig(
            provider=provider,
            api_key=api_key,
            model=str(req.model or current.get("model") or "google/gemini-2.5-flash"),
            base_url=str(req.base_url or current.get("base_url") or str(view.get("base_url") or "https://openrouter.ai/api/v1")),
            timeout_seconds=float(req.timeout_seconds or current.get("timeout_seconds") or 20.0),
        )
    )
    try:
        result = client.chat_completions(
            system="You are a connectivity probe. Reply with a single token: OK",
            user="Respond with OK only.",
            temperature=0.0,
            max_tokens=8,
        )
    except LlmError as exc:
        return LlmConnectionTestResponse(
            ok=False,
            provider=provider,
            model=str(req.model or current.get("model") or "google/gemini-2.5-flash"),
            base_url=str(req.base_url or current.get("base_url") or str(view.get("base_url") or "https://openrouter.ai/api/v1")),
            message=str(exc)[:500] or "LLM connection failed",
        )

    return LlmConnectionTestResponse(
        ok=True,
        provider=provider,
        model=str(req.model or current.get("model") or "google/gemini-2.5-flash"),
        base_url=str(req.base_url or current.get("base_url") or str(view.get("base_url") or "https://openrouter.ai/api/v1")),
        message="指定模型可用",
        model_count=int(len(result.get("choices") or [])),
        first_model=extract_first_message_text(result)[:80] or None,
    )


@router.post("/settings/llm/diagnostics")
async def settings_llm_diagnostics(req: LlmNetworkDiagnosticRequest) -> LlmNetworkDiagnosticResponse:
    view = get_llm_settings_view(actor_id=req.actor_id)
    if not bool(view.get("can_manage")):
        raise HTTPException(status_code=403, detail="actor is not allowed to manage llm settings")

    current = load_secure_llm_config()
    stored_keys = dict(current.get("api_keys") or {})
    legacy_provider = str(current.get("provider") or "openrouter").strip().lower()
    legacy_api_key = str(current.get("api_key") or "").strip()
    if legacy_api_key and legacy_provider not in stored_keys:
        stored_keys[legacy_provider] = legacy_api_key
    req_keys = {str(k).strip().lower(): str(v).strip() for k, v in dict(req.api_keys or {}).items() if str(v).strip()}
    merged_keys = {**stored_keys, **req_keys}
    providers = [
        str(x).strip().lower()
        for x in (req.providers or view.get("providers_supported") or ["openrouter", "deepseek", "minimax", "kimi", "openai", "anthropic", "google", "xai"])
        if str(x).strip()
    ]

    base_url_map = {
        "openrouter": "https://openrouter.ai/api/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "minimax": "https://api.minimax.chat/v1",
        "kimi": "https://api.moonshot.cn/v1",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "google": "https://generativelanguage.googleapis.com/v1beta/openai",
        "xai": "https://api.x.ai/v1",
    }
    default_model_map = {
        "openrouter": "google/gemini-2.5-flash",
        "deepseek": "deepseek-chat",
        "minimax": "MiniMax-M1",
        "kimi": "kimi-k2-0711-preview",
        "openai": "gpt-4.1-mini",
        "anthropic": "claude-sonnet-4-20250514",
        "google": "gemini-2.5-flash",
        "xai": "grok-3-mini",
    }

    items: List[LlmNetworkDiagnosticItem] = []
    for provider in providers:
        api_key = str(merged_keys.get(provider) or "").strip()
        if not api_key:
            items.append(
                LlmNetworkDiagnosticItem(
                    provider=provider,
                    base_url=str(base_url_map.get(provider) or ""),
                    ok=False,
                    latency_ms=0.0,
                    message="missing api key",
                )
            )
            continue

        started_at = time.perf_counter()
        client = LlmClient(
            LlmConfig(
                provider=provider,
                api_key=api_key,
                model=str(default_model_map.get(provider) or ""),
                base_url=str(base_url_map.get(provider) or ""),
                timeout_seconds=float(req.timeout_seconds or 12.0),
            )
        )
        try:
            ping = client.ping()
            items.append(
                LlmNetworkDiagnosticItem(
                    provider=provider,
                    base_url=str(base_url_map.get(provider) or ""),
                    ok=True,
                    latency_ms=(time.perf_counter() - started_at) * 1000.0,
                    message="models endpoint reachable",
                    model_count=int(ping.get("model_count") or 0),
                    first_model=ping.get("first_model"),
                )
            )
        except LlmError as exc:
            items.append(
                LlmNetworkDiagnosticItem(
                    provider=provider,
                    base_url=str(base_url_map.get(provider) or ""),
                    ok=False,
                    latency_ms=(time.perf_counter() - started_at) * 1000.0,
                    message=str(exc)[:500] or "diagnostic failed",
                )
            )

    return LlmNetworkDiagnosticResponse(items=items)

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
    envelope = EventEnvelope[_AnyPayload](
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
    symbol_options: List[str] = []

class NewsStoreCatalogResponse(BaseModel):
    items: List[NewsStoreCatalogItem]

@router.get("/news/store/catalog")
async def news_store_catalog() -> NewsStoreCatalogResponse:
    from ifrontier.infra.sqlite.securities import list_securities

    items_cfg: List[Dict[str, Any]] = [
        {"kind": "RUMOR", "price_cash": 2000.0, "requires_symbols": False},
        {"kind": "LEAK", "price_cash": 15000.0, "requires_symbols": True},
        {"kind": "ANALYST_REPORT", "price_cash": 8000.0, "requires_symbols": True},
        {"kind": "OMEN", "price_cash": 25000.0, "requires_symbols": True},
        {"kind": "DISCLOSURE", "price_cash": 45000.0, "requires_symbols": True},
        {"kind": "EARNINGS", "price_cash": 35000.0, "requires_symbols": True},
        {"kind": "MAJOR_EVENT", "price_cash": 100000.0, "requires_symbols": True},
        {"kind": "WORLD_EVENT", "price_cash": 500000.0, "requires_symbols": False},
    ]

    sec_symbols = [s.symbol for s in list_securities()]
    if not sec_symbols:
        sec_symbols = ["BLUEGOLD"]

    default_symbol_by_kind: Dict[str, List[str]] = {
        "LEAK": ["CIVILBANK", "NEURALINK", "FOODMART", "BLUEGOLD"],
        "ANALYST_REPORT": ["NEURALINK", "CIVILBANK", "FOODMART", "BLUEGOLD"],
        "OMEN": ["BLUEGOLD", "CIVILBANK", "NEURALINK", "FOODMART"],
        "DISCLOSURE": ["CIVILBANK", "BLUEGOLD", "NEURALINK", "FOODMART"],
        "EARNINGS": ["NEURALINK", "CIVILBANK", "FOODMART", "BLUEGOLD"],
        "MAJOR_EVENT": ["BLUEGOLD", "NEURALINK", "CIVILBANK", "FOODMART"],
    }

    out: List[NewsStoreCatalogItem] = []
    for it in items_cfg:
        kind = str(it["kind"])
        requires_symbols = bool(it.get("requires_symbols") or False)
        symbol_options: List[str] = []
        if requires_symbols:
            preferred = default_symbol_by_kind.get(kind, [])
            for p in preferred:
                if p in sec_symbols and p not in symbol_options:
                    symbol_options.append(p)
            if not symbol_options:
                symbol_options = [str(sec_symbols[0])]

        preview_symbols = symbol_options[:1]
        presets_texts = _news_service.get_preset_templates(kind=kind, symbols=preview_symbols)
        preview = (
            presets_texts[0]
            if presets_texts
            else _news_service.get_preset_template(kind=kind, symbols=preview_symbols)
        )
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
                symbol_options=list(symbol_options),
            )
        )

    return NewsStoreCatalogResponse(items=out)

class NewsInboxResponseItem(BaseModel):
    delivery_id: str
    card_id: str
    variant_id: str
    kind: str
    from_actor_id: str
    visibility_level: str
    delivery_reason: str
    created_at: str
    text: str
    symbols: List[str] = []
    tags: List[str] = []
    truth_payload: Optional[Dict[str, Any]] = None
    owns_card: bool = False

class NewsInboxResponse(BaseModel):
    items: List[NewsInboxResponseItem]

@router.get("/news/inbox/{player_id}")
async def news_inbox(player_id: str, limit: int = 50) -> NewsInboxResponse:
    items = _news_service.list_inbox(player_id=player_id, limit=limit)
    return NewsInboxResponse(items=[NewsInboxResponseItem(**it) for it in items])

class NewsFeedItem(BaseModel):
    variant_id: str
    card_id: str
    kind: str
    author_id: str
    text: str
    image_uri: Optional[str] = None
    created_at: str
    symbols: List[str] = []
    tags: List[str] = []

class NewsFeedResponse(BaseModel):
    items: List[NewsFeedItem]

@router.get("/news/public/feed")
async def news_public_feed(limit: int = 20) -> NewsFeedResponse:
    """获取全服广播新闻流。"""
    from ifrontier.infra.sqlite import news as news_db

    rows = news_db.list_news(limit=limit)
    items = []
    for r in rows:
        items.append(NewsFeedItem(
            variant_id=r.variant_id,
            card_id=r.card_id,
            kind=r.kind,
            author_id=r.author_id,
            text=r.text,
            image_uri=r.image_uri,
            created_at=r.created_at,
            symbols=r.symbols or [],
            tags=r.tags or [],
        ))
    return NewsFeedResponse(items=items)

class DebugNewsChainsResponse(BaseModel):
    items: List[Dict[str, Any]]

@router.get("/debug/news/chains")
async def debug_news_chains(limit: int = 50) -> DebugNewsChainsResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    from ifrontier.infra.sqlite import news_chain as news_chain_db

    rows = news_chain_db.list_all_chains(limit=limit)
    return DebugNewsChainsResponse(items=rows)

class DebugNewsChainResponse(BaseModel):
    chain: Dict[str, Any] | None = None
    major_card: Dict[str, Any] | None = None
    variants: List[Dict[str, Any]] = []

@router.get("/debug/news/chains/{chain_id}")
async def debug_news_chain(chain_id: str, variants_limit: int = 50) -> DebugNewsChainResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    from ifrontier.infra.sqlite import news_chain as news_chain_db
    from ifrontier.infra.sqlite import news as news_db

    chain_data = news_chain_db.get_chain_by_id(chain_id)
    major_card = None
    if chain_data and chain_data.get("major_card_id"):
        major_card = news_db.get_news(chain_data["major_card_id"])

    variants = []
    if chain_data and chain_data.get("major_card_id"):
        variants = news_db.list_variants_by_card(chain_data["major_card_id"], variants_limit)

    return DebugNewsChainResponse(
        chain=chain_data,
        major_card=dict(major_card) if major_card else None,
        variants=variants
    )

class DebugNewsDeliveriesResponse(BaseModel):
    items: List[Dict[str, Any]]

@router.get("/debug/news/deliveries")
async def debug_news_deliveries(variant_id: str, limit: int = 200) -> DebugNewsDeliveriesResponse:
    if not _news_debug_enabled():
        raise HTTPException(status_code=403, detail="news debug disabled")

    from ifrontier.infra.sqlite import news as news_db

    rows = news_db.list_deliveries_by_variant(variant_id, limit)
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
    try:
        _ = get_snapshot(user_id)
    except Exception:
        create_account(user_id, owner_type="user", initial_cash=0.0)
    st = upsert_hosting_state(user_id=user_id, enabled=True, status="ON_IDLE")
    from ifrontier.domain.events.payloads import AiHostingStateChangedPayload
    
    payload = AiHostingStateChangedPayload(
        user_id=str(user_id),
        enabled=True,
        status="ON_IDLE",
        changed_at=datetime.now(timezone.utc),
    )
    env = EventEnvelope[AiHostingStateChangedPayload](
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
    from ifrontier.domain.events.payloads import AiHostingStateChangedPayload
    
    payload = AiHostingStateChangedPayload(
        user_id=str(user_id),
        enabled=False,
        status="OFF",
        changed_at=datetime.now(timezone.utc),
    )
    env = EventEnvelope[AiHostingStateChangedPayload](
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
        # 测试环境中 TestClient 可能不会触发 lifespan，导致 scheduler 未启动。
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

    # Bot 真实下单：对 BUY/SELL 决策，用 bot 账户提交限价单进入撮合。
    action = (decision_json.payload or {}).get("action")
    confidence = float((decision_json.payload or {}).get("confidence") or 0.0)
    if action in {"BUY", "SELL"} and req.price_series:
        last_price = req.price_series[-1]
        eps = 0.001
        order_price = last_price * (1 + eps) if action == "BUY" else last_price * (1 - eps)

        # 简单规则：高置信度使用机构账户，低置信度使用散户账户。
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
            # 资产不足时忽略，不影响接口返回。
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

    # Apply ledger update; 璐︽湰鏍￠獙澶辫触鏃惰繑鍥?400锛岃€屼笉鏄?500
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
    listing_price: float | None = None
    day_open: float | None = None
    day_amplitude_pct: float | None = None
    sector: str = ""
    status: str = "TRADABLE"
    high_24h: float | None = None
    low_24h: float | None = None
    volume_24h: float | None = None


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
        listing_price=q.listing_price,
        day_open=q.day_open,
        day_amplitude_pct=q.day_amplitude_pct,
        sector=q.sector,
        status=q.status,
        high_24h=q.high_24h,
        low_24h=q.low_24h,
        volume_24h=q.volume_24h,
    )


class MarketSummaryResponse(BaseModel):
    total_turnover: float
    total_trades: int
    top_gainers: List[Dict[str, Any]]
    top_losers: List[Dict[str, Any]]
    active_symbols: List[Dict[str, Any]]
    refreshed_at: datetime


@router.get("/market/summary")
async def market_summary() -> MarketSummaryResponse:
    from ifrontier.services.market_analytics import get_market_summary
    s = get_market_summary()
    return MarketSummaryResponse(
        total_turnover=s.total_turnover,
        total_trades=s.total_trades,
        top_gainers=s.top_gainers,
        top_losers=s.top_losers,
        active_symbols=s.active_symbols,
        refreshed_at=s.refreshed_at,
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
        v = value_account(account_id=str(account_id).lower(), discount_factor=discount_factor)
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


class LedgerEntryResponse(BaseModel):
    entry_id: str
    account_id: str
    asset_type: str
    symbol: str
    delta: float
    event_id: str
    created_at: str


class AccountLedgerResponse(BaseModel):
    account_id: str
    items: List[LedgerEntryResponse]


@router.get("/accounts/{account_id}/ledger")
async def account_ledger(account_id: str, limit: int = 200, before: str | None = None) -> AccountLedgerResponse:
    rows = list_ledger_entries(account_id=str(account_id).lower(), limit=int(limit), before=before)
    return AccountLedgerResponse(
        account_id=str(account_id).lower(),
        items=[LedgerEntryResponse(**r) for r in rows],
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
    # 杩欓噷鍙槸闄愪环鍗曟彁浜ゅ叆鍙ｏ紝瀹為檯鎾悎鍜岃璐︾敱 MatchingEngine + SQLite 璐︽湰澶勭悊
    try:
        order_id, _matches = submit_limit_order(
        account_id=req.account_id.lower(),
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
    account_id = f"user:{str(req.player_id).lower()}"
    # 如果提供 caste_id，优先使用阶级配置；否则回退到显式 initial_cash 或 0。
    initial_cash = 0.0
    positions: Dict[str, float] = {}
    caste_id = req.caste_id

    if caste_id is not None:
        cfg = get_caste_config(caste_id)
        if cfg is not None:
            initial_cash = cfg.initial_cash
            positions = cfg.initial_positions
    if req.initial_cash is not None:
        initial_cash = req.initial_cash

    create_account(account_id, owner_type="user", initial_cash=float(initial_cash), caste_id=caste_id)

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


class OrderBookEntryResponse(BaseModel):
    order_id: str
    account_id: str
    price: float
    quantity_remaining: float
    created_at: str


class OrderBookResponse(BaseModel):
    symbol: str
    bids: List[OrderBookEntryResponse]
    asks: List[OrderBookEntryResponse]


class MyOpenOrderResponse(BaseModel):
    order_id: str
    symbol: str
    side: str
    price: float
    quantity_remaining: float
    created_at: str


class MyOpenOrdersListResponse(BaseModel):
    items: List[MyOpenOrderResponse]


@router.post("/orders/limit")
async def submit_player_limit_order(req: PlayerLimitOrderRequest) -> PlayerOrderResponse:
    account_id = f"user:{str(req.player_id).lower()}"
    try:
        order_id, matches = submit_limit_order(
            account_id=account_id,
            symbol=req.symbol,
            side=req.side,
            price=float(req.price),
            quantity=float(req.quantity),
        )
        # 骞挎挱鎴愪氦浜嬩欢
        for m in matches:
            ev = m.executed_event.model_dump()
            await hub.broadcast_json("events", ev)
            ev_type = ev.get("event_type")
            if ev_type:
                await hub.broadcast_json(str(ev_type), ev)

        return PlayerOrderResponse(order_id=order_id)
    except Exception as exc:
        print(f"[API:Order] Failed to submit limit order: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/orders/book/{symbol}")
async def get_order_book(symbol: str, limit: int = 20) -> OrderBookResponse:
    try:
        bids = list_open_orders(symbol=symbol, side="BUY", limit=limit)
        asks = list_open_orders(symbol=symbol, side="SELL", limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return OrderBookResponse(
        symbol=symbol,
        bids=[
            OrderBookEntryResponse(
                order_id=o.order_id,
                account_id=o.account_id,
                price=o.price,
                quantity_remaining=o.quantity_remaining,
                created_at=o.created_at,
            )
            for o in bids
        ],
        asks=[
            OrderBookEntryResponse(
                order_id=o.order_id,
                account_id=o.account_id,
                price=o.price,
                quantity_remaining=o.quantity_remaining,
                created_at=o.created_at,
            )
            for o in asks
        ],
    )


@router.get("/orders/open/{player_id}")
async def get_my_open_orders(player_id: str, symbol: str | None = None, limit: int = 50) -> MyOpenOrdersListResponse:
    account_id = f"user:{str(player_id).lower()}"
    try:
        rows = list_open_orders_by_account(account_id=account_id, symbol=symbol, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MyOpenOrdersListResponse(
        items=[
            MyOpenOrderResponse(
                order_id=o.order_id,
                symbol=o.symbol,
                side=o.side,
                price=o.price,
                quantity_remaining=o.quantity_remaining,
                created_at=o.created_at,
            )
            for o in rows
        ]
    )


class PlayerCancelOrderRequest(BaseModel):
    player_id: str


@router.post("/orders/{order_id}/cancel")
async def cancel_player_order(order_id: str, req: PlayerCancelOrderRequest) -> None:
    account_id = f"user:{str(req.player_id).lower()}"
    try:
        ok = cancel_order(order_id=order_id, account_id=account_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="open order not found")


class PlayerMarketOrderRequest(BaseModel):
    player_id: str
    symbol: str
    side: str
    quantity: float


@router.post("/orders/market")
async def submit_player_market_order(req: PlayerMarketOrderRequest) -> None:
    account_id = f"user:{str(req.player_id).lower()}"
    try:
        q = float(req.quantity)
        if q <= 0:
            raise ValueError("Quantity must be positive")

        matches = submit_market_order(
            account_id=account_id,
            symbol=req.symbol,
            side=req.side,
            quantity=q,
        )
        # 骞挎挱鎴愪氦浜嬩欢
        for m in matches:
            ev = m.executed_event.model_dump()
            await hub.broadcast_json("events", ev)
            ev_type = ev.get("event_type")
            if ev_type:
                await hub.broadcast_json(str(ev_type), ev)
    except Exception as exc:
        print(f"[API:Order] Failed to submit market order for {req.symbol}: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))


class PlayerAccountResponse(BaseModel):
    account_id: str
    cash: float
    positions: Dict[str, float]
    caste_id: str | None = None


class PlayerBootstrapRequest(BaseModel):
    player_id: str
    initial_cash: float | None = None
    caste_id: str | None = None


async def _warm_player_bootstrap_data(*, player_id: str, account_id: str, preferred_symbols: list[str] | None = None) -> None:
    try:
        from ifrontier.infra.sqlite.securities import list_securities

        def _run_warmup() -> None:
            value_account(account_id=account_id, discount_factor=1.0)
            get_market_session()
            get_market_trends(symbols=[])

            symbols: list[str] = []
            seen: set[str] = set()
            for sym in list(preferred_symbols or []):
                ss = str(sym or "").strip().upper()
                if ss and ss not in seen:
                    seen.add(ss)
                    symbols.append(ss)

            try:
                snap = get_snapshot(account_id)
                for sym in (snap.positions or {}).keys():
                    ss = str(sym or "").strip().upper()
                    if ss and ss not in seen:
                        seen.add(ss)
                        symbols.append(ss)
            except Exception:
                pass

            try:
                tradable = list_securities(status="TRADABLE")
            except Exception:
                tradable = []

            for sec in tradable[:6]:
                ss = str(sec.symbol or "").strip().upper()
                if ss and ss not in seen:
                    seen.add(ss)
                    symbols.append(ss)

            for sym in symbols[:8]:
                get_quote(sym)

        await run_in_threadpool(_run_warmup)
    except Exception as exc:
        print(f"[API:Bootstrap] warmup skipped for {player_id}: {exc}")


@router.post("/players/bootstrap")
async def players_bootstrap(req: PlayerBootstrapRequest) -> PlayerAccountResponse:
    # 幂等：如果已存在则返回现有数据，不报错也不重复发放初始资产（除非阶级缺失）
    account_id = f"user:{str(req.player_id).lower()}"
    
    # 检查是否已存在
    try:
        snap = get_snapshot(account_id)
        # 如果已存在但数据库中没有阶级信息，说明这是个遗留空账户或者只占了个位
        # 如果请求提供了 caste_id，则补全阶级并补发初始资金（如果当前 cash 为 0 且无持仓）
        if snap.caste_id is None and req.caste_id is not None:
            c_cfg = get_caste_config(req.caste_id)
            bonus_cash = c_cfg.initial_cash if c_cfg else 0.0
            
            conn = get_connection()
            with conn:
                if snap.cash == 0 and not snap.positions:
                    conn.execute("UPDATE accounts SET caste_id = ?, cash = ? WHERE account_id = ?", (req.caste_id, bonus_cash, account_id))
                else:
                    conn.execute("UPDATE accounts SET caste_id = ? WHERE account_id = ?", (req.caste_id, account_id))
            snap = get_snapshot(account_id)
            
        asyncio.create_task(
            _warm_player_bootstrap_data(
                player_id=str(req.player_id),
                account_id=account_id,
                preferred_symbols=list((snap.positions or {}).keys()),
            )
        )
            
        return PlayerAccountResponse(
            account_id=snap.account_id, 
            cash=snap.cash, 
            positions=snap.positions,
            caste_id=snap.caste_id
        )
    except ValueError:
        # 不存在则创建
        pass

    # 如果提供 caste_id，优先使用阶级配置；否则回退到显式 initial_cash 或 0。
    initial_cash = 0.0
    positions: Dict[str, float] = {}
    caste_id = req.caste_id

    if caste_id is not None:
        cfg = get_caste_config(caste_id)
        if cfg is not None:
            initial_cash = cfg.initial_cash
            positions = cfg.initial_positions
    if req.initial_cash is not None:
        initial_cash = req.initial_cash

    create_account(account_id, owner_type="user", initial_cash=float(initial_cash), caste_id=caste_id)

    if positions:
        conn = get_connection()
        with conn:
            for symbol, qty in positions.items():
                conn.execute(
                    "INSERT INTO positions(account_id, symbol, quantity) VALUES (?, ?, ?) "
                    "ON CONFLICT(account_id, symbol) DO UPDATE SET quantity = quantity + excluded.quantity",
                    (account_id, symbol, qty),
                )

    # 确保 SQLite 中存在该玩家 User 记录，供新闻传播使用。
    try:
        from ifrontier.infra.sqlite import news as news_db
        news_db.create_user(account_id)
    except Exception:
        pass

    snap = get_snapshot(account_id)
    asyncio.create_task(
        _warm_player_bootstrap_data(
            player_id=str(req.player_id),
            account_id=account_id,
            preferred_symbols=list((snap.positions or {}).keys()),
        )
    )
    return PlayerAccountResponse(
        account_id=snap.account_id, 
        cash=snap.cash, 
        positions=snap.positions,
        caste_id=snap.caste_id
    )


@router.get("/players/{player_id}/account")
async def get_player_account(player_id: str) -> PlayerAccountResponse:
    account_id = f"user:{str(player_id).lower()}"
    snap = get_snapshot(account_id)
    return PlayerAccountResponse(
        account_id=snap.account_id, 
        cash=snap.cash, 
        positions=snap.positions,
        caste_id=snap.caste_id
    )


class ContractParty(BaseModel):
    party_id: str
    role: str


def _normalize_contract_party_ids(parties: List[Any]) -> List[str]:
    out: List[str] = []
    for p in list(parties or []):
        if isinstance(p, ContractParty):
            out.append(str(p.party_id))
        elif isinstance(p, dict):
            pid = p.get("party_id")
            if pid is not None:
                out.append(str(pid))
        else:
            out.append(str(p))
    return out

class ContractCreateRequest(BaseModel):
    actor_id: str
    kind: str
    title: str
    terms: Dict[str, Any]
    parties: List[Any]
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
        res = await run_in_threadpool(
            _contract_agent.draft,
            actor_id=req.actor_id,
            natural_language=req.natural_language,
        )
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
    env = EventEnvelope[AiContractDraftedPayload](
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


class ContractAgentAppendEditRequest(BaseModel):
    actor_id: str
    base_contract_create: Dict[str, Any]
    instruction: str


@router.post("/contract-agent/append_edit")
async def contract_agent_append_edit(req: ContractAgentAppendEditRequest) -> ContractAgentDraftResponse:
    try:
        await run_in_threadpool(
            _contract_agent.append_edit_context,
            actor_id=req.actor_id,
            base_contract_create=req.base_contract_create,
            instruction=req.instruction,
        )
        res = await run_in_threadpool(
            _contract_agent.draft,
            actor_id=req.actor_id,
            natural_language=req.instruction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ContractAgentDraftResponse(
        draft_id=str(res.draft_id),
        template_id=str(res.template_id),
        contract_create=dict(res.contract_create),
        explanation=str(res.explanation),
        questions=list(res.questions),
        risk_rating=str(res.risk_rating),
    )


class ContractAgentAuditRequest(BaseModel):
    actor_id: str
    contract_id: str
    force: bool = False


class ContractAgentAuditResponse(BaseModel):
    audit_id: str
    contract_id: str
    summary: str
    issues: list[str]
    questions: list[str]
    risk_rating: str


@router.post("/contract-agent/audit")
async def contract_agent_audit(req: ContractAgentAuditRequest) -> ContractAgentAuditResponse:
    try:
        from ifrontier.infra.sqlite import contracts as contracts_db

        record = contracts_db.get_contract_as_dict(req.contract_id)

        if not record:
            raise HTTPException(status_code=404, detail="contract not found")

        snapshot: Dict[str, Any] = dict(record)
        try:
            snapshot["terms"] = json.loads(snapshot.get("terms_json") or "{}")
        except Exception:
            snapshot["terms"] = {}

        audit = await run_in_threadpool(
            _contract_agent.audit_contract,
            actor_id=req.actor_id,
            contract_id=req.contract_id,
            contract_snapshot=snapshot,
            force=bool(req.force),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ContractAgentAuditResponse(
        audit_id=str(audit.audit_id),
        contract_id=str(audit.contract_id),
        summary=str(audit.summary),
        issues=list(audit.issues),
        questions=list(audit.questions),
        risk_rating=str(audit.risk_rating),
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
        party_ids = _normalize_contract_party_ids(req.parties)
        contract_id = _contract_service.create_contract(
            kind=req.kind,
            title=req.title,
            terms=req.terms,
            parties=party_ids,
            required_signers=req.required_signers,
            participation_mode=req.participation_mode,
            invited_parties=req.invited_parties,
            actor_id=req.actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContractCreateResponse(contract_id=contract_id)


class PlayerListResponse(BaseModel):
    items: List[str]


@router.get("/players")
async def list_players(limit: int = 100) -> PlayerListResponse:
    """列出活跃玩家 ID，用于聊天 @ 提醒。"""
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT account_id FROM accounts WHERE owner_type = 'user' LIMIT ?",
            (int(limit),),
        ).fetchall()
        items: List[str] = []
        for r in rows:
            try:
                account_id = str(r["account_id"])  # type: ignore[index]
            except Exception:
                account_id = str(r[0])
            if account_id.startswith("user:"):
                items.append(account_id[len("user:") :])
            else:
                items.append(account_id)
        return PlayerListResponse(items=items)
    except Exception:
        # 兜底：尝试从新闻用户表中取（可能为空）
        try:
            users_from_news = _news_service.list_users(limit=int(limit))
            # 返回 raw user_id（可能是 user:xxx），这里做一次归一化
            norm = [u[len("user:") :] if str(u).startswith("user:") else str(u) for u in users_from_news]
            return PlayerListResponse(items=norm)
        except Exception:
            return PlayerListResponse(items=[])


class ContractBriefResponse(BaseModel):
    contract_id: str
    title: str
    kind: str
    status: str
    created_at: str | None = None
    parties: List[str] = []
    required_signers: List[str] = []
    signatures: List[str] = []


class ContractListResponse(BaseModel):
    items: List[ContractBriefResponse]


@router.get("/contracts/list")
async def list_contracts(
    actor_id: str | None = None,
    limit: int = 50,
    status: str | None = None,
) -> ContractListResponse:
    """列出当前玩家相关的合约，用于聊天引用。"""
    aid = actor_id
    if aid is not None:
        aid = str(aid)
        if ":" not in aid:
            aid = f"user:{aid}"
        aid = aid.lower()


    aid_plain: str | None = None
    if aid is not None and str(aid).startswith("user:"):
        aid_plain = str(aid)[len("user:") :].lower()


    st = status
    if st is not None:
        st = str(st).upper()
    try:
        from ifrontier.infra.sqlite import contracts as contracts_db

        records = contracts_db.list_contracts_by_actor(
            actor_id=aid,
            actor_id_plain=aid_plain,
            status=st,
            limit=limit,
        )

        items = [
            ContractBriefResponse(
                contract_id=str(r.get("contract_id") or ""),
                title=str(r.get("title") or ""),
                kind=str(r.get("kind") or ""),
                status=str(r.get("status") or ""),
                created_at=str(r.get("created_at") or "") or None,
                parties=list(r.get("parties") or []),
                required_signers=list(r.get("required_signers") or []),
                signatures=list(r.get("signatures") or []),
            )
            for r in records
            if (r.get("contract_id") is not None)
        ]
        return ContractListResponse(items=items)
    except Exception:
        return ContractListResponse(items=[])


class ContractRuleEventItem(BaseModel):
    event_id: str
    occurred_at: str
    actor: Dict[str, Any] | None = None
    payload: Dict[str, Any]


class ContractRuleEventsResponse(BaseModel):
    items: List[ContractRuleEventItem]


@router.get("/contracts/{contract_id}/rule_events")
async def contract_rule_events(contract_id: str, limit: int = 200) -> ContractRuleEventsResponse:
    try:
        events = _event_store.list_by_contract_id_and_type(
            contract_id=str(contract_id),
            event_type=str(EventType.CONTRACT_RULE_EXECUTED.value),
            limit=int(limit),
        )
    except Exception:
        return ContractRuleEventsResponse(items=[])

    return ContractRuleEventsResponse(
        items=[
            ContractRuleEventItem(
                event_id=e.event_id,
                occurred_at=e.occurred_at,
                actor=e.actor,
                payload=e.payload,
            )
            for e in events
        ]
    )


class ContractBatchItem(BaseModel):
    kind: str
    title: str
    terms: Dict[str, Any]
    parties: List[Any]
    required_signers: List[str]
    participation_mode: str | None = None
    invited_parties: List[str] | None = None


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
                "parties": _normalize_contract_party_ids(c.parties),
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


class ContractResponse(BaseModel):
    contract_id: str
    kind: str
    title: str
    terms: Dict[str, Any]
    status: str
    parties: List[str]
    required_signers: List[str]
    signatures: Dict[str, str]  # signer -> signed_at
    participation_mode: str
    invited_parties: List[str]
    created_at: str
    updated_at: str
    activated_at: str | None = None


@router.get("/contracts/{contract_id}")
async def contract_get(contract_id: str) -> ContractResponse:
    try:
        from ifrontier.infra.sqlite import contracts as contracts_db

        record = contracts_db.get_contract_as_dict(contract_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="contract not found")
        
        terms = json.loads(record["terms_json"] or "{}")
        
        import json
        sigs_raw = json.loads(record["signatures_json"] or "[]")
        sigs_dict = {s: "SIGNED" for s in sigs_raw}

        return ContractResponse(
            contract_id=record["contract_id"],
            kind=record["kind"],
            title=record["title"],
            terms=terms,
            status=record["status"],
            parties=json.loads(record["parties_json"] or "[]"),
            required_signers=json.loads(record["required_signers_json"] or "[]"),
            signatures=sigs_dict,
            participation_mode=record["participation_mode"] or "ALL_SIGNERS",
            invited_parties=json.loads(record["invited_parties_json"] or "[]"),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
            activated_at=record.get("activated_at"),
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=str(exc))


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
        status = _contract_service.sign_contract(contract_id=contract_id, signer=str(req.signer).strip().lower())
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
    # 该端点用于 GM、脚本或调试场景直接铸造卡牌。
    # 正式玩法中，玩家应通过 /news/store/purchase 获得卡牌，而不是自行创建。
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
    cash_cost = 0.0
    if req.spend_cash is not None and req.spend_cash > 0:
        cash_cost = float(req.spend_cash)
    else:
        unit_cash = float(os.getenv("IF_NEWS_MUTATE_CASH_PER_CHAR") or "0.0")
        cash_cost = float(len(req.new_text or "")) * float(unit_cash)

    if cash_cost > 0:
        try:
            spend_cash(account_id=req.editor_id, amount=float(cash_cost), event_id=str(uuid4()))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    try:
        new_variant_id, event_json = _news_service.mutate_variant(
            parent_variant_id=req.parent_variant_id,
            editor_id=req.editor_id,
            new_text=req.new_text,
            influence_cost=float(req.influence_cost),
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


class NewsPropagateQuoteRequest(BaseModel):
    variant_id: str
    from_actor_id: str
    spend_cash: float
    limit: int = 50


class NewsPropagateQuoteResponse(BaseModel):
    mutation_depth: int
    per_delivery_cost: float
    requested_limit: int
    affordable_limit: int
    estimated_total_cost: float


class NewsBroadcastRequest(BaseModel):
    variant_id: str
    actor_id: str
    channel: str
    visibility_level: str = "NORMAL"
    limit_users: int = 5000
    correlation_id: UUID | None = None


class NewsBroadcastResponse(BaseModel):
    delivered: int
    event_id: UUID
    correlation_id: UUID | None


@router.post("/news/propagate/quote")
async def news_propagate_quote(req: NewsPropagateQuoteRequest) -> NewsPropagateQuoteResponse:
    requested_limit = int(req.limit)
    if requested_limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")

    budget = float(req.spend_cash)
    if budget <= 0:
        raise HTTPException(status_code=400, detail="spend_cash must be > 0")

    ctx = _news_service.get_variant_context(variant_id=req.variant_id) or {}
    depth = int(ctx.get("mutation_depth") or 0)

    base_unit = float(os.getenv("IF_NEWS_PROPAGATE_CASH_PER_DELIVERY") or "500.0")
    mutation_mult = float(os.getenv("IF_NEWS_PROPAGATE_MUTATION_MULT") or "1.0")
    per_delivery_cost = base_unit * (1.0 + (float(depth) * mutation_mult))

    affordable = int(budget // per_delivery_cost)
    if affordable < 0:
        affordable = 0

    affordable_limit = min(requested_limit, affordable)
    if affordable_limit < 0:
        affordable_limit = 0

    estimated_total_cost = float(per_delivery_cost) * float(affordable_limit)
    return NewsPropagateQuoteResponse(
        mutation_depth=int(depth),
        per_delivery_cost=float(per_delivery_cost),
        requested_limit=int(requested_limit),
        affordable_limit=int(affordable_limit),
        estimated_total_cost=float(estimated_total_cost),
    )


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

        base_unit = float(os.getenv("IF_NEWS_PROPAGATE_CASH_PER_DELIVERY") or "500.0")
        mutation_mult = float(os.getenv("IF_NEWS_PROPAGATE_MUTATION_MULT") or "1.0")
        per_delivery_cost = base_unit * (1.0 + (float(depth) * mutation_mult))
        
        budget = float(req.spend_cash)
        if budget <= 0:
            raise HTTPException(status_code=400, detail="spend_cash must be > 0")
        
        affordable = int(budget // per_delivery_cost)
        if affordable < 0:
            affordable = 0
        if affordable < limit:
            limit = affordable

        if limit <= 0:
            return NewsPropagateResponse(delivered=0, correlation_id=req.correlation_id)

    from ifrontier.infra.sqlite import news as news_db

    recipients: list[str] = []
    try:
        followers = news_db.list_followers(followee_id=req.from_actor_id, limit=int(limit))
        recipients = [u for u in followers if str(u) != str(req.from_actor_id)]
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


@router.post("/news/broadcast")
async def news_broadcast(req: NewsBroadcastRequest) -> NewsBroadcastResponse:
    try:
        delivered, ev = _news_service.broadcast_variant(
            variant_id=req.variant_id,
            channel=req.channel,
            visibility_level=req.visibility_level,
            actor_id=req.actor_id,
            limit_users=int(req.limit_users),
            correlation_id=req.correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await hub.broadcast_json("events", ev.model_dump())
    await hub.broadcast_json(str(EventType.NEWS_BROADCASTED), ev.model_dump())
    _commonbot_emergency_runner.maybe_react(broadcast_event=ev)

    return NewsBroadcastResponse(
        delivered=delivered,
        event_id=ev.event_id,
        correlation_id=ev.correlation_id,
    )


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


class NewsChainStartRequest(BaseModel):
    kind: str
    actor_id: str
    t0_seconds: int
    t0_at: str | None = None
    omen_interval_seconds: int
    abort_probability: float
    grant_count: int
    seed: int
    symbols: list[str] = []
    correlation_id: UUID | None = None
    extra_truth: Dict[str, Any] | None = None


class NewsChainStartResponse(BaseModel):
    chain_id: str
    major_card_id: str
    correlation_id: UUID | None = None
    t0_at: str


class NewsTickRequest(BaseModel):
    now_iso: str | None = None
    limit: int = 50


class NewsTickResponse(BaseModel):
    now: str
    chains: List[Dict[str, Any]]
    spawned_events: List[Dict[str, Any]]


@router.post("/news/chains/start")
async def news_chain_start(req: NewsChainStartRequest) -> NewsChainStartResponse:
    t0_at: datetime | None = None
    if req.t0_at:
        try:
            t0_at = datetime.fromisoformat(str(req.t0_at))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid t0_at") from exc

    try:
        result = _news_tick_engine.start_chain(
            kind=req.kind,
            actor_id=req.actor_id,
            t0_seconds=int(req.t0_seconds),
            t0_at=t0_at,
            omen_interval_seconds=int(req.omen_interval_seconds),
            abort_probability=float(req.abort_probability),
            grant_count=int(req.grant_count),
            seed=int(req.seed),
            symbols=list(req.symbols or []),
            correlation_id=req.correlation_id,
            extra_truth=req.extra_truth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    card_event = result.get("card_created_event")
    chain_event = result.get("chain_started_event")
    if card_event is not None:
        await hub.broadcast_json("events", card_event.model_dump())
        await hub.broadcast_json(str(EventType.NEWS_CARD_CREATED), card_event.model_dump())
    if chain_event is not None:
        await hub.broadcast_json("events", chain_event.model_dump())
        await hub.broadcast_json(str(EventType.NEWS_CHAIN_STARTED), chain_event.model_dump())

    return NewsChainStartResponse(
        chain_id=str(result["chain_id"]),
        major_card_id=str(result["major_card_id"]),
        correlation_id=req.correlation_id,
        t0_at=result["t0_at"].isoformat() if hasattr(result["t0_at"], "isoformat") else str(result["t0_at"]),
    )


@router.post("/news/tick")
async def news_tick(req: NewsTickRequest) -> NewsTickResponse:
    now: datetime | None = None
    if req.now_iso:
        try:
            now = datetime.fromisoformat(str(req.now_iso))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid now_iso") from exc
    result = await _news_tick_engine.tick(now=now, limit=int(req.limit))
    return NewsTickResponse(
        now=str(result["now"]),
        chains=list(result.get("chains") or []),
        spawned_events=list(result.get("spawned_events") or []),
    )


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
    # 鍙€夛細娴嬭瘯/鐗规畩鍦烘櫙涓嬪厑璁歌嚜瀹氫箟浠锋牸锛涗笉鎻愪緵鍒欎娇鐢ㄧ郴缁熶环
    price_cash: float | None = None
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


class NewsStorePurchaseResponse(BaseModel):
    kind: str
    buyer_user_id: str
    card_id: str | None = None
    variant_id: str | None = None
    chain_id: str | None = None


@router.post("/news/store/purchase")
async def news_store_purchase(req: NewsStorePurchaseRequest) -> NewsStorePurchaseResponse:
    from ifrontier.infra.sqlite.securities import list_securities

    items_cfg: List[Dict[str, Any]] = [
        {"kind": "RUMOR", "price_cash": 2000.0, "requires_symbols": False},
        {"kind": "LEAK", "price_cash": 15000.0, "requires_symbols": True},
        {"kind": "ANALYST_REPORT", "price_cash": 8000.0, "requires_symbols": True},
        {"kind": "OMEN", "price_cash": 25000.0, "requires_symbols": True},
        {"kind": "DISCLOSURE", "price_cash": 45000.0, "requires_symbols": True},
        {"kind": "EARNINGS", "price_cash": 35000.0, "requires_symbols": True},
        {"kind": "MAJOR_EVENT", "price_cash": 100000.0, "requires_symbols": True},
        {"kind": "WORLD_EVENT", "price_cash": 500000.0, "requires_symbols": False},
    ]
    kind_key = str(req.kind)
    cfg = next((x for x in items_cfg if str(x.get("kind")) == kind_key), None)
    if cfg is None:
        raise HTTPException(status_code=400, detail="unknown kind")

    # 优先使用请求中的 price_cash；否则使用系统定价。
    req_price = float(req.price_cash) if req.price_cash is not None else 0.0
    system_price = req_price if req_price > 0 else float(cfg.get("price_cash") or 0.0)
    if system_price <= 0:
        raise HTTPException(status_code=400, detail="invalid system price")

    requires_symbols = bool(cfg.get("requires_symbols") or False)
    sec_symbols = [s.symbol for s in list_securities()]
    if not sec_symbols:
        sec_symbols = ["BLUEGOLD"]

    default_symbol_by_kind: Dict[str, List[str]] = {
        "LEAK": ["CIVILBANK", "NEURALINK", "FOODMART", "BLUEGOLD"],
        "ANALYST_REPORT": ["NEURALINK", "CIVILBANK", "FOODMART", "BLUEGOLD"],
        "OMEN": ["BLUEGOLD", "CIVILBANK", "NEURALINK", "FOODMART"],
        "DISCLOSURE": ["CIVILBANK", "BLUEGOLD", "NEURALINK", "FOODMART"],
        "EARNINGS": ["NEURALINK", "CIVILBANK", "FOODMART", "BLUEGOLD"],
        "MAJOR_EVENT": ["BLUEGOLD", "NEURALINK", "CIVILBANK", "FOODMART"],
    }

    symbol_options: List[str] = []
    if requires_symbols:
        preferred = default_symbol_by_kind.get(kind_key, [])
        for p in preferred:
            if p in sec_symbols and p not in symbol_options:
                symbol_options.append(p)
        if not symbol_options:
            symbol_options = [str(sec_symbols[0])]

    req_symbols = list(req.symbols or [])
    # 对于不需要 symbols 的类型，允许 symbol 为空。
    if symbol_options:
        # 需要 symbols 的类型：必须且只能选择一个，并且必须在可选列表中。
        if len(req_symbols) != 1:
            raise HTTPException(status_code=400, detail="exactly one symbol required")
        if req_symbols[0] not in symbol_options:
            raise HTTPException(status_code=400, detail="symbol must be in symbol_options")

    purchase_event_id = str(uuid4())
    try:
        spend_cash(account_id=req.buyer_user_id, amount=float(system_price), event_id=purchase_event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # MAJOR_EVENT / WORLD_EVENT锛氳喘涔板嵆鍒涘缓浜嬩欢閾撅紝T0 寤惰繜骞挎挱锛涗笉绔嬪嵆鎶曢€掔粰鎵€鏈変汉
    if str(req.kind) in {"MAJOR_EVENT", "WORLD_EVENT"}:
        try:
            t0_at = None
            if req.t0_at and str(req.t0_at).strip():
                try:
                    t0_at = datetime.fromisoformat(str(req.t0_at).strip())
                except ValueError:
                    t0_at = None
            
            sec_symbols = [s.symbol for s in list_securities(status="TRADABLE")]
            if not sec_symbols:
                sec_symbols = ["BLUEGOLD", "MARS_GEN", "CIVILBANK", "NEURALINK"]
            
            print(f"[API:Purchase] Starting chain for {req.kind}, t0_at={t0_at}, symbols={req_symbols or sec_symbols}")
            # v0.1: 瀵逛簬娴嬭瘯闃舵锛屽皢榛樿鍊掕鏃朵粠 60s 缂╃煭鑷?15s锛屾彁楂樺弽棣堥€熷害
            default_delay = 15 if str(req.kind) == "WORLD_EVENT" else 60
            result = _news_tick_engine.start_chain(
                kind=req.kind,
                actor_id=req.buyer_user_id,
                t0_seconds=int(req.t0_seconds if req.t0_seconds is not None else default_delay),
                t0_at=t0_at,
                omen_interval_seconds=int(req.omen_interval_seconds or 10),
                abort_probability=float(req.abort_probability if req.abort_probability is not None else 0.3),
                grant_count=int(req.grant_count if req.grant_count is not None else 2),
                seed=int(req.seed if req.seed is not None else 1),
                symbols=req_symbols if req_symbols else sec_symbols,
                correlation_id=req.correlation_id,
            )
        except Exception as exc:
            print(f"[API:Purchase] Failed to start chain: {exc}")
            raise HTTPException(status_code=400, detail=f"failed to start news chain: {str(exc)}")

        major_card_id = str(result["major_card_id"])
        # 璐拱鑰呰幏寰椾富浜嬩欢鍗℃墍鏈夋潈
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

    # 普通卡等效为“随机捡到”的新闻，先投递给购买者，后续再由其手动助推传播。
    symbols = req_symbols
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
