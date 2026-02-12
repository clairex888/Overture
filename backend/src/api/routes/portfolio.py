"""
Portfolio API routes.

Provides portfolio overview, positions, risk metrics, performance analytics,
allocation breakdowns, and rebalancing triggers.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
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
# In-memory store (swap for DB later)
# ---------------------------------------------------------------------------

_positions_store: dict[str, dict[str, Any]] = {}

_portfolio_state: dict[str, Any] = {
    "total_value": 1_000_000.00,
    "cash": 350_000.00,
    "invested": 650_000.00,
    "total_pnl": 23_450.00,
    "total_pnl_pct": 0.0235,
    "day_pnl": 1_280.00,
    "day_pnl_pct": 0.00128,
    "last_updated": datetime.utcnow().isoformat() + "Z",
}

_preferences: dict[str, Any] = PortfolioPreferences().model_dump()

# Seed a few sample positions for the prototype
_seed_positions = [
    {
        "id": str(uuid4()),
        "symbol": "AAPL",
        "direction": "long",
        "quantity": 150,
        "avg_entry_price": 178.50,
        "current_price": 185.20,
        "market_value": 27_780.00,
        "unrealized_pnl": 1_005.00,
        "unrealized_pnl_pct": 0.0375,
        "weight": 0.0428,
        "asset_class": "equities",
        "opened_at": "2025-12-15T10:30:00Z",
    },
    {
        "id": str(uuid4()),
        "symbol": "BTC-USD",
        "direction": "long",
        "quantity": 1.5,
        "avg_entry_price": 62_000.00,
        "current_price": 67_500.00,
        "market_value": 101_250.00,
        "unrealized_pnl": 8_250.00,
        "unrealized_pnl_pct": 0.0887,
        "weight": 0.1558,
        "asset_class": "crypto",
        "opened_at": "2026-01-05T14:00:00Z",
    },
    {
        "id": str(uuid4()),
        "symbol": "TLT",
        "direction": "long",
        "quantity": 500,
        "avg_entry_price": 92.30,
        "current_price": 90.10,
        "market_value": 45_050.00,
        "unrealized_pnl": -1_100.00,
        "unrealized_pnl_pct": -0.0238,
        "weight": 0.0693,
        "asset_class": "fixed_income",
        "opened_at": "2026-01-20T09:15:00Z",
    },
]
for pos in _seed_positions:
    _positions_store[pos["id"]] = pos


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=PortfolioOverview)
async def get_portfolio_overview():
    """Get portfolio overview including total value, P&L, and allocation summary."""
    state = _portfolio_state.copy()
    state["positions_count"] = len(_positions_store)
    state["last_updated"] = _now_iso()
    return PortfolioOverview(**state)


@router.get("/positions", response_model=list[Position])
async def list_positions():
    """List all current portfolio positions."""
    positions = sorted(
        _positions_store.values(),
        key=lambda p: abs(p["market_value"]),
        reverse=True,
    )
    return [Position(**p) for p in positions]


@router.get("/positions/{position_id}", response_model=Position)
async def get_position(position_id: str):
    """Get details for a specific position."""
    pos = _positions_store.get(position_id)
    if not pos:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    return Position(**pos)


@router.put("/preferences", response_model=PortfolioPreferences)
async def update_preferences(payload: PortfolioPreferences):
    """Update portfolio preferences (risk appetite, goals, views)."""
    global _preferences
    _preferences = payload.model_dump()
    return PortfolioPreferences(**_preferences)


@router.get("/risk", response_model=RiskMetrics)
async def get_risk_metrics():
    """Get portfolio risk metrics (VaR, volatility, concentration, etc.).

    In production these are calculated by the RiskManagementAgent.  The
    prototype returns representative placeholder values.
    """
    return RiskMetrics(
        var_95=15_200.00,
        var_99=24_800.00,
        portfolio_volatility=0.142,
        portfolio_beta=1.05,
        sharpe_ratio=1.32,
        max_drawdown=0.087,
        concentration_top5=0.62,
        sector_concentration={
            "technology": 0.35,
            "crypto": 0.18,
            "fixed_income": 0.15,
            "healthcare": 0.12,
            "energy": 0.08,
            "other": 0.12,
        },
        correlation_risk="moderate",
        last_calculated=_now_iso(),
    )


@router.post("/rebalance", response_model=RebalanceResult)
async def trigger_rebalance():
    """Trigger a rebalancing check against target allocation.

    In production this invokes the PortfolioManagementAgent.  The prototype
    returns a representative placeholder result.
    """
    return RebalanceResult(
        rebalance_needed=True,
        drift_detected={
            "crypto": 0.038,
            "fixed_income": -0.025,
            "equities": -0.013,
        },
        proposed_trades=[
            {"action": "reduce", "symbol": "BTC-USD", "amount_usd": 12_000},
            {"action": "increase", "symbol": "TLT", "amount_usd": 8_000},
            {"action": "increase", "symbol": "SPY", "amount_usd": 4_000},
        ],
        estimated_cost=45.00,
        triggered_at=_now_iso(),
    )


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance():
    """Get portfolio performance metrics (returns, sharpe, drawdown, etc.)."""
    return PerformanceMetrics(
        total_return=23_450.00,
        total_return_pct=0.0235,
        annualized_return_pct=0.142,
        sharpe_ratio=1.32,
        sortino_ratio=1.78,
        max_drawdown=0.087,
        max_drawdown_duration_days=12,
        win_rate=0.62,
        avg_win=3_200.00,
        avg_loss=-1_850.00,
        profit_factor=1.68,
        calmar_ratio=1.63,
        period_start="2025-12-01T00:00:00Z",
        period_end=_now_iso(),
    )


@router.get("/allocation", response_model=AllocationBreakdown)
async def get_allocation():
    """Get current vs target allocation breakdown by asset class, sector, and geography."""
    return AllocationBreakdown(
        by_asset_class=[
            AllocationEntry(category="equities", current_weight=0.42, target_weight=0.45, drift=-0.03),
            AllocationEntry(category="fixed_income", current_weight=0.15, target_weight=0.20, drift=-0.05),
            AllocationEntry(category="crypto", current_weight=0.18, target_weight=0.15, drift=0.03),
            AllocationEntry(category="commodities", current_weight=0.05, target_weight=0.05, drift=0.00),
            AllocationEntry(category="cash", current_weight=0.20, target_weight=0.15, drift=0.05),
        ],
        by_sector=[
            AllocationEntry(category="technology", current_weight=0.35, target_weight=0.30, drift=0.05),
            AllocationEntry(category="healthcare", current_weight=0.12, target_weight=0.15, drift=-0.03),
            AllocationEntry(category="energy", current_weight=0.08, target_weight=0.10, drift=-0.02),
            AllocationEntry(category="financials", current_weight=0.10, target_weight=0.10, drift=0.00),
            AllocationEntry(category="other", current_weight=0.35, target_weight=0.35, drift=0.00),
        ],
        by_geography=[
            AllocationEntry(category="us", current_weight=0.70, target_weight=0.65, drift=0.05),
            AllocationEntry(category="europe", current_weight=0.12, target_weight=0.15, drift=-0.03),
            AllocationEntry(category="asia", current_weight=0.10, target_weight=0.12, drift=-0.02),
            AllocationEntry(category="emerging", current_weight=0.08, target_weight=0.08, drift=0.00),
        ],
        last_updated=_now_iso(),
    )
