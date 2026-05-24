from __future__ import annotations

import asyncio
from typing import Dict, List, Optional
from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.app.ws import hub
from ifrontier.app.room_meta import load_room_meta

from ifrontier.services.rule_scheduler import ContractRuleScheduler
from ifrontier.services.news_tick_scheduler import NewsTickScheduler
from ifrontier.services.market_session_scheduler import MarketSessionScheduler
from ifrontier.services.market_maker_scheduler import MarketMakerScheduler
from ifrontier.services.hosting_scheduler import HostingScheduler
from ifrontier.services.victory_scheduler import VictoryScheduler


class RoomEngine:
    def __init__(self, room_id: str):
        self.room_id = room_id
        
        self.contract_scheduler: Optional[ContractRuleScheduler] = None
        self.news_scheduler: Optional[NewsTickScheduler] = None
        self.market_session_scheduler: Optional[MarketSessionScheduler] = None
        self.market_maker_scheduler: Optional[MarketMakerScheduler] = None
        self.hosting_scheduler: Optional[HostingScheduler] = None
        self.victory_scheduler: Optional[VictoryScheduler] = None
        
        # 房间级服务实例
        self.news_service: Optional[Any] = None
        self.news_tick_engine: Optional[Any] = None
        self.commonbot_emergency_runner: Optional[Any] = None
        self.chat_service: Optional[Any] = None
        self.contract_service: Optional[Any] = None

    def _make_broadcaster(self):
        room_id_captured = self.room_id
        async def _broadcast(ev: dict) -> None:
            chs = ["events"]
            ev_type = ev.get("event_type")
            if ev_type:
                chs.append(str(ev_type))
            await hub.broadcast_many(chs, ev, room_id=room_id_captured)
        return _broadcast

    def _get_room_channel_size(self):
        room_id_captured = self.room_id
        async def _size(channel: str) -> int:
            return await hub.get_channel_size(channel, room_id=room_id_captured)
        return _size

    def initialize_db(self):
        """Initialize the schema and seed data for this room."""
        token = room_id_var.set(self.room_id)
        try:
            # 1. Initialize schema
            init_schema()
            
            from ifrontier.app.api import _news_service

            # 2. Setup bots and seed news
            from ifrontier.infra.sqlite.bots import default_bot_profiles, init_bot_accounts
            init_bot_accounts()
            
            bots = default_bot_profiles()
            bot_ids = [b.account_id for b in bots] + ["system"]
            _news_service.ensure_bot_users(bot_ids)
            
            # 3. Import scenario if specified
            room_meta = load_room_meta(self.room_id)
            scenario_id = room_meta.game_settings.scenario_id if room_meta else None
            if scenario_id:
                _log.info("Importing scenario '%s' into room '%s'", scenario_id, self.room_id)
                self._import_scenario_from_global_db(scenario_id)
            else:
                _news_service.init_news_seed_data()
        finally:
            room_id_var.reset(token)

    def _import_scenario_from_global_db(self, scenario_id: str):
        """将剧本从全局库拷贝到当前房间库"""
        from ifrontier.app.api import _get_global_news_db_conn
        from ifrontier.infra.sqlite.db import get_connection
        
        global_conn = _get_global_news_db_conn()
        room_conn = get_connection()
        
        rows = global_conn.execute("SELECT * FROM news WHERE scenario_id = ?", (scenario_id,)).fetchall()
        if not rows:
            return
            
        import json
        with room_conn:
            for r in rows:
                room_conn.execute(
                    """
                    INSERT OR REPLACE INTO news (
                        card_id, variant_id, kind, text, symbols_json, tags_json, 
                        publisher_id, published_at, is_suppressed, suppression_reason,
                        truth_payload_json, image_uri, image_anchor_id, preset_id, rarity, faction, created_at,
                        author_id, parent_variant_id, mutation_depth, influence_cost, risk_roll_json,
                        parent_card_id, activation_prob, scheduled_at, success_criteria_json, failure_outcome_json,
                        scenario_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["card_id"], r["variant_id"], r["kind"], r["text"], r["symbols_json"], r["tags_json"],
                        r["publisher_id"], r["published_at"], r["is_suppressed"], r["suppression_reason"],
                        r["truth_payload_json"], r["image_uri"], r["image_anchor_id"], r["preset_id"], r["rarity"], r["faction"], r["created_at"],
                        r["author_id"], r["parent_variant_id"], r["mutation_depth"], r["influence_cost"], r["risk_roll_json"],
                        r["parent_card_id"], r["activation_prob"], r["scheduled_at"],
                        r["success_criteria_json"], r["failure_outcome_json"],
                        r["scenario_id"]
                    )
                )

    def start_schedulers(self):
        broadcaster = self._make_broadcaster()
        get_size = self._get_room_channel_size()

        room_meta = load_room_meta(self.room_id)
        game_settings = room_meta.game_settings.model_dump(exclude_none=True) if room_meta else {}
        if room_meta:
            game_settings.setdefault("game_started_at", room_meta.game_started_at or room_meta.created_at)

        from ifrontier.app.api import (
            _make_broadcaster_for_events,
        )
        from ifrontier.infra.sqlite.event_store import SqliteEventStore
        from ifrontier.services.news import NewsService
        from ifrontier.services.news_tick import NewsTickEngine
        from ifrontier.services.commonbot_emergency import CommonBotEmergencyRunner
        from ifrontier.services.chat import ChatService
        from ifrontier.services.contracts import ContractService
        from ifrontier.services.market_analytics import get_market_trends

        # 延迟导入 make_user_facade，避免循环依赖
        import ifrontier.app.api as api_module
        make_user_facade = api_module.make_user_facade

        # 为每个房间创建独立的事件存储和服务实例，确保房间隔离
        room_event_store = SqliteEventStore()
        room_contract_service = ContractService(room_event_store)
        room_news_service = NewsService(room_event_store)
        room_chat_service = ChatService(event_store=room_event_store)
        room_news_tick_engine = NewsTickEngine(room_event_store, room_news_service, broadcaster=broadcaster)
        room_commonbot_emergency_runner = CommonBotEmergencyRunner(
            news=room_news_service,
            event_store=room_event_store,
            market_data_provider=lambda symbols: get_market_trends(symbols=symbols),
            broadcaster=broadcaster,
        )
        
        # 保存房间级服务实例，供 API 层访问
        self.contract_service = room_contract_service
        self.news_service = room_news_service
        self.chat_service = room_chat_service
        self.news_tick_engine = room_news_tick_engine
        self.commonbot_emergency_runner = room_commonbot_emergency_runner

        self.contract_scheduler = ContractRuleScheduler(
            contract_service=room_contract_service,
            tick_interval_seconds=1.0,
            batch_size=50,
            max_concurrency=5,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
        )

        self.news_scheduler = NewsTickScheduler(
            tick_engine=room_news_tick_engine,
            tick_interval_seconds=1.0,
            batch_size=50,
            broadcaster=broadcaster,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
        )

        self.market_session_scheduler = MarketSessionScheduler(
            runner=room_commonbot_emergency_runner,
            tick_interval_seconds=1.0,
            broadcaster=broadcaster,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
        )

        self.market_maker_scheduler = MarketMakerScheduler(
            tick_interval_seconds=1.0,
            broadcaster=broadcaster,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
        )

        self.hosting_scheduler = HostingScheduler(
            min_players=8,
            tick_interval_seconds=1.0,
            max_per_tick=2,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
            broadcaster=broadcaster,
            make_facade=make_user_facade,
        )

        self.victory_scheduler = VictoryScheduler(
            tick_interval_seconds=5.0,
            broadcaster=broadcaster,
            get_channel_size=get_size,
            room_settings=game_settings,
            news_service=room_news_service,
        )

        token = room_id_var.set(self.room_id)
        try:
            self.contract_scheduler.start()
            self.news_scheduler.start()
            self.market_session_scheduler.start()
            self.market_maker_scheduler.start()
            self.hosting_scheduler.start()
            self.victory_scheduler.start()
        finally:
            room_id_var.reset(token)

    async def stop_schedulers(self):
        tasks = []
        if self.victory_scheduler: tasks.append(self.victory_scheduler.stop())
        if self.hosting_scheduler: tasks.append(self.hosting_scheduler.stop())
        if self.market_maker_scheduler: tasks.append(self.market_maker_scheduler.stop())
        if self.market_session_scheduler: tasks.append(self.market_session_scheduler.stop())
        if self.news_scheduler: tasks.append(self.news_scheduler.stop())
        if self.contract_scheduler: tasks.append(self.contract_scheduler.stop())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        # 释放 SQLite 数据库连接，允许被外部（如 shutil.rmtree）删除
        from ifrontier.infra.sqlite.db import close_connection
        close_connection(self.room_id)


class RoomManager:
    def __init__(self):
        self._rooms: Dict[str, RoomEngine] = {}
        self._lock = asyncio.Lock()

    async def start_room(self, room_id: str) -> None:
        async with self._lock:
            if room_id in self._rooms:
                return
            
            engine = RoomEngine(room_id)
            
            # 使用 await to_thread 来执行同步的 DB 初始化
            await asyncio.to_thread(engine.initialize_db)
            engine.start_schedulers()
            
            self._rooms[room_id] = engine

    async def stop_room(self, room_id: str) -> None:
        async with self._lock:
            engine = self._rooms.pop(room_id, None)
            if engine:
                await engine.stop_schedulers()

    async def stop_all(self) -> None:
        async with self._lock:
            for engine in self._rooms.values():
                await engine.stop_schedulers()
            self._rooms.clear()

    def get_active_rooms(self) -> List[str]:
        return list(self._rooms.keys())

    def is_room_active(self, room_id: str) -> bool:
        return room_id in self._rooms

    def active_room_count(self) -> int:
        return len(self._rooms)
    
    def get_room_engine(self, room_id: str) -> Optional[RoomEngine]:
        """获取指定房间的引擎实例"""
        return self._rooms.get(room_id)

room_manager = RoomManager()
