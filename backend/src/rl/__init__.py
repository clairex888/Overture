"""Reinforcement learning module for the Overture trading system.

This package provides the RL infrastructure that enables Overture agents
to learn from experience.  Key components:

- :class:`TradingEnvironment` -- Gym-like multi-agent trading environment.
- :class:`StateEncoder` -- Normalises raw environment state for each agent role.
- :class:`ActionSpace` -- Defines and validates actions per agent role.
- :class:`RewardCalculator` -- Computes role-specific reward signals.
- :class:`ReplayBuffer` -- Experience replay storage with prioritised sampling.
- :class:`RLTrainer` -- Orchestrates training from collected experience.
"""

from src.rl.environment import TradingEnvironment
from src.rl.state import StateEncoder
from src.rl.actions import ActionSpace
from src.rl.rewards import RewardCalculator
from src.rl.replay_buffer import ReplayBuffer
from src.rl.trainer import RLTrainer

__all__ = [
    "TradingEnvironment",
    "StateEncoder",
    "ActionSpace",
    "RewardCalculator",
    "ReplayBuffer",
    "RLTrainer",
]
