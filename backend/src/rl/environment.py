"""
Trading environment for RL training of investment agents.

Follows an OpenAI Gym-like interface but customised for a multi-agent
hedge fund where each agent role has its own state / action / reward
definition.

The environment tracks three interrelated state spaces:
1. **Market state** -- simulated or live prices, volumes, news sentiment,
   regime indicators, and sector performance.
2. **Portfolio state** -- positions, P&L, risk metrics, and allocation.
3. **Agent states** -- per-agent memory such as pending ideas, open
   trades, and recent actions.

Both *live* and *simulated* (historical replay) modes are supported.
In simulation mode the environment steps through a pre-loaded time
series; in live mode it pulls the latest market data on each step.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.config import settings
from src.utils.logging import get_logger

from src.rl.actions import ActionSpace
from src.rl.rewards import RewardCalculator
from src.rl.state import StateEncoder

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# AgentRole enum
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    """Identifies the six agent roles in the Overture pipeline."""

    IDEA_GENERATOR = "idea_generator"
    IDEA_VALIDATOR = "idea_validator"
    TRADE_EXECUTOR = "trade_executor"
    TRADE_MONITOR = "trade_monitor"
    PORTFOLIO_CONSTRUCTOR = "portfolio_constructor"
    RISK_MANAGER = "risk_manager"


# ---------------------------------------------------------------------------
# Environment mode
# ---------------------------------------------------------------------------

class EnvironmentMode(str, Enum):
    """Operating mode of the trading environment."""

    SIMULATED = "simulated"
    LIVE = "live"


# ---------------------------------------------------------------------------
# Step result dataclass
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """Result of a single environment step.

    Mirrors the classic ``(next_state, reward, done, info)`` tuple
    used in Gym-style environments, but returned as a named container
    for clarity.
    """

    next_state: dict[str, Any]
    reward: float
    done: bool
    info: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TradingEnvironment
# ---------------------------------------------------------------------------

class TradingEnvironment:
    """Multi-agent trading environment for RL.

    Each agent role has its own state / action / reward definition.
    The environment tracks market state, portfolio state, and agent
    interactions.

    Usage::

        env = TradingEnvironment(config={"mode": "simulated"})
        state = await env.reset(initial_market_state=historical_data)

        while not done:
            obs = await env.get_state(AgentRole.IDEA_GENERATOR)
            action = policy.select(obs)
            next_obs, reward, done, info = await env.step(
                AgentRole.IDEA_GENERATOR, action,
            )
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.mode = EnvironmentMode(self.config.get("mode", "simulated"))

        # Core state containers
        self.current_step: int = 0
        self.max_steps: int = self.config.get("max_steps", 1000)
        self.episode_id: str | None = None
        self.market_state: dict[str, Any] = {}
        self.portfolio_state: dict[str, Any] = {}
        self.agent_states: dict[str, dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []

        # Simulated market data (used in SIMULATED mode)
        self._market_timeline: list[dict[str, Any]] = []
        self._timeline_index: int = 0

        # Sub-components
        self.state_encoder = StateEncoder(self.config.get("state_encoder", {}))
        self.reward_calculator = RewardCalculator(self.config.get("reward_weights"))
        self.action_space = ActionSpace()

        # Tracking
        self._episode_total_reward: dict[str, float] = {}
        self._episode_start_time: datetime | None = None

    # ==================================================================
    # reset
    # ==================================================================

    async def reset(
        self,
        initial_market_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reset the environment for a new episode.

        Args:
            initial_market_state: Optional market snapshot to seed the
                environment with.  In *simulated* mode this should
                contain a ``timeline`` key with a list of market
                snapshots to replay.

        Returns:
            A dictionary keyed by agent role with each role's initial
            observation.
        """
        self.episode_id = str(uuid.uuid4())
        self.current_step = 0
        self.history = []
        self._episode_total_reward = {role.value: 0.0 for role in AgentRole}
        self._episode_start_time = datetime.now(timezone.utc)

        # Initialise market state
        if initial_market_state:
            timeline = initial_market_state.pop("timeline", None)
            self.market_state = initial_market_state
            if timeline:
                self._market_timeline = timeline
                self._timeline_index = 0
                if self._market_timeline:
                    self.market_state.update(self._market_timeline[0])
        else:
            self.market_state = self._default_market_state()

        # Initialise portfolio state
        self.portfolio_state = self._default_portfolio_state()

        # Initialise per-agent states
        self.agent_states = {
            role.value: self._default_agent_state(role.value)
            for role in AgentRole
        }

        # Build initial observations per role
        observations: dict[str, Any] = {}
        for role in AgentRole:
            observations[role.value] = await self.get_state(role)

        logger.info(
            "environment_reset",
            episode_id=self.episode_id,
            mode=self.mode.value,
            timeline_length=len(self._market_timeline),
        )
        return observations

    # ==================================================================
    # step
    # ==================================================================

    async def step(
        self,
        agent_role: AgentRole,
        action: dict[str, Any],
    ) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        """Execute *action* for *agent_role* and return the RL step tuple.

        The standard ``(next_state, reward, done, info)`` tuple is returned
        so callers can directly feed the result into a replay buffer.

        Args:
            agent_role: Which agent is acting.
            action: The structured action dict (must pass :meth:`ActionSpace.validate_action`).

        Returns:
            A 4-tuple ``(next_state, reward, done, info)``.
        """
        role_str = agent_role.value if isinstance(agent_role, AgentRole) else agent_role

        # Validate the action
        if not self.action_space.validate_action(role_str, action):
            logger.warning(
                "invalid_action",
                role=role_str,
                action=action,
            )
            next_state = await self.get_state(agent_role)
            return next_state, -0.1, False, {"error": "invalid_action"}

        # Execute the action and get outcome
        outcome = await self._execute_action(role_str, action)

        # Advance market state (only after all roles have acted for the step,
        # but for simplicity we advance after every action -- can be made
        # turn-based via config)
        if self.config.get("advance_market_per_action", True):
            self._advance_market()

        self.current_step += 1

        # Calculate reward
        reward = await self.calculate_reward(agent_role, action, outcome)
        self._episode_total_reward[role_str] = (
            self._episode_total_reward.get(role_str, 0.0) + reward
        )

        # Check termination
        done = self._is_done()

        # Get next state
        next_state = await self.get_state(agent_role)

        # Record history
        self.history.append({
            "step": self.current_step,
            "agent_role": role_str,
            "action": action,
            "reward": reward,
            "done": done,
            "outcome": outcome,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        info = {
            "episode_id": self.episode_id,
            "step": self.current_step,
            "outcome": outcome,
            "episode_reward": self._episode_total_reward[role_str],
        }

        return next_state, reward, done, info

    # ==================================================================
    # get_state
    # ==================================================================

    async def get_state(self, agent_role: AgentRole) -> dict[str, Any]:
        """Get the current observation for a specific agent role.

        Each role sees a different projection of the environment state,
        encoded by :class:`StateEncoder`.

        Args:
            agent_role: The role whose observation to construct.

        Returns:
            A normalised observation dict.
        """
        role_str = agent_role.value if isinstance(agent_role, AgentRole) else agent_role
        agent_state = self.agent_states.get(role_str, {})

        if role_str == AgentRole.IDEA_GENERATOR.value:
            knowledge_state = {
                "recent_news": agent_state.get("recent_news", []),
                "trending_topics": agent_state.get("trending_topics", []),
            }
            return self.state_encoder.encode_idea_generator_state(
                self.market_state, knowledge_state,
            )

        elif role_str == AgentRole.IDEA_VALIDATOR.value:
            pending_idea = agent_state.get("pending_idea", {})
            return self.state_encoder.encode_idea_validator_state(
                pending_idea, self.market_state,
            )

        elif role_str == AgentRole.TRADE_EXECUTOR.value:
            validated_idea = agent_state.get("validated_idea", {})
            return self.state_encoder.encode_trade_executor_state(
                validated_idea, self.portfolio_state, self.market_state,
            )

        elif role_str == AgentRole.TRADE_MONITOR.value:
            current_trade = agent_state.get("current_trade", {})
            return self.state_encoder.encode_trade_monitor_state(
                current_trade, self.market_state,
            )

        elif role_str in (
            AgentRole.PORTFOLIO_CONSTRUCTOR.value,
            AgentRole.RISK_MANAGER.value,
        ):
            return self.state_encoder.encode_portfolio_state(
                self.portfolio_state, self.market_state,
            )

        logger.warning("unknown_agent_role_for_state", role=role_str)
        return {}

    # ==================================================================
    # calculate_reward
    # ==================================================================

    async def calculate_reward(
        self,
        agent_role: AgentRole,
        action: dict[str, Any],
        outcome: dict[str, Any],
    ) -> float:
        """Calculate the reward for an agent's action given the outcome.

        Delegates to :class:`RewardCalculator` which computes a
        role-specific, multi-component reward signal.

        Args:
            agent_role: The acting agent's role.
            action: The action that was taken.
            outcome: The outcome of executing that action.

        Returns:
            A scalar reward float.
        """
        role_str = agent_role.value if isinstance(agent_role, AgentRole) else agent_role
        context = {
            "portfolio_state": self.portfolio_state,
            "market_state": self.market_state,
            "max_allowed_weight": self.config.get("max_position_weight", 0.20),
        }
        return self.reward_calculator.calculate(role_str, action, outcome, context)

    # ==================================================================
    # Internal: action execution
    # ==================================================================

    async def _execute_action(
        self,
        role: str,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        """Simulate the effect of *action* on the environment state.

        Returns an ``outcome`` dict consumed by the reward calculator.
        """
        action_type = action.get("type", "")
        params = action.get("parameters", {})
        outcome: dict[str, Any] = {"action_type": action_type}

        # ---- Idea Generator ----
        if role == AgentRole.IDEA_GENERATOR.value:
            if action_type == "skip":
                outcome["passed_validation"] = False
                outcome["rejected"] = False
            else:
                # Simulate idea generation
                idea = self._simulate_idea_generation(action_type)
                self.agent_states[AgentRole.IDEA_VALIDATOR.value]["pending_idea"] = idea
                self.agent_states[role]["last_idea"] = idea
                outcome["passed_validation"] = False  # not yet validated
                outcome["rejected"] = False
                outcome["novelty_score"] = idea.get("novelty_score", 0.5)
                outcome["redundancy_score"] = idea.get("redundancy_score", 0.0)

        # ---- Idea Validator ----
        elif role == AgentRole.IDEA_VALIDATOR.value:
            pending_idea = self.agent_states[role].get("pending_idea", {})

            if action_type == "approve":
                validated_idea = dict(pending_idea)
                validated_idea["validated"] = True
                validated_idea["confidence_score"] = params.get("confidence", 0.5)
                self.agent_states[AgentRole.TRADE_EXECUTOR.value]["validated_idea"] = validated_idea
                self.agent_states[role]["pending_idea"] = {}

                # Simulate eventual trade outcome for reward
                simulated_pnl = self._simulate_idea_outcome(validated_idea)
                outcome["trade_pnl"] = simulated_pnl
                outcome["counterfactual_profitable"] = simulated_pnl > 0

                # Also update idea generator outcome retroactively
                gen_state = self.agent_states[AgentRole.IDEA_GENERATOR.value]
                gen_state["last_outcome"] = {
                    "passed_validation": True,
                    "trade_pnl": simulated_pnl,
                }

            elif action_type == "reject":
                # Simulate counterfactual
                counterfactual_pnl = self._simulate_idea_outcome(pending_idea)
                outcome["trade_pnl"] = None
                outcome["counterfactual_profitable"] = counterfactual_pnl > 0
                self.agent_states[role]["pending_idea"] = {}

                gen_state = self.agent_states[AgentRole.IDEA_GENERATOR.value]
                gen_state["last_outcome"] = {"rejected": True}

            elif action_type == "request_more_data":
                outcome["trade_pnl"] = None
                outcome["counterfactual_profitable"] = False

            elif action_type == "backtest_with_params":
                bt_result = self._simulate_backtest(pending_idea, params.get("backtest_params", {}))
                pending_idea["backtest_results"] = bt_result
                self.agent_states[role]["pending_idea"] = pending_idea
                outcome["trade_pnl"] = None
                outcome["counterfactual_profitable"] = False

        # ---- Trade Executor ----
        elif role == AgentRole.TRADE_EXECUTOR.value:
            validated_idea = self.agent_states[role].get("validated_idea", {})

            if action_type == "construct_trade":
                trade = self._simulate_trade_construction(params, validated_idea)
                self.agent_states[AgentRole.TRADE_MONITOR.value]["current_trade"] = trade
                self._add_position_to_portfolio(trade)
                self.agent_states[role]["validated_idea"] = {}

                outcome["ideal_entry_price"] = trade.get("ideal_entry_price", params.get("entry", 0.0))
                outcome["actual_entry_price"] = trade.get("entry_price", params.get("entry", 0.0))
                outcome["direction"] = trade.get("direction", "long")
                outcome["trade_pnl_pct"] = 0.0  # just entered
                outcome["size_vs_max_ratio"] = trade.get("size_vs_max_ratio", 0.8)
                outcome["better_instrument_available"] = False
                outcome["slippage_bps"] = trade.get("slippage_bps", 2.0)

            elif action_type == "defer":
                outcome["deferred"] = True

            elif action_type == "request_portfolio_check":
                outcome["portfolio_check"] = self._portfolio_summary()

        # ---- Trade Monitor ----
        elif role == AgentRole.TRADE_MONITOR.value:
            trade = self.agent_states[role].get("current_trade", {})

            if action_type == "close":
                pnl_pct = self._close_trade(trade)
                outcome["trade_pnl_pct"] = pnl_pct
                outcome["max_favorable_excursion_pct"] = trade.get("max_favorable_excursion_pct", abs(pnl_pct))
                outcome["max_adverse_excursion_pct"] = trade.get("max_adverse_excursion_pct", 0.0)
                outcome["stop_distance_pct"] = trade.get("stop_distance_pct", -5.0)
                outcome["subsequent_pnl_pct"] = self._simulate_subsequent_pnl(trade)
                self.agent_states[role]["current_trade"] = {}

            elif action_type == "hold":
                outcome["stop_breached"] = trade.get("stop_breached", False)
                outcome["trade_pnl_pct"] = trade.get("pnl_pct", 0.0)

            elif action_type == "adjust_stop":
                outcome["old_stop"] = trade.get("stop_loss", 0.0)
                outcome["current_price"] = trade.get("current_price", 0.0)
                outcome["direction"] = trade.get("direction", "long")
                trade["stop_loss"] = params.get("new_stop", trade.get("stop_loss", 0.0))
                self.agent_states[role]["current_trade"] = trade

            elif action_type == "adjust_target":
                trade["take_profit"] = params.get("new_target", trade.get("take_profit", 0.0))
                self.agent_states[role]["current_trade"] = trade

            elif action_type == "add_to_position":
                trade["quantity"] = trade.get("quantity", 0.0) + params.get("add_size", 0.0)
                self.agent_states[role]["current_trade"] = trade
                outcome["trade_pnl_pct"] = trade.get("pnl_pct", 0.0)

            elif action_type == "reduce_position":
                fraction = params.get("reduce_fraction", 0.5)
                trade["quantity"] = trade.get("quantity", 0.0) * (1.0 - fraction)
                self.agent_states[role]["current_trade"] = trade
                outcome["trade_pnl_pct"] = trade.get("pnl_pct", 0.0)

        # ---- Portfolio Constructor ----
        elif role == AgentRole.PORTFOLIO_CONSTRUCTOR.value:
            sharpe_before = self.portfolio_state.get("performance", {}).get("sharpe", 0.0)

            if action_type == "set_allocation":
                self.portfolio_state["target_allocation"] = params.get("allocation", {})
            elif action_type == "approve_trade":
                pass  # Trade already in pipeline
            elif action_type == "reject_trade":
                self.agent_states[AgentRole.TRADE_EXECUTOR.value]["validated_idea"] = {}
            elif action_type == "request_hedge":
                self.agent_states[AgentRole.RISK_MANAGER.value]["hedge_request"] = params

            sharpe_after = self._estimate_portfolio_sharpe()
            positions = self.portfolio_state.get("positions", [])
            weights = [p.get("weight", 0.0) for p in positions]
            hhi = sum(w ** 2 for w in weights) if weights else 1.0

            outcome["sharpe_before"] = sharpe_before
            outcome["sharpe_after"] = sharpe_after
            outcome["portfolio_return_pct"] = self.portfolio_state.get("pnl_pct", 0.0)
            outcome["portfolio_volatility_pct"] = max(
                self.portfolio_state.get("risk_metrics", {}).get("volatility_pct", 10.0), 0.01
            )
            outcome["all_limits_respected"] = self._check_risk_limits()
            outcome["herfindahl_index"] = hhi
            outcome["max_position_weight"] = max(weights, default=0.0)

        # ---- Risk Manager ----
        elif role == AgentRole.RISK_MANAGER.value:
            risk_event = self._check_for_risk_event()

            if action_type == "alert":
                outcome["risk_event_occurred"] = risk_event
            elif action_type == "propose_hedge":
                hedge_pnl = self._simulate_hedge_outcome(params.get("hedge_trade", {}))
                outcome["hedge_pnl"] = hedge_pnl
                outcome["portfolio_loss"] = abs(self.portfolio_state.get("pnl", 0.0))
                outcome["risk_event_occurred"] = risk_event
            elif action_type == "reduce_exposure":
                self._reduce_portfolio_exposure(params.get("target", ""))
                outcome["risk_event_occurred"] = risk_event
            elif action_type == "no_action":
                outcome["risk_event_occurred"] = risk_event

            outcome["all_limits_respected"] = self._check_risk_limits()

        return outcome

    # ==================================================================
    # Internal: market simulation
    # ==================================================================

    def _advance_market(self) -> None:
        """Advance the market state by one tick.

        In *simulated* mode, step through the pre-loaded timeline.
        In *live* mode, this is a no-op (live data is fetched on demand).
        """
        if self.mode == EnvironmentMode.SIMULATED and self._market_timeline:
            self._timeline_index = min(
                self._timeline_index + 1,
                len(self._market_timeline) - 1,
            )
            new_snapshot = self._market_timeline[self._timeline_index]
            self.market_state.update(new_snapshot)

            # Update trade prices for the monitor
            self._update_trade_prices()

    def _update_trade_prices(self) -> None:
        """Propagate latest market prices into open trades."""
        trade = self.agent_states.get(
            AgentRole.TRADE_MONITOR.value, {}
        ).get("current_trade", {})

        if not trade:
            return

        tickers = trade.get("tickers", [])
        if not tickers:
            return

        primary_ticker = tickers[0]
        ticker_data = self.market_state.get("ticker_data", {}).get(primary_ticker, {})
        new_price = ticker_data.get("close", ticker_data.get("price"))
        if new_price is not None:
            old_price = trade.get("current_price", trade.get("entry_price", new_price))
            trade["current_price"] = new_price

            # Update P&L
            entry = trade.get("entry_price", new_price)
            direction = trade.get("direction", "long")
            if direction == "long":
                pnl_pct = (new_price - entry) / entry * 100.0 if entry else 0.0
            else:
                pnl_pct = (entry - new_price) / entry * 100.0 if entry else 0.0
            trade["pnl_pct"] = pnl_pct
            trade["pnl"] = pnl_pct * trade.get("notional_value", 0.0) / 100.0

            # Track MFE / MAE
            trade["max_favorable_excursion_pct"] = max(
                trade.get("max_favorable_excursion_pct", 0.0), pnl_pct
            )
            trade["max_adverse_excursion_pct"] = min(
                trade.get("max_adverse_excursion_pct", 0.0), pnl_pct
            )

            # Check stop breach
            stop = trade.get("stop_loss", 0.0)
            if stop > 0:
                if direction == "long":
                    trade["stop_breached"] = new_price <= stop
                else:
                    trade["stop_breached"] = new_price >= stop

            # Update elapsed time
            trade["elapsed_seconds"] = trade.get("elapsed_seconds", 0.0) + self.config.get(
                "seconds_per_step", 3600.0
            )

            self.agent_states[AgentRole.TRADE_MONITOR.value]["current_trade"] = trade

    # ==================================================================
    # Internal: simulation helpers
    # ==================================================================

    def _simulate_idea_generation(self, source_type: str) -> dict[str, Any]:
        """Create a simulated idea from the given source type."""
        import random

        tickers_pool = self.market_state.get("available_tickers", ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"])
        ticker = random.choice(tickers_pool) if tickers_pool else "SPY"

        return {
            "title": f"Simulated idea from {source_type}",
            "source": source_type.replace("generate_from_", ""),
            "tickers": [ticker],
            "confidence_score": random.uniform(0.3, 0.9),
            "expected_return": random.uniform(-5.0, 15.0),
            "risk_level": random.choice(["low", "medium", "high"]),
            "timeframe": random.choice(["short_term", "medium_term"]),
            "thesis": f"Simulated thesis for {ticker} via {source_type}.",
            "novelty_score": random.uniform(0.2, 0.95),
            "redundancy_score": random.uniform(0.0, 0.4),
        }

    def _simulate_idea_outcome(self, idea: dict[str, Any]) -> float:
        """Simulate the eventual P&L of an idea (for reward attribution)."""
        import random

        confidence = idea.get("confidence_score", 0.5)
        expected = idea.get("expected_return", 0.0)
        # Higher confidence ideas are more likely to match expected direction
        noise = random.gauss(0, 5.0)
        return expected * confidence + noise

    def _simulate_backtest(
        self,
        idea: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Return simulated backtest results for an idea."""
        import random

        return {
            "sharpe": random.uniform(-0.5, 2.5),
            "max_drawdown_pct": random.uniform(-30.0, -2.0),
            "win_rate": random.uniform(0.3, 0.7),
            "profit_factor": random.uniform(0.5, 3.0),
            "total_return_pct": random.uniform(-10.0, 40.0),
            "num_trades": random.randint(5, 100),
        }

    def _simulate_trade_construction(
        self,
        params: dict[str, Any],
        idea: dict[str, Any],
    ) -> dict[str, Any]:
        """Construct a simulated trade from execution parameters."""
        import random

        entry_price = params.get("entry", 100.0)
        slippage_bps = random.uniform(0.5, 10.0)
        actual_entry = entry_price * (1.0 + slippage_bps / 10000.0)

        direction = "long" if idea.get("expected_return", 0.0) >= 0 else "short"
        tickers = idea.get("tickers", [])
        max_position_value = self.portfolio_state.get("total_value", 100000.0) * 0.05
        notional = min(params.get("size", 10000.0), max_position_value)

        return {
            "tickers": tickers,
            "direction": direction,
            "entry_price": actual_entry,
            "ideal_entry_price": entry_price,
            "current_price": actual_entry,
            "stop_loss": params.get("stop", entry_price * 0.95),
            "take_profit": params.get("target", entry_price * 1.10),
            "quantity": notional / actual_entry if actual_entry else 0.0,
            "notional_value": notional,
            "slippage_bps": slippage_bps,
            "size_vs_max_ratio": notional / max_position_value if max_position_value else 1.0,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "max_favorable_excursion_pct": 0.0,
            "max_adverse_excursion_pct": 0.0,
            "elapsed_seconds": 0.0,
            "expected_duration_seconds": 86400.0 * 5,  # 5 days default
            "stop_breached": False,
            "thesis_signals": {"intact": True},
        }

    def _close_trade(self, trade: dict[str, Any]) -> float:
        """Close an open trade and update portfolio state."""
        pnl_pct = trade.get("pnl_pct", 0.0)
        pnl_dollar = trade.get("pnl", 0.0)

        # Update portfolio
        self.portfolio_state["pnl"] = self.portfolio_state.get("pnl", 0.0) + pnl_dollar
        self.portfolio_state["cash"] = (
            self.portfolio_state.get("cash", 0.0)
            + trade.get("notional_value", 0.0)
            + pnl_dollar
        )
        self.portfolio_state["invested"] = max(
            0.0,
            self.portfolio_state.get("invested", 0.0) - trade.get("notional_value", 0.0),
        )

        # Remove position
        tickers = set(trade.get("tickers", []))
        positions = self.portfolio_state.get("positions", [])
        self.portfolio_state["positions"] = [
            p for p in positions if p.get("ticker") not in tickers
        ]

        self._recalculate_portfolio_metrics()
        return pnl_pct

    def _simulate_subsequent_pnl(self, trade: dict[str, Any]) -> float:
        """Estimate what would have happened if the trade stayed open."""
        import random

        # Simple mean-reverting simulation
        current_pnl = trade.get("pnl_pct", 0.0)
        return current_pnl + random.gauss(0, 2.0)

    def _simulate_hedge_outcome(self, hedge_trade: dict[str, Any]) -> float:
        """Simulate the P&L of a proposed hedge trade."""
        import random
        return random.uniform(-500.0, 2000.0)

    # ==================================================================
    # Internal: portfolio helpers
    # ==================================================================

    def _add_position_to_portfolio(self, trade: dict[str, Any]) -> None:
        """Add a new position to the portfolio from a constructed trade."""
        notional = trade.get("notional_value", 0.0)
        total_value = max(self.portfolio_state.get("total_value", 1.0), 1.0)
        tickers = trade.get("tickers", ["UNKNOWN"])

        position = {
            "ticker": tickers[0] if tickers else "UNKNOWN",
            "direction": trade.get("direction", "long"),
            "quantity": trade.get("quantity", 0.0),
            "avg_entry_price": trade.get("entry_price", 0.0),
            "current_price": trade.get("current_price", 0.0),
            "market_value": notional,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "weight": notional / total_value,
            "asset_class": "equity",
        }

        self.portfolio_state.setdefault("positions", []).append(position)
        self.portfolio_state["invested"] = (
            self.portfolio_state.get("invested", 0.0) + notional
        )
        self.portfolio_state["cash"] = max(
            0.0,
            self.portfolio_state.get("cash", 0.0) - notional,
        )
        self._recalculate_portfolio_metrics()

    def _recalculate_portfolio_metrics(self) -> None:
        """Recompute derived portfolio metrics after state changes."""
        positions = self.portfolio_state.get("positions", [])
        total_invested = sum(p.get("market_value", 0.0) for p in positions)
        cash = self.portfolio_state.get("cash", 0.0)
        total_value = total_invested + cash

        self.portfolio_state["total_value"] = total_value
        self.portfolio_state["invested"] = total_invested

        # Recalculate weights
        for pos in positions:
            pos["weight"] = pos.get("market_value", 0.0) / total_value if total_value else 0.0

        self.portfolio_state["pnl_pct"] = (
            self.portfolio_state.get("pnl", 0.0) / max(total_value, 1.0) * 100.0
        )

    def _portfolio_summary(self) -> dict[str, Any]:
        """Return a compact portfolio summary."""
        return {
            "total_value": self.portfolio_state.get("total_value", 0.0),
            "cash": self.portfolio_state.get("cash", 0.0),
            "invested": self.portfolio_state.get("invested", 0.0),
            "pnl": self.portfolio_state.get("pnl", 0.0),
            "num_positions": len(self.portfolio_state.get("positions", [])),
        }

    def _estimate_portfolio_sharpe(self) -> float:
        """Rough Sharpe ratio estimate from current portfolio state."""
        import random

        perf = self.portfolio_state.get("performance", {})
        base_sharpe = perf.get("sharpe", 0.5)
        return base_sharpe + random.gauss(0, 0.1)

    def _check_risk_limits(self) -> bool:
        """Check whether all risk limits are respected."""
        positions = self.portfolio_state.get("positions", [])
        max_weight = self.config.get("max_position_weight", 0.20)

        for pos in positions:
            if pos.get("weight", 0.0) > max_weight:
                return False

        leverage = self.portfolio_state.get("risk_metrics", {}).get("leverage", 1.0)
        if leverage > self.config.get("max_leverage", 2.0):
            return False

        return True

    def _check_for_risk_event(self) -> bool:
        """Determine whether a risk event occurred at this step."""
        import random

        # Simple probabilistic model -- risk events are rare
        vix = self.market_state.get("regime", {}).get("vix", 20.0)
        prob = min(0.5, max(0.01, (vix - 15.0) / 100.0))
        return random.random() < prob

    def _reduce_portfolio_exposure(self, target: str) -> None:
        """Reduce exposure to a target sector or position."""
        positions = self.portfolio_state.get("positions", [])
        reduced = []
        for pos in positions:
            if pos.get("asset_class") == target or pos.get("ticker") == target:
                # Halve the position
                pos["quantity"] = pos.get("quantity", 0.0) * 0.5
                pos["market_value"] = pos.get("market_value", 0.0) * 0.5
            reduced.append(pos)
        self.portfolio_state["positions"] = reduced
        self._recalculate_portfolio_metrics()

    # ==================================================================
    # Internal: termination
    # ==================================================================

    def _is_done(self) -> bool:
        """Check whether the episode should terminate."""
        if self.current_step >= self.max_steps:
            return True

        # End if portfolio is wiped out
        if self.portfolio_state.get("total_value", 1.0) <= 0:
            return True

        # End of simulated timeline
        if (
            self.mode == EnvironmentMode.SIMULATED
            and self._market_timeline
            and self._timeline_index >= len(self._market_timeline) - 1
        ):
            return True

        return False

    # ==================================================================
    # Internal: default states
    # ==================================================================

    @staticmethod
    def _default_market_state() -> dict[str, Any]:
        """Return a sensible initial market state for a new episode."""
        return {
            "regime": {
                "vix": 18.0,
                "trend_strength": 0.3,
                "breadth": 0.55,
                "volatility_regime": 0.0,
                "momentum_regime": 0.2,
                "risk_on": True,
            },
            "sector_performance": {
                "technology": {"momentum_1m": 2.5},
                "healthcare": {"momentum_1m": 1.0},
                "financials": {"momentum_1m": -0.5},
                "energy": {"momentum_1m": 3.0},
                "consumer_discretionary": {"momentum_1m": 0.8},
                "industrials": {"momentum_1m": 1.2},
                "utilities": {"momentum_1m": -0.3},
                "real_estate": {"momentum_1m": -1.0},
                "materials": {"momentum_1m": 0.5},
                "communication_services": {"momentum_1m": 1.8},
                "consumer_staples": {"momentum_1m": 0.2},
            },
            "unusual_moves": [],
            "ticker_data": {},
            "available_tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA"],
            "available_instruments": [
                {"symbol": "AAPL", "type": "equity", "liquidity_score": 0.95, "spread_bps": 1.0},
                {"symbol": "MSFT", "type": "equity", "liquidity_score": 0.94, "spread_bps": 1.2},
                {"symbol": "SPY", "type": "etf", "liquidity_score": 0.99, "spread_bps": 0.5},
            ],
        }

    @staticmethod
    def _default_portfolio_state() -> dict[str, Any]:
        """Return a sensible initial portfolio state for a new episode."""
        return {
            "total_value": 100_000.0,
            "cash": 100_000.0,
            "invested": 0.0,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "positions": [],
            "risk_metrics": {
                "var_95_pct": 2.0,
                "cvar_95_pct": 3.0,
                "beta": 1.0,
                "leverage": 1.0,
                "avg_correlation": 0.3,
                "volatility_pct": 10.0,
            },
            "performance": {
                "return_1d_pct": 0.0,
                "return_1w_pct": 0.0,
                "return_1m_pct": 0.0,
                "sharpe": 0.0,
                "current_drawdown_pct": 0.0,
            },
            "target_allocation": {},
        }

    @staticmethod
    def _default_agent_state(role: str) -> dict[str, Any]:
        """Return the initial per-agent state for *role*."""
        base: dict[str, Any] = {"actions_taken": 0}

        if role == AgentRole.IDEA_GENERATOR.value:
            base["recent_news"] = []
            base["trending_topics"] = []
            base["last_idea"] = {}
            base["last_outcome"] = {}

        elif role == AgentRole.IDEA_VALIDATOR.value:
            base["pending_idea"] = {}

        elif role == AgentRole.TRADE_EXECUTOR.value:
            base["validated_idea"] = {}

        elif role == AgentRole.TRADE_MONITOR.value:
            base["current_trade"] = {}

        elif role == AgentRole.PORTFOLIO_CONSTRUCTOR.value:
            base["pending_trade_id"] = None

        elif role == AgentRole.RISK_MANAGER.value:
            base["hedge_request"] = {}

        return base
