"""
Reward functions for the Overture RL trading agents.

Each agent role receives a scalar reward signal after taking an action.
Rewards are composed of multiple weighted components so that the overall
incentive structure can be tuned independently per component.

Design principles:
* **Dense rewards** -- agents receive feedback at every step, not just at
  episode end, to speed up credit assignment.
* **Role-specific shaping** -- each role has a bespoke reward function that
  encodes the behaviour the hedge fund wants to incentivize (e.g. the idea
  generator is rewarded for novel, profitable ideas while the risk manager
  is rewarded for keeping exposure within bounds).
* **Configurable weights** -- every reward component has a weight that can
  be tuned via the ``reward_weights`` dict passed at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Default reward weights per role
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "idea_generator": {
        "idea_passed_validation": 1.0,
        "idea_became_profitable_trade": 2.0,
        "idea_rejected": -0.5,
        "idea_became_losing_trade": -1.0,
        "novelty_bonus": 0.3,
        "redundancy_penalty": -0.4,
    },
    "idea_validator": {
        "correct_approve_profitable": 1.0,
        "correct_reject_unprofitable": 1.0,
        "wrong_approve_loss": -1.0,
        "wrong_reject_missed_profit": -0.5,
        "calibration_bonus": 0.5,
    },
    "trade_executor": {
        "execution_quality": 1.0,
        "pnl_proportional": 1.0,
        "oversize_penalty": -0.8,
        "poor_instrument_penalty": -0.5,
        "slippage_penalty": -0.3,
    },
    "trade_monitor": {
        "close_near_peak": 1.0,
        "cut_loss_early": 0.8,
        "hold_past_stop_penalty": -1.0,
        "premature_exit_penalty": -0.6,
        "trailing_stop_bonus": 0.4,
    },
    "portfolio_constructor": {
        "sharpe_improvement": 1.5,
        "risk_adjusted_return": 1.0,
        "within_risk_limits": 0.5,
        "diversification_bonus": 0.6,
        "concentration_penalty": -0.8,
    },
    "risk_manager": {
        "correct_alert": 0.8,
        "false_alarm_penalty": -0.3,
        "missed_risk_penalty": -1.5,
        "successful_hedge": 1.0,
        "within_limits_bonus": 0.4,
    },
}


# ---------------------------------------------------------------------------
# Reward breakdown dataclass
# ---------------------------------------------------------------------------

@dataclass
class RewardBreakdown:
    """Itemised breakdown of a reward signal.

    Attributes:
        total: The final scalar reward (sum of weighted components).
        components: Mapping from component name to its *weighted* contribution.
        raw_components: Mapping from component name to its *unweighted* value.
    """

    total: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    raw_components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "components": self.components,
            "raw_components": self.raw_components,
        }


# ---------------------------------------------------------------------------
# RewardCalculator
# ---------------------------------------------------------------------------

class RewardCalculator:
    """Computes per-role reward signals from action outcomes.

    Usage::

        calc = RewardCalculator()
        reward = calc.calculate("idea_generator", action, outcome, context)
        breakdown = calc.get_reward_breakdown("idea_generator", action, outcome, context)

    Custom weights can be passed at construction time to override the defaults
    for any role/component combination.
    """

    def __init__(self, reward_weights: dict[str, dict[str, float]] | None = None):
        self.weights: dict[str, dict[str, float]] = {}
        for role, defaults in DEFAULT_WEIGHTS.items():
            merged = dict(defaults)
            if reward_weights and role in reward_weights:
                merged.update(reward_weights[role])
            self.weights[role] = merged

    # ---- public interface -------------------------------------------------

    def calculate(
        self,
        agent_role: str,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> float:
        """Return the scalar reward for *agent_role* after taking *action*.

        Args:
            agent_role: The role identifier (e.g. ``"idea_generator"``).
            action: The action dict that was executed.
            outcome: Environment outcome dict describing what happened.
            context: Optional additional context (portfolio state, etc.).

        Returns:
            A float reward value.
        """
        breakdown = self._compute_breakdown(agent_role, action, outcome, context or {})
        return breakdown.total

    def get_reward_breakdown(
        self,
        agent_role: str,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return an itemised reward breakdown as a plain dict.

        This is useful for logging, debugging, and interpretability.
        """
        breakdown = self._compute_breakdown(agent_role, action, outcome, context or {})
        return breakdown.to_dict()

    # ---- internal dispatch ------------------------------------------------

    def _compute_breakdown(
        self,
        agent_role: str,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Dispatch to the appropriate role-specific reward calculator."""
        dispatch = {
            "idea_generator": self._idea_generator_reward,
            "idea_validator": self._idea_validator_reward,
            "trade_executor": self._trade_executor_reward,
            "trade_monitor": self._trade_monitor_reward,
            "portfolio_constructor": self._portfolio_constructor_reward,
            "risk_manager": self._risk_manager_reward,
        }

        fn = dispatch.get(agent_role)
        if fn is None:
            logger.warning("unknown_agent_role_for_reward", role=agent_role)
            return RewardBreakdown()

        return fn(action, outcome, context)

    # ---- utility ----------------------------------------------------------

    def _weighted(self, role: str, component: str, raw_value: float) -> float:
        """Apply the weight for *component* in *role* to *raw_value*."""
        weight = self.weights.get(role, {}).get(component, 0.0)
        return weight * raw_value

    # ======================================================================
    # Role-specific reward functions
    # ======================================================================

    def _idea_generator_reward(
        self,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Reward for the idea-generator agent.

        Components:
        - **idea_passed_validation**: +1 if the generated idea passed the
          validation stage.
        - **idea_became_profitable_trade**: +1 if the idea eventually became
          a profitable trade (delayed reward, assigned retroactively).
        - **idea_rejected**: -1 if the idea was rejected by the validator.
        - **idea_became_losing_trade**: -1 if the idea became a losing trade.
        - **novelty_bonus**: +1 if the idea is sufficiently novel relative
          to recently generated ideas (cosine distance > threshold).
        - **redundancy_penalty**: -1 if the idea is very similar to a
          recent idea already in the pipeline.
        """
        role = "idea_generator"
        raw: dict[str, float] = {}
        comps: dict[str, float] = {}

        # Skip action yields zero reward
        if action.get("type") == "skip":
            return RewardBreakdown(total=0.0, components={}, raw_components={})

        # Validation outcome
        passed_validation = outcome.get("passed_validation", False)
        raw["idea_passed_validation"] = 1.0 if passed_validation else 0.0
        comps["idea_passed_validation"] = self._weighted(role, "idea_passed_validation", raw["idea_passed_validation"])

        rejected = outcome.get("rejected", False)
        raw["idea_rejected"] = 1.0 if rejected else 0.0
        comps["idea_rejected"] = self._weighted(role, "idea_rejected", raw["idea_rejected"])

        # Trade outcome (may be None if not yet resolved)
        trade_pnl = outcome.get("trade_pnl")
        if trade_pnl is not None:
            if trade_pnl > 0:
                raw["idea_became_profitable_trade"] = 1.0
                raw["idea_became_losing_trade"] = 0.0
            else:
                raw["idea_became_profitable_trade"] = 0.0
                raw["idea_became_losing_trade"] = 1.0
        else:
            raw["idea_became_profitable_trade"] = 0.0
            raw["idea_became_losing_trade"] = 0.0
        comps["idea_became_profitable_trade"] = self._weighted(
            role, "idea_became_profitable_trade", raw["idea_became_profitable_trade"]
        )
        comps["idea_became_losing_trade"] = self._weighted(
            role, "idea_became_losing_trade", raw["idea_became_losing_trade"]
        )

        # Novelty / redundancy
        novelty_score = outcome.get("novelty_score", 0.5)  # 0-1
        raw["novelty_bonus"] = max(0.0, novelty_score - 0.5) * 2.0  # scale to 0-1
        comps["novelty_bonus"] = self._weighted(role, "novelty_bonus", raw["novelty_bonus"])

        redundancy = outcome.get("redundancy_score", 0.0)  # 0-1, higher = more redundant
        raw["redundancy_penalty"] = redundancy
        comps["redundancy_penalty"] = self._weighted(role, "redundancy_penalty", raw["redundancy_penalty"])

        total = sum(comps.values())
        return RewardBreakdown(total=total, components=comps, raw_components=raw)

    # ------------------------------------------------------------------ #

    def _idea_validator_reward(
        self,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Reward for the idea-validator agent.

        Components:
        - **correct_approve_profitable**: +1 when the validator approved an
          idea that turned out profitable.
        - **correct_reject_unprofitable**: +1 when the validator rejected an
          idea that would have lost money.
        - **wrong_approve_loss**: -1 when the validator approved an idea
          that ended up losing money.
        - **wrong_reject_missed_profit**: -1 when the validator rejected an
          idea that would have been profitable.
        - **calibration_bonus**: reward proportional to how well the
          validator's stated confidence matches the realised outcome
          probability (Brier-score inspired).
        """
        role = "idea_validator"
        raw: dict[str, float] = {}
        comps: dict[str, float] = {}

        action_type = action.get("type", "")
        trade_pnl = outcome.get("trade_pnl")  # None if not yet known
        approved = action_type == "approve"
        rejected = action_type == "reject"
        profitable = (trade_pnl is not None and trade_pnl > 0)
        unprofitable = (trade_pnl is not None and trade_pnl <= 0)
        counterfactual_profitable = outcome.get("counterfactual_profitable", False)

        # Correct approve
        raw["correct_approve_profitable"] = 1.0 if (approved and profitable) else 0.0
        comps["correct_approve_profitable"] = self._weighted(
            role, "correct_approve_profitable", raw["correct_approve_profitable"]
        )

        # Correct reject
        raw["correct_reject_unprofitable"] = 1.0 if (rejected and (unprofitable or not counterfactual_profitable)) else 0.0
        comps["correct_reject_unprofitable"] = self._weighted(
            role, "correct_reject_unprofitable", raw["correct_reject_unprofitable"]
        )

        # Wrong approve
        raw["wrong_approve_loss"] = 1.0 if (approved and unprofitable) else 0.0
        comps["wrong_approve_loss"] = self._weighted(
            role, "wrong_approve_loss", raw["wrong_approve_loss"]
        )

        # Wrong reject
        raw["wrong_reject_missed_profit"] = 1.0 if (rejected and counterfactual_profitable) else 0.0
        comps["wrong_reject_missed_profit"] = self._weighted(
            role, "wrong_reject_missed_profit", raw["wrong_reject_missed_profit"]
        )

        # Calibration bonus
        confidence = action.get("parameters", {}).get("confidence", 0.5)
        actual_outcome = 1.0 if profitable else 0.0
        if approved and trade_pnl is not None:
            # Brier-score inspired: reward is higher when confidence matches outcome
            calibration_error = abs(confidence - actual_outcome)
            raw["calibration_bonus"] = max(0.0, 1.0 - 2.0 * calibration_error)
        else:
            raw["calibration_bonus"] = 0.0
        comps["calibration_bonus"] = self._weighted(
            role, "calibration_bonus", raw["calibration_bonus"]
        )

        total = sum(comps.values())
        return RewardBreakdown(total=total, components=comps, raw_components=raw)

    # ------------------------------------------------------------------ #

    def _trade_executor_reward(
        self,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Reward for the trade-executor agent.

        Components:
        - **execution_quality**: how close the entry price was to the
          ideal price (normalized 0-1, where 1 = perfect fill).
        - **pnl_proportional**: reward scaled linearly with the trade
          P&L as a fraction of the risk budget.
        - **oversize_penalty**: penalty if the position size exceeds
          the recommended max for the portfolio.
        - **poor_instrument_penalty**: penalty if a better instrument
          existed (e.g. more liquid ETF vs single stock).
        - **slippage_penalty**: penalty proportional to entry slippage.
        """
        role = "trade_executor"
        raw: dict[str, float] = {}
        comps: dict[str, float] = {}

        action_type = action.get("type", "")
        if action_type != "construct_trade":
            # Deferred or portfolio-check actions get small neutral reward
            return RewardBreakdown(total=0.0, components={}, raw_components={})

        # Execution quality: (ideal - actual) / ideal, clamped to [-1, 1]
        ideal_price = outcome.get("ideal_entry_price", 0.0)
        actual_price = outcome.get("actual_entry_price", 0.0)
        if ideal_price > 0:
            price_diff_pct = (ideal_price - actual_price) / ideal_price
            # For long trades, lower actual = better; for short, higher = better
            direction = outcome.get("direction", "long")
            quality = price_diff_pct if direction == "long" else -price_diff_pct
            raw["execution_quality"] = max(-1.0, min(1.0, quality * 10.0))  # scale
        else:
            raw["execution_quality"] = 0.0
        comps["execution_quality"] = self._weighted(role, "execution_quality", raw["execution_quality"])

        # P&L proportional
        trade_pnl_pct = outcome.get("trade_pnl_pct", 0.0)
        raw["pnl_proportional"] = max(-2.0, min(2.0, trade_pnl_pct))
        comps["pnl_proportional"] = self._weighted(role, "pnl_proportional", raw["pnl_proportional"])

        # Oversize penalty
        size_ratio = outcome.get("size_vs_max_ratio", 0.0)  # >1 means oversized
        raw["oversize_penalty"] = max(0.0, size_ratio - 1.0)
        comps["oversize_penalty"] = self._weighted(role, "oversize_penalty", raw["oversize_penalty"])

        # Poor instrument penalty
        raw["poor_instrument_penalty"] = 1.0 if outcome.get("better_instrument_available", False) else 0.0
        comps["poor_instrument_penalty"] = self._weighted(
            role, "poor_instrument_penalty", raw["poor_instrument_penalty"]
        )

        # Slippage penalty
        slippage_bps = abs(outcome.get("slippage_bps", 0.0))
        raw["slippage_penalty"] = min(1.0, slippage_bps / 50.0)  # normalize 50bps = full penalty
        comps["slippage_penalty"] = self._weighted(role, "slippage_penalty", raw["slippage_penalty"])

        total = sum(comps.values())
        return RewardBreakdown(total=total, components=comps, raw_components=raw)

    # ------------------------------------------------------------------ #

    def _trade_monitor_reward(
        self,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Reward for the trade-monitoring agent.

        Components:
        - **close_near_peak**: reward for closing near the maximum
          favourable excursion (MFE).
        - **cut_loss_early**: reward for closing a losing trade before
          the stop loss is hit, preserving capital.
        - **hold_past_stop_penalty**: penalty for continuing to hold a
          position that has breached its stop-loss level.
        - **premature_exit_penalty**: penalty for closing a profitable
          trade that subsequently would have continued to profit.
        - **trailing_stop_bonus**: reward for adjusting stops in the
          direction of profit to lock in gains.
        """
        role = "trade_monitor"
        raw: dict[str, float] = {}
        comps: dict[str, float] = {}

        action_type = action.get("type", "")
        trade_pnl_pct = outcome.get("trade_pnl_pct", 0.0)
        mfe_pct = outcome.get("max_favorable_excursion_pct", 0.0)  # best P&L during trade
        mae_pct = outcome.get("max_adverse_excursion_pct", 0.0)    # worst P&L during trade
        stop_distance_pct = outcome.get("stop_distance_pct", 0.0)
        subsequent_pnl_pct = outcome.get("subsequent_pnl_pct", 0.0)

        # Close near peak
        if action_type == "close" and mfe_pct > 0:
            capture_ratio = trade_pnl_pct / mfe_pct if mfe_pct != 0 else 0.0
            raw["close_near_peak"] = max(0.0, min(1.0, capture_ratio))
        else:
            raw["close_near_peak"] = 0.0
        comps["close_near_peak"] = self._weighted(role, "close_near_peak", raw["close_near_peak"])

        # Cut loss early
        if action_type == "close" and trade_pnl_pct < 0 and stop_distance_pct < 0:
            # Reward is higher when the loss is smaller relative to the stop
            saved_fraction = 1.0 - abs(trade_pnl_pct / stop_distance_pct) if stop_distance_pct != 0 else 0.0
            raw["cut_loss_early"] = max(0.0, min(1.0, saved_fraction))
        else:
            raw["cut_loss_early"] = 0.0
        comps["cut_loss_early"] = self._weighted(role, "cut_loss_early", raw["cut_loss_early"])

        # Hold past stop penalty
        breached_stop = outcome.get("stop_breached", False)
        if action_type == "hold" and breached_stop:
            raw["hold_past_stop_penalty"] = 1.0
        else:
            raw["hold_past_stop_penalty"] = 0.0
        comps["hold_past_stop_penalty"] = self._weighted(
            role, "hold_past_stop_penalty", raw["hold_past_stop_penalty"]
        )

        # Premature exit penalty
        if action_type == "close" and subsequent_pnl_pct > 0.02:
            raw["premature_exit_penalty"] = min(1.0, subsequent_pnl_pct / 0.10)
        else:
            raw["premature_exit_penalty"] = 0.0
        comps["premature_exit_penalty"] = self._weighted(
            role, "premature_exit_penalty", raw["premature_exit_penalty"]
        )

        # Trailing stop bonus
        if action_type == "adjust_stop":
            new_stop = action.get("parameters", {}).get("new_stop", 0.0)
            old_stop = outcome.get("old_stop", 0.0)
            current_price = outcome.get("current_price", 0.0)
            direction = outcome.get("direction", "long")
            if direction == "long" and new_stop > old_stop and new_stop < current_price:
                raw["trailing_stop_bonus"] = 1.0
            elif direction == "short" and new_stop < old_stop and new_stop > current_price:
                raw["trailing_stop_bonus"] = 1.0
            else:
                raw["trailing_stop_bonus"] = 0.0
        else:
            raw["trailing_stop_bonus"] = 0.0
        comps["trailing_stop_bonus"] = self._weighted(role, "trailing_stop_bonus", raw["trailing_stop_bonus"])

        total = sum(comps.values())
        return RewardBreakdown(total=total, components=comps, raw_components=raw)

    # ------------------------------------------------------------------ #

    def _portfolio_constructor_reward(
        self,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Reward for the portfolio-construction agent.

        Components:
        - **sharpe_improvement**: change in portfolio Sharpe ratio after
          the action, clipped to [-2, 2].
        - **risk_adjusted_return**: portfolio return divided by volatility.
        - **within_risk_limits**: +1 if all risk limits are respected.
        - **diversification_bonus**: inverse of concentration (HHI).
        - **concentration_penalty**: penalty when any single position or
          sector exceeds the configured max weight.
        """
        role = "portfolio_constructor"
        raw: dict[str, float] = {}
        comps: dict[str, float] = {}

        # Sharpe improvement
        sharpe_before = outcome.get("sharpe_before", 0.0)
        sharpe_after = outcome.get("sharpe_after", 0.0)
        raw["sharpe_improvement"] = max(-2.0, min(2.0, sharpe_after - sharpe_before))
        comps["sharpe_improvement"] = self._weighted(role, "sharpe_improvement", raw["sharpe_improvement"])

        # Risk adjusted return
        portfolio_return = outcome.get("portfolio_return_pct", 0.0)
        portfolio_vol = max(outcome.get("portfolio_volatility_pct", 1.0), 0.01)
        raw["risk_adjusted_return"] = max(-2.0, min(2.0, portfolio_return / portfolio_vol))
        comps["risk_adjusted_return"] = self._weighted(role, "risk_adjusted_return", raw["risk_adjusted_return"])

        # Within risk limits
        limits_respected = outcome.get("all_limits_respected", True)
        raw["within_risk_limits"] = 1.0 if limits_respected else 0.0
        comps["within_risk_limits"] = self._weighted(role, "within_risk_limits", raw["within_risk_limits"])

        # Diversification bonus -- based on inverse HHI (0-1)
        hhi = outcome.get("herfindahl_index", 1.0)  # 1.0 = fully concentrated
        raw["diversification_bonus"] = max(0.0, 1.0 - hhi)
        comps["diversification_bonus"] = self._weighted(role, "diversification_bonus", raw["diversification_bonus"])

        # Concentration penalty
        max_weight = outcome.get("max_position_weight", 0.0)
        weight_limit = context.get("max_allowed_weight", 0.20)
        if max_weight > weight_limit:
            raw["concentration_penalty"] = min(1.0, (max_weight - weight_limit) / weight_limit)
        else:
            raw["concentration_penalty"] = 0.0
        comps["concentration_penalty"] = self._weighted(
            role, "concentration_penalty", raw["concentration_penalty"]
        )

        total = sum(comps.values())
        return RewardBreakdown(total=total, components=comps, raw_components=raw)

    # ------------------------------------------------------------------ #

    def _risk_manager_reward(
        self,
        action: dict[str, Any],
        outcome: dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown:
        """Reward for the risk-manager agent.

        Components:
        - **correct_alert**: +1 if an alert was raised and a risk event
          subsequently materialised.
        - **false_alarm_penalty**: -1 if an alert was raised but no risk
          event occurred.
        - **missed_risk_penalty**: -1 if no alert was raised but a risk
          event occurred.
        - **successful_hedge**: +1 if a proposed hedge offset losses.
        - **within_limits_bonus**: +1 if the portfolio remains within
          all risk limits at the end of the step.
        """
        role = "risk_manager"
        raw: dict[str, float] = {}
        comps: dict[str, float] = {}

        action_type = action.get("type", "")
        risk_event_occurred = outcome.get("risk_event_occurred", False)
        alerted = action_type == "alert"

        # Correct alert
        raw["correct_alert"] = 1.0 if (alerted and risk_event_occurred) else 0.0
        comps["correct_alert"] = self._weighted(role, "correct_alert", raw["correct_alert"])

        # False alarm
        raw["false_alarm_penalty"] = 1.0 if (alerted and not risk_event_occurred) else 0.0
        comps["false_alarm_penalty"] = self._weighted(role, "false_alarm_penalty", raw["false_alarm_penalty"])

        # Missed risk
        raw["missed_risk_penalty"] = 1.0 if (action_type == "no_action" and risk_event_occurred) else 0.0
        comps["missed_risk_penalty"] = self._weighted(role, "missed_risk_penalty", raw["missed_risk_penalty"])

        # Successful hedge
        hedge_pnl = outcome.get("hedge_pnl", 0.0)
        if action_type == "propose_hedge" and hedge_pnl > 0:
            raw["successful_hedge"] = min(1.0, hedge_pnl / max(abs(outcome.get("portfolio_loss", 1.0)), 0.01))
        else:
            raw["successful_hedge"] = 0.0
        comps["successful_hedge"] = self._weighted(role, "successful_hedge", raw["successful_hedge"])

        # Within limits
        all_within = outcome.get("all_limits_respected", True)
        raw["within_limits_bonus"] = 1.0 if all_within else 0.0
        comps["within_limits_bonus"] = self._weighted(role, "within_limits_bonus", raw["within_limits_bonus"])

        total = sum(comps.values())
        return RewardBreakdown(total=total, components=comps, raw_components=raw)
