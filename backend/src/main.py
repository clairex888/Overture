import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import ideas, portfolio, agents, knowledge, trades, alerts, rl, seed, market_data
from src.api.websocket import router as ws_router
from src.config import settings
from src.models import base as db_base
from src.models.base import async_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_base.init_db()

    # Auto-seed if database is empty (idempotent)
    if db_base.db_ready:
        try:
            async with async_session_factory() as session:
                result = await seed.run_seed(session)
                await session.commit()
                logger.info("Auto-seed: %s", result.message)
        except Exception as exc:
            logger.warning("Auto-seed skipped: %s", exc)

    yield


app = FastAPI(
    title="Overture - AI Hedge Fund",
    description="Multi-agent AI-native hedge fund system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API routes
app.include_router(ideas.router, prefix="/api/ideas", tags=["ideas"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(rl.router, prefix="/api/rl", tags=["rl"])
app.include_router(seed.router, prefix="/api/seed", tags=["seed"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["market-data"])

# WebSocket
app.include_router(ws_router, prefix="/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "database": "connected" if db_base.db_ready else "unavailable",
    }
