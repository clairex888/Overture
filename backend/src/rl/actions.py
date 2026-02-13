"""
Action space definitions for the Overture RL trading agents.

Each agent role in the hedge fund pipeline has a distinct action space
representing the decisions it can make.  Actions are structured dicts
with a ``type`` key identifying the action and optional ``parameters``
providing action-specific arguments.

The :class:`ActionSpace` class validates actions, enumerates valid
actions given an agent role and environment state, and translates
between the structured action representation used by the environment
and the flat/numeric representations required by policy networks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Action-type enums (one per agent role)
# ---------------------------------------------------------------------------

class IdeaGeneratorAction(str, Enum):
    """Actions available to the idea-generation agent."""

    GENERATE_FROM_NEWS = "generate_from_news"
    GENERATE_FROM_SCREEN = "generate_from_screen"
    GENERATE_FROM_SOCIAL = "generate_from_social"
    GENERATE_FROM_ANOMALY = "generate_from_anomaly"
    SKIP = "skip"


class IdeaValidatorAction(str, Enum):
    """Actions available to the idea-validation agent."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_MORE_DATA = "request_more_data"
    BACKTEST_WITH_PARAMS = "backtest_with_params"


class TradeExecutorAction(str, Enum):
    """Actions available to the trade-execution agent."""

    CONSTRUCT_TRADE = "construct_trade"
    DEFER = "defer"
    REQUEST_PORTFOLIO_CHECK = "request_portfolio_check"


class TradeMonitorAction(str, Enum):
    """Actions available to the trade-monitoring agent."""

    HOLD = "hold"
    CLOSE = "close"
    ADJUST_STOP = "adjust_stop"
    ADJUST_TARGET = "adjust_target"
    ADD_TO_POSITION = "add_to_position"
    REDUCE_POSITION = "reduce_position"


class PortfolioConstructorAction(str, Enum):
    """Actions available to the portfolio-construction agent."""

    SET_ALLOCATION = "set_allocation"
    APPROVE_TRADE = "approve_trade"
    REJECT_TRADE = "reject_trade"
    REQUEST_HEDGE = "request_hedge"


class RiskManagerAction(str, Enum):
    """Actions available to the risk-management agent."""

    ALERT = "alert"
    PROPOSE_HEDGE = "propose_hedge"
    REDUCE_EXPOSURE = "reduce_exposure"
    NO_ACTION = "no_action"


# Mapping from role name to action enum for convenience
ROLE_ACTION_MAP: dict[str, type[Enum]] = {
    "idea_generator": IdeaGeneratorAction,
    "idea_validator": IdeaValidatorAction,
    "trade_executor": TradeExecutorAction,
    "trade_monitor": TradeMonitorAction,
    "portfolio_constructor": PortfolioConstructorAction,
    "risk_manager": RiskManagerAction,
}


