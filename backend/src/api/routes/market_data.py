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


# ---------------------------------------------------------------------------
# Asset Detail Endpoints (info, news, social, summary)
# ---------------------------------------------------------------------------


class AssetInfo(BaseModel):
    symbol: str
    name: str | None
    asset_class: str
    sector: str | None
    industry: str | None
    price: float | None
    previous_close: float | None
    change: float | None
    change_pct: float | None
    open: float | None
    day_high: float | None
    day_low: float | None
    volume: int | None
    avg_volume: int | None
    market_cap: float | None
    pe_ratio: float | None
    forward_pe: float | None
    dividend_yield: float | None
    beta: float | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    eps: float | None
    description: str | None
    updated_at: str


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: str | None
    summary: str | None
    tickers: list[str]
    sentiment: float | None


class SocialPost(BaseModel):
    title: str
    content: str
    source: str
    url: str
    author: str | None
    score: int
    comments: int
    published_at: str | None
    sentiment: str | None


class AssetSummary(BaseModel):
    symbol: str
    name: str | None
    price: float | None
    change_pct: float | None
    short_term_outlook: str
    medium_term_outlook: str
    key_factors: list[str]
    risks: list[str]
    opportunities: list[str]
    news_sentiment: str
    social_sentiment: str
    summary: str
    updated_at: str


@router.get("/info/{symbol}", response_model=AssetInfo)
async def get_asset_info(symbol: str):
    """Get comprehensive fundamental information for a ticker."""
    def _sync_fetch():
        try:
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info or {}
            fast = ticker.fast_info

            price = getattr(fast, "last_price", None)
            prev_close = getattr(fast, "previous_close", None)
            change = None
            change_pct = None
            if price and prev_close and prev_close > 0:
                change = round(price - prev_close, 4)
                change_pct = round(change / prev_close, 6)

            return AssetInfo(
                symbol=symbol.upper(),
                name=info.get("longName") or info.get("shortName"),
                asset_class=_classify_ticker(symbol.upper()),
                sector=info.get("sector"),
                industry=info.get("industry"),
                price=round(price, 4) if price else None,
                previous_close=round(prev_close, 4) if prev_close else None,
                change=change,
                change_pct=change_pct,
                open=info.get("open"),
                day_high=info.get("dayHigh"),
                day_low=info.get("dayLow"),
                volume=info.get("volume"),
                avg_volume=info.get("averageVolume"),
                market_cap=info.get("marketCap"),
                pe_ratio=info.get("trailingPE"),
                forward_pe=info.get("forwardPE"),
                dividend_yield=info.get("dividendYield"),
                beta=info.get("beta"),
                fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                eps=info.get("trailingEps"),
                description=info.get("longBusinessSummary"),
                updated_at=_now_iso(),
            )
        except Exception as exc:
            logger.warning("Failed to fetch info for %s: %s", symbol, exc)
            return AssetInfo(
                symbol=symbol.upper(),
                name=None, asset_class=_classify_ticker(symbol.upper()),
                sector=None, industry=None, price=None, previous_close=None,
                change=None, change_pct=None, open=None, day_high=None,
                day_low=None, volume=None, avg_volume=None, market_cap=None,
                pe_ratio=None, forward_pe=None, dividend_yield=None, beta=None,
                fifty_two_week_high=None, fifty_two_week_low=None, eps=None,
                description=None, updated_at=_now_iso(),
            )

    return await asyncio.to_thread(_sync_fetch)


