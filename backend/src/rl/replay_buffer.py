"""
Experience replay buffer for the Overture RL training system.

Stores agent experiences (state, action, reward, next_state) and supports
both uniform random sampling and prioritised sampling (where experiences
with larger absolute rewards are sampled more frequently).

The buffer uses a fixed-size deque so that old experiences are automatically
evicted when the buffer is full, keeping the training data fresh.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Experience:
    """A single RL experience tuple recorded during agent operation.

    Attributes:
        episode_id: Identifier of the episode this experience belongs to.
        step: The step number within the episode.
        agent_name: Name of the agent that produced this experience.
        state: The observation the agent saw before acting.
        action: The action the agent selected.
        reward: The scalar reward received after the action.
        next_state: The observation after the action was executed.
        done: Whether the episode terminated after this step.
        metadata: Additional information (e.g. reward breakdown, latency).
        timestamp: When this experience was recorded.
    """

    episode_id: str
    step: int
    agent_name: str
    state: dict[str, Any]
    action: dict[str, Any]
    reward: float
    next_state: dict[str, Any]
    done: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ReplayBuffer:
    """Fixed-size experience replay buffer with uniform and prioritised sampling.

    Usage::

        buffer = ReplayBuffer(max_size=10_000)
        buffer.add(experience)
        batch = buffer.sample(batch_size=32)
        prioritised_batch = buffer.sample_prioritized(batch_size=32, alpha=0.6)
    """

    def __init__(self, max_size: int = 10000) -> None:
        self.max_size = max_size
        self._buffer: deque[Experience] = deque(maxlen=max_size)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def add(self, experience: Experience) -> None:
        """Store an experience in the buffer.

        If the buffer is full the oldest experience is automatically
        evicted.

        Args:
            experience: The experience to store.
        """
        self._buffer.append(experience)

    def sample(self, batch_size: int) -> list[Experience]:
        """Sample a uniformly random batch of experiences.

        Args:
            batch_size: Number of experiences to sample.

        Returns:
            A list of randomly sampled experiences.  If the buffer
            contains fewer than *batch_size* experiences, all
            experiences are returned (in random order).
        """
        k = min(batch_size, len(self._buffer))
        return random.sample(list(self._buffer), k)

    def sample_prioritized(
        self, batch_size: int, alpha: float = 0.6
    ) -> list[Experience]:
        """Sample a batch of experiences prioritised by absolute reward.

        Experiences with larger ``|reward|`` are sampled with higher
        probability.  The *alpha* parameter controls how strongly the
        sampling is biased: ``alpha=0`` is uniform, ``alpha=1`` is
        fully proportional to ``|reward|``.

        Args:
            batch_size: Number of experiences to sample.
            alpha: Prioritisation exponent (0 = uniform, 1 = full
                priority).  Defaults to 0.6.

        Returns:
            A list of prioritised-sampled experiences.
        """
        if not self._buffer:
            return []

        k = min(batch_size, len(self._buffer))
        buffer_list = list(self._buffer)

        # Compute priorities as |reward|^alpha + small epsilon for stability
        epsilon = 1e-6
        priorities = [
            (abs(exp.reward) + epsilon) ** alpha for exp in buffer_list
        ]
        total_priority = sum(priorities)
        weights = [p / total_priority for p in priorities]

        # Weighted sampling without replacement
        indices = []
        remaining_weights = list(weights)
        remaining_indices = list(range(len(buffer_list)))

        for _ in range(k):
            if not remaining_indices:
                break
            chosen_idx = random.choices(
                remaining_indices, weights=remaining_weights, k=1
            )[0]
            pos = remaining_indices.index(chosen_idx)
            indices.append(chosen_idx)
            remaining_indices.pop(pos)
            remaining_weights.pop(pos)

        return [buffer_list[i] for i in indices]

    def size(self) -> int:
        """Return the number of experiences currently in the buffer."""
        return len(self._buffer)

    def clear(self) -> None:
        """Remove all experiences from the buffer."""
        self._buffer.clear()

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics about the buffer contents.

        Returns:
            Dictionary with keys:
            - ``size``: current number of experiences.
            - ``max_size``: maximum buffer capacity.
            - ``utilization_pct``: percentage of capacity used.
            - ``avg_reward``: mean reward across all experiences.
            - ``reward_std``: standard deviation of rewards.
            - ``reward_min``: minimum reward.
            - ``reward_max``: maximum reward.
            - ``reward_distribution``: histogram-like breakdown of
              reward ranges.
            - ``agents``: set of unique agent names in the buffer.
            - ``episodes``: number of unique episodes.
        """
        if not self._buffer:
            return {
                "size": 0,
                "max_size": self.max_size,
                "utilization_pct": 0.0,
                "avg_reward": 0.0,
                "reward_std": 0.0,
                "reward_min": 0.0,
                "reward_max": 0.0,
                "reward_distribution": {},
                "agents": [],
                "episodes": 0,
            }

        rewards = [exp.reward for exp in self._buffer]
        n = len(rewards)
        avg_reward = sum(rewards) / n
        variance = sum((r - avg_reward) ** 2 for r in rewards) / n
        reward_std = variance ** 0.5

        # Simple histogram buckets
        buckets = {
            "very_negative (< -1.0)": 0,
            "negative (-1.0 to 0)": 0,
            "zero (0)": 0,
            "positive (0 to 1.0)": 0,
            "very_positive (> 1.0)": 0,
        }
        for r in rewards:
            if r < -1.0:
                buckets["very_negative (< -1.0)"] += 1
            elif r < 0:
                buckets["negative (-1.0 to 0)"] += 1
            elif r == 0:
                buckets["zero (0)"] += 1
            elif r <= 1.0:
                buckets["positive (0 to 1.0)"] += 1
            else:
                buckets["very_positive (> 1.0)"] += 1

        agents = list({exp.agent_name for exp in self._buffer})
        episodes = len({exp.episode_id for exp in self._buffer})

        return {
            "size": n,
            "max_size": self.max_size,
            "utilization_pct": round(n / self.max_size * 100.0, 2),
            "avg_reward": round(avg_reward, 6),
            "reward_std": round(reward_std, 6),
            "reward_min": min(rewards),
            "reward_max": max(rewards),
            "reward_distribution": buckets,
            "agents": agents,
            "episodes": episodes,
        }

    def get_agent_experiences(
        self, agent_name: str, limit: int = 100
    ) -> list[Experience]:
        """Return experiences for a specific agent, most recent first.

        Args:
            agent_name: The agent to filter by.
            limit: Maximum number of experiences to return.

        Returns:
            A list of up to *limit* experiences for the given agent,
            ordered from most recent to oldest.
        """
        matching = [
            exp for exp in reversed(self._buffer)
            if exp.agent_name == agent_name
        ]
        return matching[:limit]
