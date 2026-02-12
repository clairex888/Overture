"""Valuation service for the Overture AI hedge fund system.

Provides fundamental valuation capabilities including discounted cash flow
(DCF) analysis, comparable company analysis, and quick summary valuations.
Uses yfinance for financial data retrieval.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DCFResult:
    """Result container for a discounted cash flow valuation."""

    intrinsic_value: float
    current_price: float
    upside_pct: float
    assumptions: dict[str, Any] = field(default_factory=dict)
    sensitivity: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompValuationResult:
    """Result container for a comparable company valuation."""

    ticker: str
    metrics: dict[str, float] = field(default_factory=dict)
    peer_avg: dict[str, float] = field(default_factory=dict)
    premium_discount: dict[str, float] = field(default_factory=dict)
    assessment: str = ""


class ValuationService:
    """Service for performing fundamental equity valuations.

    Supports DCF valuation with sensitivity analysis, comparable
    company (comps) valuation across multiple multiples, and a
    quick summary view combining both approaches.
    """

    def __init__(self) -> None:
        self._info_cache: dict[str, dict[str, Any]] = {}

    async def _get_ticker_info(self, ticker: str) -> dict[str, Any]:
        """Fetch ticker info from yfinance with caching.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dict of ticker fundamentals and metadata.
        """
        if ticker in self._info_cache:
            return self._info_cache[ticker]

        def _fetch() -> dict[str, Any]:
            t = yf.Ticker(ticker)
            return dict(t.info)

        info = await asyncio.to_thread(_fetch)
        self._info_cache[ticker] = info
        return info

    async def _get_financials(self, ticker: str) -> dict[str, Any]:
        """Fetch cash flow and financial statement data.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dict with cash_flow, income_stmt, and balance_sheet DataFrames.
        """

        def _fetch() -> dict[str, Any]:
            t = yf.Ticker(ticker)
            return {
                "cash_flow": t.cashflow,
                "income_stmt": t.income_stmt,
                "balance_sheet": t.balance_sheet,
            }

        return await asyncio.to_thread(_fetch)

    # ------------------------------------------------------------------
    # DCF Valuation
    # ------------------------------------------------------------------

    async def dcf_valuation(
        self,
        ticker: str,
        growth_rate: float = 0.10,
        discount_rate: float = 0.10,
        terminal_growth: float = 0.03,
        projection_years: int = 5,
    ) -> DCFResult:
        """Perform a discounted cash flow valuation.

        Projects free cash flows forward using the specified growth rate,
        discounts them to present value, and adds a terminal value to
        arrive at an intrinsic per-share value.

        Args:
            ticker: Stock ticker symbol.
            growth_rate: Annual FCF growth rate assumption.
            discount_rate: Weighted average cost of capital (WACC).
            terminal_growth: Perpetuity growth rate for terminal value.
            projection_years: Number of years to project FCF.

        Returns:
            DCFResult with intrinsic value, current price, and upside.
        """
        logger.info(
            "dcf_valuation",
            ticker=ticker,
            growth=growth_rate,
            discount=discount_rate,
            terminal_g=terminal_growth,
            years=projection_years,
        )

        info = await self._get_ticker_info(ticker)
        financials = await self._get_financials(ticker)

        # Extract base free cash flow
        cash_flow = financials["cash_flow"]
        base_fcf = self._extract_base_fcf(cash_flow)

        if base_fcf <= 0:
            logger.warning("negative_fcf", ticker=ticker, fcf=base_fcf)
            # Use operating cash flow as fallback
            base_fcf = self._extract_operating_cf(cash_flow)
            if base_fcf <= 0:
                base_fcf = abs(base_fcf) if base_fcf != 0 else 1_000_000.0

        # Project future free cash flows
        projected_fcf: list[float] = []
        for year in range(1, projection_years + 1):
            fcf = base_fcf * (1 + growth_rate) ** year
            projected_fcf.append(fcf)

        # Discount projected FCFs to present value
        pv_fcfs: list[float] = []
        for year, fcf in enumerate(projected_fcf, start=1):
            pv = fcf / (1 + discount_rate) ** year
            pv_fcfs.append(pv)

        # Terminal value (Gordon Growth Model)
        terminal_fcf = projected_fcf[-1] * (1 + terminal_growth)
        terminal_value = terminal_fcf / (discount_rate - terminal_growth)
        pv_terminal = terminal_value / (1 + discount_rate) ** projection_years

        # Enterprise value = sum of PV of FCFs + PV of terminal value
        enterprise_value = sum(pv_fcfs) + pv_terminal

        # Equity value: EV - net debt
        total_debt = info.get("totalDebt", 0) or 0
        cash_and_equiv = info.get("totalCash", 0) or 0
        net_debt = total_debt - cash_and_equiv
        equity_value = enterprise_value - net_debt

        # Per-share value
        shares_outstanding = info.get("sharesOutstanding", 1) or 1
        intrinsic_per_share = equity_value / shares_outstanding

        current_price = info.get("currentPrice") or info.get("previousClose", 0) or 0
        upside_pct = (
            (intrinsic_per_share - current_price) / current_price * 100
            if current_price > 0
            else 0.0
        )

        # Sensitivity analysis: vary growth and discount rates
        sensitivity = self._compute_sensitivity(
            base_fcf=base_fcf,
            projection_years=projection_years,
            terminal_growth=terminal_growth,
            net_debt=net_debt,
            shares_outstanding=shares_outstanding,
            base_growth=growth_rate,
            base_discount=discount_rate,
        )

        assumptions = {
            "base_fcf": base_fcf,
            "growth_rate": growth_rate,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "projection_years": projection_years,
            "shares_outstanding": shares_outstanding,
            "total_debt": total_debt,
            "cash_and_equivalents": cash_and_equiv,
            "net_debt": net_debt,
            "enterprise_value": enterprise_value,
            "equity_value": equity_value,
            "projected_fcf": projected_fcf,
            "pv_fcfs": pv_fcfs,
            "terminal_value": terminal_value,
            "pv_terminal_value": pv_terminal,
        }

        result = DCFResult(
            intrinsic_value=round(intrinsic_per_share, 2),
            current_price=round(current_price, 2),
            upside_pct=round(upside_pct, 2),
            assumptions=assumptions,
            sensitivity=sensitivity,
        )

        logger.info(
            "dcf_complete",
            ticker=ticker,
            intrinsic=result.intrinsic_value,
            current=result.current_price,
            upside=f"{result.upside_pct:.1f}%",
        )
        return result

    def _extract_base_fcf(self, cash_flow: pd.DataFrame) -> float:
        """Extract the most recent free cash flow from the cash flow statement.

        Tries 'Free Cash Flow' directly, then falls back to computing
        operating cash flow minus capital expenditures.
        """
        if cash_flow is None or cash_flow.empty:
            return 0.0

        # Try direct FCF row
        for label in ["Free Cash Flow", "FreeCashFlow"]:
            if label in cash_flow.index:
                val = cash_flow.loc[label].iloc[0]
                if pd.notna(val):
                    return float(val)

        # Compute from components
        operating_cf = 0.0
        capex = 0.0
        for label in ["Operating Cash Flow", "Total Cash From Operating Activities"]:
            if label in cash_flow.index:
                val = cash_flow.loc[label].iloc[0]
                if pd.notna(val):
                    operating_cf = float(val)
                    break

        for label in ["Capital Expenditure", "Capital Expenditures"]:
            if label in cash_flow.index:
                val = cash_flow.loc[label].iloc[0]
                if pd.notna(val):
                    capex = float(val)
                    break

        return operating_cf + capex  # capex is typically negative

    def _extract_operating_cf(self, cash_flow: pd.DataFrame) -> float:
        """Extract operating cash flow as a fallback metric."""
        if cash_flow is None or cash_flow.empty:
            return 0.0

        for label in ["Operating Cash Flow", "Total Cash From Operating Activities"]:
            if label in cash_flow.index:
                val = cash_flow.loc[label].iloc[0]
                if pd.notna(val):
                    return float(val)
        return 0.0

    def _compute_sensitivity(
        self,
        base_fcf: float,
        projection_years: int,
        terminal_growth: float,
        net_debt: float,
        shares_outstanding: int,
        base_growth: float,
        base_discount: float,
    ) -> dict[str, Any]:
        """Compute a sensitivity table varying growth and discount rates.

        Returns a dict mapping (growth_rate, discount_rate) combinations
        to intrinsic per-share values.
        """
        growth_rates = [
            base_growth - 0.04,
            base_growth - 0.02,
            base_growth,
            base_growth + 0.02,
            base_growth + 0.04,
        ]
        discount_rates = [
            base_discount - 0.02,
            base_discount - 0.01,
            base_discount,
            base_discount + 0.01,
            base_discount + 0.02,
        ]

        table: dict[str, list[float]] = {}
        for gr in growth_rates:
            row_key = f"growth_{gr:.1%}"
            row_vals: list[float] = []
            for dr in discount_rates:
                if dr <= terminal_growth:
                    row_vals.append(float("inf"))
                    continue
                projected = [base_fcf * (1 + gr) ** y for y in range(1, projection_years + 1)]
                pv = sum(fcf / (1 + dr) ** y for y, fcf in enumerate(projected, 1))
                tv = projected[-1] * (1 + terminal_growth) / (dr - terminal_growth)
                pv_tv = tv / (1 + dr) ** projection_years
                ev = pv + pv_tv
                eq = ev - net_debt
                per_share = eq / max(shares_outstanding, 1)
                row_vals.append(round(per_share, 2))
            table[row_key] = row_vals

        return {
            "discount_rates": [f"{dr:.1%}" for dr in discount_rates],
            "values": table,
        }

    # ------------------------------------------------------------------
    # Comparable Company Valuation
    # ------------------------------------------------------------------

    async def comparable_valuation(
        self,
        ticker: str,
        peer_tickers: list[str] | None = None,
        metrics: list[str] | None = None,
    ) -> CompValuationResult:
        """Perform a comparable company (comps) valuation.

        Compares the target ticker's valuation multiples against a
        set of peer companies. Computes premium/discount for each metric.

        Args:
            ticker: Target ticker symbol.
            peer_tickers: List of peer ticker symbols. If None, attempts
                to identify peers from sector/industry.
            metrics: Valuation metrics to compare. Defaults to
                ``["pe_ratio", "ev_ebitda", "ps_ratio", "pb_ratio"]``.

        Returns:
            CompValuationResult with metric comparisons and assessment.
        """
        if metrics is None:
            metrics = ["pe_ratio", "ev_ebitda", "ps_ratio", "pb_ratio"]

        logger.info("comparable_valuation", ticker=ticker, peers=peer_tickers, metrics=metrics)

        # Fetch target info
        target_info = await self._get_ticker_info(ticker)

        # Determine peers if not provided
        if not peer_tickers:
            peer_tickers = self._find_sector_peers(target_info)

        # Fetch peer data concurrently
        peer_infos: dict[str, dict[str, Any]] = {}
        tasks = [self._get_ticker_info(p) for p in peer_tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for p, res in zip(peer_tickers, results):
            if isinstance(res, Exception):
                logger.warning("peer_fetch_failed", peer=p, error=str(res))
                continue
            peer_infos[p] = res

        # Map metric names to yfinance info keys
        metric_map = {
            "pe_ratio": ("trailingPE", "forwardPE"),
            "ev_ebitda": ("enterpriseToEbitda",),
            "ps_ratio": ("priceToSalesTrailing12Months",),
            "pb_ratio": ("priceToBook",),
        }

        target_metrics: dict[str, float] = {}
        peer_avg_metrics: dict[str, float] = {}
        premium_discount: dict[str, float] = {}

        for metric in metrics:
            keys = metric_map.get(metric, ())
            target_val = self._extract_metric(target_info, keys)
            target_metrics[metric] = target_val

            peer_vals = [
                self._extract_metric(pi, keys)
                for pi in peer_infos.values()
            ]
            valid_peer_vals = [v for v in peer_vals if v > 0 and np.isfinite(v)]

            if valid_peer_vals:
                avg = float(np.mean(valid_peer_vals))
                peer_avg_metrics[metric] = round(avg, 2)
                if avg > 0 and target_val > 0:
                    prem = (target_val - avg) / avg * 100
                    premium_discount[metric] = round(prem, 2)
                else:
                    premium_discount[metric] = 0.0
            else:
                peer_avg_metrics[metric] = 0.0
                premium_discount[metric] = 0.0

        # Generate assessment summary
        assessment = self._generate_comp_assessment(
            ticker, target_metrics, peer_avg_metrics, premium_discount
        )

        result = CompValuationResult(
            ticker=ticker,
            metrics=target_metrics,
            peer_avg=peer_avg_metrics,
            premium_discount=premium_discount,
            assessment=assessment,
        )

        logger.info("comps_complete", ticker=ticker, assessment=assessment[:100])
        return result

    @staticmethod
    def _extract_metric(info: dict[str, Any], keys: tuple[str, ...]) -> float:
        """Extract a metric value from ticker info, trying multiple keys."""
        for key in keys:
            val = info.get(key)
            if val is not None and isinstance(val, (int, float)) and np.isfinite(val):
                return round(float(val), 2)
        return 0.0

    @staticmethod
    def _find_sector_peers(info: dict[str, Any]) -> list[str]:
        """Return a default list of sector peers based on sector/industry.

        Falls back to a set of large-cap diversified tickers if
        sector information is unavailable.
        """
        sector = info.get("sector", "")
        sector_map: dict[str, list[str]] = {
            "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
            "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK"],
            "Financial Services": ["JPM", "BAC", "GS", "MS", "WFC"],
            "Financials": ["JPM", "BAC", "GS", "MS", "WFC"],
            "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
            "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST"],
            "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
            "Industrials": ["HON", "UPS", "CAT", "GE", "MMM"],
            "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA"],
            "Basic Materials": ["LIN", "APD", "ECL", "SHW", "DD"],
            "Real Estate": ["AMT", "PLD", "CCI", "SPG", "EQIX"],
            "Utilities": ["NEE", "DUK", "SO", "D", "AEP"],
        }
        return sector_map.get(sector, ["AAPL", "MSFT", "GOOGL", "AMZN", "META"])

    @staticmethod
    def _generate_comp_assessment(
        ticker: str,
        target_metrics: dict[str, float],
        peer_avg: dict[str, float],
        premium_discount: dict[str, float],
    ) -> str:
        """Generate a human-readable assessment from comps analysis."""
        premiums = [v for v in premium_discount.values() if v != 0]
        if not premiums:
            return f"{ticker}: Insufficient data for comparative assessment."

        avg_premium = np.mean(premiums)

        if avg_premium > 20:
            verdict = "significantly overvalued"
        elif avg_premium > 5:
            verdict = "moderately overvalued"
        elif avg_premium > -5:
            verdict = "fairly valued"
        elif avg_premium > -20:
            verdict = "moderately undervalued"
        else:
            verdict = "significantly undervalued"

        details: list[str] = []
        for metric, prem in premium_discount.items():
            if prem > 0:
                details.append(f"{metric}: {prem:+.1f}% premium")
            else:
                details.append(f"{metric}: {prem:+.1f}% discount")

        return (
            f"{ticker} appears {verdict} relative to peers "
            f"(avg premium/discount: {avg_premium:+.1f}%). "
            f"Details: {'; '.join(details)}."
        )

    # ------------------------------------------------------------------
    # Quick Valuation (combined DCF + Comps)
    # ------------------------------------------------------------------

    async def quick_valuation(self, ticker: str) -> dict[str, Any]:
        """Run a quick combined DCF + comps valuation summary.

        Uses default assumptions for both models and returns a
        consolidated view of intrinsic value, relative valuation,
        and an overall assessment.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dict with DCF result, comps result, and combined assessment.
        """
        logger.info("quick_valuation", ticker=ticker)

        # Run both valuations concurrently
        dcf_task = self.dcf_valuation(ticker)
        comps_task = self.comparable_valuation(ticker)

        dcf_result, comps_result = await asyncio.gather(
            dcf_task, comps_task, return_exceptions=True
        )

        summary: dict[str, Any] = {"ticker": ticker}

        # Process DCF result
        if isinstance(dcf_result, Exception):
            logger.warning("dcf_failed", ticker=ticker, error=str(dcf_result))
            summary["dcf"] = {"error": str(dcf_result)}
            dcf_upside = None
        else:
            summary["dcf"] = {
                "intrinsic_value": dcf_result.intrinsic_value,
                "current_price": dcf_result.current_price,
                "upside_pct": dcf_result.upside_pct,
            }
            dcf_upside = dcf_result.upside_pct

        # Process comps result
        if isinstance(comps_result, Exception):
            logger.warning("comps_failed", ticker=ticker, error=str(comps_result))
            summary["comps"] = {"error": str(comps_result)}
            comps_assessment = None
        else:
            summary["comps"] = {
                "metrics": comps_result.metrics,
                "peer_avg": comps_result.peer_avg,
                "premium_discount": comps_result.premium_discount,
                "assessment": comps_result.assessment,
            }
            comps_assessment = comps_result.assessment

        # Combined assessment
        signals: list[str] = []
        if dcf_upside is not None:
            if dcf_upside > 20:
                signals.append("DCF suggests significant upside")
            elif dcf_upside > 0:
                signals.append("DCF suggests moderate upside")
            elif dcf_upside > -20:
                signals.append("DCF suggests moderate downside")
            else:
                signals.append("DCF suggests significant downside")

        if comps_assessment and "undervalued" in comps_assessment:
            signals.append("Comps suggest undervaluation")
        elif comps_assessment and "overvalued" in comps_assessment:
            signals.append("Comps suggest overvaluation")
        elif comps_assessment:
            signals.append("Comps suggest fair valuation")

        if signals:
            summary["combined_assessment"] = "; ".join(signals)
        else:
            summary["combined_assessment"] = "Insufficient data for combined assessment."

        logger.info("quick_valuation_complete", ticker=ticker)
        return summary
