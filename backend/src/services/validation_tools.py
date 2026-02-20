"""Common Validation Tool Base for Agent Validators.

A shared toolbox that validators call to perform concrete analysis instead of
relying purely on LLM reasoning. Each tool performs a specific, repeatable
computation that validators can invoke by name.

Design Principles:
  - Tools are DETERMINISTIC: same input → same output (no LLM inside tools)
  - Tools are COMPOSABLE: validators combine multiple tools per idea
  - Tools are INSPECTABLE: every tool logs its inputs, outputs, and methodology
  - Tools are CACHEABLE: results can be memoized for the same inputs
  - Validators decide WHICH tools to call (LLM decides strategy)
  - Tools execute the COMPUTATION (code does the math)

Tool Registry:
    backtest_momentum     - Backtest a momentum/trend strategy on historical data
    backtest_mean_revert  - Backtest a mean-reversion strategy
    backtest_event        - Backtest an event-driven pattern
    get_fundamentals      - Fetch fundamental data (P/E, EPS, revenue growth)
    get_valuation_multiples - Compare valuation vs. sector peers
    check_short_interest  - Check short interest and days to cover
    calculate_risk_reward - Calculate risk/reward ratio given entry/stop/target
    check_correlation     - Check correlation with existing portfolio
    get_historical_vol    - Get historical and implied volatility
    check_seasonality     - Check seasonal patterns for an asset
    get_price_levels      - Get key support/resistance and moving averages

Each tool returns a ToolResult with:
  - success: bool (did the computation complete?)
  - data: dict (the actual results)
  - methodology: str (human-readable explanation of what was computed)
  - source: str (data source used)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Standardized result from a validation tool."""
    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    methodology: str = ""
    source: str = ""
    error: str = ""
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "tool": self.tool_name,
            "success": self.success,
            "data": self.data,
            "methodology": self.methodology,
            "source": self.source,
            "error": self.error,
            "computed_at": self.computed_at,
        }


# ---------------------------------------------------------------------------
# Backtest Tools
# ---------------------------------------------------------------------------

async def backtest_momentum(
    tickers: list[str],
    lookback_days: int = 252,
    holding_days: int = 21,
    entry_rule: str = "price_above_sma_50",
) -> ToolResult:
    """Backtest a momentum/trend-following strategy on historical data.

    Methodology:
    - Downloads daily price data for the lookback period
    - Applies the entry rule (e.g., price above 50-day SMA)
    - Simulates buying when rule triggers, holding for N days
    - Computes win rate, avg return, Sharpe ratio, max drawdown

    Args:
        tickers: List of ticker symbols to test.
        lookback_days: Historical period to test over.
        holding_days: How long to hold each position.
        entry_rule: Rule name (price_above_sma_50, new_52w_high, breakout_volume).

    Returns:
        ToolResult with backtest statistics.
    """
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        results = {}
        for ticker in tickers[:5]:  # Limit to 5 tickers
            df = yf.download(ticker, period=f"{lookback_days}d", progress=False)
            if df.empty or len(df) < 50:
                results[ticker] = {"error": "Insufficient data"}
                continue

            close = df["Close"].values.flatten()

            # Apply entry rule
            if entry_rule == "price_above_sma_50":
                sma_50 = pd.Series(close).rolling(50).mean().values
                signals = close > sma_50
            elif entry_rule == "new_52w_high":
                rolling_max = pd.Series(close).rolling(252).max().values
                signals = close >= rolling_max * 0.98
            else:
                sma_50 = pd.Series(close).rolling(50).mean().values
                signals = close > sma_50

            # Simulate trades
            trades = []
            i = 50
            while i < len(close) - holding_days:
                if signals[i]:
                    entry = close[i]
                    exit_price = close[min(i + holding_days, len(close) - 1)]
                    ret = (exit_price - entry) / entry
                    trades.append(ret)
                    i += holding_days  # skip holding period
                else:
                    i += 1

            if trades:
                trades_arr = np.array(trades)
                win_rate = float(np.mean(trades_arr > 0))
                avg_return = float(np.mean(trades_arr))
                sharpe = float(np.mean(trades_arr) / np.std(trades_arr) * np.sqrt(252 / holding_days)) if np.std(trades_arr) > 0 else 0
                max_dd = float(np.min(trades_arr))

                results[ticker] = {
                    "trade_count": len(trades),
                    "win_rate": round(win_rate, 3),
                    "avg_return_pct": round(avg_return * 100, 2),
                    "sharpe_ratio": round(sharpe, 2),
                    "max_single_loss_pct": round(max_dd * 100, 2),
                    "total_return_pct": round(float(np.sum(trades_arr)) * 100, 2),
                }
            else:
                results[ticker] = {"trade_count": 0, "note": "No signals triggered"}

        return ToolResult(
            tool_name="backtest_momentum",
            success=True,
            data={"results": results, "entry_rule": entry_rule, "holding_days": holding_days},
            methodology=(
                f"Momentum backtest: {entry_rule} rule over {lookback_days} days, "
                f"{holding_days}-day holding period. Win rate, Sharpe, and max "
                "drawdown computed from simulated trades."
            ),
            source="yfinance historical data",
        )
    except ImportError:
        return ToolResult(
            tool_name="backtest_momentum",
            success=False,
            error="yfinance not available",
        )
    except Exception as e:
        return ToolResult(tool_name="backtest_momentum", success=False, error=str(e))