# ---------------------------------------------------------------------------
# Structured action dataclass
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """A structured action taken by an agent.

    Attributes:
        type: The action identifier (matches the role's action enum value).
        parameters: Action-specific arguments.  For example an ``approve``
            action carries a ``confidence`` float, while ``construct_trade``
            carries instrument, size, entry, stop, and target fields.
        metadata: Optional extra information (e.g. reasoning text, latency).
    """

    type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary (JSON-safe)."""
        return {
            "type": self.type,
            "parameters": self.parameters,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """Deserialize from a plain dictionary."""
        return cls(
            type=data["type"],
            parameters=data.get("parameters", {}),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Parameter schemas per action (used for validation)
# ---------------------------------------------------------------------------

# Each entry maps an action-type string to the set of required parameter keys.
# Optional parameters are not listed here; validation only checks that the
# required keys are present and leaves higher-level semantic checks to the
# environment.

_PARAM_SCHEMA: dict[str, set[str]] = {
    # Idea Generator -- most actions need no params (the agent picks a source)
    IdeaGeneratorAction.GENERATE_FROM_NEWS.value: set(),
    IdeaGeneratorAction.GENERATE_FROM_SCREEN.value: set(),
    IdeaGeneratorAction.GENERATE_FROM_SOCIAL.value: set(),
    IdeaGeneratorAction.GENERATE_FROM_ANOMALY.value: set(),
    IdeaGeneratorAction.SKIP.value: set(),

    # Idea Validator
    IdeaValidatorAction.APPROVE.value: {"confidence"},
    IdeaValidatorAction.REJECT.value: {"reason"},
    IdeaValidatorAction.REQUEST_MORE_DATA.value: set(),
    IdeaValidatorAction.BACKTEST_WITH_PARAMS.value: {"backtest_params"},

    # Trade Executor
    TradeExecutorAction.CONSTRUCT_TRADE.value: {
        "instrument", "size", "entry", "stop", "target",
    },
    TradeExecutorAction.DEFER.value: set(),
    TradeExecutorAction.REQUEST_PORTFOLIO_CHECK.value: set(),

    # Trade Monitor
    TradeMonitorAction.HOLD.value: set(),
    TradeMonitorAction.CLOSE.value: set(),
    TradeMonitorAction.ADJUST_STOP.value: {"new_stop"},
    TradeMonitorAction.ADJUST_TARGET.value: {"new_target"},
    TradeMonitorAction.ADD_TO_POSITION.value: {"add_size"},
    TradeMonitorAction.REDUCE_POSITION.value: {"reduce_fraction"},

    # Portfolio Constructor
    PortfolioConstructorAction.SET_ALLOCATION.value: {"allocation"},
    PortfolioConstructorAction.APPROVE_TRADE.value: {"trade_id"},
    PortfolioConstructorAction.REJECT_TRADE.value: {"trade_id", "reason"},
    PortfolioConstructorAction.REQUEST_HEDGE.value: {"target_exposure"},

    # Risk Manager
    RiskManagerAction.ALERT.value: {"level", "metric"},
    RiskManagerAction.PROPOSE_HEDGE.value: {"hedge_trade"},
    RiskManagerAction.REDUCE_EXPOSURE.value: {"target"},
    RiskManagerAction.NO_ACTION.value: set(),
}


# ---------------------------------------------------------------------------
# ActionSpace
# ---------------------------------------------------------------------------

class ActionSpace:
    """Defines, validates, and enumerates actions for every agent role.

    This is the single source of truth for what an agent is allowed to do
    at any given step.  The :meth:`validate_action` method checks structural
    correctness, while :meth:`get_available_actions` returns the list of
    actions that are *semantically* valid given the current environment state
    (e.g. you cannot ``CLOSE`` a trade if no trade is open).
    """

    # ----- validation -----

    @staticmethod
    def validate_action(agent_role: str, action: dict[str, Any]) -> bool:
        """Check whether *action* is structurally valid for *agent_role*.

        Validates that:
        1. The action ``type`` belongs to the role's action enum.
        2. All required parameters for that action type are present.

        Args:
            agent_role: One of the six role identifiers
                (``idea_generator``, ``idea_validator``, etc.).
            action: The action dict (must contain at least ``type``).

        Returns:
            ``True`` if the action is valid, ``False`` otherwise.
        """
        action_enum = ROLE_ACTION_MAP.get(agent_role)
        if action_enum is None:
            return False

        action_type = action.get("type")
        if action_type is None:
            return False

        # Check the type belongs to the role
        valid_types = {member.value for member in action_enum}
        if action_type not in valid_types:
            return False

        # Check required parameters
        required_params = _PARAM_SCHEMA.get(action_type, set())
        provided_params = set(action.get("parameters", {}).keys())
        if not required_params.issubset(provided_params):
            return False

        return True

    # ----- enumeration -----

    @staticmethod
    def get_available_actions(
        agent_role: str,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return the list of actions currently valid for *agent_role*.

        This performs **semantic** filtering based on the environment
        *state*.  For instance the trade-monitor agent cannot ``CLOSE``
        if there is no open trade, and the idea-validator cannot
        ``APPROVE`` if no idea is pending.

        Args:
            agent_role: The role identifier string.
            state: The observation dict returned by the environment for
                this role.

        Returns:
            A list of action template dicts, each containing ``type`` and
            a ``parameters`` dict with placeholder/example values.
        """
        action_enum = ROLE_ACTION_MAP.get(agent_role)
        if action_enum is None:
            return []

        available: list[dict[str, Any]] = []

        if agent_role == "idea_generator":
            available = _available_idea_generator_actions(state)
        elif agent_role == "idea_validator":
            available = _available_idea_validator_actions(state)
        elif agent_role == "trade_executor":
            available = _available_trade_executor_actions(state)
        elif agent_role == "trade_monitor":
            available = _available_trade_monitor_actions(state)
        elif agent_role == "portfolio_constructor":
            available = _available_portfolio_constructor_actions(state)
        elif agent_role == "risk_manager":
            available = _available_risk_manager_actions(state)

        return available

    # ----- helpers -----

    @staticmethod
    def action_to_index(agent_role: str, action_type: str) -> int:
        """Map an action type string to a numeric index for policy networks.

        The index is simply the position of the action value in the
        role's enum (deterministic because Python ``Enum`` preserves
        declaration order).

        Returns:
            An integer index, or ``-1`` if the action type is unknown.
        """
        action_enum = ROLE_ACTION_MAP.get(agent_role)
        if action_enum is None:
            return -1
        for idx, member in enumerate(action_enum):
            if member.value == action_type:
                return idx
        return -1

    @staticmethod
    def index_to_action(agent_role: str, index: int) -> str | None:
        """Map a numeric index back to an action type string.

        Returns:
            The action type string, or ``None`` if out of range.
        """
        action_enum = ROLE_ACTION_MAP.get(agent_role)
        if action_enum is None:
            return None
        members = list(action_enum)
        if 0 <= index < len(members):
            return members[index].value
        return None

    @staticmethod
    def num_actions(agent_role: str) -> int:
        """Return the total number of discrete action types for *agent_role*."""
        action_enum = ROLE_ACTION_MAP.get(agent_role)
        if action_enum is None:
            return 0
        return len(action_enum)


