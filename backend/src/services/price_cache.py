"""
Centralized Price Cache Service.

Provides a shared, in-memory price cache that all users share.
Prices auto-refresh every 30 minutes via a background task and can be
force-refreshed by any user.  When one user triggers a refresh, the
updated prices are immediately visible to every other user.

The cache also persists price updates into portfolio positions and
portfolio totals so that PnL is always up-to-date.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CachedPrice:
    """A single cached price entry."""

    ticker: str
    price: float
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume: int | None = None
    updated_at: datetime = field(default_factory=datetime.utcnow)


class PriceCacheService:
    """Singleton price cache shared across all users and requests.

    - Stores the latest price for every ticker held in any portfolio.
    - Auto-refreshes every ``refresh_interval`` seconds (default 30 min).
    - On each refresh, updates Position and Portfolio rows in the DB so
      that PnL, market_value, and total_value stay current.
    """

    _instance: PriceCacheService | None = None

    def __init__(self) -> None:
        self._cache: dict[str, CachedPrice] = {}
        self._last_refresh: datetime | None = None
        self._refreshing: bool = False
        self.refresh_interval: int = 1800  # 30 minutes

    @classmethod
    def get_instance(cls) -> PriceCacheService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def last_refresh(self) -> datetime | None:
        return self._last_refresh

    @property
    def is_refreshing(self) -> bool:
        return self._refreshing

    def get_price(self, ticker: str) -> CachedPrice | None:
        return self._cache.get(ticker)

    def get_prices(self, tickers: list[str]) -> dict[str, CachedPrice]:
        return {t: self._cache[t] for t in tickers if t in self._cache}

    def get_all_prices(self) -> dict[str, CachedPrice]:
        return dict(self._cache)

    def get_status(self) -> dict[str, Any]:
        return {
            "tickers_cached": len(self._cache),
            "last_refresh": (
                self._last_refresh.isoformat() + "Z" if self._last_refresh else None
            ),
            "is_refreshing": self._refreshing,
            "refresh_interval_seconds": self.refresh_interval,
        }

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------

    async def refresh_prices(
        self, tickers: list[str] | None = None
    ) -> dict[str, CachedPrice]:
        """Fetch latest prices and persist updates to the DB.

        Args:
            tickers: Explicit list of tickers to refresh.  If *None*,
                     discovers tickers from all portfolio positions.

        Returns:
            The full cache dict after the refresh.
        """
        if self._refreshing:
            logger.info("Price refresh already in progress, skipping")
            return self._cache

        self._refreshing = True
        try:
            if tickers is None:
                tickers = await self._get_all_portfolio_tickers()

            if not tickers:
                logger.info("No tickers to refresh")
                return self._cache

            logger.info("Refreshing prices for %d tickers: %s", len(tickers), tickers)
            prices = await self._batch_fetch_prices(tickers)

            now = datetime.utcnow()
            updated = 0
            for ticker, data in prices.items():
                if data is not None:
                    self._cache[ticker] = CachedPrice(
                        ticker=ticker,
                        price=data["price"],
                        prev_close=data.get("prev_close"),
                        change=data.get("change"),
                        change_pct=data.get("change_pct"),
                        volume=data.get("volume"),
                        updated_at=now,
                    )
                    updated += 1

            self._last_refresh = now
            logger.info("Price cache refreshed: %d/%d tickers updated", updated, len(tickers))

            # Persist updated prices to Position / Portfolio rows
            await self._update_portfolio_positions()

            return self._cache
        except Exception:
            logger.exception("Error during price refresh")
            return self._cache
        finally:
            self._refreshing = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_all_portfolio_tickers(self) -> list[str]:
        """Return unique tickers from every position in the DB."""
        from sqlalchemy import distinct, select

        from src.models.base import async_session_factory
        from src.models.portfolio import Position

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(distinct(Position.ticker))
                )
                return [row[0] for row in result.all()]
        except Exception:
            logger.warning("Could not query portfolio tickers", exc_info=True)
            return list(self._cache.keys())

    async def _batch_fetch_prices(
        self, tickers: list[str]
    ) -> dict[str, dict[str, Any] | None]:
        """Fetch current prices for multiple tickers via yfinance."""
        import yfinance as yf

        def _fetch() -> dict[str, dict[str, Any] | None]:
            results: dict[str, dict[str, Any] | None] = {}
            for ticker in tickers:
                try:
                    t = yf.Ticker(ticker)
                    hist = t.history(period="5d")
                    if hist.empty:
                        results[ticker] = None
                        continue

                    current = float(hist["Close"].iloc[-1])
                    prev = (
                        float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
                    )
                    volume = (
                        int(hist["Volume"].iloc[-1])
                        if "Volume" in hist.columns
                        else None
                    )

                    change = None
                    change_pct = None
                    if prev is not None and prev > 0:
                        change = current - prev
                        change_pct = change / prev * 100

                    results[ticker] = {
                        "price": current,
                        "prev_close": prev,
                        "change": change,
                        "change_pct": change_pct,
                        "volume": volume,
                    }
                except Exception:
                    logger.warning(
                        "Failed to fetch price for %s", ticker, exc_info=True
                    )
                    results[ticker] = None
            return results

        return await asyncio.to_thread(_fetch)

    async def _update_portfolio_positions(self) -> None:
        """Write cached prices into Position rows and recalculate Portfolio totals."""
        from sqlalchemy import select

        from src.models.base import async_session_factory
        from src.models.portfolio import Portfolio, Position

        try:
            async with async_session_factory() as session:
                # Update every position with cached prices
                result = await session.execute(select(Position))
                positions = result.scalars().all()

                portfolio_ids: set[str] = set()
                for pos in positions:
                    cached = self._cache.get(pos.ticker)
                    if cached is None:
                        continue

                    pos.current_price = cached.price
                    pos.market_value = (pos.quantity or 0) * cached.price

                    entry = pos.avg_entry_price or 0
                    if entry > 0:
                        pnl = (cached.price - entry) * (pos.quantity or 0)
                        pnl_pct = (cached.price - entry) / entry * 100
                        if pos.direction == "short":
                            pnl = -pnl
                            pnl_pct = -pnl_pct
                        pos.pnl = round(pnl, 2)
                        pos.pnl_pct = round(pnl_pct, 4)

                    portfolio_ids.add(pos.portfolio_id)

                # Recalculate portfolio-level totals
                for pid in portfolio_ids:
                    port_result = await session.execute(
                        select(Portfolio).where(Portfolio.id == pid)
                    )
                    portfolio = port_result.scalar_one_or_none()
                    if portfolio is None:
                        continue

                    pos_result = await session.execute(
                        select(Position).where(Position.portfolio_id == pid)
                    )
                    port_positions = pos_result.scalars().all()

                    total_market_value = sum(
                        p.market_value or 0 for p in port_positions
                    )
                    total_pnl = sum(p.pnl or 0 for p in port_positions)

                    portfolio.invested = round(total_market_value, 2)
                    portfolio.total_value = round(
                        total_market_value + (portfolio.cash or 0), 2
                    )
                    portfolio.pnl = round(total_pnl, 2)

                    initial_invested = sum(
                        (p.avg_entry_price or 0) * (p.quantity or 0)
                        for p in port_positions
                    )
                    portfolio.pnl_pct = (
                        round(total_pnl / initial_invested * 100, 4)
                        if initial_invested > 0
                        else 0
                    )

                    # Recalculate weights
                    total_val = portfolio.total_value or 1
                    for p in port_positions:
                        p.weight = round((p.market_value or 0) / total_val, 6)

                await session.commit()
                logger.info(
                    "Updated %d portfolios with latest prices", len(portfolio_ids)
                )
        except Exception:
            logger.exception("Error updating portfolio positions")


# ------------------------------------------------------------------
# Background loop
# ------------------------------------------------------------------


async def price_refresh_loop() -> None:
    """Infinite loop that refreshes prices every ``refresh_interval`` seconds.

    Designed to be launched as an ``asyncio.create_task`` during app startup.
    The first refresh fires immediately so the cache is warm.
    """
    cache = PriceCacheService.get_instance()

    # Small delay on startup so DB tables are ready
    await asyncio.sleep(5)

    while True:
        try:
            await cache.refresh_prices()
        except Exception:
            logger.exception("Price refresh loop error")

        await asyncio.sleep(cache.refresh_interval)
