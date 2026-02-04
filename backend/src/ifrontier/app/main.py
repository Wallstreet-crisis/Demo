import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.services.rule_scheduler import ContractRuleScheduler
from ifrontier.services.news_tick_scheduler import NewsTickScheduler
from ifrontier.services.market_session_scheduler import MarketSessionScheduler
from ifrontier.services.hosting_scheduler import HostingScheduler
from ifrontier.services.market_maker_scheduler import MarketMakerScheduler
 
 
def create_app() -> FastAPI:
    init_schema()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 复用 app.api 中已初始化的 driver/service
        from ifrontier.app import api as api_module
        from ifrontier.app.ws import hub
        from ifrontier.infra.sqlite.bots import default_bot_profiles

        # 同步内置机器人及系统账号到 Neo4j 用户池，确保新闻传播有目标
        bots = default_bot_profiles()
        bot_ids = [b.account_id for b in bots] + ["system"]
        api_module._news_service.ensure_bot_users(bot_ids)

        api_module._news_service.init_news_seed_data()

        scheduler = ContractRuleScheduler(
            driver=api_module._driver,
            contract_service=api_module._contract_service,
            tick_interval_seconds=1.0,
            batch_size=50,
            max_concurrency=5,
        )

        news_scheduler = NewsTickScheduler(
            tick_engine=api_module._news_tick_engine,
            tick_interval_seconds=1.0,
            batch_size=50,
            broadcaster=_make_news_broadcaster(hub),
        )

        market_session_scheduler = MarketSessionScheduler(
            runner=api_module._commonbot_emergency_runner,
            tick_interval_seconds=1.0,
            broadcaster=_make_news_broadcaster(hub),
        )

        market_maker_scheduler = MarketMakerScheduler(
            driver=api_module._driver,
            tick_interval_seconds=1.0,
            broadcaster=_make_news_broadcaster(hub),
        )

        hosting_scheduler = HostingScheduler(
            min_players=8,
            tick_interval_seconds=1.0,
            max_per_tick=2,
            channel_for_online_stats="events",
            get_channel_size=hub.get_channel_size,
            broadcaster=_make_news_broadcaster(hub),
            make_facade=api_module.make_user_facade,
        )

        api_module._hosting_scheduler = hosting_scheduler
        scheduler.start()
        news_scheduler.start()
        market_session_scheduler.start()
        market_maker_scheduler.start()
        hosting_scheduler.start()
        try:
            yield
        finally:
            await hosting_scheduler.stop()
            await market_maker_scheduler.stop()
            api_module._hosting_scheduler = None
            await market_session_scheduler.stop()
            await news_scheduler.stop()
            await scheduler.stop()

    app = FastAPI(title="Information Frontier", lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(ws_router)
    return app


def _make_news_broadcaster(hub):
    async def _broadcast(ev: dict) -> None:
        await hub.broadcast_json("events", ev)
        ev_type = ev.get("event_type")
        if ev_type:
            await hub.broadcast_json(str(ev_type), ev)

    return _broadcast


app = create_app()
