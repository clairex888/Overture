"""
RL Trainer and Episode Manager for the Overture multi-agent system.
Manages training loops, experience collection, and agent improvement
based on reinforcement learning from investment outcomes.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.rl.replay_buffer import Experience, ReplayBuffer


@dataclass
class TrainResult:
    """Result of a training step."""

    agent_name: str
    batch_size: int
    avg_reward: float
    reward_std: float
    insights: list[str] = field(default_factory=list)
    updated_parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeSummary:
    """Summary of a completed episode."""

    episode_id: str
    agent_name: str
    total_reward: float
    total_steps: int
    outcome: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None = None


class RLTrainer:
    """
    Manages RL training for all agents in the Overture system.

    In the current scaffold, 'training' means:
    1. Collecting experiences from agent interactions
    2. Computing statistics over batches of experiences
    3. Generating human-readable insights about what works/doesn't
    4. Suggesting parameter adjustments for agent prompts/behavior

    Future versions will implement actual policy gradient or Q-learning.
    """

    def __init__(self, replay_buffer: ReplayBuffer | None = None):
        self.replay_buffer = replay_buffer or ReplayBuffer()
        self._train_counts: dict[str, int] = defaultdict(int)
        self._last_train_time: dict[str, datetime] = {}
        self._training_history: dict[str, list[TrainResult]] = defaultdict(list)
        self._min_experiences_to_train = 100
        self._train_interval_seconds = 300  # 5 minutes between training steps
        self._running = False

    def record_experience(
        self,
        agent_name: str,
        state: dict[str, Any],
        action: dict[str, Any],
        reward: float,
        next_state: dict[str, Any],
        done: bool,
        metadata: dict[str, Any] | None = None,
        episode_id: str = "",
    ) -> None:
        """Record an experience from an agent interaction."""
        experience = Experience(
            episode_id=episode_id,
            step=self._get_next_step(episode_id),
            agent_name=agent_name,
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            metadata=metadata or {},
            timestamp=datetime.utcnow(),
        )
        self.replay_buffer.add(experience)

    def _get_next_step(self, episode_id: str) -> int:
        """Get the next step number for an episode."""
        if not episode_id:
            return 0
        existing = [
            e.step
            for e in self.replay_buffer._buffer
            if e.episode_id == episode_id
        ]
        return max(existing, default=-1) + 1

    def should_train(self, agent_name: str) -> bool:
        """Check if enough experiences have been collected to warrant training."""
        agent_experiences = self.replay_buffer.get_agent_experiences(
            agent_name, limit=self._min_experiences_to_train
        )
        if len(agent_experiences) < self._min_experiences_to_train:
            return False

        last_train = self._last_train_time.get(agent_name)
        if last_train:
            elapsed = (datetime.utcnow() - last_train).total_seconds()
            if elapsed < self._train_interval_seconds:
                return False

        return True

    def train_step(self, agent_name: str, batch_size: int = 64) -> TrainResult:
        """
        Perform one training step for an agent.

        Current implementation: analyze experience batch and generate insights.
        Future: actual gradient-based policy updates.
        """
        batch = self.replay_buffer.sample(min(batch_size, self.replay_buffer.size()))

        agent_batch = [e for e in batch if e.agent_name == agent_name]
        if not agent_batch:
            agent_batch = self.replay_buffer.get_agent_experiences(agent_name, limit=batch_size)

        if not agent_batch:
            return TrainResult(
                agent_name=agent_name,
                batch_size=0,
                avg_reward=0.0,
                reward_std=0.0,
                insights=["No experiences available for training"],
            )

        rewards = [e.reward for e in agent_batch]
        avg_reward = sum(rewards) / len(rewards)
        reward_std = (sum((r - avg_reward) ** 2 for r in rewards) / len(rewards)) ** 0.5

        insights = self._generate_insights(agent_name, agent_batch, avg_reward, reward_std)
        updated_params = self._suggest_parameter_updates(agent_name, agent_batch, avg_reward)

        result = TrainResult(
            agent_name=agent_name,
            batch_size=len(agent_batch),
            avg_reward=avg_reward,
            reward_std=reward_std,
            insights=insights,
            updated_parameters=updated_params,
        )

        self._train_counts[agent_name] += 1
        self._last_train_time[agent_name] = datetime.utcnow()
        self._training_history[agent_name].append(result)

        return result

    def _generate_insights(
        self,
        agent_name: str,
        batch: list[Experience],
        avg_reward: float,
        reward_std: float,
    ) -> list[str]:
        """Generate human-readable insights from experience batch."""
        insights = []

        positive = [e for e in batch if e.reward > 0]
        negative = [e for e in batch if e.reward < 0]
        win_rate = len(positive) / len(batch) if batch else 0

        insights.append(
            f"Win rate: {win_rate:.1%} ({len(positive)}/{len(batch)} positive outcomes)"
        )
        insights.append(f"Avg reward: {avg_reward:.3f} (std: {reward_std:.3f})")

        if positive:
            best = max(positive, key=lambda e: e.reward)
            insights.append(
                f"Best action: {best.action.get('type', 'unknown')} "
                f"with reward {best.reward:.3f}"
            )

            pos_actions = defaultdict(list)
            for e in positive:
                pos_actions[e.action.get("type", "unknown")].append(e.reward)
            best_action_type = max(pos_actions, key=lambda k: sum(pos_actions[k]) / len(pos_actions[k]))
            insights.append(
                f"Most profitable action type: '{best_action_type}' "
                f"(avg reward: {sum(pos_actions[best_action_type]) / len(pos_actions[best_action_type]):.3f})"
            )

        if negative:
            worst = min(negative, key=lambda e: e.reward)
            insights.append(
                f"Worst action: {worst.action.get('type', 'unknown')} "
                f"with reward {worst.reward:.3f}"
            )

        if len(batch) >= 10:
            recent = sorted(batch, key=lambda e: e.timestamp)[-10:]
            recent_avg = sum(e.reward for e in recent) / len(recent)
            trend = "improving" if recent_avg > avg_reward else "declining"
            insights.append(f"Recent performance trend: {trend} (recent avg: {recent_avg:.3f})")

        return insights

    def _suggest_parameter_updates(
        self,
        agent_name: str,
        batch: list[Experience],
        avg_reward: float,
    ) -> dict[str, Any]:
        """Suggest parameter adjustments based on experience patterns."""
        updates: dict[str, Any] = {}

        action_rewards: dict[str, list[float]] = defaultdict(list)
        for e in batch:
            action_type = e.action.get("type", "unknown")
            action_rewards[action_type].append(e.reward)

        action_preferences = {}
        for action_type, rewards in action_rewards.items():
            action_avg = sum(rewards) / len(rewards)
            action_preferences[action_type] = {
                "avg_reward": round(action_avg, 4),
                "count": len(rewards),
                "preference_weight": round(max(0.1, min(2.0, 1.0 + action_avg)), 4),
            }
        updates["action_preferences"] = action_preferences

        win_rate = sum(1 for e in batch if e.reward > 0) / len(batch) if batch else 0
        if win_rate < 0.3:
            updates["suggested_adjustments"] = [
                "Consider more conservative approach",
                "Increase validation threshold",
                "Reduce position sizing",
            ]
        elif win_rate > 0.7:
            updates["suggested_adjustments"] = [
                "Current strategy performing well",
                "Consider slightly increasing position sizes",
                "Explore similar patterns in other asset classes",
            ]

        updates["confidence_calibration"] = round(win_rate, 4)
        updates["train_iteration"] = self._train_counts.get(agent_name, 0) + 1

        return updates

    def get_training_stats(self, agent_name: str) -> dict[str, Any]:
        """Get aggregated training statistics for an agent."""
        history = self._training_history.get(agent_name, [])

        if not history:
            return {
                "agent_name": agent_name,
                "total_train_steps": 0,
                "status": "untrained",
            }

        return {
            "agent_name": agent_name,
            "total_train_steps": len(history),
            "latest_avg_reward": history[-1].avg_reward,
            "latest_reward_std": history[-1].reward_std,
            "reward_trend": [r.avg_reward for r in history[-20:]],
            "latest_insights": history[-1].insights,
            "total_experiences": self.replay_buffer.size(),
            "last_trained": self._last_train_time.get(agent_name, "never"),
        }

    def get_all_training_stats(self) -> list[dict[str, Any]]:
        """Get training stats for all agents that have been trained."""
        agents = set(self._train_counts.keys())
        agent_experiences = set(e.agent_name for e in self.replay_buffer._buffer)
        all_agents = agents | agent_experiences
        return [self.get_training_stats(name) for name in sorted(all_agents)]

    def update_agent_from_experience(
        self, agent_name: str, insights: list[str]
    ) -> dict[str, Any]:
        """
        Return updated parameters/prompt adjustments based on learned patterns.
        In the future this would directly modify agent behavior.
        """
        stats = self.get_training_stats(agent_name)

        return {
            "agent_name": agent_name,
            "insights_applied": insights,
            "updated_at": datetime.utcnow().isoformat(),
            "training_stats": stats,
            "prompt_additions": [
                f"Based on {stats.get('total_train_steps', 0)} training iterations: "
                + "; ".join(insights[:3])
            ]
            if insights
            else [],
        }


class EpisodeManager:
    """Manages RL episodes for tracking agent performance over time."""

    def __init__(self):
        self._episodes: dict[str, EpisodeSummary] = {}
        self._agent_episodes: dict[str, list[str]] = defaultdict(list)

    def start_episode(self, agent_name: str) -> str:
        """Start a new episode and return the episode ID."""
        episode_id = str(uuid.uuid4())
        summary = EpisodeSummary(
            episode_id=episode_id,
            agent_name=agent_name,
            total_reward=0.0,
            total_steps=0,
            outcome={},
            started_at=datetime.utcnow(),
        )
        self._episodes[episode_id] = summary
        self._agent_episodes[agent_name].append(episode_id)
        return episode_id

    def record_step(self, episode_id: str, reward: float) -> None:
        """Record a step within an episode."""
        if episode_id in self._episodes:
            self._episodes[episode_id].total_reward += reward
            self._episodes[episode_id].total_steps += 1

    def end_episode(self, episode_id: str, outcome: dict[str, Any]) -> EpisodeSummary | None:
        """End an episode and save the outcome."""
        if episode_id not in self._episodes:
            return None

        summary = self._episodes[episode_id]
        summary.ended_at = datetime.utcnow()
        summary.outcome = outcome
        return summary

    def get_episode(self, episode_id: str) -> EpisodeSummary | None:
        """Get a specific episode summary."""
        return self._episodes.get(episode_id)

    def get_episode_stats(
        self, agent_name: str, n_episodes: int = 50
    ) -> dict[str, Any]:
        """Get performance statistics over recent episodes for an agent."""
        episode_ids = self._agent_episodes.get(agent_name, [])[-n_episodes:]
        episodes = [self._episodes[eid] for eid in episode_ids if eid in self._episodes]

        if not episodes:
            return {
                "agent_name": agent_name,
                "total_episodes": 0,
                "status": "no episodes recorded",
            }

        completed = [e for e in episodes if e.ended_at is not None]
        rewards = [e.total_reward for e in completed]

        avg_reward = sum(rewards) / len(rewards) if rewards else 0
        best_reward = max(rewards) if rewards else 0
        worst_reward = min(rewards) if rewards else 0

        durations = []
        for e in completed:
            if e.ended_at and e.started_at:
                durations.append((e.ended_at - e.started_at).total_seconds())

        return {
            "agent_name": agent_name,
            "total_episodes": len(episodes),
            "completed_episodes": len(completed),
            "avg_reward": round(avg_reward, 4),
            "best_reward": round(best_reward, 4),
            "worst_reward": round(worst_reward, 4),
            "avg_steps": round(
                sum(e.total_steps for e in completed) / len(completed), 1
            )
            if completed
            else 0,
            "avg_duration_seconds": round(sum(durations) / len(durations), 1)
            if durations
            else 0,
            "reward_history": [round(r, 4) for r in rewards[-20:]],
            "recent_outcomes": [
                {
                    "episode_id": e.episode_id,
                    "reward": round(e.total_reward, 4),
                    "steps": e.total_steps,
                    "outcome": e.outcome,
                    "duration": (
                        (e.ended_at - e.started_at).total_seconds()
                        if e.ended_at
                        else None
                    ),
                }
                for e in completed[-10:]
            ],
        }

    def get_all_agent_stats(self) -> list[dict[str, Any]]:
        """Get episode stats for all agents."""
        return [
            self.get_episode_stats(agent_name)
            for agent_name in sorted(self._agent_episodes.keys())
        ]
