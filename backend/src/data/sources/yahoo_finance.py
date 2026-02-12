"""
Yahoo Finance data source connector.

Provides price data, fundamentals, options chains, anomaly detection, and
stock screening via the ``yfinance`` library.  Because yfinance is synchronous,
every blocking call is dispatched through ``asyncio.to_thread`` so the event
loop is never stalled.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import yfinance as yf

from src.data.sources.base import BaseDataSource, DataItem

logger = logging.getLogger(__name__)


class YahooFinanceSource(BaseDataSource):
    """Connector to Yahoo Finance via the ``yfinance`` library.

    Exposes helpers for price history, company info, options chains,
    unusual-move detection, and simple fundamental screening.
    """

    def __init__(self) -> None:
        super().__init__(name="yahoo_finance", source_type="price")

    # ------------------------------------------------------------------
    # BaseDataSource interface
    # ------------------------------------------------------------------

    async def fetch(self, **kwargs) -> list[DataItem]:
        """Generic entry point.  Delegates to specialised helpers based on
        the ``action`` keyword argument.

        Supported actions:
            price   -> fetch_price(ticker, period, interval)
            info    -> fetch_info(ticker)
            options -> fetch_options(ticker)
            screen  -> screen(criteria)
            anomaly -> detect_unusual_moves(tickers, threshold_sigma)
        """

        action = kwargs.get("action", "price")
        ticker = kwargs.get("ticker", "SPY")
        tickers = kwargs.get("tickers", [ticker])

        if action == "price":
            return [
                await self.fetch_price(
                    ticker=ticker,
                    period=kwargs.get("period", "5d"),
                    interval=kwargs.get("interval", "1d"),
                )
            ]
        elif action == "info":
            return [await self.fetch_info(ticker)]
        elif action == "options":
            return await self.fetch_options(ticker)
        elif action == "screen":
            return await self.screen(kwargs.get("criteria", {}))
        elif action == "anomaly":
            return await self.detect_unusual_moves(
                tickers=tickers,
                threshold_sigma=kwargs.get("threshold_sigma", 3.0),
            )
        else:
            logger.warning("Unknown action '%s', falling back to price fetch.", action)
            return [await self.fetch_price(ticker=ticker)]

    async def health_check(self) -> bool:
        """Validate connectivity by requesting a single-day quote for SPY."""
        try:
            data = await asyncio.to_thread(
                lambda: yf.Ticker("SPY").history(period="1d")
            )
            return len(data) > 0
        except Exception:
            logger.exception("Yahoo Finance health check failed")
            return False

    # ------------------------------------------------------------------
    # Price data
    # ------------------------------------------------------------------

    async def fetch_price(
        self,
        ticker: str = "SPY",
        period: str = "5d",
        interval: str = "1d",
    ) -> DataItem:
        """Fetch OHLCV price history for *ticker*.

        Args:
            ticker: Equity / ETF symbol.
            period: yfinance period string (e.g. "1mo", "1y", "max").
            interval: Bar width (e.g. "1m", "5m", "1d").

        Returns:
            A ``DataItem`` with ``metadata`` containing the OHLCV DataFrame
            serialized as a list of row dicts.
        """

        logger.info("Fetching price data for %s (period=%s, interval=%s)", ticker, period, interval)

        def _fetch() -> dict[str, Any]:
            t = yf.Ticker(ticker)
            hist = t.history(period=period, interval=interval)
            if hist.empty:
                return {"rows": [], "last_close": None, "last_volume": None}
            rows = hist.reset_index().to_dict(orient="records")
            # Convert Timestamps to ISO strings for JSON-safety
            for row in rows:
                for key, val in row.items():
                    if hasattr(val, "isoformat"):
                        row[key] = val.isoformat()
            last = hist.iloc[-1]
            return {
                "rows": rows,
                "last_close": float(last["Close"]),
                "last_volume": int(last["Volume"]) if "Volume" in last.index else None,
            }

        result = await asyncio.to_thread(_fetch)
        num_bars = len(result["rows"])
        content_parts = [f"{ticker} — {num_bars} bars ({period} / {interval})"]
        if result["last_close"] is not None:
            content_parts.append(f"Last close: {result['last_close']:.2f}")
        if result["last_volume"] is not None:
            content_parts.append(f"Last volume: {result['last_volume']:,}")

        return DataItem(
            source=self.name,
            source_type="price",
            title=f"{ticker} Price Data",
            content=" | ".join(content_parts),
            tickers=[ticker],
            asset_classes=["equity"],
            metadata={
                "period": period,
                "interval": interval,
                "num_bars": num_bars,
                "last_close": result["last_close"],
                "last_volume": result["last_volume"],
                "ohlcv": result["rows"],
            },
        )

    # ------------------------------------------------------------------
    # Company info / fundamentals
    # ------------------------------------------------------------------

    async def fetch_info(self, ticker: str) -> DataItem:
        """Fetch company profile and key fundamental ratios.

        Returns a ``DataItem`` whose ``metadata`` dict mirrors the raw
        ``yfinance.Ticker.info`` payload, supplemented with curated fields.
        """

        logger.info("Fetching company info for %s", ticker)

        def _fetch() -> dict[str, Any]:
            t = yf.Ticker(ticker)
            info: dict[str, Any] = t.info or {}
            return info

        info = await asyncio.to_thread(_fetch)

        name = info.get("longName") or info.get("shortName") or ticker
        sector = info.get("sector", "N/A")
        industry = info.get("industry", "N/A")
        market_cap = info.get("marketCap")
        pe_ratio = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        dividend_yield = info.get("dividendYield")
        summary = info.get("longBusinessSummary", "")

        content_lines = [
            f"Name: {name}",
            f"Sector: {sector} | Industry: {industry}",
        ]
        if market_cap is not None:
            content_lines.append(f"Market Cap: ${market_cap:,.0f}")
        if pe_ratio is not None:
            content_lines.append(f"Trailing P/E: {pe_ratio:.2f}")
        if forward_pe is not None:
            content_lines.append(f"Forward P/E: {forward_pe:.2f}")
        if dividend_yield is not None:
            content_lines.append(f"Dividend Yield: {dividend_yield:.2%}")

        return DataItem(
            source=self.name,
            source_type="research",
            title=f"{ticker} Company Info",
            content="\n".join(content_lines),
            tickers=[ticker],
            asset_classes=["equity"],
            metadata={
                "name": name,
                "sector": sector,
                "industry": industry,
                "market_cap": market_cap,
                "trailing_pe": pe_ratio,
                "forward_pe": forward_pe,
                "dividend_yield": dividend_yield,
                "summary": summary,
                "raw_info": info,
            },
        )

    # ------------------------------------------------------------------
    # Options chain
    # ------------------------------------------------------------------

    async def fetch_options(self, ticker: str) -> list[DataItem]:
        """Fetch the full options chain for *ticker*.

        Returns one ``DataItem`` per expiration date, with calls and puts
        serialized inside ``metadata``.
        """

        logger.info("Fetching options chain for %s", ticker)

        def _fetch() -> list[dict[str, Any]]:
            t = yf.Ticker(ticker)
            expirations: tuple[str, ...] = t.options  # type: ignore[assignment]
            results: list[dict[str, Any]] = []
            for exp in expirations:
                chain = t.option_chain(exp)
                calls = chain.calls.to_dict(orient="records") if chain.calls is not None else []
                puts = chain.puts.to_dict(orient="records") if chain.puts is not None else []
                results.append({"expiration": exp, "calls": calls, "puts": puts})
            return results

        chains = await asyncio.to_thread(_fetch)

        items: list[DataItem] = []
        for chain in chains:
            exp = chain["expiration"]
            num_calls = len(chain["calls"])
            num_puts = len(chain["puts"])
            items.append(
                DataItem(
                    source=self.name,
                    source_type="price",
                    title=f"{ticker} Options — {exp}",
                    content=f"Expiration {exp}: {num_calls} calls, {num_puts} puts",
                    tickers=[ticker],
                    asset_classes=["equity", "options"],
                    metadata={
                        "expiration": exp,
                        "num_calls": num_calls,
                        "num_puts": num_puts,
                        "calls": chain["calls"],
                        "puts": chain["puts"],
                    },
                )
            )
        return items

    # ------------------------------------------------------------------
    # Anomaly / unusual-move detection
    # ------------------------------------------------------------------

    async def detect_unusual_moves(
        self,
        tickers: list[str],
        threshold_sigma: float = 3.0,
        lookback_days: int = 252,
    ) -> list[DataItem]:
        """Detect tickers whose latest daily return exceeds *threshold_sigma*
        standard deviations from the historical mean.

        This is the kind of signal that would flag a 10-sigma move in silver,
        for example.

        Args:
            tickers: List of ticker symbols to scan.
            threshold_sigma: Number of standard deviations to flag.
            lookback_days: Calendar days of history used for the mean / std.

        Returns:
            A list of ``DataItem`` objects, one per anomaly detected.
        """

        logger.info(
            "Scanning %d tickers for moves > %.1f sigma",
            len(tickers),
            threshold_sigma,
        )

        def _scan() -> list[dict[str, Any]]:
            anomalies: list[dict[str, Any]] = []
            for sym in tickers:
                try:
                    t = yf.Ticker(sym)
                    hist = t.history(period=f"{lookback_days}d")
                    if hist.empty or len(hist) < 20:
                        continue

                    returns = hist["Close"].pct_change().dropna()
                    if returns.std() == 0:
                        continue

                    mean_ret = float(returns.mean())
                    std_ret = float(returns.std())
                    latest_ret = float(returns.iloc[-1])
                    z_score = (latest_ret - mean_ret) / std_ret

                    if abs(z_score) >= threshold_sigma:
                        anomalies.append(
                            {
                                "ticker": sym,
                                "latest_return": latest_ret,
                                "z_score": z_score,
                                "mean_return": mean_ret,
                                "std_return": std_ret,
                                "last_close": float(hist["Close"].iloc[-1]),
                                "prev_close": float(hist["Close"].iloc[-2]),
                            }
                        )
                except Exception:
                    logger.warning("Error scanning %s for anomalies", sym, exc_info=True)
            return anomalies

        anomalies = await asyncio.to_thread(_scan)

        items: list[DataItem] = []
        for a in anomalies:
            direction = "up" if a["z_score"] > 0 else "down"
            items.append(
                DataItem(
                    source=self.name,
                    source_type="price",
                    title=f"ANOMALY: {a['ticker']} moved {abs(a['z_score']):.1f}σ {direction}",
                    content=(
                        f"{a['ticker']} returned {a['latest_return']:.2%} "
                        f"(z={a['z_score']:.2f}) vs mean={a['mean_return']:.4f}, "
                        f"std={a['std_return']:.4f}. "
                        f"Close: {a['last_close']:.2f} (prev {a['prev_close']:.2f})."
                    ),
                    tickers=[a["ticker"]],
                    asset_classes=["equity"],
                    relevance_score=min(abs(a["z_score"]) / 10.0, 1.0),
                    metadata=a,
                )
            )
        return items

    # ------------------------------------------------------------------
    # Stock screener
    # ------------------------------------------------------------------

    async def screen(self, criteria: dict[str, Any]) -> list[DataItem]:
        """Screen a universe of tickers against fundamental / technical
        criteria.

        Supported criteria keys (all optional):
            tickers         : list[str]  — universe to screen (default: S&P-500
                              subset via a small hard-coded list).
            min_market_cap  : float
            max_market_cap  : float
            min_pe          : float
            max_pe          : float
            min_volume      : int
            min_dividend    : float
            sector          : str

        Returns:
            A ``DataItem`` per ticker that passes all filters.
        """

        # Default small universe if none specified
        universe: list[str] = criteria.get(
            "tickers",
            [
                "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA",
                "JPM", "V", "JNJ", "WMT", "PG", "XOM", "UNH", "HD",
                "BAC", "PFE", "CSCO", "ADBE", "CRM", "NFLX", "AMD",
                "INTC", "QCOM", "COST",
            ],
        )

        min_market_cap = criteria.get("min_market_cap")
        max_market_cap = criteria.get("max_market_cap")
        min_pe = criteria.get("min_pe")
        max_pe = criteria.get("max_pe")
        min_volume = criteria.get("min_volume")
        min_dividend = criteria.get("min_dividend")
        sector_filter = criteria.get("sector")

        logger.info("Running screen on %d tickers with criteria: %s", len(universe), criteria)

        def _screen() -> list[dict[str, Any]]:
            matches: list[dict[str, Any]] = []
            for sym in universe:
                try:
                    info = yf.Ticker(sym).info or {}

                    mc = info.get("marketCap")
                    pe = info.get("trailingPE")
                    vol = info.get("averageVolume")
                    div_yield = info.get("dividendYield")
                    sec = info.get("sector")

                    # Apply filters
                    if min_market_cap is not None and (mc is None or mc < min_market_cap):
                        continue
                    if max_market_cap is not None and (mc is None or mc > max_market_cap):
                        continue
                    if min_pe is not None and (pe is None or pe < min_pe):
                        continue
                    if max_pe is not None and (pe is None or pe > max_pe):
                        continue
                    if min_volume is not None and (vol is None or vol < min_volume):
                        continue
                    if min_dividend is not None and (div_yield is None or div_yield < min_dividend):
                        continue
                    if sector_filter is not None and sec != sector_filter:
                        continue

                    matches.append(
                        {
                            "ticker": sym,
                            "name": info.get("longName") or info.get("shortName") or sym,
                            "market_cap": mc,
                            "trailing_pe": pe,
                            "average_volume": vol,
                            "dividend_yield": div_yield,
                            "sector": sec,
                            "industry": info.get("industry"),
                        }
                    )
                except Exception:
                    logger.warning("Error screening %s", sym, exc_info=True)
            return matches

        matches = await asyncio.to_thread(_screen)

        items: list[DataItem] = []
        for m in matches:
            summary_parts: list[str] = [f"{m['ticker']} ({m['name']})"]
            if m["market_cap"]:
                summary_parts.append(f"MCap: ${m['market_cap']:,.0f}")
            if m["trailing_pe"]:
                summary_parts.append(f"P/E: {m['trailing_pe']:.2f}")
            if m["average_volume"]:
                summary_parts.append(f"AvgVol: {m['average_volume']:,}")

            items.append(
                DataItem(
                    source=self.name,
                    source_type="screen",
                    title=f"Screen Match: {m['ticker']}",
                    content=" | ".join(summary_parts),
                    tickers=[m["ticker"]],
                    asset_classes=["equity"],
                    metadata=m,
                )
            )
        return items