# ---------------------------------------------------------------------------
# Per-role available-action helpers
# ---------------------------------------------------------------------------

def _available_idea_generator_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Determine which idea-generation actions are available given *state*."""
    actions: list[dict[str, Any]] = []

    # News-based generation available when there are recent news items
    if state.get("recent_news_embeddings") or state.get("has_news", True):
        actions.append({"type": IdeaGeneratorAction.GENERATE_FROM_NEWS.value, "parameters": {}})

    # Screen-based generation is always available
    actions.append({"type": IdeaGeneratorAction.GENERATE_FROM_SCREEN.value, "parameters": {}})

    # Social-media generation available if social data is present
    if state.get("trending_topics") or state.get("has_social", True):
        actions.append({"type": IdeaGeneratorAction.GENERATE_FROM_SOCIAL.value, "parameters": {}})

    # Anomaly-based generation available if unusual moves exist
    if state.get("unusual_moves") or state.get("has_anomalies", True):
        actions.append({"type": IdeaGeneratorAction.GENERATE_FROM_ANOMALY.value, "parameters": {}})

    # Skip is always available
    actions.append({"type": IdeaGeneratorAction.SKIP.value, "parameters": {}})

    return actions


def _available_idea_validator_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Determine which idea-validation actions are available given *state*."""
    actions: list[dict[str, Any]] = []

    # Validator needs a pending idea to act on
    has_idea = bool(state.get("idea_features"))
    if not has_idea:
        return actions

    actions.append({
        "type": IdeaValidatorAction.APPROVE.value,
        "parameters": {"confidence": 0.0},
    })
    actions.append({
        "type": IdeaValidatorAction.REJECT.value,
        "parameters": {"reason": ""},
    })
    actions.append({
        "type": IdeaValidatorAction.REQUEST_MORE_DATA.value,
        "parameters": {},
    })
    actions.append({
        "type": IdeaValidatorAction.BACKTEST_WITH_PARAMS.value,
        "parameters": {"backtest_params": {}},
    })

    return actions


