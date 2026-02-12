"""
RSS / News feed data source connector.

Ingests articles from a configurable list of financial-news RSS feeds and
normalises them into ``DataItem`` objects.  Ticker extraction is performed
via a simple ``$TICKER`` regex applied to titles and descriptions.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp
import feedparser

from src.data.sources.base import BaseDataSource, DataItem

logger = logging.getLogger(__name__)

# Regex that matches cashtag-style ticker mentions (e.g. $AAPL, $TSLA).
_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Default set of financial-news RSS feed URLs.
DEFAULT_FEEDS: list[str] = [
    # Reuters
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    # CNBC
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    # Bloomberg (Markets)
    "https://feeds.bloomberg.com/markets/news.rss",
    # Financial Times
    "https://www.ft.com/?format=rss",
    # MarketWatch
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    # Yahoo Finance
    "https://finance.yahoo.com/news/rssindex",
    # Seeking Alpha
    "https://seekingalpha.com/market_currents.xml",
    # Investing.com
    "https://www.investing.com/rss/news.rss",
]


class RSSNewsSource(BaseDataSource):
    """Connector that fetches and parses multiple RSS feeds concurrently.

    Args:
        feeds: Optional list of RSS feed URLs.  Falls back to
               ``DEFAULT_FEEDS`` when not provided.
        request_timeout: Per-feed HTTP timeout in seconds.
    """

    def __init__(
        self,
        feeds: list[str] | None = None,
        request_timeout: float = 15.0,
    ) -> None:
        super().__init__(name="rss_news", source_type="news")
        self.feeds: list[str] = feeds or list(DEFAULT_FEEDS)
        self.request_timeout = request_timeout

    # ------------------------------------------------------------------
    # BaseDataSource interface
    # ------------------------------------------------------------------

    async def fetch(self, **kwargs) -> list[DataItem]:
        """Fetch articles from all configured RSS feeds concurrently.

        Keyword Args:
            feeds: Override the instance feed list for this call.

        Returns:
            Flat list of ``DataItem`` objects across all feeds.
        """

        feeds = kwargs.get("feeds", self.feeds)
        tasks = [self.fetch_feed(url) for url in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[DataItem] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Feed fetch failed: %s", result)
                continue
            items.extend(result)

        logger.info("Fetched %d news items from %d feeds", len(items), len(feeds))
        return items

    async def health_check(self) -> bool:
        """Try to reach the first configured feed."""
        if not self.feeds:
            return False
        try:
            items = await self.fetch_feed(self.feeds[0])
            return len(items) > 0
        except Exception:
            logger.exception("RSS health check failed")
            return False

    # ------------------------------------------------------------------
    # Single-feed fetcher
    # ------------------------------------------------------------------

    async def fetch_feed(self, url: str) -> list[DataItem]:
        """Download and parse a single RSS feed.

        Args:
            url: URL of the RSS feed.

        Returns:
            List of ``DataItem`` objects parsed from the feed entries.
        """

        logger.debug("Fetching RSS feed: %s", url)
        raw_xml = await self._download(url)
        if not raw_xml:
            return []

        # feedparser is synchronous; offload to a thread.
        parsed = await asyncio.to_thread(feedparser.parse, raw_xml)

        items: list[DataItem] = []
        feed_title = getattr(parsed.feed, "title", url)

        for entry in parsed.entries:
            title: str = getattr(entry, "title", "")
            description: str = getattr(entry, "summary", getattr(entry, "description", ""))
            link: str = getattr(entry, "link", "")

            # Attempt to parse the publication date
            published_at = self._parse_date(entry)

            # Extract mentioned tickers from title + description
            tickers = self._extract_tickers(f"{title} {description}")

            items.append(
                DataItem(
                    source=self.name,
                    source_type="news",
                    title=title,
                    content=description,
                    url=link,
                    tickers=tickers,
                    asset_classes=["equity"] if tickers else [],
                    metadata={
                        "feed_url": url,
                        "feed_title": feed_title,
                        "author": getattr(entry, "author", None),
                        "tags": [
                            tag.get("term", "") for tag in getattr(entry, "tags", [])
                        ],
                    },
                    published_at=published_at,
                )
            )

        return items

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _download(self, url: str) -> str:
        """Download raw feed content via aiohttp."""
        try:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={"User-Agent": "Overture/1.0"}) as resp:
                    if resp.status != 200:
                        logger.warning("Non-200 status %d from %s", resp.status, url)
                        return ""
                    return await resp.text()
        except Exception:
            logger.warning("Failed to download feed %s", url, exc_info=True)
            return ""

    @staticmethod
    def _extract_tickers(text: str) -> list[str]:
        """Return unique, uppercased ticker symbols found as cashtags."""
        return sorted(set(_TICKER_RE.findall(text)))

    @staticmethod
    def _parse_date(entry: Any) -> datetime | None:
        """Best-effort parse of an RSS entry's publication date."""
        raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
        if not raw:
            return None
        try:
            return parsedate_to_datetime(raw)
        except Exception:
            pass
        # feedparser also exposes a parsed tuple
        struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if struct:
            try:
                return datetime(*struct[:6])
            except Exception:
                pass
        return None
