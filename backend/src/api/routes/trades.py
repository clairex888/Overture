"""
Trades API routes.

Manages the trade lifecycle: creation from idea execution plans, approval
workflow (human-in-the-loop), parameter adjustment, and closing of positions.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TradeAdjustment(BaseModel):
    """Parameters that can be adjusted on a pending or active trade."""
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
    status: str = Field(
        ...,
        description="pending_approval, approved, rejected, open, partially_filled, filled, closed, cancelled",
    )
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
# In-memory store (swap for DB later)
# ---------------------------------------------------------------------------

_trades_store: dict[str, dict[str, Any]] = {}

# Seed some sample trades
_seed_trades = [
    {
        "id": str(uuid4()),
        "idea_id": None,
        "symbol": "NVDA",
        "direction": "buy",
        "instrument_type": "stock",
        "quantity": 50,
        "limit_price": 890.00,
        "stop_loss": 850.00,
        "take_profit": 950.00,
        "status": "pending_approval",
        "fill_price": None,
        "fill_quantity": None,
        "pnl": None,
        "notes": "AI chip momentum play",
        "created_at": "2026-02-10T14:30:00Z",
        "updated_at": "2026-02-10T14:30:00Z",
    },
    {
        "id": str(uuid4()),
        "idea_id": None,
        "symbol": "ETH-USD",
        "direction": "buy",
        "instrument_type": "crypto",
        "quantity": 5.0,
        "limit_price": 3_200.00,
        "stop_loss": 2_900.00,
        "take_profit": 3_800.00,
        "status": "open",
        "fill_price": 3_180.00,
        "fill_quantity": 5.0,
        "pnl": 350.00,
        "notes": "ETH breakout trade",
        "created_at": "2026-02-05T09:00:00Z",
        "updated_at": "2026-02-10T16:00:00Z",
    },
    {
        "id": str(uuid4()),
        "idea_id": None,
        "symbol": "SPY",
        "direction": "sell",
        "instrument_type": "stock",
        "quantity": 100,
        "limit_price": None,
        "stop_loss": 510.00,
        "take_profit": 470.00,
        "status": "pending_approval",
        "fill_price": None,
        "fill_quantity": None,
        "pnl": None,
        "notes": "Hedging position against drawdown",
        "created_at": "2026-02-11T11:00:00Z",
        "updated_at": "2026-02-11T11:00:00Z",
    },
]
for t in _seed_trades:
    _trades_store[t["id"]] = t


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _trade_to_response(trade: dict[str, Any]) -> TradeResponse:
    return TradeResponse(**trade)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pending", response_model=PendingSummary)
async def list_pending_trades():
    """Get all trades pending human approval."""
    pending = [
        t for t in _trades_store.values() if t["status"] == "pending_approval"
    ]
    pending.sort(key=lambda t: t["created_at"], reverse=True)
    return PendingSummary(
        count=len(pending),
        trades=[_trade_to_response(t) for t in pending],
    )


@router.get("/active", response_model=ActiveSummary)
async def list_active_trades():
    """Get all active (open / partially filled) trades."""
    active_statuses = {"open", "partially_filled"}
    active = [t for t in _trades_store.values() if t["status"] in active_statuses]
    active.sort(key=lambda t: t["updated_at"], reverse=True)

    total_exposure = sum(
        (t.get("fill_price") or t.get("limit_price") or 0) * t["quantity"]
        for t in active
    )
    return ActiveSummary(
        count=len(active),
        total_exposure=total_exposure,
        trades=[_trade_to_response(t) for t in active],
    )


@router.get("/", response_model=list[TradeResponse])
async def list_trades(
    status: str | None = Query(None, description="Filter by status"),
    direction: str | None = Query(None, description="Filter by direction (buy, sell)"),
    instrument_type: str | None = Query(None, description="Filter by instrument type"),
):
    """List all trades with optional filters."""
    results = list(_trades_store.values())

    if status:
        results = [t for t in results if t["status"] == status]
    if direction:
        results = [t for t in results if t["direction"] == direction]
    if instrument_type:
        results = [t for t in results if t["instrument_type"] == instrument_type]

    results.sort(key=lambda t: t["created_at"], reverse=True)
    return [_trade_to_response(t) for t in results]


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str):
    """Get details for a specific trade."""
    trade = _trades_store.get(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    return _trade_to_response(trade)


@router.post("/{trade_id}/approve", response_model=TradeResponse)
async def approve_trade(trade_id: str):
    """Approve a pending trade plan so it can be executed.

    In production this would submit the order to the broker.  The prototype
    moves the status to 'approved'.
    """
    trade = _trades_store.get(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade["status"] != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Trade must be 'pending_approval' to approve, currently '{trade['status']}'",
        )

    trade["status"] = "approved"
    trade["updated_at"] = _now_iso()
    return _trade_to_response(trade)


@router.post("/{trade_id}/reject", response_model=TradeResponse)
async def reject_trade(trade_id: str, payload: TradeRejectPayload):
    """Reject a pending trade plan with a reason."""
    trade = _trades_store.get(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    if trade["status"] != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Trade must be 'pending_approval' to reject, currently '{trade['status']}'",
        )

    trade["status"] = "rejected"
    trade["notes"] = f"{trade.get('notes', '') or ''} | Rejected: {payload.reason}".strip(" |")
    trade["updated_at"] = _now_iso()
    return _trade_to_response(trade)


@router.post("/{trade_id}/adjust", response_model=TradeResponse)
async def adjust_trade(trade_id: str, payload: TradeAdjustment):
    """Adjust trade parameters (size, stop loss, take profit, etc.)."""
    trade = _trades_store.get(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    adjustable_statuses = {"pending_approval", "approved", "open", "partially_filled"}
    if trade["status"] not in adjustable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot adjust trade in '{trade['status']}' status",
        )

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        trade[key] = value

    trade["updated_at"] = _now_iso()
    return _trade_to_response(trade)


@router.post("/{trade_id}/close", response_model=TradeResponse)
async def close_trade(trade_id: str, payload: TradeClosePayload | None = None):
    """Close/exit an active trade.

    In production this submits a closing order to the broker.  The prototype
    moves status to 'closed'.
    """
    trade = _trades_store.get(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    closeable = {"open", "partially_filled", "approved"}
    if trade["status"] not in closeable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close trade in '{trade['status']}' status",
        )

    reason = payload.reason if payload else None
    if reason:
        trade["notes"] = f"{trade.get('notes', '') or ''} | Closed: {reason}".strip(" |")

    trade["status"] = "closed"
    trade["updated_at"] = _now_iso()
    return _trade_to_response(trade)