def _available_trade_executor_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Determine which trade-execution actions are available given *state*."""
    actions: list[dict[str, Any]] = []

    has_idea = bool(state.get("idea_params"))
    has_instruments = bool(state.get("available_instruments"))

    if has_idea and has_instruments:
        actions.append({
            "type": TradeExecutorAction.CONSTRUCT_TRADE.value,
            "parameters": {
                "instrument": "",
                "size": 0.0,
                "entry": 0.0,
                "stop": 0.0,
                "target": 0.0,
            },
        })

    # Defer is always available when there is an idea to consider
    if has_idea:
        actions.append({
            "type": TradeExecutorAction.DEFER.value,
            "parameters": {},
        })

    actions.append({
        "type": TradeExecutorAction.REQUEST_PORTFOLIO_CHECK.value,
        "parameters": {},
    })

    return actions


def _available_trade_monitor_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Determine which trade-monitoring actions are available given *state*."""
    actions: list[dict[str, Any]] = []

    has_open_trade = state.get("trade_pnl") is not None

    if not has_open_trade:
        return actions

    actions.append({"type": TradeMonitorAction.HOLD.value, "parameters": {}})
    actions.append({"type": TradeMonitorAction.CLOSE.value, "parameters": {}})
    actions.append({
        "type": TradeMonitorAction.ADJUST_STOP.value,
        "parameters": {"new_stop": 0.0},
    })
    actions.append({
        "type": TradeMonitorAction.ADJUST_TARGET.value,
        "parameters": {"new_target": 0.0},
    })
    actions.append({
        "type": TradeMonitorAction.ADD_TO_POSITION.value,
        "parameters": {"add_size": 0.0},
    })
    actions.append({
        "type": TradeMonitorAction.REDUCE_POSITION.value,
        "parameters": {"reduce_fraction": 0.0},
    })

    return actions


def _available_portfolio_constructor_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Determine which portfolio-construction actions are available given *state*."""
    actions: list[dict[str, Any]] = []

    # Allocation adjustment is always available
    actions.append({
        "type": PortfolioConstructorAction.SET_ALLOCATION.value,
        "parameters": {"allocation": {}},
    })

    # Trade approval/rejection require a pending trade
    has_pending_trade = bool(state.get("pending_trade_id"))
    if has_pending_trade:
        actions.append({
            "type": PortfolioConstructorAction.APPROVE_TRADE.value,
            "parameters": {"trade_id": state.get("pending_trade_id", "")},
        })
        actions.append({
            "type": PortfolioConstructorAction.REJECT_TRADE.value,
            "parameters": {"trade_id": state.get("pending_trade_id", ""), "reason": ""},
        })

    actions.append({
        "type": PortfolioConstructorAction.REQUEST_HEDGE.value,
        "parameters": {"target_exposure": {}},
    })

    return actions


def _available_risk_manager_actions(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Determine which risk-management actions are available given *state*."""
    actions: list[dict[str, Any]] = []

    risk_metrics = state.get("risk_metrics", {})
    has_breach = any(
        v > threshold
        for metric_name, v in risk_metrics.items()
        if isinstance(v, (int, float))
        for threshold in [0.8]  # normalized breach threshold
    )

    actions.append({
        "type": RiskManagerAction.ALERT.value,
        "parameters": {"level": "info", "metric": ""},
    })

    if has_breach or state.get("needs_hedge", False):
        actions.append({
            "type": RiskManagerAction.PROPOSE_HEDGE.value,
            "parameters": {"hedge_trade": {}},
        })

    actions.append({
        "type": RiskManagerAction.REDUCE_EXPOSURE.value,
        "parameters": {"target": ""},
    })

    actions.append({
        "type": RiskManagerAction.NO_ACTION.value,
        "parameters": {},
    })

    return actions
