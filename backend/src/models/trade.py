"""Trade model for the Overture system."""

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class TradeStatus(str, enum.Enum):
    """Lifecycle status of a trade."""

    PLANNED = "planned"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TradeDirection(str, enum.Enum):
    """Direction of a trade position."""

    LONG = "long"
    SHORT = "short"


class InstrumentType(str, enum.Enum):
    """Financial instrument type for the trade."""

    EQUITY = "equity"
    OPTION = "option"
    FUTURE = "future"
    ETF = "etf"
    BOND = "bond"
    CRYPTO = "crypto"


class Trade(Base):
    """Represents a trade derived from an investment idea.

    Tracks the full lifecycle of a trade from planning through
    execution and closure, including P&L tracking and risk parameters.
    """

    __tablename__ = "trades"

    idea_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("ideas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[TradeStatus] = mapped_column(
        Enum(TradeStatus, name="trade_status", native_enum=False),
        nullable=False,
        default=TradeStatus.PLANNED,
    )
    direction: Mapped[TradeDirection] = mapped_column(
        Enum(TradeDirection, name="trade_direction", native_enum=False),
        nullable=False,
    )
    tickers: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType, name="instrument_type", native_enum=False),
        nullable=False,
        default=InstrumentType.EQUITY,
    )
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notional_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    exit_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    execution_plan: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=dict
    )
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True, default=dict
    )

    # Relationships
    idea: Mapped[Optional["Idea"]] = relationship(  # noqa: F821
        "Idea", back_populates="trades", lazy="selectin"
    )
    positions: Mapped[list["Position"]] = relationship(  # noqa: F821
        "Position", back_populates="trade", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id!r}, direction={self.direction!r}, "
            f"status={self.status!r}, pnl={self.pnl!r})>"
        )
