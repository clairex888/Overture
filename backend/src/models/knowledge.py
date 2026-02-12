"""Knowledge models for the Overture system.

Stores curated market knowledge, research, and outlook
across multiple time horizons and asset classes.
"""

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Enum, Float, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class KnowledgeCategory(str, enum.Enum):
    """Category classification for knowledge entries."""

    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MACRO = "macro"
    EVENT = "event"
    RESEARCH = "research"
    EDUCATION = "education"


class KnowledgeLayer(str, enum.Enum):
    """Time-horizon layer for knowledge and outlooks."""

    LONG_TERM = "long_term"
    MID_TERM = "mid_term"
    SHORT_TERM = "short_term"


class OutlookSentiment(str, enum.Enum):
    """Directional outlook sentiment."""

    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"


class KnowledgeEntry(Base):
    """A curated piece of market knowledge or research.

    Stores structured knowledge with categorization, source
    credibility tracking, and optional vector embeddings
    for future semantic search capabilities.
    """

    __tablename__ = "knowledge_entries"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[KnowledgeCategory] = mapped_column(
        Enum(KnowledgeCategory, name="knowledge_category", native_enum=False),
        nullable=False,
    )
    layer: Mapped[KnowledgeLayer] = mapped_column(
        Enum(KnowledgeLayer, name="knowledge_layer", native_enum=False),
        nullable=False,
    )
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    source_credibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    asset_classes: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    tickers: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Vector embedding for future semantic search (e.g., 1536-dim OpenAI embeddings)",
    )
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True, default=dict
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"<KnowledgeEntry(id={self.id!r}, title={self.title!r}, "
            f"category={self.category!r}, layer={self.layer!r})>"
        )


class MarketOutlook(Base):
    """Directional market outlook for a specific asset class and time horizon.

    Captures the system's current view on market direction,
    confidence level, and key drivers informing the outlook.
    """

    __tablename__ = "market_outlooks"

    layer: Mapped[KnowledgeLayer] = mapped_column(
        Enum(KnowledgeLayer, name="knowledge_layer", native_enum=False, create_constraint=False),
        nullable=False,
    )
    asset_class: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    outlook: Mapped[OutlookSentiment] = mapped_column(
        Enum(OutlookSentiment, name="outlook_sentiment", native_enum=False),
        nullable=False,
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_drivers: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<MarketOutlook(id={self.id!r}, asset_class={self.asset_class!r}, "
            f"outlook={self.outlook!r}, layer={self.layer!r})>"
        )
