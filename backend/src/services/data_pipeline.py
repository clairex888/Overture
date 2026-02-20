"""Centralized Data Pipeline for Agent Ingestion.

Architecture Decision: CENTRALIZED pipeline over per-agent fetching.

Why centralized is better:
  1. Avoids redundant API calls (6 agents hitting the same API = 6x cost)
  2. Consistent data snapshot — all agents analyze the same data simultaneously
  3. Rate limit management in ONE place instead of distributed chaos
  4. Agents focus purely on ANALYSIS, not data collection
  5. Easy to add new data sources without modifying agents
  6. Data quality checks happen once at ingestion, not per-agent

Data Flow:
    External APIs ──→ DataPipeline.collect() ──→ normalized DataSnapshot
                                                      │
    ┌─────────────────────────────────────────────────┘
    │
    ├──→ MacroNewsAgent (gets macro-tagged news + rates + yield data)
    ├──→ IndustryNewsAgent (gets sector news + earnings + screens)
    ├──→ CryptoAgent (gets crypto news + on-chain + prices)
    ├──→ CommoditiesAgent (gets commodity news + inventory + prices)
    ├──→ QuantSystematicAgent (gets market data + screen results)
    └──→ SocialMediaAgent (gets social signals + sentiment scores)

Each agent receives the FULL DataSnapshot but filters to its domain
using the keyword classifiers in parallel_generators.py.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DataSnapshot:
    """Immutable snapshot of market data collected by the pipeline.

    All generators receive the same snapshot to ensure consistency.
    Each agent filters the snapshot to extract domain-relevant data.
    """
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # News articles (all domains mixed, agents filter by keywords)
    news_items: list[dict] = field(default_factory=list)

    # Market data: prices, volumes, technicals
    market_data: dict[str, Any] = field(default_factory=dict)

    # Social media signals (Reddit, X, Substack)
    social_signals: list[dict] = field(default_factory=list)

    # Quantitative screen results
    screen_results: list[dict] = field(default_factory=list)

    # Commodity-specific: inventory reports, OPEC data
    commodity_data: dict[str, Any] = field(default_factory=dict)

    # Crypto-specific: on-chain metrics
    crypto_data: dict[str, Any] = field(default_factory=dict)

    # Metadata: data quality, staleness, source counts
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_agent_input(self) -> dict[str, Any]:
        """Convert snapshot to the dict format agents expect."""
        return {
            "news_items": self.news_items,
            "market_data": {
                **self.market_data,
                **(self.commodity_data if self.commodity_data else {}),
                **(self.crypto_data if self.crypto_data else {}),
            },
            "social_signals": self.social_signals,
            "screen_results": self.screen_results,
        }


class DataCollector:
    """Abstract base for pluggable data source collectors."""

    name: str = "base"

    async def collect(self) -> dict[str, Any]:
        """Collect data from this source. Returns raw data dict."""
        raise NotImplementedError


class NewsCollector(DataCollector):
    """Collects news from RSS feeds and optional news APIs.

    Uses the real RSSNewsSource connector which fetches from Reuters,
    CNBC, Bloomberg, MarketWatch, Yahoo Finance, and other financial
    news RSS feeds — no API key required.
    """

    name = "news"

    def __init__(self, api_key: str = "", sources: list[str] | None = None):
        self.api_key = api_key
        self.sources = sources or []

    async def collect(self) -> dict[str, Any]:
        """Fetch news from RSS feeds (always works) + optional news API."""
        from dataclasses import asdict
        all_news: list[dict] = []

        # 1. RSS feeds — always available, no API key needed
        try:
            from src.data.sources.news_rss import RSSNewsSource
            rss = RSSNewsSource()
            rss_items = await rss.fetch()
            for item in rss_items:
                d = asdict(item)
                d["source_type"] = "news"
                all_news.append(d)
            logger.info("RSS news collected %d articles", len(rss_items))
        except Exception:
            logger.warning("RSS news collection failed", exc_info=True)

        # 2. Optional: paid news API (NewsAPI, Alpha Vantage, etc.)
        if self.api_key:
            try:
                # Placeholder for premium news API integration
                pass
            except Exception:
                logger.warning("Premium news API collection failed", exc_info=True)

        return {"news_items": all_news}


class MarketDataCollector(DataCollector):
    """Collects market prices, volumes, and technical indicators via yfinance."""

    name = "market_data"

    def __init__(self, watchlist: list[str] | None = None):
        self.watchlist = watchlist or [
            # Major indices
            "SPY", "QQQ", "IWM", "DIA", "VIX",
            # Sectors
            "XLK", "XLF", "XLE", "XLV", "XLI", "XLU",
            # Bonds
            "TLT", "IEF", "HYG", "LQD",
            # Commodities
            "GLD", "SLV", "USO", "UNG", "DBC",
            # Crypto proxies
            "BTC-USD", "ETH-USD",
            # FX
            "UUP", "FXE",
        ]

    async def collect(self) -> dict[str, Any]:
        """Fetch current prices and daily changes for watchlist."""
        try:
            import yfinance as yf
            data: dict[str, Any] = {"prices": {}, "changes": {}}

            # Use yfinance download for batch efficiency
            tickers_str = " ".join(self.watchlist)
            df = yf.download(
                tickers_str, period="5d", interval="1d",
                progress=False, threads=True,
            )

            if df.empty:
                return {"market_data": data}

            for ticker in self.watchlist:
                try:
                    if len(self.watchlist) > 1:
                        close = df["Close"][ticker]
                    else:
                        close = df["Close"]
                    if close.empty:
                        continue
                    last = float(close.iloc[-1])
                    prev = float(close.iloc[-2]) if len(close) > 1 else last
                    pct_change = ((last - prev) / prev * 100) if prev != 0 else 0

                    data["prices"][ticker] = round(last, 2)
                    data["changes"][ticker] = round(pct_change, 2)
                except (KeyError, IndexError):
                    continue

            return {"market_data": data}
        except ImportError:
            logger.debug("yfinance not available, skipping market data")
            return {"market_data": {}}
        except Exception:
            logger.warning("Market data collection failed", exc_info=True)
            return {"market_data": {}}


class SocialCollector(DataCollector):
    """Collects social media signals from Reddit, X/Twitter, and Substack.

    Uses the real data source connectors:
      - RedditSource (public JSON API — no auth needed)
      - SocialAggregatorSource (Substack RSS + X API v2)
    """

    name = "social"

    async def collect(self) -> dict[str, Any]:
        """Fetch social signals from all available platforms."""
        from dataclasses import asdict
        from src.data.sources.reddit import RedditSource
        from src.data.sources.social import SocialAggregatorSource

        all_signals: list[dict] = []

        # 1. Reddit (always works — no auth needed)
        try:
            reddit = RedditSource()
            reddit_items = await reddit.fetch(limit=20)
            for item in reddit_items:
                d = asdict(item)
                d["platform"] = "reddit"
                all_signals.append(d)
        except Exception:
            logger.warning("Reddit collection failed", exc_info=True)

        # 2. Substack + X via the social aggregator
        try:
            social = SocialAggregatorSource(enabled_platforms=["substack", "twitter"])
            social_items = await social.fetch(limit=25)
            for item in social_items:
                d = asdict(item)
                all_signals.append(d)
        except Exception:
            logger.warning("Social aggregator collection failed", exc_info=True)

        return {"social_signals": all_signals}


class ScreenCollector(DataCollector):
    """Runs quantitative screens on market data."""

    name = "screens"

    async def collect(self) -> dict[str, Any]:
        """Run basic screens. Uses backend screening service if available."""
        try:
            from src.services.screening import run_screen
            # Run a few standard screens
            results = []
            for screen_type in ["momentum_leaders", "value_opportunities", "unusual_volume"]:
                try:
                    screen_result = await run_screen(screen_type, {})
                    if screen_result:
                        results.extend(screen_result[:10])
                except Exception:
                    pass
            return {"screen_results": results}
        except ImportError:
            return {"screen_results": []}
        except Exception:
            logger.warning("Screen collection failed", exc_info=True)
            return {"screen_results": []}


class DataPipeline:
    """Centralized data pipeline that collects from all sources.

    Usage:
        pipeline = DataPipeline()
        snapshot = await pipeline.collect()
        # Feed snapshot to all parallel generators
        ideas = await run_parallel_generators(
            snapshot.to_agent_input(), context, llm
        )
    """

    def __init__(self) -> None:
        from src.config import settings

        self.collectors: list[DataCollector] = [
            NewsCollector(api_key=settings.news_api_key),
            MarketDataCollector(),
            SocialCollector(),
            ScreenCollector(),
        ]

    async def collect(self) -> DataSnapshot:
        """Run all collectors in parallel and merge into a DataSnapshot."""
        logger.info("Data pipeline: collecting from %d sources", len(self.collectors))

        tasks = [c.collect() for c in self.collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        snapshot = DataSnapshot()
        source_counts: dict[str, int] = {}

        for collector, result in zip(self.collectors, results):
            if isinstance(result, Exception):
                logger.warning("Collector %s failed: %s", collector.name, result)
                source_counts[collector.name] = 0
                continue

            if "news_items" in result:
                snapshot.news_items.extend(result["news_items"])
                source_counts["news"] = len(result["news_items"])

            if "market_data" in result:
                snapshot.market_data.update(result["market_data"])
                source_counts["market_data"] = len(result.get("market_data", {}).get("prices", {}))

            if "social_signals" in result:
                snapshot.social_signals.extend(result["social_signals"])
                source_counts["social"] = len(result["social_signals"])

            if "screen_results" in result:
                snapshot.screen_results.extend(result["screen_results"])
                source_counts["screens"] = len(result["screen_results"])

        snapshot.metadata = {
            "collected_at": snapshot.timestamp,
            "source_counts": source_counts,
            "collector_count": len(self.collectors),
        }

        logger.info(
            "Data pipeline collected: %s",
            ", ".join(f"{k}={v}" for k, v in source_counts.items()),
        )

        return snapshot

    def add_collector(self, collector: DataCollector) -> None:
        """Add a custom data collector to the pipeline."""
        self.collectors.append(collector)
        logger.info("Added data collector: %s", collector.name)


# Module-level singleton
try:
    data_pipeline = DataPipeline()
except Exception:
    data_pipeline = None  # type: ignore[assignment]
    logger.warning("Data pipeline initialization failed", exc_info=True)
