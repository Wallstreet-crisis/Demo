import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.services.rule_scheduler import ContractRuleScheduler
from ifrontier.services.news_tick_scheduler import NewsTickScheduler
 
 
def create_app() -> FastAPI:
    init_schema()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 复用 app.api 中已初始化的 driver/service
        from ifrontier.app import api as api_module
        from ifrontier.app.ws import hub

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
        scheduler.start()
        news_scheduler.start()
        try:
            yield
        finally:
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
