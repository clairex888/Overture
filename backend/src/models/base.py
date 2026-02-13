"""Base model and database session setup for the Overture system."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import uuid4

from sqlalchemy import MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import settings

logger = logging.getLogger(__name__)

# Naming convention for constraints (helps Alembic generate clean migrations)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base declarative model with common fields for all Overture models."""

    metadata = MetaData(naming_convention=convention)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


async def init_db(retries: int = 5, delay: float = 2.0) -> None:
    """Create all database tables.

    Should be called once at application startup. In production,
    prefer Alembic migrations over auto-creation.

    Retries connection with exponential backoff to handle cases where
    the database is still starting up (e.g. Railway deployments).
    """
    for attempt in range(1, retries + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully.")
            return
        except Exception as exc:
            if attempt == retries:
                logger.error("Failed to connect to database after %d attempts: %s", retries, exc)
                raise
            wait = delay * (2 ** (attempt - 1))
            logger.warning(
                "Database connection attempt %d/%d failed (%s). Retrying in %.1fs...",
                attempt, retries, exc, wait,
            )
            await asyncio.sleep(wait)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for dependency injection.

    Usage with FastAPI:
        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