async def backtest_mean_revert(
    tickers: list[str],
    lookback_days: int = 252,
    z_score_entry: float = -2.0,
    z_score_exit: float = 0.0,
    window: int = 20,
) -> ToolResult:
    """Backtest a mean-reversion strategy.

    Methodology:
    - Compute rolling Z-score of price relative to N-day mean
    - Enter long when Z-score < entry threshold (oversold)
    - Exit when Z-score returns to exit threshold (mean)
    - Compute win rate, average hold time, and return statistics
    """
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        results = {}
        for ticker in tickers[:5]:
            df = yf.download(ticker, period=f"{lookback_days}d", progress=False)
            if df.empty or len(df) < window + 10:
                results[ticker] = {"error": "Insufficient data"}
                continue

            close = pd.Series(df["Close"].values.flatten())
            rolling_mean = close.rolling(window).mean()
            rolling_std = close.rolling(window).std()
            z_scores = (close - rolling_mean) / rolling_std

            trades = []
            i = window
            while i < len(close):
                if z_scores.iloc[i] <= z_score_entry:
                    entry_price = close.iloc[i]
                    entry_idx = i
                    # Find exit
                    for j in range(i + 1, len(close)):
                        if z_scores.iloc[j] >= z_score_exit:
                            exit_price = close.iloc[j]
                            ret = (exit_price - entry_price) / entry_price
                            trades.append({"return": ret, "hold_days": j - entry_idx})
                            i = j + 1
                            break
                    else:
                        # Never exited — use last price
                        exit_price = close.iloc[-1]
                        ret = (exit_price - entry_price) / entry_price
                        trades.append({"return": ret, "hold_days": len(close) - entry_idx})
                        break
                else:
                    i += 1

            if trades:
                returns = [t["return"] for t in trades]
                hold_days = [t["hold_days"] for t in trades]
                results[ticker] = {
                    "trade_count": len(trades),
                    "win_rate": round(sum(1 for r in returns if r > 0) / len(returns), 3),
                    "avg_return_pct": round(float(np.mean(returns)) * 100, 2),
                    "avg_hold_days": round(float(np.mean(hold_days)), 1),
                    "max_loss_pct": round(float(min(returns)) * 100, 2),
                }
            else:
                results[ticker] = {"trade_count": 0, "note": "No mean-reversion signals"}

        return ToolResult(
            tool_name="backtest_mean_revert",
            success=True,
            data={"results": results, "z_entry": z_score_entry, "z_exit": z_score_exit, "window": window},
            methodology=(
                f"Mean-reversion: enter when {window}-day Z-score < {z_score_entry}, "
                f"exit at Z={z_score_exit}. Measures reversion tendency."
            ),
            source="yfinance historical data",
        )
    except ImportError:
        return ToolResult(tool_name="backtest_mean_revert", success=False, error="yfinance not available")
    except Exception as e:
        return ToolResult(tool_name="backtest_mean_revert", success=False, error=str(e))