@router.get("/news/{symbol}", response_model=list[NewsItem])
async def get_asset_news(symbol: str):
    """Get latest news for a ticker from RSS feeds."""
    import aiohttp
    import feedparser
    import re

    symbol_upper = symbol.upper()
    feeds = [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US".format(symbol=symbol_upper),
        f"https://news.google.com/rss/search?q={symbol_upper}+stock&hl=en-US&gl=US&ceid=US:en",
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://seekingalpha.com/market_currents.xml",
    ]

    async def _fetch_feed(url: str) -> list[NewsItem]:
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return []
                    text = await resp.text()

            feed = await asyncio.to_thread(feedparser.parse, text)
            items = []
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")

                # Check if the news is relevant to the symbol
                full_text = f"{title} {summary}".upper()
                if symbol_upper not in full_text and f"${symbol_upper}" not in full_text:
                    continue

                # Extract tickers
                ticker_matches = re.findall(r'\$([A-Z]{1,5})\b', f"{title} {summary}")

                pub_date = None
                if hasattr(entry, "published"):
                    pub_date = entry.published

                items.append(NewsItem(
                    title=title[:300],
                    source=feed.feed.get("title", url.split("/")[2]),
                    url=link,
                    published_at=pub_date,
                    summary=summary[:500] if summary else None,
                    tickers=list(set(ticker_matches)) or [symbol_upper],
                    sentiment=None,
                ))
            return items
        except Exception as exc:
            logger.debug("Feed fetch error for %s: %s", url, exc)
            return []

    all_tasks = [_fetch_feed(url) for url in feeds]
    results = await asyncio.gather(*all_tasks)

    all_items: list[NewsItem] = []
    for items in results:
        all_items.extend(items)

    # Deduplicate by title similarity and limit
    seen_titles: set[str] = set()
    unique_items: list[NewsItem] = []
    for item in all_items:
        short_title = item.title[:60].lower()
        if short_title not in seen_titles:
            seen_titles.add(short_title)
            unique_items.append(item)

    return unique_items[:20]


