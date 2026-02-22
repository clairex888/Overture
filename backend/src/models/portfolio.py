"""Portfolio, Position, and PortfolioSnapshot models for the Overture system."""

import enum
from datetime import datetime, date as date_type
from typing import Any, Optional

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text, Date, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class PortfolioStatus(str, enum.Enum):
    """Operational status of a portfolio."""

    ACTIVE = "active"
    PAUSED = "paused"


class Portfolio(Base):
    """Represents a managed investment portfolio.

    Tracks overall portfolio value, cash allocation, P&L,
    risk metrics, and user-defined preferences such as
    risk appetite and asset allocation targets.
    """

    __tablename__ = "portfolios"

    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Owner of this portfolio. Nullable for legacy/migration compatibility.",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    invested: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    preferences: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
        comment="Portfolio preferences: goals, risk_appetite, asset_allocation targets, etc.",
    )
    status: Mapped[PortfolioStatus] = mapped_column(
        Enum(PortfolioStatus, name="portfolio_status", native_enum=False),
        nullable=False,
        default=PortfolioStatus.ACTIVE,
    )

    # Relationships
    positions: Mapped[list["Position"]] = relationship(
        "Position", back_populates="portfolio", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Portfolio(id={self.id!r}, name={self.name!r}, "
            f"total_value={self.total_value!r}, status={self.status!r})>"
        )


class Position(Base):
    """Represents an individual position within a portfolio.

    Links a portfolio to a trade, tracking the current state
    of the position including market value, P&L, and portfolio weight.
    """

    __tablename__ = "positions"

    portfolio_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trade_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("trades.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="Position weight as fraction of total portfolio value"
    )
    asset_class: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio", back_populates="positions", lazy="selectin"
    )
    trade: Mapped[Optional["Trade"]] = relationship(  # noqa: F821
        "Trade", back_populates="positions", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Position(id={self.id!r}, ticker={self.ticker!r}, "
            f"direction={self.direction!r}, quantity={self.quantity!r})>"
        )


class PortfolioSnapshot(Base):
    """Daily snapshot of portfolio value for historical tracking.

    Recorded by the price-cache refresh loop so the dashboard can
    display a real portfolio value chart.
    """

    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "snapshot_date", name="uq_portfolio_snapshot_date"),
    )

    portfolio_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    total_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invested: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    positions_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<PortfolioSnapshot(portfolio_id={self.portfolio_id!r}, date={self.snapshot_date!r}, value={self.total_value!r})>"
