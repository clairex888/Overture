import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import ideas, portfolio, agents, knowledge, trades, alerts, rl, seed, market_data, auth
from src.api.websocket import router as ws_router
from src.config import settings
from src.models import base as db_base
from src.models.base import async_session_factory
import src.models.user  # noqa: F401 — ensure User table is created

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

        # Seed master admin account (idempotent)
        try:
            await _seed_master_user()
        except Exception as exc:
            logger.error("Master user seed FAILED: %s", exc, exc_info=True)

        # Add user_id column to portfolios if missing (schema migration)
        try:
            await _migrate_portfolio_user_id()
        except Exception as exc:
            logger.error("Portfolio user_id migration FAILED: %s", exc, exc_info=True)

        # Migrate orphan portfolios (no user_id) to the admin user
        try:
            await _assign_orphan_portfolios()
        except Exception as exc:
            logger.error("Orphan portfolio migration FAILED: %s", exc, exc_info=True)

    yield


async def _seed_master_user() -> None:
    """Create or reset the master admin account.

    Resets the password on every startup so the master account always works
    even if the JWT secret or bcrypt rounds changed between deploys.
    """
    from sqlalchemy import select
    from src.models.user import User, UserRole
    from src.auth import hash_password
    from uuid import uuid4

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "admin@overture.ai")
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Reset password on every startup so the master account always works
            existing.hashed_password = hash_password("admin123")
            existing.is_active = True
            await session.commit()
            logger.info("Master admin password reset: admin@overture.ai")
            return

        admin = User(
            id=str(uuid4()),
            email="admin@overture.ai",
            hashed_password=hash_password("admin123"),
            display_name="Master Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        logger.info("Master admin account created: admin@overture.ai")


async def _migrate_portfolio_user_id() -> None:
    """Add user_id column to portfolios table if it doesn't exist.

    create_all() only creates new tables — it never adds columns to existing
    ones. This handles the schema migration without Alembic.

    The column must be UUID type (not VARCHAR) to match users.id which is
    also UUID. PostgreSQL rejects FK constraints between mismatched types.
    """
    from sqlalchemy import text

    async with async_session_factory() as session:
        # Check if the column already exists
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'portfolios' AND column_name = 'user_id'"
        ))
        if result.scalar_one_or_none():
            return  # Column already exists

        # Add the column — must be UUID to match users.id type
        await session.execute(text(
            "ALTER TABLE portfolios "
            "ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE"
        ))
        await session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_portfolios_user_id ON portfolios (user_id)"
        ))
        await session.commit()
        logger.info("Added user_id column to portfolios table.")


async def _assign_orphan_portfolios() -> None:
    """One-time migration: assign any portfolios without a user_id to the admin."""
    from sqlalchemy import select, update
    from src.models.portfolio import Portfolio
    from src.models.user import User

    async with async_session_factory() as session:
        # Find admin user
        result = await session.execute(
            select(User).where(User.email == "admin@overture.ai")
        )
        admin = result.scalar_one_or_none()
        if not admin:
            return

        # Assign orphan portfolios to admin
        result = await session.execute(
            update(Portfolio)
            .where(Portfolio.user_id.is_(None))
            .values(user_id=admin.id)
        )
        if result.rowcount > 0:
            await session.commit()
            logger.info("Assigned %d orphan portfolios to admin user.", result.rowcount)


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
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# WebSocket
app.include_router(ws_router, prefix="/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "database": "connected" if db_base.db_ready else "unavailable",
    }