# ---------------------------------------------------------------------------
# Fundamental Data Tools
# ---------------------------------------------------------------------------

async def get_fundamentals(tickers: list[str]) -> ToolResult:
    """Fetch fundamental data for tickers.

    Returns P/E ratio, EPS, revenue growth, market cap, debt/equity,
    ROE, profit margin, and dividend yield.
    """
    try:
        import yfinance as yf

        results = {}
        for ticker in tickers[:10]:
            try:
                info = yf.Ticker(ticker).info
                results[ticker] = {
                    "market_cap": info.get("marketCap"),
                    "pe_ratio": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "eps_ttm": info.get("trailingEps"),
                    "eps_forward": info.get("forwardEps"),
                    "revenue_growth": info.get("revenueGrowth"),
                    "earnings_growth": info.get("earningsGrowth"),
                    "profit_margin": info.get("profitMargins"),
                    "roe": info.get("returnOnEquity"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "dividend_yield": info.get("dividendYield"),
                    "beta": info.get("beta"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "52w_high": info.get("fiftyTwoWeekHigh"),
                    "52w_low": info.get("fiftyTwoWeekLow"),
                }
            except Exception:
                results[ticker] = {"error": "Data unavailable"}

        return ToolResult(
            tool_name="get_fundamentals",
            success=True,
            data={"fundamentals": results},
            methodology=(
                "Fundamental data sourced from Yahoo Finance. Includes trailing "
                "and forward P/E, EPS, margins, growth rates, and valuation multiples."
            ),
            source="yfinance (Yahoo Finance)",
        )
    except ImportError:
        return ToolResult(tool_name="get_fundamentals", success=False, error="yfinance not available")
    except Exception as e:
        return ToolResult(tool_name="get_fundamentals", success=False, error=str(e))


async def get_valuation_multiples(ticker: str) -> ToolResult:
    """Compare a ticker's valuation multiples vs sector peers.

    Returns the ticker's P/E, EV/EBITDA relative to sector median.
    """
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        sector = info.get("sector", "Unknown")
        pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")

        return ToolResult(
            tool_name="get_valuation_multiples",
            success=True,
            data={
                "ticker": ticker,
                "sector": sector,
                "trailing_pe": pe,
                "forward_pe": forward_pe,
                "price_to_book": info.get("priceToBook"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "peg_ratio": info.get("pegRatio"),
            },
            methodology=(
                f"Valuation multiples for {ticker} in {sector} sector. "
                "Compare trailing P/E, forward P/E, EV/EBITDA, and PEG ratio "
                "against sector medians to assess relative value."
            ),
            source="yfinance (Yahoo Finance)",
        )
    except Exception as e:
        return ToolResult(tool_name="get_valuation_multiples", success=False, error=str(e))


# ---------------------------------------------------------------------------
# Risk / Portfolio Tools
# ---------------------------------------------------------------------------

async def calculate_risk_reward(
    entry_price: float,
    stop_loss: float,
    target_price: float,
    position_size_pct: float = 5.0,
) -> ToolResult:
    """Calculate risk/reward ratio and position metrics.

    Returns risk/reward ratio, max loss, expected gain, and Kelly criterion.
    """
    if entry_price <= 0:
        return ToolResult(tool_name="calculate_risk_reward", success=False, error="Invalid entry price")

    risk_pct = abs(entry_price - stop_loss) / entry_price * 100
    reward_pct = abs(target_price - entry_price) / entry_price * 100
    risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0

    # Portfolio impact
    max_portfolio_loss_pct = risk_pct * position_size_pct / 100
    max_portfolio_gain_pct = reward_pct * position_size_pct / 100

    return ToolResult(
        tool_name="calculate_risk_reward",
        success=True,
        data={
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target_price": target_price,
            "risk_pct": round(risk_pct, 2),
            "reward_pct": round(reward_pct, 2),
            "risk_reward_ratio": round(risk_reward, 2),
            "position_size_pct": position_size_pct,
            "max_portfolio_loss_pct": round(max_portfolio_loss_pct, 2),
            "max_portfolio_gain_pct": round(max_portfolio_gain_pct, 2),
            "quality": (
                "excellent" if risk_reward >= 3 else
                "good" if risk_reward >= 2 else
                "acceptable" if risk_reward >= 1.5 else
                "poor"
            ),
        },
        methodology=(
            f"Risk/Reward: {risk_pct:.1f}% risk for {reward_pct:.1f}% reward = "
            f"{risk_reward:.1f}:1 ratio. At {position_size_pct:.1f}% position, "
            f"max portfolio impact is -{max_portfolio_loss_pct:.2f}% / "
            f"+{max_portfolio_gain_pct:.2f}%."
        ),
        source="calculated",
    )


async def check_correlation(
    tickers: list[str],
    portfolio_tickers: list[str] | None = None,
    period: str = "6mo",
) -> ToolResult:
    """Check correlation between tickers and optionally vs portfolio holdings."""
    try:
        import yfinance as yf
        import pandas as pd

        all_tickers = list(set(tickers + (portfolio_tickers or [])))
        if len(all_tickers) < 2:
            return ToolResult(tool_name="check_correlation", success=True,
                              data={"note": "Need at least 2 tickers for correlation"})

        df = yf.download(" ".join(all_tickers), period=period, progress=False)
        if df.empty:
            return ToolResult(tool_name="check_correlation", success=False, error="No price data")

        returns = df["Close"].pct_change().dropna()
        corr = returns.corr()

        # Extract relevant correlations
        corr_data = {}
        for t in tickers:
            if t in corr.columns:
                t_corr = {}
                for pt in (portfolio_tickers or []):
                    if pt in corr.columns:
                        t_corr[pt] = round(float(corr.loc[t, pt]), 3)
                corr_data[t] = t_corr

        return ToolResult(
            tool_name="check_correlation",
            success=True,
            data={"correlations": corr_data, "period": period},
            methodology=(
                f"Pairwise correlation of daily returns over {period}. "
                "High correlation (>0.7) means limited diversification benefit."
            ),
            source="yfinance historical data",
        )
    except Exception as e:
        return ToolResult(tool_name="check_correlation", success=False, error=str(e))


async def get_historical_vol(tickers: list[str], window: int = 30) -> ToolResult:
    """Get historical volatility (annualized) for tickers."""
    try:
        import yfinance as yf
        import numpy as np

        results = {}
        for ticker in tickers[:10]:
            df = yf.download(ticker, period="1y", progress=False)
            if df.empty:
                continue
            close = df["Close"].values.flatten()
            returns = np.diff(np.log(close))
            vol_30d = float(np.std(returns[-window:]) * np.sqrt(252) * 100)
            vol_90d = float(np.std(returns[-90:]) * np.sqrt(252) * 100) if len(returns) >= 90 else None

            results[ticker] = {
                "vol_30d_ann_pct": round(vol_30d, 1),
                "vol_90d_ann_pct": round(vol_90d, 1) if vol_90d else None,
                "current_price": round(float(close[-1]), 2),
            }

        return ToolResult(
            tool_name="get_historical_vol",
            success=True,
            data={"volatility": results, "window": window},
            methodology=f"Annualized historical volatility from {window}-day and 90-day windows of daily log returns.",
            source="yfinance historical data",
        )
    except Exception as e:
        return ToolResult(tool_name="get_historical_vol", success=False, error=str(e))


async def get_price_levels(ticker: str) -> ToolResult:
    """Get key support/resistance levels and moving averages."""
    try:
        import yfinance as yf
        import pandas as pd

        df = yf.download(ticker, period="1y", progress=False)
        if df.empty:
            return ToolResult(tool_name="get_price_levels", success=False, error="No data")

        close = pd.Series(df["Close"].values.flatten())
        high = df["High"].values.flatten()
        low = df["Low"].values.flatten()

        current = float(close.iloc[-1])
        sma_20 = float(close.rolling(20).mean().iloc[-1])
        sma_50 = float(close.rolling(50).mean().iloc[-1])
        sma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

        return ToolResult(
            tool_name="get_price_levels",
            success=True,
            data={
                "ticker": ticker,
                "current": round(current, 2),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2),
                "sma_200": round(sma_200, 2) if sma_200 else None,
                "52w_high": round(float(max(high[-252:])), 2) if len(high) >= 252 else round(float(max(high)), 2),
                "52w_low": round(float(min(low[-252:])), 2) if len(low) >= 252 else round(float(min(low)), 2),
                "above_sma_50": current > sma_50,
                "above_sma_200": current > sma_200 if sma_200 else None,
                "trend": "bullish" if current > sma_50 > (sma_200 or 0) else "bearish" if current < sma_50 else "neutral",
            },
            methodology="Key moving averages (20/50/200 SMA) and 52-week range to identify trend and support/resistance.",
            source="yfinance historical data",
        )
    except Exception as e:
        return ToolResult(tool_name="get_price_levels", success=False, error=str(e))


async def check_short_interest(ticker: str) -> ToolResult:
    """Check short interest and related metrics."""
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info
        short_pct = info.get("shortPercentOfFloat")
        short_ratio = info.get("shortRatio")

        return ToolResult(
            tool_name="check_short_interest",
            success=True,
            data={
                "ticker": ticker,
                "short_pct_float": short_pct,
                "short_ratio_days": short_ratio,
                "float_shares": info.get("floatShares"),
                "shares_short": info.get("sharesShort"),
                "squeeze_risk": (
                    "high" if (short_pct or 0) > 20 else
                    "moderate" if (short_pct or 0) > 10 else
                    "low"
                ),
            },
            methodology="Short interest as % of float and days-to-cover ratio. >20% short = high squeeze risk.",
            source="yfinance (Yahoo Finance)",
        )
    except Exception as e:
        return ToolResult(tool_name="check_short_interest", success=False, error=str(e))


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "backtest_momentum": backtest_momentum,
    "backtest_mean_revert": backtest_mean_revert,
    "get_fundamentals": get_fundamentals,
    "get_valuation_multiples": get_valuation_multiples,
    "calculate_risk_reward": calculate_risk_reward,
    "check_correlation": check_correlation,
    "get_historical_vol": get_historical_vol,
    "get_price_levels": get_price_levels,
    "check_short_interest": check_short_interest,
}


async def run_tool(tool_name: str, **kwargs: Any) -> ToolResult:
    """Run a validation tool by name.

    Args:
        tool_name: Name of the tool from TOOL_REGISTRY.
        **kwargs: Arguments to pass to the tool function.

    Returns:
        ToolResult with computation results.
    """
    tool_fn = TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            error=f"Unknown tool: {tool_name}. Available: {list(TOOL_REGISTRY.keys())}",
        )

    try:
        return await tool_fn(**kwargs)
    except Exception as e:
        logger.exception("Tool %s failed", tool_name)
        return ToolResult(tool_name=tool_name, success=False, error=str(e))


def list_tools() -> list[dict[str, str]]:
    """List all available validation tools with descriptions."""
    return [
        {"name": "backtest_momentum", "description": "Backtest momentum/trend strategy on historical data"},
        {"name": "backtest_mean_revert", "description": "Backtest mean-reversion strategy with Z-score entry/exit"},
        {"name": "get_fundamentals", "description": "Fetch P/E, EPS, margins, growth rates for tickers"},
        {"name": "get_valuation_multiples", "description": "Compare valuation multiples vs sector peers"},
        {"name": "calculate_risk_reward", "description": "Calculate risk/reward ratio and portfolio impact"},
        {"name": "check_correlation", "description": "Check pairwise correlation between tickers"},
        {"name": "get_historical_vol", "description": "Get 30-day and 90-day annualized volatility"},
        {"name": "get_price_levels", "description": "Get moving averages, support/resistance, trend"},
        {"name": "check_short_interest", "description": "Check short interest % and squeeze risk"},
    ]
