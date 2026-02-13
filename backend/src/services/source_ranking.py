"""Source credibility scoring service for the Overture AI hedge fund system.

Tracks the credibility of information sources (news outlets, analysts,
data providers) based on the historical accuracy and profitability of
investment ideas they generate. Designed to use an in-memory store for
the prototype with a clean interface for later database/Redis persistence.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SourceScore:
    """Credibility score and statistics for an information source."""

    name: str
    credibility_score: float = 0.5
    total_ideas: int = 0
    profitable_pct: float = 0.0
    avg_return: float = 0.0
    categories: list[str] = field(default_factory=list)
    last_updated: str = ""

    # Internal tracking (not always exposed)
    ideas_validated: int = 0
    ideas_profitable: int = 0
    total_return: float = 0.0
    returns_history: list[float] = field(default_factory=list)


# Default credibility priors for well-known source categories
_DEFAULT_PRIORS: dict[str, float] = {
    # Tier 1: Highly credible
    "bloomberg": 0.75,
    "reuters": 0.75,
    "wall_street_journal": 0.72,
    "financial_times": 0.72,
    "sec_filings": 0.80,
    "federal_reserve": 0.85,
    # Tier 2: Credible with caveats
    "cnbc": 0.60,
    "barrons": 0.65,
    "morningstar": 0.68,
    "seeking_alpha": 0.50,
    "yahoo_finance": 0.55,
    "marketwatch": 0.58,
    # Tier 3: Mixed credibility
    "reddit_wallstreetbets": 0.30,
    "reddit_investing": 0.40,
    "twitter_fintwit": 0.35,
    "stocktwits": 0.30,
    "motley_fool": 0.45,
    # Tier 4: Low base credibility
    "unknown": 0.25,
    "anonymous": 0.20,
    "penny_stock_newsletter": 0.10,
    # Internal
    "agent_generated": 0.55,
    "user_submitted": 0.50,
    "quantitative_screen": 0.60,
}


class SourceRankingService:
    """Service for tracking and ranking information source credibility.

    Maintains a credibility score for each source based on the
    historical outcomes of ideas attributed to that source. Scores
    are updated using a Bayesian-inspired approach that blends
    prior expectations with observed performance.

    Data is stored in-memory (dict) for the prototype. The interface
    is designed so the storage backend can be swapped to Redis or a
    database with minimal changes.
    """

    # Weight given to prior vs observed data (higher = more weight on prior)
    PRIOR_WEIGHT = 5
    # Minimum observations before score is considered reliable
    MIN_OBSERVATIONS = 3
    # Score decay factor per day of inactivity
    DECAY_FACTOR = 0.999

    def __init__(self) -> None:
        self._scores: dict[str, SourceScore] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Credibility score
    # ------------------------------------------------------------------

    async def get_credibility_score(self, source_name: str) -> float:
        """Get the current credibility score for a source.

        Returns the tracked score if available, otherwise the default
        prior for the source category, or 0.25 for unknown sources.

        Args:
            source_name: Canonical name of the source.

        Returns:
            Credibility score between 0.0 and 1.0.
        """
        normalized = self._normalize_name(source_name)

        async with self._lock:
            if normalized in self._scores:
                return self._scores[normalized].credibility_score

        # Return prior
        return _DEFAULT_PRIORS.get(normalized, 0.25)

    # ------------------------------------------------------------------
    # Score update
    # ------------------------------------------------------------------

    async def update_score(
        self,
        source_name: str,
        idea_id: str,
        outcome: dict[str, Any],
    ) -> float:
        """Update a source's credibility based on an idea outcome.

        The outcome dict should contain:
        - ``validated`` (bool): Whether the idea was validated.
        - ``profitable`` (bool): Whether the idea was profitable.
        - ``return_pct`` (float): The realized return percentage.
        - ``category`` (str, optional): The idea category.

        The credibility score is updated using a weighted blend of the
        prior expectation and the observed hit rate, incorporating a
        return-weighted bonus/penalty.

        Args:
            source_name: Canonical name of the source.
            idea_id: Unique identifier for the idea.
            outcome: Dict describing the idea's outcome.

        Returns:
            The updated credibility score.
        """
        normalized = self._normalize_name(source_name)
        validated = outcome.get("validated", False)
        profitable = outcome.get("profitable", False)
        return_pct = outcome.get("return_pct", 0.0)
        category = outcome.get("category", "general")

        async with self._lock:
            score = self._scores.get(normalized)
            if score is None:
                prior = _DEFAULT_PRIORS.get(normalized, 0.25)
                score = SourceScore(
                    name=source_name,
                    credibility_score=prior,
                    categories=[],
                )
                self._scores[normalized] = score

            # Update counters
            score.total_ideas += 1
            if validated:
                score.ideas_validated += 1
            if profitable:
                score.ideas_profitable += 1
            score.total_return += return_pct
            score.returns_history.append(return_pct)

            if category and category not in score.categories:
                score.categories.append(category)

            # Recompute credibility score using Bayesian-inspired update
            prior = _DEFAULT_PRIORS.get(normalized, 0.25)
            n = score.total_ideas

            # Profitability rate component
            if n > 0:
                observed_profitable_rate = score.ideas_profitable / n
            else:
                observed_profitable_rate = 0.0

            # Weighted blend of prior and observed
            # As n increases, observed data dominates
            blended_rate = (
                (self.PRIOR_WEIGHT * prior + n * observed_profitable_rate)
                / (self.PRIOR_WEIGHT + n)
            )

            # Return quality bonus/penalty
            if score.returns_history:
                avg_ret = np.mean(score.returns_history)
                # Map average return to a bonus in [-0.1, +0.1]
                return_bonus = float(np.clip(avg_ret * 2, -0.1, 0.1))
            else:
                return_bonus = 0.0

            # Final score: blend + bonus, clamped to [0, 1]
            new_score = float(np.clip(blended_rate + return_bonus, 0.0, 1.0))

            score.credibility_score = round(new_score, 4)
            score.profitable_pct = round(
                score.ideas_profitable / max(score.total_ideas, 1), 4
            )
            score.avg_return = round(
                score.total_return / max(score.total_ideas, 1), 4
            )
            score.last_updated = datetime.utcnow().isoformat()

        logger.info(
            "source_score_updated",
            source=source_name,
            idea_id=idea_id,
            new_score=score.credibility_score,
            total_ideas=score.total_ideas,
        )
        return score.credibility_score

    # ------------------------------------------------------------------
    # Top sources
    # ------------------------------------------------------------------

    async def get_top_sources(
        self,
        n: int = 10,
        category: str | None = None,
    ) -> list[SourceScore]:
        """Get the top N most credible sources.

        Args:
            n: Number of sources to return.
            category: Filter by idea category (optional).

        Returns:
            List of SourceScore ordered by credibility (descending).
        """
        async with self._lock:
            sources = list(self._scores.values())

        if category:
            sources = [s for s in sources if category in s.categories]

        # Only include sources with minimum observations
        qualified = [s for s in sources if s.total_ideas >= self.MIN_OBSERVATIONS]

        # Sort by credibility score descending, then by total ideas descending
        qualified.sort(key=lambda s: (-s.credibility_score, -s.total_ideas))

        return qualified[:n]

    # ------------------------------------------------------------------
    # Source statistics
    # ------------------------------------------------------------------

    async def get_source_stats(self, source_name: str) -> dict[str, Any]:
        """Get detailed statistics for a specific source.

        Args:
            source_name: Canonical name of the source.

        Returns:
            Dict with comprehensive source statistics, or a stub
            with default values if the source has no history.
        """
        normalized = self._normalize_name(source_name)

        async with self._lock:
            score = self._scores.get(normalized)

        if score is None:
            prior = _DEFAULT_PRIORS.get(normalized, 0.25)
            return {
                "name": source_name,
                "credibility_score": prior,
                "total_ideas": 0,
                "ideas_validated": 0,
                "ideas_profitable": 0,
                "profitable_pct": 0.0,
                "avg_return": 0.0,
                "categories": [],
                "reliability": "no_data",
                "prior_score": prior,
                "returns_distribution": {},
            }

        # Compute return distribution stats
        returns_dist: dict[str, Any] = {}
        if score.returns_history:
            arr = np.array(score.returns_history)
            returns_dist = {
                "mean": round(float(np.mean(arr)), 4),
                "median": round(float(np.median(arr)), 4),
                "std": round(float(np.std(arr)), 4),
                "min": round(float(np.min(arr)), 4),
                "max": round(float(np.max(arr)), 4),
                "count": len(arr),
                "positive_pct": round(float(np.mean(arr > 0)), 4),
            }

        # Reliability assessment
        if score.total_ideas >= 20:
            reliability = "high"
        elif score.total_ideas >= 10:
            reliability = "moderate"
        elif score.total_ideas >= self.MIN_OBSERVATIONS:
            reliability = "low"
        else:
            reliability = "insufficient"

        return {
            "name": score.name,
            "credibility_score": score.credibility_score,
            "total_ideas": score.total_ideas,
            "ideas_validated": score.ideas_validated,
            "ideas_profitable": score.ideas_profitable,
            "profitable_pct": score.profitable_pct,
            "avg_return": score.avg_return,
            "categories": score.categories,
            "reliability": reliability,
            "prior_score": _DEFAULT_PRIORS.get(normalized, 0.25),
            "returns_distribution": returns_dist,
            "last_updated": score.last_updated,
        }

    # ------------------------------------------------------------------
    # Idea re-ranking
    # ------------------------------------------------------------------

    async def rank_ideas_by_source(
        self,
        ideas: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Re-rank a list of ideas weighted by source credibility.

        Each idea dict should contain a ``source`` field and an
        optional ``confidence_score`` field. The final ranking score
        is a weighted combination of the idea's own confidence and
        the source's credibility.

        Args:
            ideas: List of idea dicts with at least ``source`` and
                optionally ``confidence_score``.

        Returns:
            The same list of ideas, sorted by combined score descending,
            with an added ``source_adjusted_score`` field.
        """
        logger.info("ranking_ideas_by_source", ideas_count=len(ideas))

        # Confidence weight vs source weight
        confidence_weight = 0.6
        source_weight = 0.4

        ranked: list[dict[str, Any]] = []
        for idea in ideas:
            source = idea.get("source", "unknown")
            confidence = idea.get("confidence_score", 0.5)
            source_cred = await self.get_credibility_score(source)

            adjusted = (confidence * confidence_weight) + (source_cred * source_weight)
            idea_copy = dict(idea)
            idea_copy["source_credibility"] = round(source_cred, 4)
            idea_copy["source_adjusted_score"] = round(adjusted, 4)
            ranked.append(idea_copy)

        ranked.sort(key=lambda i: -i["source_adjusted_score"])
        return ranked

    # ------------------------------------------------------------------
    # Bulk initialization
    # ------------------------------------------------------------------

    async def initialize_sources(
        self,
        sources: list[dict[str, Any]],
    ) -> None:
        """Bulk-initialize source scores from persisted data.

        Designed to be called at startup to restore state from a
        database or configuration file.

        Args:
            sources: List of dicts with source data matching
                SourceScore fields.
        """
        async with self._lock:
            for src in sources:
                name = src.get("name", "")
                normalized = self._normalize_name(name)
                self._scores[normalized] = SourceScore(
                    name=name,
                    credibility_score=src.get("credibility_score", 0.5),
                    total_ideas=src.get("total_ideas", 0),
                    profitable_pct=src.get("profitable_pct", 0.0),
                    avg_return=src.get("avg_return", 0.0),
                    categories=src.get("categories", []),
                    last_updated=src.get("last_updated", ""),
                    ideas_validated=src.get("ideas_validated", 0),
                    ideas_profitable=src.get("ideas_profitable", 0),
                    total_return=src.get("total_return", 0.0),
                    returns_history=src.get("returns_history", []),
                )

        logger.info("sources_initialized", count=len(sources))

    async def export_scores(self) -> list[dict[str, Any]]:
        """Export all source scores for persistence.

        Returns:
            List of dicts representing each tracked source.
        """
        async with self._lock:
            return [
                {
                    "name": s.name,
                    "credibility_score": s.credibility_score,
                    "total_ideas": s.total_ideas,
                    "profitable_pct": s.profitable_pct,
                    "avg_return": s.avg_return,
                    "categories": s.categories,
                    "last_updated": s.last_updated,
                    "ideas_validated": s.ideas_validated,
                    "ideas_profitable": s.ideas_profitable,
                    "total_return": s.total_return,
                    "returns_history": s.returns_history,
                }
                for s in self._scores.values()
            ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize a source name for consistent lookup.

        Converts to lowercase, replaces spaces and hyphens with
        underscores, and strips whitespace.
        """
        return name.strip().lower().replace(" ", "_").replace("-", "_")
