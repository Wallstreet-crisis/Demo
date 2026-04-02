import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
from ifrontier.infra.sqlite.db import room_id_var
from ifrontier.app.room_engine import room_manager
from ifrontier.app.room_meta import room_exists

# 房间激活保护常量
_MAX_ACTIVE_ROOMS = 20
_ROOM_ACTIVATE_COOLDOWN_S = 2.0
_last_room_activate_at: float = 0.0
 
 
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

    # ── 全局异常处理：将 ValueError 映射为 HTTP 400 ──
    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\d+\.\d+\.\d+\.\d+)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def room_context_middleware(request: Request, call_next):
        global _last_room_activate_at

        if request.method == "OPTIONS":
            return await call_next(request)

        room_id = request.headers.get("X-Room-Id", "default")
        if not room_id.strip():
            room_id = "default"

        # 确保 default 房间始终存活
        if room_id == "default":
            if not room_manager.is_room_active("default"):
                await room_manager.start_room("default")
        elif not room_manager.is_room_active(room_id):
            # 非 default 房间：仅在磁盘上存在时才激活，且受数量上限和速率保护
            if room_exists(room_id):
                active_count = room_manager.active_room_count()
                now = time.monotonic()
                if active_count >= _MAX_ACTIVE_ROOMS:
                    return JSONResponse(
                        status_code=503,
                        content={"detail": f"Too many active rooms ({active_count}/{_MAX_ACTIVE_ROOMS}). Try again later."},
                    )
                if now - _last_room_activate_at < _ROOM_ACTIVATE_COOLDOWN_S:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Room activation rate limited. Try again shortly."},
                    )
                _last_room_activate_at = now
                await room_manager.start_room(room_id)

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
