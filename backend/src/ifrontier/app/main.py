from fastapi import FastAPI

from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
from ifrontier.infra.sqlite.schema import init_schema
 
 
def create_app() -> FastAPI:
    init_schema()
    app = FastAPI(title="Information Frontier")
    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
