"""
Market Data API routes.

Fetches real-time and historical price/volume data for equities, futures,
and crypto using yfinance. Provides price snapshots and OHLCV history.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Watchlists (default tickers for each asset class)
# ---------------------------------------------------------------------------

EQUITY_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM",
    "GS", "V", "UNH", "JNJ", "XOM", "PG", "HD", "BAC",
]

FUTURES_TICKERS = [
    "ES=F",   # S&P 500 E-mini
    "NQ=F",   # Nasdaq 100 E-mini
    "YM=F",   # Dow Jones E-mini
    "RTY=F",  # Russell 2000 E-mini
    "CL=F",   # Crude Oil
    "GC=F",   # Gold
    "SI=F",   # Silver
    "ZB=F",   # 30-Year Treasury Bond
    "ZN=F",   # 10-Year Treasury Note
    "NG=F",   # Natural Gas
]

CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "DOT-USD", "MATIC-USD",
]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PriceSnapshot(BaseModel):
    symbol: str
    price: float | None
    change: float | None
    change_pct: float | None
    volume: int | None
    market_cap: float | None
    asset_class: str
    updated_at: str


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class HistoryResponse(BaseModel):
    symbol: str
    period: str
    interval: str
    bars: list[OHLCVBar]


class WatchlistResponse(BaseModel):
    asset_class: str
    tickers: list[str]
    prices: list[PriceSnapshot]
    fetched_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _classify_ticker(symbol: str) -> str:
    """Determine asset class from ticker symbol."""
    if symbol.endswith("-USD") or symbol.endswith("-USDT"):
        return "crypto"
    if symbol.endswith("=F"):
        return "futures"
    return "equities"


async def _fetch_price(symbol: str) -> PriceSnapshot:
    """Fetch current price for a single ticker via yfinance."""
    def _sync_fetch():
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)
            market_cap = getattr(info, "market_cap", None)

            change = None
            change_pct = None
            if price is not None and prev_close is not None and prev_close > 0:
                change = round(price - prev_close, 4)
                change_pct = round(change / prev_close, 6)

            # Try to get volume
            hist = ticker.history(period="1d")
            volume = int(hist["Volume"].iloc[-1]) if not hist.empty else None

            return PriceSnapshot(
                symbol=symbol,
                price=round(price, 4) if price else None,
                change=change,
                change_pct=change_pct,
                volume=volume,
                market_cap=market_cap,
                asset_class=_classify_ticker(symbol),
                updated_at=_now_iso(),
            )
        except Exception as exc:
            logger.warning("Failed to fetch price for %s: %s", symbol, exc)
            return PriceSnapshot(
                symbol=symbol,
                price=None,
                change=None,
                change_pct=None,
                volume=None,
                market_cap=None,
                asset_class=_classify_ticker(symbol),
                updated_at=_now_iso(),
            )

    return await asyncio.to_thread(_sync_fetch)


async def _fetch_history(symbol: str, period: str, interval: str) -> list[OHLCVBar]:
    """Fetch OHLCV history for a single ticker."""
    def _sync_fetch():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            bars = []
            for idx, row in hist.iterrows():
                bars.append(OHLCVBar(
                    date=idx.isoformat(),
                    open=round(row["Open"], 4),
                    high=round(row["High"], 4),
                    low=round(row["Low"], 4),
                    close=round(row["Close"], 4),
                    volume=int(row["Volume"]),
                ))
            return bars
        except Exception as exc:
            logger.warning("Failed to fetch history for %s: %s", symbol, exc)
            return []

    return await asyncio.to_thread(_sync_fetch)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/price/{symbol}", response_model=PriceSnapshot)
async def get_price(symbol: str):
    """Get current price snapshot for a single ticker."""
    return await _fetch_price(symbol.upper())


@router.get("/prices", response_model=list[PriceSnapshot])
async def get_prices(
    symbols: str = Query(..., description="Comma-separated ticker symbols"),
):
    """Get current prices for multiple tickers."""
    ticker_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(ticker_list) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 symbols per request")

    tasks = [_fetch_price(s) for s in ticker_list]
    results = await asyncio.gather(*tasks)
    return list(results)


@router.get("/history/{symbol}", response_model=HistoryResponse)
async def get_history(
    symbol: str,
    period: str = Query("1mo", description="1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max"),
    interval: str = Query("1d", description="1m, 5m, 15m, 1h, 1d, 1wk, 1mo"),
):
    """Get OHLCV history for a ticker."""
    bars = await _fetch_history(symbol.upper(), period, interval)
    return HistoryResponse(
        symbol=symbol.upper(),
        period=period,
        interval=interval,
        bars=bars,
    )


@router.get("/watchlist/{asset_class}", response_model=WatchlistResponse)
async def get_watchlist(
    asset_class: str,
):
    """Get prices for a predefined watchlist by asset class."""
    tickers_map = {
        "equities": EQUITY_TICKERS,
        "futures": FUTURES_TICKERS,
        "crypto": CRYPTO_TICKERS,
    }

    tickers = tickers_map.get(asset_class)
    if tickers is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown asset class '{asset_class}'. Must be one of: {', '.join(tickers_map.keys())}",
        )

    tasks = [_fetch_price(s) for s in tickers]
    prices = await asyncio.gather(*tasks)

    return WatchlistResponse(
        asset_class=asset_class,
        tickers=tickers,
        prices=list(prices),
        fetched_at=_now_iso(),
    )


@router.get("/watchlists", response_model=dict[str, list[str]])
async def get_all_watchlists():
    """Get all available watchlist tickers organized by asset class."""
    return {
        "equities": EQUITY_TICKERS,
        "futures": FUTURES_TICKERS,
        "crypto": CRYPTO_TICKERS,
    }
