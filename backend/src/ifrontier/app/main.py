import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.app.room_engine import room_manager
 
 
def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动默认房间，保持向后兼容
        await room_manager.start_room("default")
        try:
            yield
        finally:
            await room_manager.stop_all()

    app = FastAPI(title="Information Frontier", lifespan=lifespan)

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def room_context_middleware(request: Request, call_next):
        room_id = request.headers.get("X-Room-Id", "default")
        if not room_id.strip():
            room_id = "default"
        
        token = room_id_var.set(room_id)
        try:
            response = await call_next(request)
            return response
        finally:
            room_id_var.reset(token)

    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
