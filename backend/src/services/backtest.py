"""Backtesting engine for the Overture AI hedge fund system.

Provides strategy backtesting capabilities including buy-the-dip,
mean reversion, and momentum strategies. Uses yfinance for historical
data and numpy/pandas for quantitative calculations.
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
class BacktestResult:
    """Container for backtesting results and performance metrics."""

    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    avg_trade_return: float
    sample_size: int
    returns_series: list[float] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BacktestEngine:
    """Engine for running backtests on various trading strategies.

    Supports generic strategy backtesting as well as specialized
    implementations for buy-the-dip, mean reversion, and momentum
    strategies. All market data is fetched via yfinance with async
    wrappers for non-blocking execution.
    """

    TRADING_DAYS_PER_YEAR = 252
    RISK_FREE_RATE = 0.05  # Annualized risk-free rate assumption

    def __init__(self) -> None:
        self._data_cache: dict[str, pd.DataFrame] = {}

    async def _fetch_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data from yfinance.

        Args:
            ticker: Stock ticker symbol.
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.

        Returns:
            DataFrame with OHLCV data indexed by date.
        """
        cache_key = f"{ticker}_{start_date}_{end_date}"
        if cache_key in self._data_cache:
            return self._data_cache[cache_key]

        def _download() -> pd.DataFrame:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            return data

        logger.info("fetching_market_data", ticker=ticker, start=start_date, end=end_date)
        data = await asyncio.to_thread(_download)

        if data.empty:
            raise ValueError(f"No data returned for {ticker} between {start_date} and {end_date}")

        # Flatten MultiIndex columns if present (yfinance returns MultiIndex for single ticker)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        self._data_cache[cache_key] = data
        return data

    @staticmethod
    def _calculate_sharpe(
        returns: pd.Series,
        risk_free_rate: float = 0.05,
        periods_per_year: int = 252,
    ) -> float:
        """Calculate the annualized Sharpe ratio.

        Args:
            returns: Series of periodic returns.
            risk_free_rate: Annualized risk-free rate.
            periods_per_year: Number of trading periods per year.

        Returns:
            Annualized Sharpe ratio.
        """
        if returns.std() == 0 or len(returns) < 2:
            return 0.0
        excess = returns.mean() - (risk_free_rate / periods_per_year)
        return float(excess / returns.std() * np.sqrt(periods_per_year))

    @staticmethod
    def _calculate_max_drawdown(equity_curve: pd.Series) -> float:
        """Calculate the maximum drawdown from an equity curve.

        Args:
            equity_curve: Series of portfolio values over time.

        Returns:
            Maximum drawdown as a negative fraction (e.g. -0.15 for 15% drawdown).
        """
        if equity_curve.empty:
            return 0.0
        running_max = equity_curve.cummax()
        drawdown = (equity_curve - running_max) / running_max
        return float(drawdown.min())

    # ------------------------------------------------------------------
    # Generic strategy runner
    # ------------------------------------------------------------------

    async def run_backtest(
        self,
        strategy: dict[str, Any],
        tickers: list[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 100_000.0,
    ) -> BacktestResult:
        """Run a generic strategy backtest over historical data.

        The *strategy* dict must contain:
        - ``signal_type`` -- one of ``"buy_dip"``, ``"mean_reversion"``, ``"momentum"``
        - ``parameters``  -- dict of strategy-specific parameters

        Args:
            strategy: Strategy configuration dict.
            tickers: List of ticker symbols to trade.
            start_date: Backtest start date (YYYY-MM-DD).
            end_date: Backtest end date (YYYY-MM-DD).
            initial_capital: Starting portfolio value in USD.

        Returns:
            BacktestResult with performance metrics and equity curve.
        """
        signal_type = strategy.get("signal_type", "buy_dip")
        params = strategy.get("parameters", {})

        logger.info(
            "running_backtest",
            signal_type=signal_type,
            tickers=tickers,
            start=start_date,
            end=end_date,
            capital=initial_capital,
        )

        # Aggregate results across tickers using equal-weight allocation
        capital_per_ticker = initial_capital / max(len(tickers), 1)
        all_returns: list[float] = []
        combined_equity: list[float] = []
        total_trades = 0
        winning_trades = 0
        trade_returns: list[float] = []

        for ticker in tickers:
            data = await self._fetch_data(ticker, start_date, end_date)
            close = data["Close"]
            daily_returns = close.pct_change().dropna()

            if signal_type == "buy_dip":
                result = self._simulate_buy_dip(
                    daily_returns,
                    close,
                    capital_per_ticker,
                    sigma_threshold=params.get("sigma_threshold", 2.0),
                    holding_period=params.get("holding_period", 5),
                )
            elif signal_type == "mean_reversion":
                result = self._simulate_mean_reversion(
                    close,
                    capital_per_ticker,
                    entry_z=params.get("entry_z", 2.0),
                    exit_z=params.get("exit_z", 0.0),
                    lookback=params.get("lookback", 20),
                )
            elif signal_type == "momentum":
                result = self._simulate_momentum(
                    close,
                    capital_per_ticker,
                    lookback=params.get("lookback", 20),
                    holding_period=params.get("holding_period", 5),
                )
            else:
                raise ValueError(f"Unknown signal_type: {signal_type}")

            all_returns.extend(result["returns"])
            combined_equity.extend(result["equity"])
            total_trades += result["total_trades"]
            winning_trades += result["winning_trades"]
            trade_returns.extend(result["trade_returns"])

        # Compute aggregate statistics
        returns_series = pd.Series(all_returns) if all_returns else pd.Series(dtype=float)
        total_return = float((1 + returns_series).prod() - 1) if not returns_series.empty else 0.0
        n_days = len(returns_series) if not returns_series.empty else 1
        annualized_return = float(
            (1 + total_return) ** (self.TRADING_DAYS_PER_YEAR / max(n_days, 1)) - 1
        )
        sharpe = self._calculate_sharpe(returns_series)
        equity_series = pd.Series(combined_equity) if combined_equity else pd.Series([initial_capital])
        max_dd = self._calculate_max_drawdown(equity_series)
        win_rate = winning_trades / max(total_trades, 1)
        avg_trade_ret = float(np.mean(trade_returns)) if trade_returns else 0.0

        result = BacktestResult(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=total_trades,
            avg_trade_return=avg_trade_ret,
            sample_size=len(trade_returns),
            returns_series=returns_series.tolist(),
            equity_curve=equity_series.tolist(),
            metadata={
                "strategy": strategy,
                "tickers": tickers,
                "start_date": start_date,
                "end_date": end_date,
                "initial_capital": initial_capital,
            },
        )

        logger.info(
            "backtest_complete",
            total_return=f"{total_return:.2%}",
            sharpe=f"{sharpe:.2f}",
            trades=total_trades,
        )
        return result

    # ------------------------------------------------------------------
    # Internal simulation helpers
    # ------------------------------------------------------------------

    def _simulate_buy_dip(
        self,
        daily_returns: pd.Series,
        close: pd.Series,
        capital: float,
        sigma_threshold: float,
        holding_period: int,
    ) -> dict[str, Any]:
        """Simulate a buy-the-dip strategy on a single ticker.

        Buys when the daily return drops below -sigma_threshold standard
        deviations and holds for *holding_period* trading days.
        """
        mean_ret = daily_returns.mean()
        std_ret = daily_returns.std()
        threshold = mean_ret - sigma_threshold * std_ret

        trades_returns: list[float] = []
        equity = capital
        equity_curve: list[float] = [equity]
        portfolio_returns: list[float] = []

        i = 0
        dates = daily_returns.index.tolist()
        while i < len(dates):
            ret = daily_returns.iloc[i]
            if ret <= threshold:
                # Enter position: buy at close
                entry_idx = close.index.get_loc(dates[i])
                exit_idx = min(entry_idx + holding_period, len(close) - 1)
                entry_price = close.iloc[entry_idx]
                exit_price = close.iloc[exit_idx]
                trade_ret = float((exit_price - entry_price) / entry_price)
                trades_returns.append(trade_ret)
                equity *= 1 + trade_ret
                equity_curve.append(equity)
                portfolio_returns.append(trade_ret)
                # Skip ahead past the holding period
                i += holding_period
            else:
                portfolio_returns.append(0.0)
                equity_curve.append(equity)
                i += 1

        winning = sum(1 for r in trades_returns if r > 0)
        return {
            "returns": portfolio_returns,
            "equity": equity_curve,
            "total_trades": len(trades_returns),
            "winning_trades": winning,
            "trade_returns": trades_returns,
        }

    def _simulate_mean_reversion(
        self,
        close: pd.Series,
        capital: float,
        entry_z: float,
        exit_z: float,
        lookback: int,
    ) -> dict[str, Any]:
        """Simulate a mean reversion strategy on a single ticker.

        Enters long when price z-score falls below -entry_z and exits
        when z-score crosses above -exit_z. Enters short when z-score
        rises above +entry_z and exits when it falls below +exit_z.
        """
        rolling_mean = close.rolling(window=lookback).mean()
        rolling_std = close.rolling(window=lookback).std()
        z_scores = (close - rolling_mean) / rolling_std

        equity = capital
        equity_curve: list[float] = [equity]
        portfolio_returns: list[float] = []
        trades_returns: list[float] = []
        position: Optional[str] = None  # "long" or "short"
        entry_price = 0.0

        for i in range(lookback, len(close)):
            z = z_scores.iloc[i]
            price = close.iloc[i]
            prev_price = close.iloc[i - 1]

            if position is None:
                # Look for entry signals
                if z <= -entry_z:
                    position = "long"
                    entry_price = price
                elif z >= entry_z:
                    position = "short"
                    entry_price = price
                portfolio_returns.append(0.0)
                equity_curve.append(equity)
            elif position == "long":
                daily_ret = (price - prev_price) / prev_price
                portfolio_returns.append(daily_ret)
                equity *= 1 + daily_ret
                equity_curve.append(equity)
                if z >= -exit_z:
                    trade_ret = (price - entry_price) / entry_price
                    trades_returns.append(trade_ret)
                    position = None
            elif position == "short":
                daily_ret = -(price - prev_price) / prev_price
                portfolio_returns.append(daily_ret)
                equity *= 1 + daily_ret
                equity_curve.append(equity)
                if z <= exit_z:
                    trade_ret = -(price - entry_price) / entry_price
                    trades_returns.append(trade_ret)
                    position = None

        # Close any open position at the end
        if position == "long":
            trade_ret = (close.iloc[-1] - entry_price) / entry_price
            trades_returns.append(trade_ret)
        elif position == "short":
            trade_ret = -(close.iloc[-1] - entry_price) / entry_price
            trades_returns.append(trade_ret)

        winning = sum(1 for r in trades_returns if r > 0)
        return {
            "returns": portfolio_returns,
            "equity": equity_curve,
            "total_trades": len(trades_returns),
            "winning_trades": winning,
            "trade_returns": trades_returns,
        }

    def _simulate_momentum(
        self,
        close: pd.Series,
        capital: float,
        lookback: int,
        holding_period: int,
    ) -> dict[str, Any]:
        """Simulate a momentum strategy on a single ticker.

        Enters long when the trailing *lookback*-day return is positive
        and holds for *holding_period* days.
        """
        trades_returns: list[float] = []
        equity = capital
        equity_curve: list[float] = [equity]
        portfolio_returns: list[float] = []

        i = lookback
        while i < len(close):
            trailing_return = (close.iloc[i] - close.iloc[i - lookback]) / close.iloc[i - lookback]
            if trailing_return > 0:
                # Enter long
                entry_price = close.iloc[i]
                exit_idx = min(i + holding_period, len(close) - 1)
                exit_price = close.iloc[exit_idx]
                trade_ret = float((exit_price - entry_price) / entry_price)
                trades_returns.append(trade_ret)
                equity *= 1 + trade_ret
                equity_curve.append(equity)
                portfolio_returns.append(trade_ret)
                i += holding_period
            else:
                portfolio_returns.append(0.0)
                equity_curve.append(equity)
                i += 1

        winning = sum(1 for r in trades_returns if r > 0)
        return {
            "returns": portfolio_returns,
            "equity": equity_curve,
            "total_trades": len(trades_returns),
            "winning_trades": winning,
            "trade_returns": trades_returns,
        }

    # ------------------------------------------------------------------
    # Specialized backtest: buy-the-dip (silver example)
    # ------------------------------------------------------------------

    async def buy_the_dip_backtest(
        self,
        ticker: str,
        sigma_threshold: float = 2.0,
        holding_periods: list[int] | None = None,
        lookback_years: int = 10,
    ) -> dict[str, Any]:
        """Run a specialized buy-the-dip analysis.

        Designed for the silver (SLV) example: identifies days where
        the price moved more than *sigma_threshold* standard deviations
        and calculates forward returns over multiple holding periods.

        Args:
            ticker: Ticker symbol (e.g. ``"SLV"``).
            sigma_threshold: Number of standard deviations for trigger.
            holding_periods: List of forward holding periods in days.
            lookback_years: How many years of historical data to use.

        Returns:
            Dict with per-holding-period statistics: win_rate, avg_return,
            median_return, max_drawdown, and sample_size.
        """
        if holding_periods is None:
            holding_periods = [1, 5, 10, 21, 63]

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_years * 365)).strftime("%Y-%m-%d")

        data = await self._fetch_data(ticker, start_date, end_date)
        close = data["Close"]
        daily_returns = close.pct_change().dropna()

        mean_ret = daily_returns.mean()
        std_ret = daily_returns.std()

        # Identify dip days: returns worse than -sigma_threshold * std
        dip_mask = daily_returns <= (mean_ret - sigma_threshold * std_ret)
        dip_dates = daily_returns[dip_mask].index
        sample_size = len(dip_dates)

        logger.info(
            "buy_the_dip_analysis",
            ticker=ticker,
            sigma=sigma_threshold,
            dip_events=sample_size,
        )

        results: dict[str, Any] = {
            "ticker": ticker,
            "sigma_threshold": sigma_threshold,
            "total_dip_events": sample_size,
            "analysis_start": start_date,
            "analysis_end": end_date,
            "holding_periods": {},
        }

        for hp in holding_periods:
            forward_returns: list[float] = []
            max_drawdowns: list[float] = []

            for dip_date in dip_dates:
                entry_idx = close.index.get_loc(dip_date)
                exit_idx = min(entry_idx + hp, len(close) - 1)

                if exit_idx <= entry_idx:
                    continue

                entry_price = close.iloc[entry_idx]
                exit_price = close.iloc[exit_idx]
                fwd_ret = float((exit_price - entry_price) / entry_price)
                forward_returns.append(fwd_ret)

                # Compute intra-trade drawdown
                trade_slice = close.iloc[entry_idx : exit_idx + 1]
                running_max = trade_slice.cummax()
                dd = ((trade_slice - running_max) / running_max).min()
                max_drawdowns.append(float(dd))

            if forward_returns:
                fr_arr = np.array(forward_returns)
                results["holding_periods"][hp] = {
                    "win_rate": float(np.mean(fr_arr > 0)),
                    "avg_return": float(np.mean(fr_arr)),
                    "median_return": float(np.median(fr_arr)),
                    "max_drawdown": float(np.min(max_drawdowns)) if max_drawdowns else 0.0,
                    "std_return": float(np.std(fr_arr)),
                    "sample_size": len(forward_returns),
                }
            else:
                results["holding_periods"][hp] = {
                    "win_rate": 0.0,
                    "avg_return": 0.0,
                    "median_return": 0.0,
                    "max_drawdown": 0.0,
                    "std_return": 0.0,
                    "sample_size": 0,
                }

        return results

    # ------------------------------------------------------------------
    # Specialized backtest: mean reversion
    # ------------------------------------------------------------------

    async def mean_reversion_backtest(
        self,
        ticker: str,
        entry_z: float = 2.0,
        exit_z: float = 0.0,
        lookback: int = 20,
        lookback_years: int = 5,
    ) -> BacktestResult:
        """Run a mean reversion backtest on a single ticker.

        Enters long when the z-score of price relative to a rolling
        mean falls below -entry_z and exits when it rises above -exit_z.
        Symmetric for short positions.

        Args:
            ticker: Ticker symbol.
            entry_z: Z-score threshold for entry (absolute value).
            exit_z: Z-score threshold for exit (absolute value).
            lookback: Rolling window size in trading days.
            lookback_years: Years of historical data to use.

        Returns:
            BacktestResult with strategy performance metrics.
        """
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_years * 365)).strftime("%Y-%m-%d")

        data = await self._fetch_data(ticker, start_date, end_date)
        close = data["Close"]
        initial_capital = 100_000.0

        sim = self._simulate_mean_reversion(close, initial_capital, entry_z, exit_z, lookback)

        returns_series = pd.Series(sim["returns"])
        equity_series = pd.Series(sim["equity"])
        total_return = float((1 + returns_series).prod() - 1) if not returns_series.empty else 0.0
        n_days = len(returns_series) if not returns_series.empty else 1
        annualized = float(
            (1 + total_return) ** (self.TRADING_DAYS_PER_YEAR / max(n_days, 1)) - 1
        )
        sharpe = self._calculate_sharpe(returns_series)
        max_dd = self._calculate_max_drawdown(equity_series)
        win_rate = sim["winning_trades"] / max(sim["total_trades"], 1)
        avg_tr = float(np.mean(sim["trade_returns"])) if sim["trade_returns"] else 0.0

        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=sim["total_trades"],
            avg_trade_return=avg_tr,
            sample_size=sim["total_trades"],
            returns_series=returns_series.tolist(),
            equity_curve=equity_series.tolist(),
            metadata={
                "ticker": ticker,
                "strategy": "mean_reversion",
                "entry_z": entry_z,
                "exit_z": exit_z,
                "lookback": lookback,
            },
        )

    # ------------------------------------------------------------------
    # Specialized backtest: momentum
    # ------------------------------------------------------------------

    async def momentum_backtest(
        self,
        ticker: str,
        lookback: int = 20,
        holding_period: int = 5,
        lookback_years: int = 5,
    ) -> BacktestResult:
        """Run a momentum backtest on a single ticker.

        Enters long when the trailing *lookback*-day return is positive
        and holds the position for *holding_period* trading days.

        Args:
            ticker: Ticker symbol.
            lookback: Number of days to measure trailing momentum.
            holding_period: Number of days to hold each trade.
            lookback_years: Years of historical data to use.

        Returns:
            BacktestResult with strategy performance metrics.
        """
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_years * 365)).strftime("%Y-%m-%d")

        data = await self._fetch_data(ticker, start_date, end_date)
        close = data["Close"]
        initial_capital = 100_000.0

        sim = self._simulate_momentum(close, initial_capital, lookback, holding_period)

        returns_series = pd.Series(sim["returns"])
        equity_series = pd.Series(sim["equity"])
        total_return = float((1 + returns_series).prod() - 1) if not returns_series.empty else 0.0
        n_days = len(returns_series) if not returns_series.empty else 1
        annualized = float(
            (1 + total_return) ** (self.TRADING_DAYS_PER_YEAR / max(n_days, 1)) - 1
        )
        sharpe = self._calculate_sharpe(returns_series)
        max_dd = self._calculate_max_drawdown(equity_series)
        win_rate = sim["winning_trades"] / max(sim["total_trades"], 1)
        avg_tr = float(np.mean(sim["trade_returns"])) if sim["trade_returns"] else 0.0

        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=sim["total_trades"],
            avg_trade_return=avg_tr,
            sample_size=sim["total_trades"],
            returns_series=returns_series.tolist(),
            equity_curve=equity_series.tolist(),
            metadata={
                "ticker": ticker,
                "strategy": "momentum",
                "lookback": lookback,
                "holding_period": holding_period,
            },
        )
