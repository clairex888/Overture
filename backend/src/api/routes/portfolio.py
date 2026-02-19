"""
Portfolio API routes.

Provides portfolio overview, positions, risk metrics, performance analytics,
allocation breakdowns, rebalancing triggers, and portfolio initialization.
All data is persisted in PostgreSQL via SQLAlchemy async models.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.portfolio import Portfolio, Position as PositionModel, PortfolioStatus
from src.models.trade import Trade, TradeStatus, TradeDirection, InstrumentType
from src.services.portfolio_init import (
    fetch_last_close_prices,
    generate_proposal,
    compute_trading_cost,
    ASSET_UNIVERSE,
    INTRA_CLASS_WEIGHTS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_PORTFOLIOS = 5

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


class AssetAllocationTarget(BaseModel):
    asset_class: str
    target_weight: float


class PortfolioPreferences(BaseModel):
    """Matches frontend PortfolioPreferences interface exactly."""
    # Portfolio Goals
    target_annual_return: float = Field(12, ge=0, le=50)
    max_drawdown_tolerance: float = Field(15, ge=0, le=50)
    investment_horizon: str = Field("medium_term", description="short_term, medium_term, long_term")
    benchmark: str = Field("SPY")

    # Asset Allocation Targets
    allocation_targets: list[AssetAllocationTarget] = Field(default_factory=lambda: [
        AssetAllocationTarget(asset_class="equities", target_weight=50),
        AssetAllocationTarget(asset_class="fixed_income", target_weight=20),
        AssetAllocationTarget(asset_class="crypto", target_weight=10),
        AssetAllocationTarget(asset_class="commodities", target_weight=10),
        AssetAllocationTarget(asset_class="cash", target_weight=10),
    ])

    # Risk Parameters
    risk_appetite: str = Field("moderate", description="conservative, moderate, aggressive")
    max_position_size: float = Field(10, ge=1, le=50)
    concentration_limit: float = Field(30, ge=10, le=100)
    stop_loss_pct: float = Field(5, ge=0, le=50)

    # Constraints & Rules
    excluded_sectors: list[str] = Field(default_factory=list)
    excluded_tickers: list[str] = Field(default_factory=list)
    hard_rules: str = Field("")

    # Rebalance Schedule
    rebalance_frequency: str = Field("monthly", description="daily, weekly, monthly, quarterly")
    drift_tolerance: float = Field(5, ge=1, le=20)
    auto_rebalance: bool = Field(False)


class RebalanceResult(BaseModel):
    rebalance_needed: bool
    drift_detected: dict[str, float]
    proposed_trades: list[dict[str, Any]]
    estimated_cost: float
    triggered_at: str


class PortfolioListItem(BaseModel):
    id: str
    name: str
    total_value: float
    cash: float
    invested: float
    pnl: float
    pnl_pct: float
    status: str
    positions_count: int
    created_at: str


class InitializeRequest(BaseModel):
    initial_amount: float = Field(1_000_000, gt=0)
    name: str = Field("Paper Portfolio", max_length=255)
    portfolio_id: str | None = Field(None, description="If provided, reinitialize this portfolio")


class InitializeResult(BaseModel):
    portfolio_id: str
    name: str
    initial_amount: float
    message: str


class GenerateProposalRequest(BaseModel):
    portfolio_id: str


class ProposedHolding(BaseModel):
    ticker: str
    name: str
    asset_class: str
    sub_class: str
    instrument: str
    direction: str
    quantity: float
    price: float
    fill_price: float
    market_value: float
    weight: float
    trading_cost: dict[str, float]


class ProposedTrade(BaseModel):
    ticker: str
    name: str
    direction: str
    instrument: str
    quantity: float
    price: float
    fill_price: float
    notional: float
    spread_cost: float
    impact_cost: float
    commission: float
    sec_fee: float
    total_cost: float
    slippage_pct: float


class PortfolioProposal(BaseModel):
    portfolio_id: str
    initial_amount: float
    total_value: float
    total_invested: float
    cash: float
    total_trading_cost: float
    num_positions: int
    holdings: list[ProposedHolding]
    trades: list[ProposedTrade]
    allocation_summary: dict[str, float]
    risk_appetite: str
    strategy_notes: list[str]


class TweakRequest(BaseModel):
    """User can tweak individual holdings before approving."""
    portfolio_id: str
    initial_amount: float = Field(1_000_000, gt=0)
    holdings: list[dict[str, Any]] = Field(
        ..., description="Modified holdings list with ticker, quantity, etc."
    )


class ApproveRequest(BaseModel):
    """User approves the proposal to execute."""
    portfolio_id: str
    initial_amount: float = Field(1_000_000, gt=0)
    holdings: list[dict[str, Any]]


class ApproveResult(BaseModel):
    success: bool
    portfolio_id: str
    positions_created: int
    trades_created: int
    total_value: float
    cash: float
    total_invested: float
    total_trading_cost: float
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _dt_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_iso()
    return dt.isoformat() + "Z"


async def _get_portfolio_by_id(session: AsyncSession, portfolio_id: str) -> Portfolio:
    """Fetch a portfolio by its ID or raise 404."""
    result = await session.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(
            status_code=404,
            detail=f"Portfolio {portfolio_id} not found.",
        )
    return portfolio


async def _get_portfolio(session: AsyncSession, portfolio_id: str | None = None) -> Portfolio:
    """Return a portfolio by ID, or fall back to the first active portfolio."""
    if portfolio_id:
        return await _get_portfolio_by_id(session, portfolio_id)
    # Fallback: first active portfolio (backward compat)
    result = await session.execute(
        select(Portfolio).where(Portfolio.status == PortfolioStatus.ACTIVE).limit(1)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(
            status_code=404,
            detail="No active portfolio found. Call POST /api/portfolio/initialize to create one.",
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


@router.get("/list", response_model=list[PortfolioListItem])
async def list_portfolios(session: AsyncSession = Depends(get_session)):
    """Return all portfolios with summary info."""
    result = await session.execute(
        select(Portfolio).order_by(Portfolio.created_at.desc())
    )
    portfolios = result.scalars().all()

    items: list[PortfolioListItem] = []
    for p in portfolios:
        count_result = await session.execute(
            select(func.count())
            .select_from(PositionModel)
            .where(PositionModel.portfolio_id == p.id)
        )
        positions_count = count_result.scalar() or 0

        items.append(PortfolioListItem(
            id=p.id,
            name=p.name,
            total_value=p.total_value or 0,
            cash=p.cash or 0,
            invested=p.invested or 0,
            pnl=p.pnl or 0,
            pnl_pct=p.pnl_pct or 0,
            status=p.status.value if hasattr(p.status, "value") else str(p.status),
            positions_count=positions_count,
            created_at=_dt_iso(p.created_at),
        ))

    return items


@router.get("/", response_model=PortfolioOverview)
async def get_portfolio_overview(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get portfolio overview including total value, P&L, and allocation summary."""
    portfolio = await _get_portfolio(session, portfolio_id)

    count_result = await session.execute(
        select(func.count())
        .select_from(PositionModel)
        .where(PositionModel.portfolio_id == portfolio.id)
    )
    positions_count = count_result.scalar() or 0

    result = PortfolioOverview(
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
    logger.info(
        "Overview for portfolio %s: invested=%.2f, positions=%d, total_value=%.2f",
        portfolio.id, result.invested, result.positions_count, result.total_value,
    )
    return result


@router.get("/positions", response_model=list[Position])
async def list_positions(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """List all current portfolio positions."""
    portfolio = await _get_portfolio(session, portfolio_id)

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
async def get_preferences(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get current portfolio preferences."""
    portfolio = await _get_portfolio(session, portfolio_id)
    prefs = portfolio.preferences or {}

    # Build with defaults for any missing fields (backward compat with old data)
    try:
        return PortfolioPreferences(**prefs)
    except Exception:
        # If stored prefs don't match new schema, return defaults
        return PortfolioPreferences()


@router.put("/preferences", response_model=PortfolioPreferences)
async def update_preferences(
    payload: PortfolioPreferences,
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Update portfolio preferences (risk appetite, goals, allocation, rules)."""
    portfolio = await _get_portfolio(session, portfolio_id)
    data = payload.model_dump()
    # Serialize allocation_targets as list of dicts for JSON storage
    data["allocation_targets"] = [t.model_dump() if hasattr(t, 'model_dump') else t for t in payload.allocation_targets]
    portfolio.preferences = data
    await session.commit()
    return payload


@router.get("/risk", response_model=RiskMetrics)
async def get_risk_metrics(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get portfolio risk metrics (VaR, volatility, concentration, etc.)."""
    portfolio = await _get_portfolio(session, portfolio_id)

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
async def trigger_rebalance(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Trigger a rebalancing check against target allocation."""
    portfolio = await _get_portfolio(session, portfolio_id)
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
async def get_performance(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get portfolio performance metrics (returns, sharpe, drawdown, etc.)."""
    portfolio = await _get_portfolio(session, portfolio_id)

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
async def get_allocation(
    portfolio_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """Get current vs target allocation breakdown by asset class, sector, geography."""
    portfolio = await _get_portfolio(session, portfolio_id)
    prefs = portfolio.preferences or {}
    # Read from new allocation_targets format, fall back to legacy target_allocation
    alloc_targets = prefs.get("allocation_targets")
    if alloc_targets and isinstance(alloc_targets, list):
        target_alloc = {t["asset_class"]: t["target_weight"] / 100.0 for t in alloc_targets}
    else:
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


# ---------------------------------------------------------------------------
# Portfolio Initialization / Proposal / Approval
# ---------------------------------------------------------------------------


@router.post("/initialize", response_model=InitializeResult)
async def initialize_portfolio(
    payload: InitializeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a new portfolio shell (or reinitialize an existing one).

    If portfolio_id is provided, resets that portfolio's cash/values.
    Otherwise creates a new portfolio record. Enforces MAX_PORTFOLIOS limit
    on non-paused portfolios.
    Does NOT generate a proposal -- call POST /generate-proposal next.
    """
    if payload.portfolio_id:
        # Reinitialize existing portfolio
        portfolio = await _get_portfolio_by_id(session, payload.portfolio_id)
        # Delete existing positions for restart
        await session.execute(
            delete(PositionModel).where(PositionModel.portfolio_id == portfolio.id)
        )
        portfolio.name = payload.name
        portfolio.total_value = payload.initial_amount
        portfolio.cash = payload.initial_amount
        portfolio.invested = 0
        portfolio.pnl = 0
        portfolio.pnl_pct = 0
        portfolio.status = PortfolioStatus.ACTIVE
        await session.commit()

        return InitializeResult(
            portfolio_id=portfolio.id,
            name=portfolio.name,
            initial_amount=payload.initial_amount,
            message="Portfolio reinitialized successfully.",
        )

    # Creating a new portfolio -- enforce limit
    count_result = await session.execute(
        select(func.count())
        .select_from(Portfolio)
        .where(Portfolio.status != PortfolioStatus.PAUSED)
    )
    active_count = count_result.scalar() or 0
    if active_count >= MAX_PORTFOLIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum of {MAX_PORTFOLIOS} active portfolios reached. "
                   "Pause or delete an existing portfolio first.",
        )

    portfolio = Portfolio(
        id=str(uuid4()),
        name=payload.name,
        description="AI Hedge Fund Paper Trading Portfolio",
        status=PortfolioStatus.ACTIVE,
        total_value=payload.initial_amount,
        cash=payload.initial_amount,
        invested=0,
        pnl=0,
        pnl_pct=0,
        preferences={},
    )
    session.add(portfolio)
    await session.commit()

    return InitializeResult(
        portfolio_id=portfolio.id,
        name=portfolio.name,
        initial_amount=payload.initial_amount,
        message="Portfolio created successfully. Call POST /generate-proposal to get an allocation proposal.",
    )


@router.post("/generate-proposal", response_model=PortfolioProposal)
async def generate_portfolio_proposal(
    payload: GenerateProposalRequest,
    session: AsyncSession = Depends(get_session),
):
    """Generate an allocation proposal for a given portfolio.

    Reads that portfolio's preferences, fetches latest prices, and generates
    an optimal allocation proposal using core-satellite + risk parity approach.
    Returns the proposal for user review before execution.
    """
    portfolio = await _get_portfolio_by_id(session, payload.portfolio_id)
    preferences = portfolio.preferences or {}
    initial_amount = portfolio.cash or portfolio.total_value or 1_000_000

    # Gather all tickers from the universe
    all_tickers: list[str] = []
    for assets in ASSET_UNIVERSE.values():
        all_tickers.extend(a["ticker"] for a in assets)

    # Fetch latest prices
    prices = await fetch_last_close_prices(all_tickers)

    # Generate proposal
    proposal = generate_proposal(initial_amount, preferences, prices)

    return PortfolioProposal(portfolio_id=portfolio.id, **proposal)


@router.post("/propose", response_model=PortfolioProposal)
async def propose_portfolio(
    payload: TweakRequest,
    session: AsyncSession = Depends(get_session),
):
    """Recalculate proposal after user tweaks holdings.

    Accepts a modified holdings list and recalculates weights, costs, and totals.
    """
    portfolio = await _get_portfolio_by_id(session, payload.portfolio_id)

    # Get prices for all tickers in the tweaked holdings
    tickers = [h["ticker"] for h in payload.holdings]
    prices = await fetch_last_close_prices(tickers)

    holdings_out: list[dict[str, Any]] = []
    trades_out: list[dict[str, Any]] = []
    total_invested = 0.0
    total_trading_cost = 0.0

    for h in payload.holdings:
        ticker = h["ticker"]
        quantity = h.get("quantity", 0)
        instrument = h.get("instrument", "etf")
        price = prices.get(ticker) or h.get("price", 0)

        if quantity <= 0 or price <= 0:
            continue

        cost_info = compute_trading_cost(ticker, quantity, price, instrument)
        actual_notional = quantity * price
        fill_price = cost_info["fill_price"]

        holding = {
            "ticker": ticker,
            "name": h.get("name", ticker),
            "asset_class": h.get("asset_class", "equities"),
            "sub_class": h.get("sub_class", ""),
            "instrument": instrument,
            "direction": "long",
            "quantity": quantity,
            "price": round(price, 4),
            "fill_price": fill_price,
            "market_value": round(actual_notional, 2),
            "weight": 0,
            "trading_cost": cost_info,
        }
        holdings_out.append(holding)

        trades_out.append({
            "ticker": ticker,
            "name": h.get("name", ticker),
            "direction": "buy",
            "instrument": instrument,
            "quantity": quantity,
            "price": round(price, 4),
            "fill_price": fill_price,
            "notional": round(actual_notional, 2),
            **cost_info,
        })

        total_invested += quantity * fill_price
        total_trading_cost += cost_info["total_cost"]

    cash = payload.initial_amount - total_invested - total_trading_cost
    if cash < 0:
        cash = 0
    total_value = total_invested + cash

    for h in holdings_out:
        h["weight"] = round(h["market_value"] / total_value * 100, 2) if total_value > 0 else 0

    # Build allocation summary
    class_summary: dict[str, float] = {}
    for h in holdings_out:
        ac = h["asset_class"]
        class_summary[ac] = class_summary.get(ac, 0) + h["market_value"]
    class_summary["cash"] = cash
    allocation_summary = {
        k: round(v / total_value * 100, 2) if total_value > 0 else 0
        for k, v in class_summary.items()
    }

    return PortfolioProposal(
        portfolio_id=portfolio.id,
        initial_amount=payload.initial_amount,
        total_value=round(total_value, 2),
        total_invested=round(total_invested, 2),
        cash=round(cash, 2),
        total_trading_cost=round(total_trading_cost, 2),
        num_positions=len(holdings_out),
        holdings=holdings_out,
        trades=trades_out,
        allocation_summary=allocation_summary,
        risk_appetite="custom",
        strategy_notes=["User-modified allocation"],
    )


_INSTRUMENT_MAP = {
    "etf": InstrumentType.ETF,
    "equity": InstrumentType.EQUITY,
    "crypto": InstrumentType.CRYPTO,
    "bond": InstrumentType.BOND,
    "option": InstrumentType.OPTION,
    "future": InstrumentType.FUTURE,
}


@router.post("/approve", response_model=ApproveResult)
async def approve_portfolio(
    payload: ApproveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Approve and execute the proposed portfolio.

    Creates/resets the portfolio, creates position records at fill prices,
    and creates trade records with trading cost metadata.
    Requires portfolio_id -- only modifies that specific portfolio.
    """
    portfolio = await _get_portfolio_by_id(session, payload.portfolio_id)

    # Delete existing positions for this portfolio
    await session.execute(
        delete(PositionModel).where(PositionModel.portfolio_id == portfolio.id)
    )

    total_invested = 0.0
    total_trading_cost = 0.0
    positions_created = 0
    trades_created = 0

    for h in payload.holdings:
        ticker = h.get("ticker", "")
        quantity = h.get("quantity", 0)
        price = h.get("price", 0)
        fill_price = h.get("fill_price", price)
        market_value = h.get("market_value", quantity * price)
        instrument = h.get("instrument", "etf")
        asset_class = h.get("asset_class", "equities")
        cost = h.get("trading_cost", {})
        trade_cost = cost.get("total_cost", 0)

        if quantity <= 0:
            continue

        # Create Trade record
        trade_id = str(uuid4())
        inst_type = _INSTRUMENT_MAP.get(instrument, InstrumentType.ETF)
        trade = Trade(
            id=trade_id,
            tickers=[ticker],
            direction=TradeDirection.LONG,
            instrument_type=inst_type,
            status=TradeStatus.CLOSED,
            quantity=quantity,
            entry_price=fill_price,
            current_price=price,
            notional_value=market_value,
            pnl=0,
            pnl_pct=0,
            entry_time=datetime.utcnow(),
            metadata_={
                "symbol": ticker,
                "direction_label": "buy",
                "fill_price": fill_price,
                "fill_quantity": quantity,
                "limit_price": price,
                "notes": f"Portfolio initialization — {h.get('name', ticker)}",
                "trading_cost": cost,
                "slippage_pct": cost.get("slippage_pct", 0),
                "spread_cost": cost.get("spread_cost", 0),
                "impact_cost": cost.get("impact_cost", 0),
                "commission": cost.get("commission", 0),
                "total_cost": trade_cost,
                "init_trade": True,
            },
        )
        session.add(trade)
        trades_created += 1

        # Create Position record
        position = PositionModel(
            id=str(uuid4()),
            portfolio_id=portfolio.id,
            trade_id=trade_id,
            ticker=ticker,
            direction="long",
            quantity=quantity,
            avg_entry_price=fill_price,
            current_price=price,
            market_value=market_value,
            pnl=0,
            pnl_pct=0,
            weight=h.get("weight", 0) / 100.0 if h.get("weight", 0) > 1 else h.get("weight", 0),
            asset_class=asset_class,
        )
        session.add(position)
        positions_created += 1

        total_invested += quantity * fill_price
        total_trading_cost += trade_cost

    cash = payload.initial_amount - total_invested - total_trading_cost
    if cash < 0:
        cash = 0
    total_value = total_invested + cash

    # Update portfolio totals
    portfolio.total_value = total_value
    portfolio.cash = cash
    portfolio.invested = total_invested
    portfolio.pnl = 0
    portfolio.pnl_pct = 0

    # Explicit commit so data is visible to subsequent requests immediately.
    # (The get_session cleanup commit runs AFTER the response is sent,
    # which creates a race condition with the frontend redirect.)
    await session.commit()

    logger.info(
        "Portfolio %s approved: %d positions, %d trades, invested=%.2f, cash=%.2f, total=%.2f",
        portfolio.id, positions_created, trades_created, total_invested, cash, total_value,
    )

    # Verify the commit worked by counting positions in a fresh query
    verify_result = await session.execute(
        select(func.count()).select_from(PositionModel).where(
            PositionModel.portfolio_id == portfolio.id
        )
    )
    verified_count = verify_result.scalar() or 0
    logger.info(
        "Post-commit verification: %d positions found for portfolio %s",
        verified_count, portfolio.id,
    )

    return ApproveResult(
        success=True,
        portfolio_id=portfolio.id,
        positions_created=positions_created,
        trades_created=trades_created,
        total_value=round(total_value, 2),
        cash=round(cash, 2),
        total_invested=round(total_invested, 2),
        total_trading_cost=round(total_trading_cost, 2),
        message=f"Portfolio initialized with {positions_created} positions. "
                f"Trading costs: ${total_trading_cost:,.2f}",
    )
