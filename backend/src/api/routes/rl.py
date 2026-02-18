"""
RL Training API routes.

Provides reinforcement learning training stats, episode history,
replay buffer metrics, and training control.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4
import math
import random

router = APIRouter()


class AgentRLStats(BaseModel):
    agent_name: str
    total_episodes: int
    avg_reward: float
    best_episode_reward: float
    worst_episode_reward: float
    status: str = Field(..., description="training, paused, converged, error")
    learning_rate: float
    epsilon: float
    reward_trend: list[float]
    insights: list[str]
    last_updated: str


class EpisodeEntry(BaseModel):
    id: str
    agent_name: str
    steps: int
    total_reward: float
    outcome: str
    duration_seconds: float
    timestamp: str


class ReplayBufferStats(BaseModel):
    size: int
    capacity: int
    avg_reward: float
    min_reward: float
    max_reward: float
    samples_per_second: int


class TrainingControlResponse(BaseModel):
    agent_name: str
    action: str
    success: bool
    message: str


# Seed data
_rl_stats: dict[str, dict[str, Any]] = {
    "idea_generation": {
        "agent_name": "idea_generation",
        "total_episodes": 4520,
        "avg_reward": 0.72,
        "best_episode_reward": 1.84,
        "worst_episode_reward": -0.93,
        "status": "training",
        "learning_rate": 0.0003,
        "epsilon": 0.15,
        "reward_trend": [round(0.1 + math.log(i + 1) * 0.18 + (random.random() - 0.5) * 0.15, 3) for i in range(50)],
        "insights": [
            "Buy-the-dip strategies after >3 sigma moves show 78% win rate over 2,100 episodes.",
            "News sentiment combined with options flow data improved idea quality score by 15%.",
            "Earnings surprise > 10% creates 3-day momentum in 71% of cases.",
        ],
        "last_updated": "2026-02-18T16:45:00Z",
    },
    "execution": {
        "agent_name": "execution",
        "total_episodes": 3890,
        "avg_reward": 0.58,
        "best_episode_reward": 2.12,
        "worst_episode_reward": -1.45,
        "status": "paused",
        "learning_rate": 0.0001,
        "epsilon": 0.10,
        "reward_trend": [round(-0.2 + math.log(i + 1) * 0.15 + (random.random() - 0.5) * 0.2, 3) for i in range(50)],
        "insights": [
            "Trailing stop at 2x ATR outperforms fixed stops by 23% in backtested episodes.",
            "Limit orders at bid/ask midpoint fill rate: 64%. Adjusting aggressiveness based on spread width.",
        ],
        "last_updated": "2026-02-18T15:30:00Z",
    },
    "portfolio_management": {
        "agent_name": "portfolio_management",
        "total_episodes": 6210,
        "avg_reward": 0.85,
        "best_episode_reward": 1.96,
        "worst_episode_reward": -0.67,
        "status": "training",
        "learning_rate": 0.0002,
        "epsilon": 0.08,
        "reward_trend": [round(0.15 + math.log(i + 1) * 0.2 + (random.random() - 0.5) * 0.12, 3) for i in range(50)],
        "insights": [
            "Sector concentration penalty (HHI > 0.15) consistently leads to -0.3 reward.",
            "Risk parity weighting outperforms equal weight by 0.12 Sharpe points.",
            "Rebalancing frequency of weekly outperforms daily by 0.08 Sharpe after transaction costs.",
        ],
        "last_updated": "2026-02-18T17:00:00Z",
    },
    "risk_management": {
        "agent_name": "risk_management",
        "total_episodes": 5100,
        "avg_reward": 0.91,
        "best_episode_reward": 1.52,
        "worst_episode_reward": -0.32,
        "status": "converged",
        "learning_rate": 0.00005,
        "epsilon": 0.03,
        "reward_trend": [round(0.3 + math.log(i + 1) * 0.16 + (random.random() - 0.5) * 0.08, 3) for i in range(50)],
        "insights": [
            "Converged on optimal VaR threshold of 2.5% NAV.",
            "Cross-asset correlation spikes during high-VIX regimes. Dynamically adjusts hedging.",
        ],
        "last_updated": "2026-02-18T12:00:00Z",
    },
}

_episodes: list[dict[str, Any]] = [
    {"id": "EP-4520", "agent_name": "idea_generation", "steps": 342, "total_reward": 1.24, "outcome": "profitable", "duration_seconds": 252, "timestamp": "2026-02-18T16:45:00Z"},
    {"id": "EP-4519", "agent_name": "idea_generation", "steps": 289, "total_reward": -0.31, "outcome": "loss", "duration_seconds": 225, "timestamp": "2026-02-18T16:40:00Z"},
    {"id": "EP-6210", "agent_name": "portfolio_management", "steps": 518, "total_reward": 1.67, "outcome": "profitable", "duration_seconds": 382, "timestamp": "2026-02-18T17:00:00Z"},
    {"id": "EP-6209", "agent_name": "portfolio_management", "steps": 445, "total_reward": 0.92, "outcome": "profitable", "duration_seconds": 338, "timestamp": "2026-02-18T16:55:00Z"},
    {"id": "EP-3890", "agent_name": "execution", "steps": 156, "total_reward": -0.85, "outcome": "loss", "duration_seconds": 123, "timestamp": "2026-02-18T15:30:00Z"},
    {"id": "EP-3889", "agent_name": "execution", "steps": 234, "total_reward": 1.45, "outcome": "profitable", "duration_seconds": 191, "timestamp": "2026-02-18T15:25:00Z"},
    {"id": "EP-5100", "agent_name": "risk_management", "steps": 612, "total_reward": 1.12, "outcome": "profitable", "duration_seconds": 465, "timestamp": "2026-02-18T12:00:00Z"},
    {"id": "EP-5099", "agent_name": "risk_management", "steps": 580, "total_reward": 0.88, "outcome": "profitable", "duration_seconds": 432, "timestamp": "2026-02-18T11:55:00Z"},
    {"id": "EP-4518", "agent_name": "idea_generation", "steps": 310, "total_reward": 0.56, "outcome": "profitable", "duration_seconds": 238, "timestamp": "2026-02-18T16:35:00Z"},
    {"id": "EP-6208", "agent_name": "portfolio_management", "steps": 490, "total_reward": -0.22, "outcome": "loss", "duration_seconds": 355, "timestamp": "2026-02-18T16:50:00Z"},
    {"id": "EP-3888", "agent_name": "execution", "steps": 198, "total_reward": 0.73, "outcome": "profitable", "duration_seconds": 161, "timestamp": "2026-02-18T15:20:00Z"},
    {"id": "EP-5098", "agent_name": "risk_management", "steps": 595, "total_reward": 1.05, "outcome": "profitable", "duration_seconds": 450, "timestamp": "2026-02-18T11:50:00Z"},
]

_replay_buffer = ReplayBufferStats(
    size=128450,
    capacity=256000,
    avg_reward=0.64,
    min_reward=-2.31,
    max_reward=2.85,
    samples_per_second=1240,
)


@router.get("/stats", response_model=list[AgentRLStats])
async def get_all_rl_stats():
    """Get RL training stats for all agents."""
    return [AgentRLStats(**s) for s in _rl_stats.values()]


@router.get("/stats/{agent_name}", response_model=AgentRLStats)
async def get_agent_rl_stats(agent_name: str):
    """Get RL training stats for a specific agent."""
    stats = _rl_stats.get(agent_name)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return AgentRLStats(**stats)


@router.get("/episodes/{agent_name}", response_model=list[EpisodeEntry])
async def get_episodes(
    agent_name: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Get episode history for a specific agent."""
    results = [e for e in _episodes if e["agent_name"] == agent_name]
    results.sort(key=lambda e: e["timestamp"], reverse=True)
    return [EpisodeEntry(**e) for e in results[:limit]]


