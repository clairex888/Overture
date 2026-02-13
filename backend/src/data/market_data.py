"""
Market Data Manager.

High-level, cache-aware interface for market data queries.  Wraps the
lower-level ``YahooFinanceSource`` connector and layers Redis-based TTL
caching on top to reduce redundant API calls.

All public methods are async and return structured ``DataItem`` objects or
the data payloads directly for convenience.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from src.config import settings
from src.data.sources.base import DataItem
from src.data.sources.yahoo_finance import YahooFinanceSource

logger = logging.getLogger(__name__)

# Redis key prefix and default TTLs (seconds)
_CACHE_PREFIX = "overture:market:"
_TTL_QUOTE = 30  # live quotes refresh frequently
_TTL_PRICE = 300  # 5-min cache for OHLCV history
_TTL_FUNDAMENTALS = 3600  # 1 hour for fundamentals
_TTL_OPTIONS = 600  # 10 min for options chains
_TTL_SCREEN = 900  # 15 min for screening results


class MarketDataManager:
    """Unified, cache-backed interface for market data.

    Internally delegates to :class:`YahooFinanceSource` and caches results
    in Redis with source-type-specific TTLs.

    Args:
        redis_url: Override for the Redis connection string.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._yf = YahooFinanceSource()
        self._redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_price(
        self,
        ticker: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> DataItem:
        """Return OHLCV price history for *ticker*.

        Results are cached in Redis for ``_TTL_PRICE`` seconds.

        Args:
            ticker: Equity / ETF symbol.
            period: yfinance period string (e.g. "1mo", "1y", "max").
            interval: Bar width (e.g. "1m", "5m", "1d").

        Returns:
            A ``DataItem`` whose ``metadata["ohlcv"]`` contains the bars.
        """

        cache_key = self._key("price", ticker, period, interval)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for price %s", cache_key)
            return cached

        item = await self._yf.fetch_price(ticker=ticker, period=period, interval=interval)
        await self._cache_set(cache_key, item, ttl=_TTL_PRICE)
        return item

    async def get_quote(self, ticker: str) -> DataItem:
        """Return the latest quote / snapshot for *ticker*.

        Internally fetches a single-day price bar and caches it briefly
        (``_TTL_QUOTE`` seconds) to provide near-real-time data.

        Args:
            ticker: Equity / ETF symbol.

        Returns:
            A ``DataItem`` with the most recent close, volume, etc.
        """

        cache_key = self._key("quote", ticker)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for quote %s", cache_key)
            return cached

        item = await self._yf.fetch_price(ticker=ticker, period="1d", interval="1m")
        await self._cache_set(cache_key, item, ttl=_TTL_QUOTE)
        return item

    async def get_fundamentals(self, ticker: str) -> DataItem:
        """Return company profile and fundamental ratios for *ticker*.

        Cached for ``_TTL_FUNDAMENTALS`` seconds since fundamentals change
        infrequently.

        Args:
            ticker: Equity / ETF symbol.

        Returns:
            A ``DataItem`` with fundamental data in ``metadata``.
        """

        cache_key = self._key("fundamentals", ticker)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for fundamentals %s", cache_key)
            return cached

        item = await self._yf.fetch_info(ticker=ticker)
        await self._cache_set(cache_key, item, ttl=_TTL_FUNDAMENTALS)
        return item

    async def get_options_chain(self, ticker: str) -> list[DataItem]:
        """Return the full options chain for *ticker*.

        Cached for ``_TTL_OPTIONS`` seconds.

        Args:
            ticker: Equity / ETF symbol.

        Returns:
            List of ``DataItem`` objects, one per expiration date.
        """

        cache_key = self._key("options", ticker)
        cached_list = await self._cache_get_list(cache_key)
        if cached_list is not None:
            logger.debug("Cache hit for options %s", cache_key)
            return cached_list

        items = await self._yf.fetch_options(ticker=ticker)
        await self._cache_set_list(cache_key, items, ttl=_TTL_OPTIONS)
        return items

    async def detect_anomalies(
        self,
        tickers: list[str],
        lookback_days: int = 252,
        sigma_threshold: float = 3.0,
    ) -> list[DataItem]:
        """Scan *tickers* for statistically unusual daily returns.

        This is the primary anomaly detection surface -- it will flag events
        like a 10-sigma move in silver so that downstream agents can react.

        Args:
            tickers: Universe of symbols to scan.
            lookback_days: Historical window (calendar days) for computing
                mean and standard deviation of returns.
            sigma_threshold: Z-score cutoff above which a move is flagged.

        Returns:
            List of ``DataItem`` objects, one per anomalous ticker.
        """

        # Anomaly detection is time-sensitive; don't cache.
        return await self._yf.detect_unusual_moves(
            tickers=tickers,
            threshold_sigma=sigma_threshold,
            lookback_days=lookback_days,
        )

    async def run_screen(self, criteria: dict[str, Any]) -> list[DataItem]:
        """Screen a universe of tickers against fundamental criteria.

        Results are cached for ``_TTL_SCREEN`` seconds.

        Supported criteria keys:
            tickers, min_market_cap, max_market_cap, min_pe, max_pe,
            min_volume, min_dividend, sector.

        Args:
            criteria: Dict of screening filters.

        Returns:
            List of ``DataItem`` objects for tickers passing all filters.
        """

        # Build a stable cache key from sorted criteria
        sorted_criteria = json.dumps(criteria, sort_keys=True, default=str)
        cache_key = self._key("screen", sorted_criteria)

        cached_list = await self._cache_get_list(cache_key)
        if cached_list is not None:
            logger.debug("Cache hit for screen %s", cache_key)
            return cached_list

        items = await self._yf.screen(criteria=criteria)
        await self._cache_set_list(cache_key, items, ttl=_TTL_SCREEN)
        return items

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key(*parts: str) -> str:
        """Build a namespaced Redis key."""
        return _CACHE_PREFIX + ":".join(parts)

    async def _get_redis(self) -> aioredis.Redis | None:
        """Lazily initialise the Redis connection."""
        if self._redis is not None:
            return self._redis
        try:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
            await self._redis.ping()
            return self._redis
        except Exception:
            logger.debug("Redis not available at %s -- caching disabled.", self._redis_url)
            self._redis = None
            return None

    async def _cache_get(self, key: str) -> DataItem | None:
        """Retrieve a single cached ``DataItem``, or None."""
        redis = await self._get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
            return self._deserialize_item(raw)
        except Exception:
            logger.debug("Cache read error for %s", key, exc_info=True)
            return None

    async def _cache_set(self, key: str, item: DataItem, ttl: int) -> None:
        """Store a single ``DataItem`` in Redis with the given TTL."""
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            payload = self._serialize_item(item)
            await redis.set(key, payload, ex=ttl)
        except Exception:
            logger.debug("Cache write error for %s", key, exc_info=True)

    async def _cache_get_list(self, key: str) -> list[DataItem] | None:
        """Retrieve a cached list of ``DataItem`` objects."""
        redis = await self._get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
            data_list = json.loads(raw)
            return [self._deserialize_item(json.dumps(d)) for d in data_list]
        except Exception:
            logger.debug("Cache list read error for %s", key, exc_info=True)
            return None

    async def _cache_set_list(self, key: str, items: list[DataItem], ttl: int) -> None:
        """Store a list of ``DataItem`` objects in Redis."""
        redis = await self._get_redis()
        if redis is None:
            return
        try:
            serialized = [json.loads(self._serialize_item(item)) for item in items]
            await redis.set(key, json.dumps(serialized, default=str), ex=ttl)
        except Exception:
            logger.debug("Cache list write error for %s", key, exc_info=True)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_item(item: DataItem) -> str:
        """Convert a ``DataItem`` to a JSON string."""
        from dataclasses import asdict

        d = asdict(item)
        for key in ("published_at", "fetched_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = val.isoformat()
        return json.dumps(d, default=str)

    @staticmethod
    def _deserialize_item(raw: str) -> DataItem:
        """Reconstruct a ``DataItem`` from a JSON string."""
        d = json.loads(raw)

        # Restore datetime fields
        for key in ("published_at", "fetched_at"):
            val = d.get(key)
            if isinstance(val, str) and val:
                try:
                    d[key] = datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    d[key] = None
            elif not isinstance(val, datetime):
                d[key] = None

        # Ensure fetched_at is never None
        if d.get("fetched_at") is None:
            d["fetched_at"] = datetime.utcnow()

        return DataItem(**d)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the Redis connection, if any."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
