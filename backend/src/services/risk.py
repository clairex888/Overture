"""Risk calculation service for the Overture AI hedge fund system.

Provides portfolio and position-level risk analytics including
Value at Risk (VaR), portfolio metrics, stress testing, and
risk limit monitoring. Uses historical market data via yfinance
and numpy/pandas for quantitative calculations.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PortfolioRiskMetrics:
    """Comprehensive risk metrics for a portfolio."""

    total_value: float
    daily_var: float
    volatility: float
    beta: float
    sharpe: float
    max_drawdown: float
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    concentration_hhi: float = 0.0
    sector_exposure: dict[str, float] = field(default_factory=dict)


@dataclass
class RiskAlert:
    """Alert generated when a risk limit is breached or approached."""

    level: str  # "info", "warning", "critical"
    metric: str
    current_value: float
    limit_value: float
    message: str


@dataclass
class PositionRisk:
    """Risk metrics for an individual position."""

    ticker: str
    quantity: float
    entry_price: float
    current_price: float
    market_value: float
    pnl: float
    pnl_pct: float
    daily_var: float
    volatility: float
    beta: float
    max_drawdown: float
    weight: float = 0.0


@dataclass
class StressTestResult:
    """Result of a stress test scenario."""

    scenario_name: str
    description: str
    portfolio_impact_pct: float
    portfolio_impact_usd: float
    position_impacts: dict[str, float] = field(default_factory=dict)


class RiskService:
    """Service for calculating portfolio and position risk metrics.

    Provides Value at Risk (VaR) calculation via historical simulation,
    comprehensive portfolio analytics, position-level risk assessment,
    stress testing against predefined scenarios, and risk limit
    monitoring with alerts.
    """

    TRADING_DAYS_PER_YEAR = 252
    RISK_FREE_RATE = 0.05
    BENCHMARK_TICKER = "SPY"

    # Predefined stress test scenarios: {ticker_type: shock_pct}
    STRESS_SCENARIOS: dict[str, dict[str, Any]] = {
        "market_crash": {
            "description": "Broad market decline of 20%",
            "equity_shock": -0.20,
            "bond_shock": 0.05,
            "commodity_shock": -0.15,
        },
        "rate_hike": {
            "description": "Sudden interest rate increase of 100bps",
            "equity_shock": -0.08,
            "bond_shock": -0.10,
            "commodity_shock": -0.05,
        },
        "sector_rotation": {
            "description": "Growth-to-value rotation with tech sell-off",
            "tech_shock": -0.15,
            "healthcare_shock": -0.05,
            "financial_shock": 0.05,
            "energy_shock": 0.10,
            "default_shock": -0.03,
        },
        "black_swan": {
            "description": "Extreme tail event with 35% market decline",
            "equity_shock": -0.35,
            "bond_shock": 0.10,
            "commodity_shock": -0.25,
        },
        "mild_correction": {
            "description": "Mild market correction of 10%",
            "equity_shock": -0.10,
            "bond_shock": 0.02,
            "commodity_shock": -0.08,
        },
    }

    def __init__(self) -> None:
        self._data_cache: dict[str, pd.DataFrame] = {}
        self._info_cache: dict[str, dict[str, Any]] = {}

    async def _fetch_returns(
        self,
        ticker: str,
        lookback_days: int = 252,
    ) -> pd.Series:
        """Fetch historical daily returns for a ticker.

        Args:
            ticker: Stock ticker symbol.
            lookback_days: Number of calendar days of history.

        Returns:
            Series of daily returns indexed by date.
        """
        cache_key = f"{ticker}_{lookback_days}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]["Close"].pct_change().dropna()

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        def _download() -> pd.DataFrame:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            return data

        data = await asyncio.to_thread(_download)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        self._data_cache[cache_key] = data
        return data["Close"].pct_change().dropna()

    async def _get_ticker_info(self, ticker: str) -> dict[str, Any]:
        """Fetch and cache ticker info."""
        if ticker in self._info_cache:
            return self._info_cache[ticker]

        def _fetch() -> dict[str, Any]:
            try:
                t = yf.Ticker(ticker)
                return dict(t.info)
            except Exception:
                return {}

        info = await asyncio.to_thread(_fetch)
        self._info_cache[ticker] = info
        return info

    # ------------------------------------------------------------------
    # Value at Risk
    # ------------------------------------------------------------------

    async def calculate_var(
        self,
        positions: list[dict[str, Any]],
        confidence: float = 0.95,
        horizon_days: int = 1,
        lookback_days: int = 504,
    ) -> dict[str, Any]:
        """Calculate portfolio Value at Risk using historical simulation.

        Constructs a portfolio return series from position weights and
        individual asset returns, then computes VaR at the specified
        confidence level.

        Args:
            positions: List of position dicts with keys ``ticker``,
                ``market_value``.
            confidence: Confidence level (e.g. 0.95 for 95% VaR).
            horizon_days: Risk horizon in trading days.
            lookback_days: Calendar days of historical data.

        Returns:
            Dict with ``var_pct``, ``var_usd``, ``cvar_pct``, ``cvar_usd``,
            and ``confidence``.
        """
        logger.info(
            "calculating_var",
            positions=len(positions),
            confidence=confidence,
            horizon=horizon_days,
        )

        if not positions:
            return {
                "var_pct": 0.0,
                "var_usd": 0.0,
                "cvar_pct": 0.0,
                "cvar_usd": 0.0,
                "confidence": confidence,
            }

        # Calculate total portfolio value
        total_value = sum(p.get("market_value", 0) for p in positions)
        if total_value <= 0:
            return {
                "var_pct": 0.0,
                "var_usd": 0.0,
                "cvar_pct": 0.0,
                "cvar_usd": 0.0,
                "confidence": confidence,
            }

        # Fetch returns for all positions concurrently
        tickers = [p["ticker"] for p in positions]
        weights = [p.get("market_value", 0) / total_value for p in positions]

        returns_tasks = [self._fetch_returns(t, lookback_days) for t in tickers]
        all_returns = await asyncio.gather(*returns_tasks, return_exceptions=True)

        # Build aligned returns DataFrame
        returns_dict: dict[str, pd.Series] = {}
        for ticker, ret in zip(tickers, all_returns):
            if isinstance(ret, Exception):
                logger.warning("returns_fetch_failed", ticker=ticker, error=str(ret))
                continue
            returns_dict[ticker] = ret

        if not returns_dict:
            return {
                "var_pct": 0.0,
                "var_usd": 0.0,
                "cvar_pct": 0.0,
                "cvar_usd": 0.0,
                "confidence": confidence,
            }

        returns_df = pd.DataFrame(returns_dict).dropna()

        if returns_df.empty:
            return {
                "var_pct": 0.0,
                "var_usd": 0.0,
                "cvar_pct": 0.0,
                "cvar_usd": 0.0,
                "confidence": confidence,
            }

        # Align weights with available tickers
        aligned_weights = []
        for ticker in returns_df.columns:
            idx = tickers.index(ticker)
            aligned_weights.append(weights[idx])

        weight_arr = np.array(aligned_weights)
        weight_arr = weight_arr / weight_arr.sum()  # Renormalize

        # Portfolio returns (weighted sum)
        portfolio_returns = returns_df.values @ weight_arr

        # Scale to the requested horizon
        if horizon_days > 1:
            portfolio_returns = portfolio_returns * np.sqrt(horizon_days)

        # Historical VaR (loss is positive)
        var_pct = float(-np.percentile(portfolio_returns, (1 - confidence) * 100))
        var_usd = var_pct * total_value

        # Conditional VaR (Expected Shortfall)
        threshold = np.percentile(portfolio_returns, (1 - confidence) * 100)
        tail_returns = portfolio_returns[portfolio_returns <= threshold]
        cvar_pct = float(-tail_returns.mean()) if len(tail_returns) > 0 else var_pct
        cvar_usd = cvar_pct * total_value

        result = {
            "var_pct": round(var_pct, 6),
            "var_usd": round(var_usd, 2),
            "cvar_pct": round(cvar_pct, 6),
            "cvar_usd": round(cvar_usd, 2),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "total_value": round(total_value, 2),
        }

        logger.info("var_calculated", var_pct=f"{var_pct:.4%}", var_usd=f"${var_usd:,.2f}")
        return result

    # ------------------------------------------------------------------
    # Portfolio metrics
    # ------------------------------------------------------------------

    async def calculate_portfolio_metrics(
        self,
        positions: list[dict[str, Any]],
        lookback_days: int = 504,
    ) -> PortfolioRiskMetrics:
        """Calculate comprehensive portfolio risk metrics.

        Computes volatility, beta, Sharpe ratio, max drawdown,
        correlation matrix, concentration (HHI), and sector exposure.

        Args:
            positions: List of position dicts with keys ``ticker``,
                ``market_value``, and optionally ``sector``.
            lookback_days: Calendar days of historical data.

        Returns:
            PortfolioRiskMetrics with all computed metrics.
        """
        logger.info("calculating_portfolio_metrics", positions=len(positions))

        if not positions:
            return PortfolioRiskMetrics(
                total_value=0.0,
                daily_var=0.0,
                volatility=0.0,
                beta=0.0,
                sharpe=0.0,
                max_drawdown=0.0,
            )

        total_value = sum(p.get("market_value", 0) for p in positions)
        tickers = [p["ticker"] for p in positions]
        weights = np.array([p.get("market_value", 0) / max(total_value, 1) for p in positions])

        # Fetch returns
        returns_tasks = [self._fetch_returns(t, lookback_days) for t in tickers]
        benchmark_task = self._fetch_returns(self.BENCHMARK_TICKER, lookback_days)
        all_results = await asyncio.gather(*returns_tasks, benchmark_task, return_exceptions=True)

        asset_returns = all_results[:-1]
        benchmark_returns = all_results[-1]

        # Build returns DataFrame
        returns_dict: dict[str, pd.Series] = {}
        for ticker, ret in zip(tickers, asset_returns):
            if not isinstance(ret, Exception):
                returns_dict[ticker] = ret

        if not returns_dict:
            return PortfolioRiskMetrics(
                total_value=total_value,
                daily_var=0.0,
                volatility=0.0,
                beta=0.0,
                sharpe=0.0,
                max_drawdown=0.0,
            )

        returns_df = pd.DataFrame(returns_dict).dropna()

        # Align weights
        aligned_weights = []
        for ticker in returns_df.columns:
            idx = tickers.index(ticker)
            aligned_weights.append(weights[idx])
        w = np.array(aligned_weights)
        w = w / w.sum()

        # Portfolio returns
        port_returns = pd.Series(returns_df.values @ w, index=returns_df.index)

        # Volatility (annualized)
        daily_vol = float(port_returns.std())
        annual_vol = daily_vol * np.sqrt(self.TRADING_DAYS_PER_YEAR)

        # Sharpe ratio
        avg_daily = port_returns.mean()
        excess = avg_daily - (self.RISK_FREE_RATE / self.TRADING_DAYS_PER_YEAR)
        sharpe = float(excess / daily_vol * np.sqrt(self.TRADING_DAYS_PER_YEAR)) if daily_vol > 0 else 0.0

        # Beta against benchmark
        beta = 0.0
        if not isinstance(benchmark_returns, Exception):
            aligned = pd.concat([port_returns, benchmark_returns], axis=1).dropna()
            if len(aligned) > 10:
                aligned.columns = ["portfolio", "benchmark"]
                cov = aligned["portfolio"].cov(aligned["benchmark"])
                var_bench = aligned["benchmark"].var()
                beta = float(cov / var_bench) if var_bench > 0 else 0.0

        # Max drawdown
        equity = (1 + port_returns).cumprod()
        running_max = equity.cummax()
        drawdown = (equity - running_max) / running_max
        max_drawdown = float(drawdown.min())

        # VaR (95%, 1-day)
        daily_var = float(-np.percentile(port_returns, 5)) * total_value

        # Correlation matrix
        corr_df = returns_df.corr()
        correlation_matrix: dict[str, dict[str, float]] = {}
        for col in corr_df.columns:
            correlation_matrix[col] = {
                row: round(float(corr_df.loc[row, col]), 4) for row in corr_df.index
            }

        # Concentration (Herfindahl-Hirschman Index)
        hhi = float(np.sum(w ** 2))

        # Sector exposure
        sector_exposure: dict[str, float] = {}
        for pos, weight in zip(positions, weights):
            sector = pos.get("sector", "Unknown")
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + float(weight)

        metrics = PortfolioRiskMetrics(
            total_value=round(total_value, 2),
            daily_var=round(daily_var, 2),
            volatility=round(annual_vol, 4),
            beta=round(beta, 4),
            sharpe=round(sharpe, 4),
            max_drawdown=round(max_drawdown, 4),
            correlation_matrix=correlation_matrix,
            concentration_hhi=round(hhi, 4),
            sector_exposure={k: round(v, 4) for k, v in sector_exposure.items()},
        )

        logger.info(
            "portfolio_metrics_calculated",
            volatility=f"{annual_vol:.2%}",
            beta=f"{beta:.2f}",
            sharpe=f"{sharpe:.2f}",
        )
        return metrics

    # ------------------------------------------------------------------
    # Position risk
    # ------------------------------------------------------------------

    async def calculate_position_risk(
        self,
        ticker: str,
        quantity: float,
        entry_price: float,
        portfolio_value: float = 0.0,
        lookback_days: int = 504,
    ) -> PositionRisk:
        """Calculate risk metrics for a single position.

        Args:
            ticker: Stock ticker symbol.
            quantity: Number of shares held.
            entry_price: Average entry price per share.
            portfolio_value: Total portfolio value for weight calculation.
            lookback_days: Calendar days of historical data.

        Returns:
            PositionRisk with position-level risk metrics.
        """
        logger.info("calculating_position_risk", ticker=ticker, quantity=quantity)

        # Fetch current price
        info = await self._get_ticker_info(ticker)
        current_price = info.get("currentPrice") or info.get("previousClose") or entry_price

        market_value = quantity * current_price
        pnl = (current_price - entry_price) * quantity
        pnl_pct = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0.0
        weight = market_value / portfolio_value if portfolio_value > 0 else 1.0

        # Fetch returns
        returns = await self._fetch_returns(ticker, lookback_days)
        daily_vol = float(returns.std()) if not returns.empty else 0.0
        annual_vol = daily_vol * np.sqrt(self.TRADING_DAYS_PER_YEAR)

        # VaR (95%, 1-day)
        daily_var = float(-np.percentile(returns, 5)) * market_value if not returns.empty else 0.0

        # Beta
        beta = 0.0
        try:
            bench_returns = await self._fetch_returns(self.BENCHMARK_TICKER, lookback_days)
            aligned = pd.concat([returns, bench_returns], axis=1).dropna()
            if len(aligned) > 10:
                aligned.columns = ["asset", "benchmark"]
                cov = aligned["asset"].cov(aligned["benchmark"])
                var_bench = aligned["benchmark"].var()
                beta = float(cov / var_bench) if var_bench > 0 else 0.0
        except Exception:
            pass

        # Max drawdown
        if not returns.empty:
            equity = (1 + returns).cumprod()
            running_max = equity.cummax()
            drawdown = (equity - running_max) / running_max
            max_dd = float(drawdown.min())
        else:
            max_dd = 0.0

        return PositionRisk(
            ticker=ticker,
            quantity=quantity,
            entry_price=round(entry_price, 2),
            current_price=round(current_price, 2),
            market_value=round(market_value, 2),
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            daily_var=round(daily_var, 2),
            volatility=round(annual_vol, 4),
            beta=round(beta, 4),
            max_drawdown=round(max_dd, 4),
            weight=round(weight, 4),
        )

    # ------------------------------------------------------------------
    # Stress testing
    # ------------------------------------------------------------------

    async def stress_test(
        self,
        positions: list[dict[str, Any]],
        scenarios: list[str] | None = None,
    ) -> list[StressTestResult]:
        """Run stress tests against predefined scenarios.

        Each scenario applies asset-class or sector-specific shocks
        to estimate the portfolio impact.

        Args:
            positions: List of position dicts with keys ``ticker``,
                ``market_value``, and optionally ``sector``, ``asset_class``.
            scenarios: List of scenario names to run. Uses all
                predefined scenarios if None.

        Returns:
            List of StressTestResult, one per scenario.
        """
        if scenarios is None:
            scenarios = list(self.STRESS_SCENARIOS.keys())

        logger.info("stress_testing", scenarios=scenarios, positions=len(positions))

        total_value = sum(p.get("market_value", 0) for p in positions)
        if total_value <= 0:
            return []

        # Fetch sector info for each position if not provided
        for pos in positions:
            if "sector" not in pos:
                try:
                    info = await self._get_ticker_info(pos["ticker"])
                    pos["sector"] = info.get("sector", "Unknown")
                    pos["asset_class"] = info.get("quoteType", "equity").lower()
                except Exception:
                    pos["sector"] = "Unknown"
                    pos["asset_class"] = "equity"

        results: list[StressTestResult] = []

        for scenario_name in scenarios:
            scenario = self.STRESS_SCENARIOS.get(scenario_name)
            if scenario is None:
                logger.warning("unknown_scenario", scenario=scenario_name)
                continue

            description = scenario.get("description", scenario_name)
            position_impacts: dict[str, float] = {}
            total_impact = 0.0

            for pos in positions:
                ticker = pos["ticker"]
                mv = pos.get("market_value", 0)
                sector = pos.get("sector", "Unknown").lower()
                asset_class = pos.get("asset_class", "equity").lower()

                # Determine the shock for this position
                shock = self._get_scenario_shock(scenario, sector, asset_class)
                impact = mv * shock
                position_impacts[ticker] = round(impact, 2)
                total_impact += impact

            impact_pct = total_impact / total_value * 100 if total_value > 0 else 0.0

            results.append(
                StressTestResult(
                    scenario_name=scenario_name,
                    description=description,
                    portfolio_impact_pct=round(impact_pct, 2),
                    portfolio_impact_usd=round(total_impact, 2),
                    position_impacts=position_impacts,
                )
            )

        logger.info("stress_test_complete", scenarios_run=len(results))
        return results

    @staticmethod
    def _get_scenario_shock(
        scenario: dict[str, Any],
        sector: str,
        asset_class: str,
    ) -> float:
        """Determine the shock percentage for a position within a scenario.

        Looks for sector-specific shocks first, then asset-class shocks,
        then falls back to equity shock or default.
        """
        # Check for sector-specific shock
        sector_key = f"{sector.split()[0].lower()}_shock" if sector else ""
        if sector_key in scenario:
            return scenario[sector_key]

        # Check for asset-class shock
        asset_key = f"{asset_class}_shock"
        if asset_key in scenario:
            return scenario[asset_key]

        # Fallback hierarchy
        if "equity_shock" in scenario:
            return scenario["equity_shock"]
        if "default_shock" in scenario:
            return scenario["default_shock"]

        return -0.10  # Conservative default

    # ------------------------------------------------------------------
    # Risk limit checking
    # ------------------------------------------------------------------

    async def check_risk_limits(
        self,
        portfolio: dict[str, Any],
        limits: dict[str, Any] | None = None,
    ) -> list[RiskAlert]:
        """Check portfolio against configured risk limits.

        Default limits are applied if none are provided. Generates
        alerts at info, warning, or critical levels.

        Args:
            portfolio: Dict with keys ``positions`` (list of position
                dicts) and optionally ``total_value``, ``max_drawdown``.
            limits: Dict of limit configurations. Supported keys:
                - ``max_position_weight``: Max single-position weight (fraction).
                - ``max_sector_exposure``: Max sector weight (fraction).
                - ``max_drawdown``: Max allowable drawdown (negative fraction).
                - ``max_var_pct``: Max daily VaR as fraction of portfolio.
                - ``max_correlation``: Max pairwise correlation.
                - ``min_positions``: Minimum number of positions.
                - ``max_concentration_hhi``: Max HHI concentration index.

        Returns:
            List of RiskAlert objects for any breached or approaching limits.
        """
        if limits is None:
            limits = {
                "max_position_weight": 0.20,
                "max_sector_exposure": 0.40,
                "max_drawdown": -0.15,
                "max_var_pct": 0.03,
                "max_correlation": 0.85,
                "min_positions": 5,
                "max_concentration_hhi": 0.25,
            }

        positions = portfolio.get("positions", [])
        alerts: list[RiskAlert] = []

        if not positions:
            alerts.append(
                RiskAlert(
                    level="warning",
                    metric="position_count",
                    current_value=0,
                    limit_value=limits.get("min_positions", 5),
                    message="Portfolio has no positions.",
                )
            )
            return alerts

        total_value = portfolio.get("total_value") or sum(
            p.get("market_value", 0) for p in positions
        )

        # --- Position weight check ---
        max_pos_weight = limits.get("max_position_weight", 0.20)
        for pos in positions:
            mv = pos.get("market_value", 0)
            weight = mv / total_value if total_value > 0 else 0
            if weight > max_pos_weight:
                alerts.append(
                    RiskAlert(
                        level="critical" if weight > max_pos_weight * 1.5 else "warning",
                        metric="position_weight",
                        current_value=round(weight, 4),
                        limit_value=max_pos_weight,
                        message=(
                            f"{pos['ticker']} weight {weight:.1%} exceeds "
                            f"limit of {max_pos_weight:.1%}."
                        ),
                    )
                )
            elif weight > max_pos_weight * 0.8:
                alerts.append(
                    RiskAlert(
                        level="info",
                        metric="position_weight",
                        current_value=round(weight, 4),
                        limit_value=max_pos_weight,
                        message=(
                            f"{pos['ticker']} weight {weight:.1%} approaching "
                            f"limit of {max_pos_weight:.1%}."
                        ),
                    )
                )

        # --- Sector exposure check ---
        max_sector = limits.get("max_sector_exposure", 0.40)
        sector_weights: dict[str, float] = {}
        for pos in positions:
            sector = pos.get("sector", "Unknown")
            mv = pos.get("market_value", 0)
            weight = mv / total_value if total_value > 0 else 0
            sector_weights[sector] = sector_weights.get(sector, 0) + weight

        for sector, sw in sector_weights.items():
            if sw > max_sector:
                alerts.append(
                    RiskAlert(
                        level="warning",
                        metric="sector_exposure",
                        current_value=round(sw, 4),
                        limit_value=max_sector,
                        message=(
                            f"Sector '{sector}' exposure {sw:.1%} exceeds "
                            f"limit of {max_sector:.1%}."
                        ),
                    )
                )

        # --- Min positions check ---
        min_positions = limits.get("min_positions", 5)
        if len(positions) < min_positions:
            alerts.append(
                RiskAlert(
                    level="warning",
                    metric="position_count",
                    current_value=len(positions),
                    limit_value=min_positions,
                    message=(
                        f"Portfolio has {len(positions)} positions, "
                        f"below minimum of {min_positions}."
                    ),
                )
            )

        # --- Concentration (HHI) check ---
        max_hhi = limits.get("max_concentration_hhi", 0.25)
        weights_arr = np.array(
            [p.get("market_value", 0) / max(total_value, 1) for p in positions]
        )
        hhi = float(np.sum(weights_arr ** 2))
        if hhi > max_hhi:
            alerts.append(
                RiskAlert(
                    level="warning",
                    metric="concentration_hhi",
                    current_value=round(hhi, 4),
                    limit_value=max_hhi,
                    message=(
                        f"Portfolio HHI concentration {hhi:.4f} exceeds "
                        f"limit of {max_hhi:.4f}."
                    ),
                )
            )

        # --- Drawdown check ---
        max_dd_limit = limits.get("max_drawdown", -0.15)
        current_dd = portfolio.get("max_drawdown", 0.0)
        if current_dd < max_dd_limit:
            alerts.append(
                RiskAlert(
                    level="critical",
                    metric="max_drawdown",
                    current_value=round(current_dd, 4),
                    limit_value=max_dd_limit,
                    message=(
                        f"Portfolio drawdown {current_dd:.1%} breaches "
                        f"limit of {max_dd_limit:.1%}."
                    ),
                )
            )

        # --- VaR check (requires async calculation) ---
        max_var = limits.get("max_var_pct", 0.03)
        try:
            var_result = await self.calculate_var(positions, confidence=0.95, horizon_days=1)
            var_pct = var_result.get("var_pct", 0.0)
            if var_pct > max_var:
                alerts.append(
                    RiskAlert(
                        level="critical" if var_pct > max_var * 1.5 else "warning",
                        metric="daily_var",
                        current_value=round(var_pct, 6),
                        limit_value=max_var,
                        message=(
                            f"Daily VaR {var_pct:.2%} exceeds limit of {max_var:.2%}."
                        ),
                    )
                )
        except Exception as exc:
            logger.warning("var_check_failed", error=str(exc))

        # Sort alerts by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda a: severity_order.get(a.level, 3))

        logger.info("risk_limits_checked", alerts=len(alerts))
        return alerts