@router.get("/replay-buffer/stats", response_model=ReplayBufferStats)
async def get_replay_buffer_stats():
    """Get replay buffer statistics."""
    return _replay_buffer


@router.post("/train/{agent_name}", response_model=TrainingControlResponse)
async def start_training(agent_name: str):
    """Start RL training for a specific agent."""
    stats = _rl_stats.get(agent_name)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    if stats["status"] == "training":
        return TrainingControlResponse(
            agent_name=agent_name,
            action="start",
            success=False,
            message=f"Agent '{agent_name}' is already training.",
        )

    stats["status"] = "training"
    stats["last_updated"] = datetime.utcnow().isoformat() + "Z"

    return TrainingControlResponse(
        agent_name=agent_name,
        action="start",
        success=True,
        message=f"Training started for '{agent_name}'.",
    )


@router.post("/train/{agent_name}/stop", response_model=TrainingControlResponse)
async def stop_training(agent_name: str):
    """Stop RL training for a specific agent."""
    stats = _rl_stats.get(agent_name)
    if not stats:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    if stats["status"] != "training":
        return TrainingControlResponse(
            agent_name=agent_name,
            action="stop",
            success=False,
            message=f"Agent '{agent_name}' is not currently training.",
        )

    stats["status"] = "paused"
    stats["last_updated"] = datetime.utcnow().isoformat() + "Z"

    return TrainingControlResponse(
        agent_name=agent_name,
        action="stop",
        success=True,
        message=f"Training stopped for '{agent_name}'.",
    )
