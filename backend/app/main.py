from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings
from app.database import init_db, close_db
from app.services.redis_client import init_redis, close_redis
from app.services.scheduler import start_scheduler, stop_scheduler
from app.routers import watchlist, signals, assets, sse

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Trading Agent API", version="1.0.0-beta", env=settings.app_env)
    await init_db()
    await init_redis()
    await start_scheduler()
    logger.info("All services started — ready to trade")
    yield
    logger.info("Shutting down Trading Agent API")
    await stop_scheduler()
    await close_redis()
    await close_db()


app = FastAPI(
    title="Trading Agent API",
    description="Système d'aide à la décision swing trading — PEA/CTO",
    version="1.0.0-beta",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(watchlist.router, prefix="/api/watchlists", tags=["watchlists"])
app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
app.include_router(assets.router, prefix="/api/assets", tags=["assets"])
app.include_router(sse.router, prefix="/api/stream", tags=["stream"])


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "version": "1.0.0-beta", "env": settings.app_env}
