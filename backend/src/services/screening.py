"""Market screening service for the Overture AI hedge fund system.

Provides stock screening capabilities based on fundamental criteria,
technical indicators, and anomaly detection. Uses yfinance for market
data and supports filtering against a configurable universe of tickers.
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
class ScreenCriteria:
    """Criteria for fundamental stock screening.

    All fields are optional. Only non-None fields are applied as filters.
    """

    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None
    min_pe_ratio: Optional[float] = None
    max_pe_ratio: Optional[float] = None
    min_pb_ratio: Optional[float] = None
    max_pb_ratio: Optional[float] = None
    min_dividend_yield: Optional[float] = None
    max_dividend_yield: Optional[float] = None
    min_revenue_growth: Optional[float] = None
    max_revenue_growth: Optional[float] = None
    min_volume: Optional[float] = None
    max_volume: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_beta: Optional[float] = None
    max_beta: Optional[float] = None


@dataclass
class ScreenResult:
    """Result for a single ticker that passes screening criteria."""

    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: float = 0.0
    price: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    dividend_yield: float = 0.0
    revenue_growth: float = 0.0
    volume: float = 0.0
    beta: float = 0.0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ScreeningService:
    """Service for screening stocks based on fundamental and technical criteria.

    Provides fundamental screening against valuation, growth, and
    quality metrics, technical screening using indicators like RSI and
    moving averages, and anomaly detection for unusual price or volume
    movements.
    """

    def __init__(self) -> None:
        self._info_cache: dict[str, dict[str, Any]] = {}

    async def _get_ticker_info(self, ticker: str) -> dict[str, Any]:
        """Fetch and cache ticker info from yfinance.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dict of ticker metadata and fundamentals.
        """
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

    async def _fetch_price_data(
        self,
        ticker: str,
        period: str = "6mo",
    ) -> pd.DataFrame:
        """Fetch recent price history for technical analysis.

        Args:
            ticker: Stock ticker symbol.
            period: yfinance period string (e.g. ``"6mo"``, ``"1y"``).

        Returns:
            DataFrame with OHLCV data.
        """

        def _download() -> pd.DataFrame:
            data = yf.download(ticker, period=period, progress=False)
            return data

        data = await asyncio.to_thread(_download)

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data

    # ------------------------------------------------------------------
    # Default universe
    # ------------------------------------------------------------------

    def get_default_universe(self) -> list[str]:
        """Return the default screening universe (top 100 S&P 500 tickers).

        This hardcoded list covers the largest components by market
        capitalization and serves as a prototype universe.

        Returns:
            List of ticker symbols.
        """
        return [
            # Technology
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
            "ADBE", "CRM", "AMD", "INTC", "CSCO", "ORCL", "ACN", "TXN",
            "QCOM", "IBM", "NOW", "INTU",
            # Healthcare
            "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT",
            "DHR", "BMY", "AMGN", "GILD", "MDT", "SYK", "ISRG",
            # Financial Services
            "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS",
            "BLK", "SCHW", "AXP", "C", "USB", "PNC", "TFC",
            # Consumer
            "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "TJX", "CMG",
            "PG", "KO", "PEP", "WMT", "COST", "CL", "MDLZ",
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO",
            # Industrials
            "HON", "UPS", "CAT", "GE", "RTX", "BA", "DE", "LMT",
            "MMM", "FDX",
            # Communication
            "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS",
            # Real Estate & Utilities
            "AMT", "PLD", "CCI", "NEE", "DUK", "SO",
            # Materials
            "LIN", "APD", "SHW", "ECL", "DD",
        ]

    # ------------------------------------------------------------------
    # Fundamental screen
    # ------------------------------------------------------------------

    async def run_screen(
        self,
        criteria: ScreenCriteria,
        universe: list[str] | None = None,
        max_concurrent: int = 10,
    ) -> list[ScreenResult]:
        """Screen tickers against fundamental criteria.

        Fetches info for each ticker in the universe and applies all
        non-None criteria as filters.

        Args:
            criteria: Screening criteria to apply.
            universe: Ticker universe to screen. Uses default if None.
            max_concurrent: Max concurrent yfinance requests.

        Returns:
            List of ScreenResult for tickers passing all criteria.
        """
        if universe is None:
            universe = self.get_default_universe()

        logger.info("running_screen", universe_size=len(universe))

        results: list[ScreenResult] = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _screen_one(ticker: str) -> Optional[ScreenResult]:
            async with semaphore:
                try:
                    info = await self._get_ticker_info(ticker)
                    if not info:
                        return None
                    return self._apply_criteria(ticker, info, criteria)
                except Exception as exc:
                    logger.warning("screen_ticker_error", ticker=ticker, error=str(exc))
                    return None

        tasks = [_screen_one(t) for t in universe]
        outcomes = await asyncio.gather(*tasks)

        for outcome in outcomes:
            if outcome is not None:
                results.append(outcome)

        # Sort by score (higher is better), then market cap
        results.sort(key=lambda r: (-r.score, -r.market_cap))

        logger.info("screen_complete", matches=len(results), universe_size=len(universe))
        return results

    def _apply_criteria(
        self,
        ticker: str,
        info: dict[str, Any],
        criteria: ScreenCriteria,
    ) -> Optional[ScreenResult]:
        """Test a single ticker against the screening criteria.

        Returns a ScreenResult if the ticker passes all criteria, or
        None if it fails any filter.
        """
        # Extract values with safe defaults
        market_cap = info.get("marketCap") or 0
        pe = info.get("trailingPE") or 0
        pb = info.get("priceToBook") or 0
        div_yield = info.get("dividendYield") or 0
        rev_growth = info.get("revenueGrowth") or 0
        volume = info.get("averageVolume") or 0
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        price = info.get("currentPrice") or info.get("previousClose") or 0
        beta = info.get("beta") or 0
        name = info.get("shortName") or info.get("longName") or ticker

        # Apply filters
        if criteria.min_market_cap is not None and market_cap < criteria.min_market_cap:
            return None
        if criteria.max_market_cap is not None and market_cap > criteria.max_market_cap:
            return None
        if criteria.min_pe_ratio is not None and (pe <= 0 or pe < criteria.min_pe_ratio):
            return None
        if criteria.max_pe_ratio is not None and pe > criteria.max_pe_ratio:
            return None
        if criteria.min_pb_ratio is not None and (pb <= 0 or pb < criteria.min_pb_ratio):
            return None
        if criteria.max_pb_ratio is not None and pb > criteria.max_pb_ratio:
            return None
        if criteria.min_dividend_yield is not None and div_yield < criteria.min_dividend_yield:
            return None
        if criteria.max_dividend_yield is not None and div_yield > criteria.max_dividend_yield:
            return None
        if criteria.min_revenue_growth is not None and rev_growth < criteria.min_revenue_growth:
            return None
        if criteria.max_revenue_growth is not None and rev_growth > criteria.max_revenue_growth:
            return None
        if criteria.min_volume is not None and volume < criteria.min_volume:
            return None
        if criteria.max_volume is not None and volume > criteria.max_volume:
            return None
        if criteria.sector is not None and sector.lower() != criteria.sector.lower():
            return None
        if criteria.industry is not None and industry.lower() != criteria.industry.lower():
            return None
        if criteria.min_price is not None and price < criteria.min_price:
            return None
        if criteria.max_price is not None and price > criteria.max_price:
            return None
        if criteria.min_beta is not None and beta < criteria.min_beta:
            return None
        if criteria.max_beta is not None and beta > criteria.max_beta:
            return None

        # Composite quality score (0-100): simple heuristic weighting
        score = 50.0
        if 0 < pe < 25:
            score += 10
        elif pe > 40:
            score -= 10
        if rev_growth > 0.1:
            score += 15
        elif rev_growth > 0:
            score += 5
        if div_yield > 0.02:
            score += 10
        if market_cap > 100_000_000_000:
            score += 5
        if 0 < pb < 3:
            score += 10

        return ScreenResult(
            ticker=ticker,
            name=name,
            sector=sector,
            industry=industry,
            market_cap=market_cap,
            price=round(price, 2),
            pe_ratio=round(pe, 2),
            pb_ratio=round(pb, 2),
            dividend_yield=round(div_yield, 4),
            revenue_growth=round(rev_growth, 4),
            volume=volume,
            beta=round(beta, 2),
            score=round(score, 2),
        )

    # ------------------------------------------------------------------
    # Technical screen
    # ------------------------------------------------------------------

    async def technical_screen(
        self,
        criteria: dict[str, Any] | None = None,
        universe: list[str] | None = None,
        max_concurrent: int = 10,
    ) -> list[ScreenResult]:
        """Screen tickers based on technical indicators.

        Supported criteria keys:
        - ``rsi_below``: RSI(14) below this threshold (oversold signal).
        - ``rsi_above``: RSI(14) above this threshold (overbought signal).
        - ``above_sma_50``: bool, price above 50-day SMA.
        - ``above_sma_200``: bool, price above 200-day SMA.
        - ``golden_cross``: bool, 50-day SMA crossed above 200-day SMA.
        - ``volume_spike_multiple``: volume > N * average volume.

        Args:
            criteria: Dict of technical filter criteria.
            universe: Tickers to screen. Uses default if None.
            max_concurrent: Max concurrent data fetches.

        Returns:
            List of ScreenResult for tickers matching technical criteria.
        """
        if criteria is None:
            criteria = {"rsi_below": 30}  # Default: find oversold stocks

        if universe is None:
            universe = self.get_default_universe()

        logger.info("technical_screen", criteria=criteria, universe_size=len(universe))

        results: list[ScreenResult] = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _screen_one(ticker: str) -> Optional[ScreenResult]:
            async with semaphore:
                try:
                    data = await self._fetch_price_data(ticker, period="1y")
                    if data.empty or len(data) < 50:
                        return None
                    return self._apply_technical_criteria(ticker, data, criteria)
                except Exception as exc:
                    logger.warning("technical_screen_error", ticker=ticker, error=str(exc))
                    return None

        tasks = [_screen_one(t) for t in universe]
        outcomes = await asyncio.gather(*tasks)

        for outcome in outcomes:
            if outcome is not None:
                results.append(outcome)

        results.sort(key=lambda r: -r.score)
        logger.info("technical_screen_complete", matches=len(results))
        return results

    def _apply_technical_criteria(
        self,
        ticker: str,
        data: pd.DataFrame,
        criteria: dict[str, Any],
    ) -> Optional[ScreenResult]:
        """Evaluate a single ticker against technical criteria."""
        close = data["Close"]
        volume = data["Volume"]

        # Calculate RSI(14)
        rsi = self._calculate_rsi(close, period=14)

        # Moving averages
        sma_50 = close.rolling(50).mean()
        sma_200 = close.rolling(200).mean() if len(close) >= 200 else pd.Series(dtype=float)

        current_price = float(close.iloc[-1])
        current_rsi = float(rsi.iloc[-1]) if not rsi.empty else 50.0
        current_volume = float(volume.iloc[-1])
        avg_volume = float(volume.rolling(20).mean().iloc[-1])

        # Apply filters
        if "rsi_below" in criteria and current_rsi > criteria["rsi_below"]:
            return None
        if "rsi_above" in criteria and current_rsi < criteria["rsi_above"]:
            return None

        if criteria.get("above_sma_50") and not sma_50.empty:
            if current_price <= float(sma_50.iloc[-1]):
                return None

        if criteria.get("above_sma_200") and not sma_200.empty:
            if len(sma_200) > 0 and pd.notna(sma_200.iloc[-1]):
                if current_price <= float(sma_200.iloc[-1]):
                    return None

        if criteria.get("golden_cross") and not sma_200.empty:
            if len(sma_50) >= 2 and len(sma_200) >= 2:
                prev_50 = float(sma_50.iloc[-2])
                curr_50 = float(sma_50.iloc[-1])
                prev_200 = float(sma_200.iloc[-2])
                curr_200 = float(sma_200.iloc[-1])
                if not (prev_50 <= prev_200 and curr_50 > curr_200):
                    return None

        if "volume_spike_multiple" in criteria:
            required = criteria["volume_spike_multiple"]
            if avg_volume > 0 and current_volume / avg_volume < required:
                return None

        # Technical score heuristic
        score = 50.0
        if current_rsi < 30:
            score += 20  # Oversold
        elif current_rsi > 70:
            score -= 10  # Overbought
        if not sma_50.empty and current_price > float(sma_50.iloc[-1]):
            score += 10
        if not sma_200.empty and len(sma_200) > 0 and pd.notna(sma_200.iloc[-1]):
            if current_price > float(sma_200.iloc[-1]):
                score += 10
        if avg_volume > 0 and current_volume > avg_volume * 1.5:
            score += 5

        return ScreenResult(
            ticker=ticker,
            price=round(current_price, 2),
            volume=current_volume,
            score=round(score, 2),
            metadata={
                "rsi_14": round(current_rsi, 2),
                "sma_50": round(float(sma_50.iloc[-1]), 2) if not sma_50.empty else None,
                "sma_200": (
                    round(float(sma_200.iloc[-1]), 2)
                    if not sma_200.empty and pd.notna(sma_200.iloc[-1])
                    else None
                ),
                "volume_ratio": round(current_volume / avg_volume, 2) if avg_volume > 0 else 0,
            },
        )

    @staticmethod
    def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate the Relative Strength Index (RSI).

        Args:
            close: Series of closing prices.
            period: RSI lookback period (default 14).

        Returns:
            Series of RSI values.
        """
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.fillna(50.0)

    # ------------------------------------------------------------------
    # Anomaly screen
    # ------------------------------------------------------------------

    async def anomaly_screen(
        self,
        sigma_threshold: float = 2.5,
        lookback: int = 60,
        universe: list[str] | None = None,
        max_concurrent: int = 10,
    ) -> list[ScreenResult]:
        """Find tickers with unusual recent price or volume movements.

        Identifies stocks where the most recent daily return or volume
        exceeds *sigma_threshold* standard deviations from the rolling
        mean over *lookback* trading days.

        Args:
            sigma_threshold: Number of standard deviations for anomaly.
            lookback: Rolling window for calculating statistics.
            universe: Tickers to screen. Uses default if None.
            max_concurrent: Max concurrent data fetches.

        Returns:
            List of ScreenResult for tickers with detected anomalies.
        """
        if universe is None:
            universe = self.get_default_universe()

        logger.info(
            "anomaly_screen",
            sigma=sigma_threshold,
            lookback=lookback,
            universe_size=len(universe),
        )

        results: list[ScreenResult] = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _check_one(ticker: str) -> Optional[ScreenResult]:
            async with semaphore:
                try:
                    data = await self._fetch_price_data(ticker, period="6mo")
                    if data.empty or len(data) < lookback:
                        return None
                    return self._detect_anomaly(ticker, data, sigma_threshold, lookback)
                except Exception as exc:
                    logger.warning("anomaly_check_error", ticker=ticker, error=str(exc))
                    return None

        tasks = [_check_one(t) for t in universe]
        outcomes = await asyncio.gather(*tasks)

        for outcome in outcomes:
            if outcome is not None:
                results.append(outcome)

        results.sort(key=lambda r: -abs(r.score))
        logger.info("anomaly_screen_complete", anomalies=len(results))
        return results

    def _detect_anomaly(
        self,
        ticker: str,
        data: pd.DataFrame,
        sigma_threshold: float,
        lookback: int,
    ) -> Optional[ScreenResult]:
        """Check if the most recent data point is anomalous."""
        close = data["Close"]
        volume = data["Volume"]

        daily_returns = close.pct_change().dropna()
        if len(daily_returns) < lookback:
            return None

        # Price anomaly check
        rolling_mean = daily_returns.rolling(lookback).mean()
        rolling_std = daily_returns.rolling(lookback).std()
        latest_return = daily_returns.iloc[-1]
        mean_val = rolling_mean.iloc[-1]
        std_val = rolling_std.iloc[-1]

        price_z = (latest_return - mean_val) / std_val if std_val > 0 else 0.0

        # Volume anomaly check
        vol_mean = volume.rolling(lookback).mean().iloc[-1]
        vol_std = volume.rolling(lookback).std().iloc[-1]
        latest_vol = volume.iloc[-1]
        volume_z = (latest_vol - vol_mean) / vol_std if vol_std > 0 else 0.0

        # Check if either exceeds threshold
        is_price_anomaly = abs(price_z) >= sigma_threshold
        is_volume_anomaly = abs(volume_z) >= sigma_threshold

        if not is_price_anomaly and not is_volume_anomaly:
            return None

        anomaly_types: list[str] = []
        if is_price_anomaly:
            anomaly_types.append("price")
        if is_volume_anomaly:
            anomaly_types.append("volume")

        # Score is the max absolute z-score
        score = max(abs(price_z), abs(volume_z))

        return ScreenResult(
            ticker=ticker,
            price=round(float(close.iloc[-1]), 2),
            volume=float(latest_vol),
            score=round(float(score), 2),
            metadata={
                "anomaly_types": anomaly_types,
                "price_z_score": round(float(price_z), 2),
                "volume_z_score": round(float(volume_z), 2),
                "latest_return": round(float(latest_return), 4),
                "sigma_threshold": sigma_threshold,
            },
        )
