"""
Trades API routes.

Manages the trade lifecycle: creation from idea execution plans, approval
workflow (human-in-the-loop), parameter adjustment, and closing of positions.
All data is persisted in PostgreSQL via SQLAlchemy async models.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.trade import Trade, TradeStatus, TradeDirection, InstrumentType

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas (match frontend expectations)
# ---------------------------------------------------------------------------


class TradeAdjustment(BaseModel):
    quantity: float | None = Field(None, gt=0)
    limit_price: float | None = Field(None, gt=0)
    stop_loss: float | None = Field(None, gt=0)
    take_profit: float | None = Field(None, gt=0)
    notes: str | None = None


class TradeResponse(BaseModel):
    id: str
    idea_id: str | None
    symbol: str
    direction: str = Field(..., description="buy or sell")
    instrument_type: str = Field(..., description="stock, option, future, crypto, bond")
    quantity: float
    limit_price: float | None
    stop_loss: float | None
    take_profit: float | None
    status: str
    fill_price: float | None
    fill_quantity: float | None
    pnl: float | None
    notes: str | None
    created_at: str
    updated_at: str


class TradeRejectPayload(BaseModel):
    reason: str = Field(..., min_length=1)


class TradeClosePayload(BaseModel):
    reason: str | None = None
    market_order: bool = Field(True, description="Close at market if True, else use limit")
    limit_price: float | None = None


class PendingSummary(BaseModel):
    count: int
    trades: list[TradeResponse]


class ActiveSummary(BaseModel):
    count: int
    total_exposure: float
    trades: list[TradeResponse]


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_DIRECTION_DB_TO_API = {
    TradeDirection.LONG: "buy",
    TradeDirection.SHORT: "sell",
}

_DIRECTION_API_TO_DB = {v: k for k, v in _DIRECTION_DB_TO_API.items()}

_INSTRUMENT_DB_TO_API = {
    InstrumentType.EQUITY: "stock",
    InstrumentType.OPTION: "option",
    InstrumentType.FUTURE: "future",
    InstrumentType.ETF: "etf",
    InstrumentType.BOND: "bond",
    InstrumentType.CRYPTO: "crypto",
}

_INSTRUMENT_API_TO_DB = {v: k for k, v in _INSTRUMENT_DB_TO_API.items()}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _dt_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_iso()
    return dt.isoformat() + "Z"


def _trade_to_response(trade: Trade) -> TradeResponse:
    """Convert ORM Trade to API response."""
    meta = trade.metadata_ or {}

    # Symbol: from metadata or first ticker
    symbol = meta.get("symbol", "")
    if not symbol and trade.tickers:
        symbol = trade.tickers[0] if isinstance(trade.tickers[0], str) else str(trade.tickers[0])

    # Direction: from metadata label or DB enum
    direction = meta.get("direction_label", _DIRECTION_DB_TO_API.get(trade.direction, "buy"))

    # Instrument type mapping
    instrument = _INSTRUMENT_DB_TO_API.get(trade.instrument_type, "stock")

    return TradeResponse(
        id=trade.id,
        idea_id=trade.idea_id,
        symbol=symbol,
        direction=direction,
        instrument_type=instrument,
        quantity=trade.quantity or 0,
        limit_price=meta.get("limit_price") or trade.entry_price,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit,
        status=trade.status.value if trade.status else "pending_approval",
        fill_price=meta.get("fill_price") or (trade.entry_price if trade.status in (TradeStatus.OPEN, TradeStatus.CLOSED) else None),
        fill_quantity=meta.get("fill_quantity") or (trade.quantity if trade.status in (TradeStatus.OPEN, TradeStatus.CLOSED) else None),
        pnl=trade.pnl,
        notes=meta.get("notes"),
        created_at=_dt_iso(trade.created_at),
        updated_at=_dt_iso(trade.updated_at),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pending", response_model=PendingSummary)
async def list_pending_trades(session: AsyncSession = Depends(get_session)):
    """Get all trades pending human approval."""
    result = await session.execute(
        select(Trade)
        .where(Trade.status == TradeStatus.PENDING_APPROVAL)
        .order_by(Trade.created_at.desc())
    )
    trades = result.scalars().all()
    return PendingSummary(
        count=len(trades),
        trades=[_trade_to_response(t) for t in trades],
    )


@router.get("/active", response_model=ActiveSummary)
async def list_active_trades(session: AsyncSession = Depends(get_session)):
    """Get all active (open / partially filled) trades."""
    result = await session.execute(
        select(Trade)
        .where(Trade.status.in_([TradeStatus.OPEN, TradeStatus.EXECUTING]))
        .order_by(Trade.updated_at.desc())
    )
    trades = result.scalars().all()

    total_exposure = 0.0
    for t in trades:
        meta = t.metadata_ or {}
        price = meta.get("fill_price") or t.entry_price or meta.get("limit_price") or 0
        total_exposure += price * (t.quantity or 0)

    return ActiveSummary(
        count=len(trades),
        total_exposure=total_exposure,
        trades=[_trade_to_response(t) for t in trades],
    )


@router.get("/", response_model=list[TradeResponse])
async def list_trades(
    status: str | None = Query(None, description="Filter by status"),
    direction: str | None = Query(None, description="Filter by direction (buy, sell)"),
    instrument_type: str | None = Query(None, description="Filter by instrument type"),
    session: AsyncSession = Depends(get_session),
):
    """List all trades with optional filters."""
    stmt = select(Trade)

    if status:
        try:
            status_enum = TradeStatus(status)
            stmt = stmt.where(Trade.status == status_enum)
        except ValueError:
            pass

    if direction:
        dir_enum = _DIRECTION_API_TO_DB.get(direction)
        if dir_enum:
            stmt = stmt.where(Trade.direction == dir_enum)

    if instrument_type:
        inst_enum = _INSTRUMENT_API_TO_DB.get(instrument_type)
        if inst_enum:
            stmt = stmt.where(Trade.instrument_type == inst_enum)

    stmt = stmt.order_by(Trade.created_at.desc())
    result = await session.execute(stmt)
    trades = result.scalars().all()
    return [_trade_to_response(t) for t in trades]


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str, session: AsyncSession = Depends(get_session)):
    """Get details for a specific trade."""
    result = await session.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return _trade_to_response(trade)


@router.post("/{trade_id}/approve", response_model=TradeResponse)
async def approve_trade(trade_id: str, session: AsyncSession = Depends(get_session)):
    """Approve a pending trade plan so it can be executed."""
    result = await session.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade.status != TradeStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Trade must be 'pending_approval' to approve, currently '{trade.status.value}'",
        )

    trade.status = TradeStatus.APPROVED
    return _trade_to_response(trade)


@router.post("/{trade_id}/reject", response_model=TradeResponse)
async def reject_trade(
    trade_id: str,
    payload: TradeRejectPayload,
    session: AsyncSession = Depends(get_session),
):
    """Reject a pending trade plan with a reason."""
    result = await session.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade.status != TradeStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Trade must be 'pending_approval' to reject, currently '{trade.status.value}'",
        )

    trade.status = TradeStatus.CANCELLED
    meta = dict(trade.metadata_ or {})
    existing_notes = meta.get("notes", "")
    meta["notes"] = f"{existing_notes} | Rejected: {payload.reason}".strip(" |")
    trade.metadata_ = meta
    return _trade_to_response(trade)


@router.post("/{trade_id}/adjust", response_model=TradeResponse)
async def adjust_trade(
    trade_id: str,
    payload: TradeAdjustment,
    session: AsyncSession = Depends(get_session),
):
    """Adjust trade parameters (size, stop loss, take profit, etc.)."""
    result = await session.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    adjustable = {TradeStatus.PENDING_APPROVAL, TradeStatus.APPROVED, TradeStatus.OPEN, TradeStatus.EXECUTING}
    if trade.status not in adjustable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot adjust trade in '{trade.status.value}' status",
        )

    updates = payload.model_dump(exclude_unset=True)
    meta = dict(trade.metadata_ or {})

    if "quantity" in updates:
        trade.quantity = updates["quantity"]
    if "limit_price" in updates:
        meta["limit_price"] = updates["limit_price"]
        trade.entry_price = updates["limit_price"]
    if "stop_loss" in updates:
        trade.stop_loss = updates["stop_loss"]
    if "take_profit" in updates:
        trade.take_profit = updates["take_profit"]
    if "notes" in updates:
        meta["notes"] = updates["notes"]

    trade.metadata_ = meta
    return _trade_to_response(trade)


@router.post("/{trade_id}/close", response_model=TradeResponse)
async def close_trade(
    trade_id: str,
    payload: TradeClosePayload | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Close/exit an active trade."""
    result = await session.execute(select(Trade).where(Trade.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    closeable = {TradeStatus.OPEN, TradeStatus.EXECUTING, TradeStatus.APPROVED}
    if trade.status not in closeable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close trade in '{trade.status.value}' status",
        )

    reason = payload.reason if payload else None
    if reason:
        meta = dict(trade.metadata_ or {})
        existing_notes = meta.get("notes", "")
        meta["notes"] = f"{existing_notes} | Closed: {reason}".strip(" |")
        trade.metadata_ = meta

    trade.status = TradeStatus.CLOSED
    return _trade_to_response(trade)