@router.get("/social/{symbol}", response_model=list[SocialPost])
async def get_asset_social(symbol: str):
    """Get latest Reddit posts mentioning a ticker."""
    import aiohttp

    symbol_upper = symbol.upper()
    subreddits = ["wallstreetbets", "investing", "stocks", "options"]

    async def _fetch_subreddit(sub: str) -> list[SocialPost]:
        try:
            url = f"https://www.reddit.com/r/{sub}/search.json?q={symbol_upper}&sort=new&limit=10&restrict_sr=on&t=week"
            timeout = aiohttp.ClientTimeout(total=10)
            headers = {"User-Agent": "Overture/1.0"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            posts = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                if post.get("removed_by_category") or post.get("selftext") == "[removed]":
                    continue

                score = post.get("score", 0)
                comments = post.get("num_comments", 0)

                # Simple sentiment from score
                sentiment = "positive" if score > 50 else ("negative" if score < 0 else "neutral")

                created_utc = post.get("created_utc")
                pub_date = None
                if created_utc:
                    from datetime import timezone
                    pub_date = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

                posts.append(SocialPost(
                    title=post.get("title", "")[:300],
                    content=(post.get("selftext", "") or "")[:500],
                    source=f"r/{sub}",
                    url=f"https://reddit.com{post.get('permalink', '')}",
                    author=post.get("author"),
                    score=score,
                    comments=comments,
                    published_at=pub_date,
                    sentiment=sentiment,
                ))
            return posts
        except Exception as exc:
            logger.debug("Reddit fetch error for r/%s: %s", sub, exc)
            return []

    all_tasks = [_fetch_subreddit(sub) for sub in subreddits]
    results = await asyncio.gather(*all_tasks)

    all_posts: list[SocialPost] = []
    for posts in results:
        all_posts.extend(posts)

    # Sort by score descending
    all_posts.sort(key=lambda p: p.score, reverse=True)
    return all_posts[:20]


@router.get("/summary/{symbol}", response_model=AssetSummary)
async def get_asset_summary(symbol: str):
    """Generate an AI-style summary for a ticker based on available data.

    Uses fundamental data and price action to create a structured outlook.
    In production this would invoke an LLM; for now it uses rule-based analysis.
    """
    def _sync_generate():
        try:
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info or {}
            fast = ticker.fast_info

            name = info.get("longName") or info.get("shortName") or symbol.upper()
            price = getattr(fast, "last_price", None)
            prev_close = getattr(fast, "previous_close", None)
            change_pct = None
            if price and prev_close and prev_close > 0:
                change_pct = round((price - prev_close) / prev_close, 6)

            # Get recent history for trend analysis
            hist = ticker.history(period="3mo")
            short_trend = "neutral"
            medium_trend = "neutral"
            if not hist.empty and len(hist) > 5:
                recent_5d = hist["Close"].iloc[-5:].mean()
                recent_20d = hist["Close"].iloc[-20:].mean() if len(hist) >= 20 else recent_5d
                recent_60d = hist["Close"].iloc[-60:].mean() if len(hist) >= 60 else recent_20d
                current = hist["Close"].iloc[-1]

                if current > recent_5d * 1.01:
                    short_trend = "bullish"
                elif current < recent_5d * 0.99:
                    short_trend = "bearish"

                if current > recent_60d * 1.03:
                    medium_trend = "bullish"
                elif current < recent_60d * 0.97:
                    medium_trend = "bearish"

            # Build factors
            key_factors = []
            risks = []
            opportunities = []

            pe = info.get("trailingPE")
            if pe:
                if pe < 15:
                    key_factors.append(f"Attractive valuation (P/E: {pe:.1f})")
                    opportunities.append("Value opportunity at current multiples")
                elif pe > 35:
                    key_factors.append(f"Premium valuation (P/E: {pe:.1f})")
                    risks.append("Elevated valuation may limit upside")
                else:
                    key_factors.append(f"Fair valuation (P/E: {pe:.1f})")

            beta = info.get("beta")
            if beta:
                if beta > 1.3:
                    risks.append(f"High beta ({beta:.2f}) implies elevated volatility")
                elif beta < 0.7:
                    opportunities.append(f"Low beta ({beta:.2f}) provides defensive characteristics")

            div_yield = info.get("dividendYield")
            if div_yield and div_yield > 0.02:
                opportunities.append(f"Dividend yield of {div_yield*100:.1f}% provides income")

            mc = info.get("marketCap")
            if mc:
                if mc > 500e9:
                    key_factors.append("Mega-cap with strong market presence")
                elif mc > 10e9:
                    key_factors.append("Large-cap with established market position")

            sector = info.get("sector", "")
            if sector:
                key_factors.append(f"Operates in {sector} sector")

            week52_high = info.get("fiftyTwoWeekHigh")
            if week52_high and price:
                pct_from_high = (price - week52_high) / week52_high
                if pct_from_high > -0.05:
                    key_factors.append("Trading near 52-week high")
                    risks.append("Limited upside from current levels near highs")
                elif pct_from_high < -0.20:
                    opportunities.append(f"Trading {abs(pct_from_high)*100:.0f}% below 52-week high")

            if not key_factors:
                key_factors.append(f"Current price: ${price:.2f}" if price else "Price data unavailable")
            if not risks:
                risks.append("Market-wide systematic risk")
            if not opportunities:
                opportunities.append("Monitor for entry points on pullbacks")

            # Generate summary text
            trend_word = {"bullish": "positive", "bearish": "negative", "neutral": "mixed"}.get(medium_trend, "mixed")
            summary = (
                f"{name} is showing {trend_word} medium-term momentum. "
                f"{'The stock trades at a P/E of ' + f'{pe:.1f}' + ', ' if pe else ''}"
                f"{'suggesting ' + ('undervaluation' if pe and pe < 18 else 'fair value' if pe and pe < 30 else 'growth premium') + '. ' if pe else ''}"
                f"Short-term price action is {short_trend} with the stock "
                f"{'above' if short_trend == 'bullish' else 'below' if short_trend == 'bearish' else 'near'} "
                f"its 5-day moving average."
            )

            return AssetSummary(
                symbol=symbol.upper(),
                name=name,
                price=round(price, 4) if price else None,
                change_pct=change_pct,
                short_term_outlook=short_trend,
                medium_term_outlook=medium_trend,
                key_factors=key_factors[:5],
                risks=risks[:4],
                opportunities=opportunities[:4],
                news_sentiment="neutral",
                social_sentiment="neutral",
                summary=summary,
                updated_at=_now_iso(),
            )
        except Exception as exc:
            logger.warning("Failed to generate summary for %s: %s", symbol, exc)
            return AssetSummary(
                symbol=symbol.upper(), name=None, price=None, change_pct=None,
                short_term_outlook="neutral", medium_term_outlook="neutral",
                key_factors=["Data unavailable"], risks=["Data unavailable"],
                opportunities=["Data unavailable"], news_sentiment="neutral",
                social_sentiment="neutral", summary=f"Unable to generate summary for {symbol.upper()} at this time.",
                updated_at=_now_iso(),
            )

    return await asyncio.to_thread(_sync_generate)
