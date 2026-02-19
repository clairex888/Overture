"""
Portfolio API routes.

Provides portfolio overview, positions, risk metrics, performance analytics,
allocation breakdowns, and rebalancing triggers.
All data is persisted in PostgreSQL via SQLAlchemy async models.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.portfolio import Portfolio, Position as PositionModel, PortfolioStatus

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas (match frontend expectations exactly)
# ---------------------------------------------------------------------------


class Position(BaseModel):
    id: str
    symbol: str
    direction: str = Field(..., description="long or short")
    quantity: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight: float = Field(..., description="Portfolio weight 0-1")
    asset_class: str
    opened_at: str


class PortfolioOverview(BaseModel):
    total_value: float
    cash: float
    invested: float
    total_pnl: float
    total_pnl_pct: float
    day_pnl: float
    day_pnl_pct: float
    positions_count: int
    last_updated: str


class RiskMetrics(BaseModel):
    var_95: float = Field(..., description="Value at Risk 95%")
    var_99: float = Field(..., description="Value at Risk 99%")
    portfolio_volatility: float
    portfolio_beta: float
    sharpe_ratio: float
    max_drawdown: float
    concentration_top5: float = Field(..., description="Weight of top 5 positions")
    sector_concentration: dict[str, float]
    correlation_risk: str
    last_calculated: str


class PerformanceMetrics(BaseModel):
    total_return: float
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration_days: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    calmar_ratio: float
    period_start: str
    period_end: str


class AllocationEntry(BaseModel):
    category: str
    current_weight: float
    target_weight: float
    drift: float


class AllocationBreakdown(BaseModel):
    by_asset_class: list[AllocationEntry]
    by_sector: list[AllocationEntry]
    by_geography: list[AllocationEntry]
    last_updated: str


class PortfolioPreferences(BaseModel):
    risk_appetite: str = Field("moderate", description="conservative, moderate, aggressive")
    target_annual_return: float = Field(0.12, ge=0, le=1)
    max_drawdown_tolerance: float = Field(0.15, ge=0, le=1)
    target_allocation: dict[str, float] | None = None
    excluded_sectors: list[str] = Field(default_factory=list)
    excluded_tickers: list[str] = Field(default_factory=list)
    max_single_position_pct: float = Field(0.10, ge=0, le=1)
    rebalance_frequency: str = Field("weekly", description="daily, weekly, monthly")
    views: dict[str, Any] = Field(default_factory=dict, description="User market views")


class RebalanceResult(BaseModel):
    rebalance_needed: bool
    drift_detected: dict[str, float]
    proposed_trades: list[dict[str, Any]]
    estimated_cost: float
    triggered_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _dt_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_iso()
    return dt.isoformat() + "Z"


async def _get_active_portfolio(session: AsyncSession) -> Portfolio:
    """Return the first active portfolio or raise 404."""
    result = await session.execute(
        select(Portfolio).where(Portfolio.status == PortfolioStatus.ACTIVE).limit(1)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(
            status_code=404,
            detail="No active portfolio found. Call POST /api/seed to initialize.",
        )
    return portfolio


def _position_to_response(pos: PositionModel) -> Position:
    return Position(
        id=pos.id,
        symbol=pos.ticker,
        direction=pos.direction,
        quantity=pos.quantity or 0,
        avg_entry_price=pos.avg_entry_price or 0,
        current_price=pos.current_price or 0,
        market_value=pos.market_value or 0,
        unrealized_pnl=pos.pnl or 0,
        unrealized_pnl_pct=pos.pnl_pct or 0,
        weight=pos.weight or 0,
        asset_class=pos.asset_class or "unknown",
        opened_at=_dt_iso(pos.created_at),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=PortfolioOverview)
async def get_portfolio_overview(session: AsyncSession = Depends(get_session)):
    """Get portfolio overview including total value, P&L, and allocation summary."""
    portfolio = await _get_active_portfolio(session)

    count_result = await session.execute(
        select(func.count())
        .select_from(PositionModel)
        .where(PositionModel.portfolio_id == portfolio.id)
    )
    positions_count = count_result.scalar() or 0

    return PortfolioOverview(
        total_value=portfolio.total_value or 0,
        cash=portfolio.cash or 0,
        invested=portfolio.invested or 0,
        total_pnl=portfolio.pnl or 0,
        total_pnl_pct=portfolio.pnl_pct or 0,
        day_pnl=0,
        day_pnl_pct=0,
        positions_count=positions_count,
        last_updated=_dt_iso(portfolio.updated_at),
    )


@router.get("/positions", response_model=list[Position])
async def list_positions(session: AsyncSession = Depends(get_session)):
    """List all current portfolio positions."""
    portfolio = await _get_active_portfolio(session)

    result = await session.execute(
        select(PositionModel)
        .where(PositionModel.portfolio_id == portfolio.id)
        .order_by(PositionModel.market_value.desc().nullslast())
    )
    positions = result.scalars().all()
    return [_position_to_response(p) for p in positions]


@router.get("/positions/{position_id}", response_model=Position)
async def get_position(position_id: str, session: AsyncSession = Depends(get_session)):
    """Get details for a specific position."""
    result = await session.execute(
        select(PositionModel).where(PositionModel.id == position_id)
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return _position_to_response(pos)


@router.get("/preferences", response_model=PortfolioPreferences)
async def get_preferences(session: AsyncSession = Depends(get_session)):
    """Get current portfolio preferences."""
    portfolio = await _get_active_portfolio(session)
    prefs = portfolio.preferences or {}
    return PortfolioPreferences(**{
        "risk_appetite": prefs.get("risk_appetite", "moderate"),
        "target_annual_return": prefs.get("target_annual_return", 0.12),
        "max_drawdown_tolerance": prefs.get("max_drawdown_tolerance", 0.15),
        "target_allocation": prefs.get("target_allocation"),
        "excluded_sectors": prefs.get("excluded_sectors", []),
        "excluded_tickers": prefs.get("excluded_tickers", []),
        "max_single_position_pct": prefs.get("max_single_position_pct", 0.10),
        "rebalance_frequency": prefs.get("rebalance_frequency", "weekly"),
        "views": prefs.get("views", {}),
    })


@router.put("/preferences", response_model=PortfolioPreferences)
async def update_preferences(
    payload: PortfolioPreferences,
    session: AsyncSession = Depends(get_session),
):
    """Update portfolio preferences (risk appetite, goals, views)."""
    portfolio = await _get_active_portfolio(session)
    portfolio.preferences = payload.model_dump()
    return PortfolioPreferences(**portfolio.preferences)


@router.get("/risk", response_model=RiskMetrics)
async def get_risk_metrics(session: AsyncSession = Depends(get_session)):
    """Get portfolio risk metrics (VaR, volatility, concentration, etc.)."""
    portfolio = await _get_active_portfolio(session)

    result = await session.execute(
        select(PositionModel).where(PositionModel.portfolio_id == portfolio.id)
    )
    positions = result.scalars().all()

    total_invested = portfolio.invested or 0
    weights: list[float] = []
    sector_weights: dict[str, float] = {}

    for pos in positions:
        w = pos.weight or 0
        weights.append(w)
        ac = pos.asset_class or "other"
        sector_weights[ac] = sector_weights.get(ac, 0) + w

    weights.sort(reverse=True)
    top5 = sum(weights[:5])

    if not sector_weights:
        sector_weights = {"cash": 1.0}

    return RiskMetrics(
        var_95=total_invested * 0.015 if total_invested > 0 else 0,
        var_99=total_invested * 0.025 if total_invested > 0 else 0,
        portfolio_volatility=0.0,
        portfolio_beta=1.0 if total_invested > 0 else 0,
        sharpe_ratio=0.0,
        max_drawdown=0.0,
        concentration_top5=top5,
        sector_concentration=sector_weights,
        correlation_risk="low" if len(positions) < 3 else "moderate",
        last_calculated=_now_iso(),
    )


@router.post("/rebalance", response_model=RebalanceResult)
async def trigger_rebalance(session: AsyncSession = Depends(get_session)):
    """Trigger a rebalancing check against target allocation."""
    portfolio = await _get_active_portfolio(session)
    prefs = portfolio.preferences or {}
    target_alloc = prefs.get("target_allocation", {})

    result = await session.execute(
        select(PositionModel).where(PositionModel.portfolio_id == portfolio.id)
    )
    positions = result.scalars().all()
    total_val = portfolio.total_value or 1

    current_alloc: dict[str, float] = {}
    for pos in positions:
        ac = pos.asset_class or "other"
        current_alloc[ac] = current_alloc.get(ac, 0) + (pos.market_value or 0) / total_val

    current_alloc["cash"] = (portfolio.cash or 0) / total_val

    drift: dict[str, float] = {}
    for cat, target in target_alloc.items():
        current = current_alloc.get(cat, 0)
        drift[cat] = round(current - target, 4)

    rebalance_needed = any(abs(d) > 0.02 for d in drift.values())

    return RebalanceResult(
        rebalance_needed=rebalance_needed,
        drift_detected=drift,
        proposed_trades=[],
        estimated_cost=0,
        triggered_at=_now_iso(),
    )


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance(session: AsyncSession = Depends(get_session)):
    """Get portfolio performance metrics (returns, sharpe, drawdown, etc.)."""
    portfolio = await _get_active_portfolio(session)

    total_pnl = portfolio.pnl or 0
    total_val = portfolio.total_value or 1_000_000
    initial = total_val - total_pnl
    pnl_pct = total_pnl / initial if initial > 0 else 0

    return PerformanceMetrics(
        total_return=total_pnl,
        total_return_pct=pnl_pct,
        annualized_return_pct=pnl_pct,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        max_drawdown=0.0,
        max_drawdown_duration_days=0,
        win_rate=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        profit_factor=0.0,
        calmar_ratio=0.0,
        period_start=_dt_iso(portfolio.created_at),
        period_end=_now_iso(),
    )


@router.get("/allocation", response_model=AllocationBreakdown)
async def get_allocation(session: AsyncSession = Depends(get_session)):
    """Get current vs target allocation breakdown by asset class, sector, geography."""
    portfolio = await _get_active_portfolio(session)
    prefs = portfolio.preferences or {}
    target_alloc = prefs.get("target_allocation", {
        "equities": 0.45,
        "fixed_income": 0.20,
        "crypto": 0.15,
        "commodities": 0.05,
        "cash": 0.15,
    })

    result = await session.execute(
        select(PositionModel).where(PositionModel.portfolio_id == portfolio.id)
    )
    positions = result.scalars().all()
    total_val = portfolio.total_value or 1

    current_alloc: dict[str, float] = {}
    for pos in positions:
        ac = pos.asset_class or "other"
        current_alloc[ac] = current_alloc.get(ac, 0) + (pos.market_value or 0) / total_val
    current_alloc["cash"] = (portfolio.cash or 0) / total_val

    all_categories = set(list(target_alloc.keys()) + list(current_alloc.keys()))
    by_asset_class = []
    for cat in sorted(all_categories):
        current = round(current_alloc.get(cat, 0), 4)
        target = round(target_alloc.get(cat, 0), 4)
        by_asset_class.append(AllocationEntry(
            category=cat,
            current_weight=current,
            target_weight=target,
            drift=round(current - target, 4),
        ))

    return AllocationBreakdown(
        by_asset_class=by_asset_class,
        by_sector=[],
        by_geography=[],
        last_updated=_now_iso(),
    )
