"""
Social media aggregator data source.

Provides a unified interface for ingesting signals from social-media
platforms beyond Reddit (which has its own dedicated connector).  Currently
contains stub implementations for:

    - X / Twitter
    - Substack newsletters
    - YouTube transcript analysis

Each platform method is designed with the production interface in mind so
that future implementations can slot in without changing the public API.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from src.data.sources.base import BaseDataSource, DataItem

logger = logging.getLogger(__name__)


class SocialAggregatorSource(BaseDataSource):
    """Aggregated social-media signal connector.

    Orchestrates fetching from multiple social platforms and merges the
    results into a single stream of ``DataItem`` objects.

    Args:
        enabled_platforms: Subset of platforms to activate.  Accepted values
            are ``"twitter"``, ``"substack"``, and ``"youtube"``.  Defaults
            to all three.
    """

    SUPPORTED_PLATFORMS = ("twitter", "substack", "youtube")

    def __init__(
        self,
        enabled_platforms: list[str] | None = None,
    ) -> None:
        super().__init__(name="social_aggregator", source_type="social")
        self.enabled_platforms: list[str] = enabled_platforms or list(self.SUPPORTED_PLATFORMS)

    # ------------------------------------------------------------------
    # BaseDataSource interface
    # ------------------------------------------------------------------

    async def fetch(self, **kwargs) -> list[DataItem]:
        """Fetch social signals from all enabled platforms concurrently.

        Keyword Args:
            platforms: Override enabled platforms for this call.
            query: Search query / keywords to look for.
            tickers: List of ticker symbols to filter on.
            limit: Max items per platform.

        Returns:
            Merged list of ``DataItem`` objects.
        """

        platforms = kwargs.get("platforms", self.enabled_platforms)
        query = kwargs.get("query", "")
        tickers: list[str] = kwargs.get("tickers", [])
        limit = kwargs.get("limit", 25)

        fetchers: dict[str, Any] = {
            "twitter": self.fetch_twitter,
            "substack": self.fetch_substack,
            "youtube": self.fetch_youtube,
        }

        tasks = []
        for platform in platforms:
            fn = fetchers.get(platform)
            if fn is None:
                logger.warning("Unknown social platform: %s", platform)
                continue
            tasks.append(fn(query=query, tickers=tickers, limit=limit))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[DataItem] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Social platform fetch failed: %s", result)
                continue
            items.extend(result)

        logger.info(
            "Social aggregator produced %d items from %d platforms",
            len(items),
            len(platforms),
        )
        return items

    async def health_check(self) -> bool:
        """Return True if at least one platform stub is reachable.

        Since all platforms are currently stubs, this always returns True to
        indicate the aggregator itself is operational.
        """
        return True

    # ------------------------------------------------------------------
    # Twitter / X
    # ------------------------------------------------------------------

    async def fetch_twitter(
        self,
        query: str = "",
        tickers: list[str] | None = None,
        limit: int = 25,
    ) -> list[DataItem]:
        """Fetch tweets mentioning financial topics or tickers.

        TODO: Implement using the X API v2 (requires Bearer Token).
              - Search endpoint: GET /2/tweets/search/recent
              - Filter by cashtags, financial influencers, keyword queries
              - Extract engagement metrics (likes, retweets, replies)
              - Compute sentiment via LLM or lexicon
              - Rate-limit handling (450 requests / 15-min window)

        TODO: Consider alternative approaches:
              - Nitter scraping (fragile, but no API key needed)
              - Pre-built datasets from Kaggle or academic sources
              - Third-party APIs (Stocktwits, Swaggystocks)
        """

        logger.debug(
            "Twitter fetch stub called (query=%r, tickers=%s, limit=%d)",
            query,
            tickers,
            limit,
        )
        # Stub: return empty list until implementation is ready
        return []

    # ------------------------------------------------------------------
    # Substack
    # ------------------------------------------------------------------

    async def fetch_substack(
        self,
        query: str = "",
        tickers: list[str] | None = None,
        limit: int = 25,
    ) -> list[DataItem]:
        """Fetch recent posts from financial Substack newsletters.

        TODO: Implement Substack ingestion.
              - Target newsletters: Matt Levine (Money Stuff), Doomberg,
                Kyla Scanlon, The Diff, Net Interest, Bits about Money
              - Substack exposes RSS feeds at <publication>.substack.com/feed
              - Parse via feedparser (similar to RSSNewsSource)
              - Extract key themes, mentioned tickers, and sentiment
              - Store full article text for LLM summarisation

        TODO: Consider building a curated registry of newsletter URLs
              that can be managed via the admin UI.
        """

        logger.debug(
            "Substack fetch stub called (query=%r, tickers=%s, limit=%d)",
            query,
            tickers,
            limit,
        )
        # Stub: return empty list until implementation is ready
        return []

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------

    async def fetch_youtube(
        self,
        query: str = "",
        tickers: list[str] | None = None,
        limit: int = 25,
    ) -> list[DataItem]:
        """Fetch and transcribe finance-related YouTube videos.

        TODO: Implement YouTube transcript ingestion.
              - Use the YouTube Data API v3 to search for relevant videos
                (channels: Patrick Boyle, The Plain Bagel, Graham Stephan,
                 Aswath Damodaran, etc.)
              - Download auto-generated or manual captions via
                ``youtube_transcript_api``
              - Summarise transcripts with LLM to extract:
                - Key themes and opinions
                - Ticker mentions
                - Sentiment / conviction signals
              - Rate-limit: 10,000 units/day quota

        TODO: Consider caching transcripts in Redis or Postgres to avoid
              re-processing videos already seen.
        """

        logger.debug(
            "YouTube fetch stub called (query=%r, tickers=%s, limit=%d)",
            query,
            tickers,
            limit,
        )
        # Stub: return empty list until implementation is ready
        return []

    # ------------------------------------------------------------------
    # Utility for future implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _build_search_query(query: str, tickers: list[str] | None) -> str:
        """Combine a free-text query with cashtag tickers into a single
        search string suitable for most social-platform search APIs.

        Example::

            >>> SocialAggregatorSource._build_search_query("earnings", ["AAPL", "MSFT"])
            'earnings $AAPL $MSFT'
        """
        parts: list[str] = []
        if query:
            parts.append(query)
        if tickers:
            parts.extend(f"${t}" for t in tickers)
        return " ".join(parts)
