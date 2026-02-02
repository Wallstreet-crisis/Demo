import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
from ifrontier.infra.sqlite.schema import init_schema
from ifrontier.services.rule_scheduler import ContractRuleScheduler
 
 
def create_app() -> FastAPI:
    init_schema()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 复用 app.api 中已初始化的 driver/service
        from ifrontier.app import api as api_module

        scheduler = ContractRuleScheduler(
            driver=api_module._driver,
            contract_service=api_module._contract_service,
            tick_interval_seconds=1.0,
            batch_size=50,
            max_concurrency=5,
        )
        scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(title="Information Frontier", lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
