"""Reinforcement learning models for the Overture system.

Stores experience tuples and episode summaries for RL-based
agent training, enabling experience replay and performance tracking.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class RLExperience(Base):
    """A single experience tuple (s, a, r, s', done) for RL training.

    Stores individual state transitions collected during agent
    episodes, forming the basis for experience replay buffers
    used in off-policy RL algorithms.
    """

    __tablename__ = "rl_experiences"

    episode_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    action: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reward: Mapped[float] = mapped_column(Float, nullable=False)
    next_state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True, default=dict
    )

    def __repr__(self) -> str:
        return (
            f"<RLExperience(id={self.id!r}, episode_id={self.episode_id!r}, "
            f"step={self.step!r}, reward={self.reward!r})>"
        )


class RLEpisode(Base):
    """Summary of a complete RL training episode.

    Captures aggregate metrics for an episode including total reward,
    step count, and outcome details for tracking agent learning progress.
    """

    __tablename__ = "rl_episodes"

    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    total_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RLEpisode(id={self.id!r}, agent_name={self.agent_name!r}, "
            f"total_reward={self.total_reward!r}, total_steps={self.total_steps!r})>"
        )
