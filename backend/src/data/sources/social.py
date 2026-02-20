"""
Social media aggregator data source.

Provides a unified interface for ingesting signals from social-media
platforms beyond Reddit (which has its own dedicated connector):

    - X / Twitter  (API v2 — requires Bearer Token)
    - Substack newsletters  (public RSS feeds — no auth needed)
    - YouTube transcript analysis  (stub)

Each platform method is designed with the production interface in mind so
that future implementations can slot in without changing the public API.
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

from src.config import settings
from src.data.sources.base import BaseDataSource, DataItem

logger = logging.getLogger(__name__)

# Cashtag regex for extracting ticker symbols from text
_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")

_TICKER_STOPWORDS: set[str] = {
    "I", "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO",
    "HE", "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "OK",
    "ON", "OR", "SO", "TO", "UP", "US", "WE", "DD", "CEO", "IMO",
    "TL", "DR", "FYI", "PSA", "GDP", "CPI", "IPO", "EPS", "SEC",
    "ATH", "EOD", "OTM", "ITM", "ATM", "DTE", "RSI", "MACD", "EMA",
    "SMA", "YOLO", "FOMO", "HODL", "LMAO",
}

# ---------------------------------------------------------------------------
# Curated Substack newsletter registry
# ---------------------------------------------------------------------------

# Each entry is (slug, display_name, focus_tags).  The RSS feed URL is
# derived as ``https://{slug}.substack.com/feed``.
DEFAULT_SUBSTACK_NEWSLETTERS: list[tuple[str, str, list[str]]] = [
    ("mattstoller", "BIG by Matt Stoller", ["antitrust", "policy", "macro"]),
    ("doomberg", "Doomberg", ["energy", "commodities", "macro"]),
    ("kaborasays", "Kyla Scanlon", ["macro", "economy", "markets"]),
    ("thediff", "The Diff", ["tech", "strategy", "finance"]),
    ("netinterest", "Net Interest", ["banking", "fintech", "macro"]),
    ("bitsaboutmoney", "Bits about Money", ["fintech", "payments", "banking"]),
    ("noahpinion", "Noahpinion", ["economics", "macro", "policy"]),
    ("capitalflows", "Capital Flows", ["macro", "rates", "fixed-income"]),
    ("thegeneralasst", "The Generalist", ["tech", "venture", "strategy"]),
    ("platformer", "Platformer", ["tech", "regulation", "social-media"]),
]

# ---------------------------------------------------------------------------
# Curated X/Twitter finance accounts & search terms
# ---------------------------------------------------------------------------

DEFAULT_X_FINANCE_QUERIES: list[str] = [
    "$SPY OR $QQQ OR $DIA lang:en -is:retweet",
    "from:jimcramer OR from:elonmusk OR from:chaaborma OR from:zabormetrics lang:en -is:retweet",
    "#fintwit (earnings OR breakout OR short OR bearish OR bullish) lang:en -is:retweet",
    "(macro OR FOMC OR CPI OR inflation) (market OR stocks) lang:en -is:retweet",
    "(crypto OR bitcoin OR ethereum) (breakout OR crash OR rally) lang:en -is:retweet",
]


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
        """Return True if at least one platform is reachable."""
        checks = []
        if "substack" in self.enabled_platforms:
            checks.append(self._substack_health())
        if "twitter" in self.enabled_platforms and getattr(settings, "x_bearer_token", ""):
            checks.append(self._twitter_health())
        if not checks:
            return True
        results = await asyncio.gather(*checks, return_exceptions=True)
        return any(r is True for r in results)

    async def _substack_health(self) -> bool:
        try:
            items = await self.fetch_substack(limit=1)
            return len(items) > 0
        except Exception:
            return False

    async def _twitter_health(self) -> bool:
        try:
            items = await self.fetch_twitter(limit=1)
            return len(items) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Twitter / X  (API v2)
    # ------------------------------------------------------------------

    async def fetch_twitter(
        self,
        query: str = "",
        tickers: list[str] | None = None,
        limit: int = 25,
    ) -> list[DataItem]:
        """Fetch recent tweets about financial topics via the X API v2.

        Requires ``X_BEARER_TOKEN`` to be set in the environment.  When
        the token is missing, returns an empty list silently.

        Uses the ``GET /2/tweets/search/recent`` endpoint with tweet fields
        for engagement metrics and author expansion.
        """

        bearer_token = getattr(settings, "x_bearer_token", "")
        if not bearer_token:
            logger.debug("X_BEARER_TOKEN not set — skipping Twitter fetch")
            return []

        # Build search queries
        queries = []
        if query:
            queries.append(query)
        if tickers:
            cashtags = " OR ".join(f"${t}" for t in tickers[:10])
            queries.append(f"({cashtags}) lang:en -is:retweet")
        if not queries:
            queries = list(DEFAULT_X_FINANCE_QUERIES)

        all_items: list[DataItem] = []
        per_query_limit = max(10, limit // len(queries))

        for q in queries:
            items = await self._search_tweets(
                bearer_token, q, max_results=min(per_query_limit, 100)
            )
            all_items.extend(items)
            if len(all_items) >= limit:
                break

        logger.info("Twitter fetched %d tweets from %d queries", len(all_items), len(queries))
        return all_items[:limit]

    async def _search_tweets(
        self,
        bearer_token: str,
        query: str,
        max_results: int = 25,
    ) -> list[DataItem]:
        """Call the X API v2 search/recent endpoint."""

        url = "https://api.x.com/2/tweets/search/recent"
        params = {
            "query": query,
            "max_results": max(10, min(max_results, 100)),
            "tweet.fields": "created_at,public_metrics,author_id,entities",
            "expansions": "author_id",
            "user.fields": "name,username,public_metrics",
        }
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "Overture/1.0",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 429:
                        logger.warning("X API rate-limited (429)")
                        return []
                    if resp.status == 401:
                        logger.error("X API auth failed (401) — check X_BEARER_TOKEN")
                        return []
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning("X API error %d: %s", resp.status, body[:200])
                        return []
                    data = await resp.json()
        except Exception:
            logger.warning("X API request failed", exc_info=True)
            return []

        tweets = data.get("data", [])
        # Build author lookup from includes
        users_list = data.get("includes", {}).get("users", [])
        authors = {u["id"]: u for u in users_list}

        items: list[DataItem] = []
        for tweet in tweets:
            text = tweet.get("text", "")
            tweet_id = tweet.get("id", "")
            author_id = tweet.get("author_id", "")
            author = authors.get(author_id, {})
            author_name = author.get("name", "")
            author_username = author.get("username", "")
            author_followers = author.get("public_metrics", {}).get("followers_count", 0)

            metrics = tweet.get("public_metrics", {})
            likes = metrics.get("like_count", 0)
            retweets = metrics.get("retweet_count", 0)
            replies = metrics.get("reply_count", 0)
            quotes = metrics.get("quote_count", 0)

            # Extract tickers from cashtags in entities
            tickers: list[str] = []
            for cashtag in tweet.get("entities", {}).get("cashtags", []):
                tag = cashtag.get("tag", "").upper()
                if tag and tag not in _TICKER_STOPWORDS:
                    tickers.append(tag)
            # Also extract from text
            text_tickers = self._extract_tickers(text)
            for t in text_tickers:
                if t not in tickers:
                    tickers.append(t)

            # Parse created_at
            published_at = None
            raw_date = tweet.get("created_at", "")
            if raw_date:
                try:
                    published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            engagement = likes + retweets * 2 + replies + quotes
            relevance = min(engagement / 500.0, 1.0)
            # Boost relevance for high-follower accounts
            if author_followers > 100_000:
                relevance = min(relevance + 0.3, 1.0)
            elif author_followers > 10_000:
                relevance = min(relevance + 0.15, 1.0)

            items.append(DataItem(
                source="twitter",
                source_type="social",
                title=f"@{author_username}: {text[:120]}",
                content=text,
                url=f"https://x.com/{author_username}/status/{tweet_id}" if author_username else "",
                tickers=tickers,
                asset_classes=self._infer_asset_classes(text, tickers),
                sentiment=None,  # Sentiment computed downstream by LLM
                relevance_score=relevance,
                metadata={
                    "platform": "twitter",
                    "author_name": author_name,
                    "author_username": author_username,
                    "author_followers": author_followers,
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                    "quotes": quotes,
                    "engagement_total": engagement,
                },
                published_at=published_at,
            ))

        return items

    # ------------------------------------------------------------------
    # Substack  (RSS feeds)
    # ------------------------------------------------------------------

    async def fetch_substack(
        self,
        query: str = "",
        tickers: list[str] | None = None,
        limit: int = 25,
        newsletters: list[tuple[str, str, list[str]]] | None = None,
    ) -> list[DataItem]:
        """Fetch recent posts from curated financial Substack newsletters.

        Uses the public RSS feed at ``<slug>.substack.com/feed``.  No API
        key or authentication is required.

        Args:
            query: Optional text filter — only include posts whose title
                or content contains this substring.
            tickers: Optional list of tickers — only include posts that
                mention at least one.
            limit: Maximum number of items to return.
            newsletters: Override the default newsletter registry.
        """

        registry = newsletters or DEFAULT_SUBSTACK_NEWSLETTERS
        tasks = [
            self._fetch_substack_feed(slug, display_name, tags)
            for slug, display_name, tags in registry
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[DataItem] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Substack feed fetch failed: %s", result)
                continue
            all_items.extend(result)

        # Apply optional filters
        if query:
            q_lower = query.lower()
            all_items = [
                item for item in all_items
                if q_lower in item.title.lower() or q_lower in item.content.lower()
            ]

        if tickers:
            ticker_set = {t.upper() for t in tickers}
            all_items = [
                item for item in all_items
                if ticker_set & set(item.tickers)
            ]

        # Sort by publication date (newest first)
        all_items.sort(
            key=lambda i: i.published_at or datetime.min,
            reverse=True,
        )

        logger.info(
            "Substack fetched %d articles from %d newsletters",
            len(all_items), len(registry),
        )
        return all_items[:limit]

    async def _fetch_substack_feed(
        self,
        slug: str,
        display_name: str,
        tags: list[str],
    ) -> list[DataItem]:
        """Download and parse a single Substack RSS feed."""

        feed_url = f"https://{slug}.substack.com/feed"
        logger.debug("Fetching Substack feed: %s", feed_url)

        raw_xml = await self._download(feed_url)
        if not raw_xml:
            return []

        # feedparser is synchronous — offload to a thread
        parsed = await asyncio.to_thread(feedparser.parse, raw_xml)

        items: list[DataItem] = []
        for entry in parsed.entries:
            title: str = getattr(entry, "title", "")
            # Prefer content over summary for fuller text
            content_list = getattr(entry, "content", [])
            if content_list:
                raw_content = content_list[0].get("value", "")
            else:
                raw_content = getattr(entry, "summary", getattr(entry, "description", ""))

            # Strip HTML tags for cleaner text
            content = re.sub(r"<[^>]+>", " ", raw_content)
            content = re.sub(r"\s+", " ", content).strip()
            # Truncate very long articles for pipeline efficiency
            if len(content) > 5000:
                content = content[:5000] + "... [truncated]"

            link: str = getattr(entry, "link", "")
            author: str = getattr(entry, "author", display_name)

            # Parse publication date
            published_at = self._parse_date(entry)

            # Extract tickers
            combined_text = f"{title} {content}"
            extracted_tickers = self._extract_tickers(combined_text)

            items.append(DataItem(
                source="substack",
                source_type="social",
                title=f"[{display_name}] {title}",
                content=content,
                url=link,
                tickers=extracted_tickers,
                asset_classes=self._infer_asset_classes(content, extracted_tickers),
                sentiment=None,
                relevance_score=0.6,  # Curated newsletters have baseline credibility
                metadata={
                    "platform": "substack",
                    "newsletter_slug": slug,
                    "newsletter_name": display_name,
                    "author": author,
                    "tags": tags,
                    "rss_tags": [
                        tag.get("term", "") for tag in getattr(entry, "tags", [])
                    ],
                },
                published_at=published_at,
            ))

        return items

    # ------------------------------------------------------------------
    # YouTube  (stub — future implementation)
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
        return []

    # ------------------------------------------------------------------
    # Shared utilities
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

    @staticmethod
    def _extract_tickers(text: str) -> list[str]:
        """Return unique ticker symbols mentioned as cashtags in *text*."""
        matches = _TICKER_RE.findall(text)
        return sorted({m for m in matches if m not in _TICKER_STOPWORDS})

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
        struct = getattr(entry, "published_parsed", None) or getattr(
            entry, "updated_parsed", None
        )
        if struct:
            try:
                return datetime(*struct[:6])
            except Exception:
                pass
        return None

    @staticmethod
    def _infer_asset_classes(text: str, tickers: list[str]) -> list[str]:
        """Infer asset class tags from text content and tickers."""
        classes: set[str] = set()
        text_lower = text.lower()

        crypto_keywords = {"bitcoin", "btc", "ethereum", "eth", "crypto", "defi", "nft", "solana"}
        commodity_keywords = {"oil", "gold", "silver", "commodity", "energy", "natural gas", "copper"}
        fx_keywords = {"dollar", "euro", "yen", "forex", "currency", "fx"}

        if any(kw in text_lower for kw in crypto_keywords):
            classes.add("crypto")
        if any(kw in text_lower for kw in commodity_keywords):
            classes.add("commodities")
        if any(kw in text_lower for kw in fx_keywords):
            classes.add("fx")
        if tickers:
            classes.add("equity")

        return sorted(classes) if classes else ["equity"]

    async def _download(self, url: str) -> str:
        """Download raw content via aiohttp."""
        try:
            timeout = aiohttp.ClientTimeout(total=15.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers={"User-Agent": "Overture/1.0"}) as resp:
                    if resp.status != 200:
                        logger.warning("Non-200 status %d from %s", resp.status, url)
                        return ""
                    return await resp.text()
        except Exception:
            logger.warning("Failed to download %s", url, exc_info=True)
            return ""
