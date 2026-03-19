from __future__ import annotations

import asyncio
from typing import Dict, List, Optional
from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.app.ws import hub

from ifrontier.services.rule_scheduler import ContractRuleScheduler
from ifrontier.services.news_tick_scheduler import NewsTickScheduler
from ifrontier.services.market_session_scheduler import MarketSessionScheduler
from ifrontier.services.market_maker_scheduler import MarketMakerScheduler
from ifrontier.services.hosting_scheduler import HostingScheduler


class RoomEngine:
    def __init__(self, room_id: str):
        self.room_id = room_id
        
        self.contract_scheduler: Optional[ContractRuleScheduler] = None
        self.news_scheduler: Optional[NewsTickScheduler] = None
        self.market_session_scheduler: Optional[MarketSessionScheduler] = None
        self.market_maker_scheduler: Optional[MarketMakerScheduler] = None
        self.hosting_scheduler: Optional[HostingScheduler] = None

    def _make_broadcaster(self):
        room_id_captured = self.room_id
        async def _broadcast(ev: dict) -> None:
            await hub.broadcast_json("events", ev, room_id=room_id_captured)
            ev_type = ev.get("event_type")
            if ev_type:
                await hub.broadcast_json(str(ev_type), ev, room_id=room_id_captured)
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
            _news_service.init_news_seed_data()
        finally:
            room_id_var.reset(token)

    def start_schedulers(self):
        broadcaster = self._make_broadcaster()
        get_size = self._get_room_channel_size()

        from ifrontier.app.api import (
            _contract_service,
            _news_service,
            _news_tick_engine,
            _commonbot_emergency_runner,
        )

        # 延迟导入 make_user_facade，避免循环依赖
        import ifrontier.app.api as api_module
        make_user_facade = api_module.make_user_facade

        self.contract_scheduler = ContractRuleScheduler(
            contract_service=_contract_service,
            tick_interval_seconds=1.0,
            batch_size=50,
            max_concurrency=5,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
        )

        self.news_scheduler = NewsTickScheduler(
            tick_engine=_news_tick_engine,
            tick_interval_seconds=1.0,
            batch_size=50,
            broadcaster=broadcaster,
            channel_for_online_stats="presence",
            get_channel_size=get_size,
        )

        self.market_session_scheduler = MarketSessionScheduler(
            runner=_commonbot_emergency_runner,
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

        token = room_id_var.set(self.room_id)
        try:
            self.contract_scheduler.start()
            self.news_scheduler.start()
            self.market_session_scheduler.start()
            self.market_maker_scheduler.start()
            self.hosting_scheduler.start()
        finally:
            room_id_var.reset(token)

    async def stop_schedulers(self):
        tasks = []
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

room_manager = RoomManager()
