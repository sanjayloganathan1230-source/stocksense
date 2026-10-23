import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market_routes import router as market_router
from app.api.websocket_routes import manager as websocket_manager
from app.api.websocket_routes import router as websocket_router
from app.config import BACKEND_HOST, BACKEND_PORT

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await websocket_manager.close()


app = FastAPI(title="StockSense API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router)
app.include_router(websocket_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "StockSense API"}


@app.get("/api/system/status")
def system_status() -> dict[str, str]:
    return {
        "service": "StockSense API",
        "status": "ok",
        "market_data_provider": getattr(websocket_manager.provider, "provider_name", "unconfigured"),
        "data_mode": getattr(websocket_manager.provider, "data_mode", "unavailable"),
        "stream_status": websocket_manager.stream_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=BACKEND_HOST, port=BACKEND_PORT, reload=True)
