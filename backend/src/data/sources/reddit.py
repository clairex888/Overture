"""
Reddit data source connector.

Fetches posts from finance-related subreddits using the public Reddit JSON
API (no OAuth required for read-only access to public subreddits).  Extracts
ticker mentions from post titles and self-text.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.data.sources.base import BaseDataSource, DataItem

logger = logging.getLogger(__name__)

# Regex for cashtag-style ticker mentions ($AAPL) and bare uppercase tickers
# that are 1-5 chars.  We use the cashtag pattern primarily because bare
# uppercase words produce too many false positives.
_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")

# Common English words that happen to be uppercase and match ticker-like
# patterns — used to suppress false positives.
_TICKER_STOPWORDS: set[str] = {
    "I", "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO",
    "HE", "IF", "IN", "IS", "IT", "ME", "MY", "NO", "OF", "OK",
    "ON", "OR", "SO", "TO", "UP", "US", "WE", "DD", "CEO", "IMO",
    "TL", "DR", "FYI", "PSA", "GDP", "CPI", "IPO", "EPS", "SEC",
    "ATH", "EOD", "OTM", "ITM", "ATM", "DTE", "RSI", "MACD", "EMA",
    "SMA", "YOLO", "FOMO", "HODL", "LMAO",
}

DEFAULT_SUBREDDITS: list[str] = [
    "wallstreetbets",
    "investing",
    "stocks",
    "options",
    "economics",
]


class RedditSource(BaseDataSource):
    """Connector that ingests posts from finance-related subreddits.

    Uses the unauthenticated Reddit JSON endpoint (``<url>.json``) so no
    API keys are needed.

    Args:
        subreddits: List of subreddit names to monitor.
        request_timeout: Per-request HTTP timeout in seconds.
    """

    REDDIT_BASE = "https://www.reddit.com"

    def __init__(
        self,
        subreddits: list[str] | None = None,
        request_timeout: float = 15.0,
    ) -> None:
        super().__init__(name="reddit", source_type="social")
        self.subreddits: list[str] = subreddits or list(DEFAULT_SUBREDDITS)
        self.request_timeout = request_timeout

    # ------------------------------------------------------------------
    # BaseDataSource interface
    # ------------------------------------------------------------------

    async def fetch(self, **kwargs) -> list[DataItem]:
        """Fetch posts from all configured subreddits concurrently.

        Keyword Args:
            subreddits: Override the instance subreddit list.
            sort: Reddit sort order — "hot", "new", "top", "rising".
            limit: Max posts per subreddit (default 25, max 100).

        Returns:
            Flat list of ``DataItem`` objects across all subreddits.
        """

        subreddits = kwargs.get("subreddits", self.subreddits)
        sort = kwargs.get("sort", "hot")
        limit = kwargs.get("limit", 25)

        tasks = [
            self.fetch_subreddit(name=sub, sort=sort, limit=limit)
            for sub in subreddits
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[DataItem] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Subreddit fetch failed: %s", result)
                continue
            items.extend(result)

        logger.info(
            "Fetched %d Reddit posts from %d subreddits",
            len(items),
            len(subreddits),
        )
        return items

    async def health_check(self) -> bool:
        """Verify connectivity by requesting a single post from r/stocks."""
        try:
            items = await self.fetch_subreddit("stocks", sort="hot", limit=1)
            return len(items) > 0
        except Exception:
            logger.exception("Reddit health check failed")
            return False

    # ------------------------------------------------------------------
    # Single-subreddit fetcher
    # ------------------------------------------------------------------

    async def fetch_subreddit(
        self,
        name: str,
        sort: str = "hot",
        limit: int = 25,
    ) -> list[DataItem]:
        """Fetch posts from a single subreddit.

        Args:
            name: Subreddit name (without ``r/`` prefix).
            sort: One of "hot", "new", "top", "rising".
            limit: Number of posts to request (capped at 100 by Reddit).

        Returns:
            List of ``DataItem`` objects, one per post.
        """

        url = f"{self.REDDIT_BASE}/r/{name}/{sort}.json"
        params = {"limit": min(limit, 100), "raw_json": 1}

        data = await self._get_json(url, params)
        if data is None:
            return []

        children = data.get("data", {}).get("children", [])

        items: list[DataItem] = []
        for child in children:
            post = child.get("data", {})
            item = self._post_to_dataitem(post, subreddit=name)
            if item is not None:
                items.append(item)

        return items

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _post_to_dataitem(self, post: dict[str, Any], subreddit: str) -> DataItem | None:
        """Convert a raw Reddit post JSON object into a ``DataItem``."""
        title: str = post.get("title", "")
        selftext: str = post.get("selftext", "")
        permalink: str = post.get("permalink", "")
        url = f"{self.REDDIT_BASE}{permalink}" if permalink else ""

        # Skip removed / deleted stubs
        if title in ("[removed]", "[deleted]"):
            return None

        # Parse creation timestamp
        created_utc = post.get("created_utc")
        published_at: datetime | None = None
        if created_utc:
            published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)

        # Extract tickers from title and body
        combined_text = f"{title} {selftext}"
        tickers = self._extract_tickers(combined_text)

        # Basic engagement metrics stored in metadata
        score = post.get("score", 0)
        num_comments = post.get("num_comments", 0)
        upvote_ratio = post.get("upvote_ratio", 0.0)

        # Compute a simple relevance heuristic based on engagement
        relevance = min((score + num_comments * 2) / 1000.0, 1.0)

        return DataItem(
            source=self.name,
            source_type="social",
            title=f"[r/{subreddit}] {title}",
            content=selftext[:2000] if selftext else title,
            url=url,
            tickers=tickers,
            asset_classes=["equity"] if tickers else [],
            relevance_score=relevance,
            metadata={
                "subreddit": subreddit,
                "author": post.get("author"),
                "score": score,
                "num_comments": num_comments,
                "upvote_ratio": upvote_ratio,
                "flair": post.get("link_flair_text"),
                "is_self": post.get("is_self", False),
                "over_18": post.get("over_18", False),
            },
            published_at=published_at,
        )

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Perform a GET request and return parsed JSON, or None on failure."""
        try:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            headers = {"User-Agent": "Overture/1.0 (financial research bot)"}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status == 429:
                        logger.warning("Reddit rate-limited on %s", url)
                        return None
                    if resp.status != 200:
                        logger.warning("Non-200 status %d from %s", resp.status, url)
                        return None
                    return await resp.json()
        except Exception:
            logger.warning("Request to %s failed", url, exc_info=True)
            return None

    @staticmethod
    def _extract_tickers(text: str) -> list[str]:
        """Return unique ticker symbols mentioned as cashtags in *text*.

        Filters out common stop-words that look like tickers but are not.
        """
        matches = _TICKER_RE.findall(text)
        return sorted(
            {m for m in matches if m not in _TICKER_STOPWORDS}
        )
