from fastapi import FastAPI
 
from ifrontier.app.api import router as api_router
from ifrontier.app.ws import router as ws_router
 
 
def create_app() -> FastAPI:
    app = FastAPI(title="Information Frontier")
    app.include_router(api_router)
    app.include_router(ws_router)
    return app


app = create_app()
