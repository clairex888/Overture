"""
Data Pipeline Orchestrator.

Manages all registered data sources, coordinates periodic / on-demand
fetching, maintains an in-memory buffer of recent items, and publishes
new items to Redis for real-time subscribers (e.g. the WebSocket layer
or downstream agents).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis

from src.config import settings
from src.data.sources.base import BaseDataSource, DataItem

logger = logging.getLogger(__name__)

# Redis channel / key prefixes
_REDIS_CHANNEL = "overture:data:stream"
_REDIS_BUFFER_KEY = "overture:data:buffer"

# Default in-memory buffer size per source type
_DEFAULT_BUFFER_SIZE = 500


class DataPipeline:
    """Central orchestrator for all Overture data sources.

    Responsibilities:
        1. Source registration and lifecycle management.
        2. Concurrent fetching from all (or a subset of) sources.
        3. Continuous background polling loop.
        4. In-memory ring-buffer of recent ``DataItem`` objects.
        5. Publishing new items to Redis Pub/Sub for real-time consumers.

    Usage::

        pipeline = DataPipeline()
        pipeline.register_source(YahooFinanceSource())
        pipeline.register_source(RSSNewsSource())
        await pipeline.start_continuous(interval_seconds=300)
        ...
        await pipeline.stop()
    """

    def __init__(
        self,
        redis_url: str | None = None,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
    ) -> None:
        self._sources: dict[str, BaseDataSource] = {}
        self._buffer: dict[str, deque[DataItem]] = defaultdict(
            lambda: deque(maxlen=buffer_size)
        )
        self._buffer_size = buffer_size
        self._redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Source registration
    # ------------------------------------------------------------------

    def register_source(self, source: BaseDataSource) -> None:
        """Add a data source to the pipeline.

        Args:
            source: An instance of a ``BaseDataSource`` subclass.

        Raises:
            ValueError: If a source with the same name is already registered.
        """

        if source.name in self._sources:
            raise ValueError(f"Source '{source.name}' is already registered.")
        self._sources[source.name] = source
        logger.info(
            "Registered data source: %s (type=%s)", source.name, source.source_type
        )

    def unregister_source(self, name: str) -> None:
        """Remove a previously registered source by name."""
        self._sources.pop(name, None)
        logger.info("Unregistered data source: %s", name)

    @property
    def sources(self) -> dict[str, BaseDataSource]:
        """Read-only view of registered sources."""
        return dict(self._sources)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    async def fetch_all(self) -> list[DataItem]:
        """Fetch from **all** enabled sources concurrently.

        Returns:
            Merged list of ``DataItem`` objects from every source.
        """

        enabled = [s for s in self._sources.values() if s._enabled]
        if not enabled:
            logger.warning("No enabled sources to fetch from.")
            return []

        logger.info("Fetching from %d enabled sources...", len(enabled))
        tasks = [self._safe_fetch(source) for source in enabled]
        results = await asyncio.gather(*tasks)

        all_items: list[DataItem] = []
        for items in results:
            all_items.extend(items)

        # Buffer and publish
        await self._ingest(all_items)
        logger.info("fetch_all produced %d items total.", len(all_items))
        return all_items

    async def fetch_by_type(self, source_type: str) -> list[DataItem]:
        """Fetch from sources matching *source_type* (e.g. "news", "price").

        Args:
            source_type: The type tag to filter on.

        Returns:
            Merged list of ``DataItem`` objects from matching sources.
        """

        matching = [
            s for s in self._sources.values()
            if s.source_type == source_type and s._enabled
        ]
        if not matching:
            logger.warning("No enabled sources of type '%s'.", source_type)
            return []

        tasks = [self._safe_fetch(source) for source in matching]
        results = await asyncio.gather(*tasks)

        all_items: list[DataItem] = []
        for items in results:
            all_items.extend(items)

        await self._ingest(all_items)
        return all_items

    # ------------------------------------------------------------------
    # Continuous background loop
    # ------------------------------------------------------------------

    async def start_continuous(self, interval_seconds: int = 300) -> None:
        """Start a background task that calls ``fetch_all`` on a timer.

        Args:
            interval_seconds: Seconds between successive fetch cycles.
        """

        if self._running:
            logger.warning("Continuous pipeline is already running.")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop(interval_seconds))
        logger.info(
            "Started continuous data pipeline (interval=%ds).", interval_seconds
        )

    async def stop(self) -> None:
        """Stop the background fetching loop and close Redis."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._redis is not None:
            await self._redis.close()
            self._redis = None

        logger.info("Data pipeline stopped.")

    # ------------------------------------------------------------------
    # Querying the buffer
    # ------------------------------------------------------------------

    def get_latest(
        self,
        source_type: str | None = None,
        limit: int = 50,
    ) -> list[DataItem]:
        """Return the most recent items from the in-memory buffer.

        Args:
            source_type: If provided, only return items of this type.
            limit: Maximum number of items to return.

        Returns:
            List of ``DataItem`` objects, newest first.
        """

        if source_type is not None:
            items = list(self._buffer.get(source_type, []))
        else:
            items = []
            for buf in self._buffer.values():
                items.extend(buf)

        # Sort newest first, then slice
        items.sort(key=lambda i: i.fetched_at, reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _safe_fetch(self, source: BaseDataSource) -> list[DataItem]:
        """Call ``source.fetch()`` and swallow exceptions so that one
        failing source does not break the entire pipeline."""
        try:
            return await source.fetch()
        except Exception:
            logger.exception("Error fetching from source '%s'", source.name)
            return []

    async def _ingest(self, items: list[DataItem]) -> None:
        """Buffer items and publish to Redis."""
        for item in items:
            self._buffer[item.source_type].append(item)

        # Publish to Redis if available
        await self._publish_to_redis(items)

    async def _publish_to_redis(self, items: list[DataItem]) -> None:
        """Publish each item to the Redis Pub/Sub channel."""
        if not items:
            return
        try:
            redis = await self._get_redis()
            if redis is None:
                return

            pipe = redis.pipeline()
            for item in items:
                payload = self._serialize_item(item)
                pipe.publish(_REDIS_CHANNEL, payload)
                # Also push to a capped Redis list for persistence
                pipe.lpush(_REDIS_BUFFER_KEY, payload)

            # Trim the Redis list to prevent unbounded growth
            pipe.ltrim(_REDIS_BUFFER_KEY, 0, self._buffer_size * 5)
            await pipe.execute()
        except Exception:
            logger.warning("Failed to publish items to Redis", exc_info=True)

    async def _get_redis(self) -> aioredis.Redis | None:
        """Lazily connect to Redis, returning None if unavailable."""
        if self._redis is not None:
            return self._redis
        try:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
            await self._redis.ping()
            return self._redis
        except Exception:
            logger.debug("Redis not available at %s", self._redis_url)
            self._redis = None
            return None

    async def _loop(self, interval: int) -> None:
        """Internal loop for continuous fetching."""
        while self._running:
            try:
                await self.fetch_all()
            except Exception:
                logger.exception("Error in continuous fetch cycle")
            await asyncio.sleep(interval)

    @staticmethod
    def _serialize_item(item: DataItem) -> str:
        """Serialize a ``DataItem`` to a JSON string for Redis."""
        d = asdict(item)
        # Convert datetimes to ISO strings
        for key in ("published_at", "fetched_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = val.isoformat()
        return json.dumps(d, default=str)
