"""Base agent class and shared context for the Overture agent system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
import uuid


@dataclass
class AgentContext:
    """Shared context passed between agents.

    This dataclass carries state that flows through the agent pipeline,
    enabling agents to share information about the current session, user
    preferences, market conditions, portfolio state, and accumulated
    knowledge.

    Attributes:
        session_id: Unique identifier for the current agent session.
        user_preferences: User-specific settings such as risk appetite, asset
            class preferences, and notification thresholds.
        market_context: Current market conditions including regime indicators,
            volatility levels, and macro outlook.
        portfolio_state: Snapshot of the current portfolio including holdings,
            allocation percentages, and open orders.
        knowledge_context: Accumulated knowledge entries relevant to the
            current task, drawn from the knowledge library.
        messages: Inter-agent messages for coordination and information
            passing within a single pipeline execution.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_preferences: dict[str, Any] = field(default_factory=dict)
    market_context: dict[str, Any] = field(default_factory=dict)
    portfolio_state: dict[str, Any] = field(default_factory=dict)
    knowledge_context: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


class BaseAgent(ABC):
    """Base class for all Overture agents.

    Every agent in the Overture system inherits from this class, which
    provides a consistent interface for execution, prompt management, tool
    registration, and action logging.  The orchestrator injects an LLM
    provider instance via the ``_llm`` attribute before calling ``execute``.

    Attributes:
        name: Human-readable name of the agent.
        agent_type: Category of the agent (e.g. "idea", "portfolio",
            "knowledge", "context").
        description: Short description of what the agent does.
    """

    def __init__(self, name: str, agent_type: str, description: str):
        self.name = name
        self.agent_type = agent_type
        self.description = description
        self._llm = None  # Set by orchestrator

    @abstractmethod
    async def execute(
        self, input_data: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Execute the agent's primary task.

        Args:
            input_data: Task-specific input payload.
            context: Shared context with session, portfolio, and market state.

        Returns:
            A dictionary containing the agent's output, whose schema is
            defined by the concrete agent implementation.
        """
        ...

    def get_system_prompt(self) -> str:
        """Return the agent's system prompt for LLM interactions."""
        return f"You are {self.name}, an AI agent specialized in {self.description}."

    def get_tools(self) -> list[dict]:
        """Return tool definitions available to this agent.

        Each tool is described as a dictionary following the standard
        function-calling schema expected by the LLM provider.
        """
        return []

    async def log_action(
        self,
        action: str,
        input_data: dict,
        output_data: dict,
        status: str = "success",
        duration_ms: int = 0,
    ) -> dict[str, Any]:
        """Log an agent action for reinforcement learning and monitoring.

        Args:
            action: Name of the action performed.
            input_data: Inputs that triggered the action.
            output_data: Results produced by the action.
            status: Outcome status ("success", "failure", "partial").
            duration_ms: Wall-clock duration of the action in milliseconds.

        Returns:
            A structured log entry dictionary.
        """
        return {
            "agent_name": self.name,
            "agent_type": self.agent_type,
            "action": action,
            "input_data": input_data,
            "output_data": output_data,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }
