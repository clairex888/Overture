"""Trade Execution Agent for the Overture system.

This agent takes a validated investment idea and constructs an optimal trade
execution plan.  It selects instruments, determines position sizing, plans
entry timing, and sets risk limits -- all within the context of the current
portfolio and market conditions.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Trade Execution Agent for Overture, an AI-driven
hedge fund assistant.  You are an expert at constructing optimal trade plans
that translate validated investment ideas into concrete, executable positions.

Your responsibilities:
1. INSTRUMENT SELECTION: Choose the best securities to express the thesis.
   Consider: direct equity, ETFs, futures, options (for leverage or defined
   risk), pairs trades, or baskets.  Prefer liquid instruments.  Use options
   when asymmetric payoffs are desired or when risk needs to be capped.
2. POSITION SIZING: Determine allocation based on conviction, portfolio risk
   budget, correlation with existing holdings, and volatility of the
   instrument.  Never risk more than the user's per-trade risk limit.
3. ENTRY STRATEGY: Plan entry timing and price levels.  Consider scaling in,
   limit vs. market orders, optimal execution windows (avoiding illiquid
   periods), and whether to use dollar-cost averaging.
4. RISK LIMITS: Set stop-loss, take-profit, and maximum holding period.
   Account for instrument-specific risks (options decay, futures roll costs).
5. EXIT PLAN: Define clear conditions for exiting the position -- both on the
   upside (profit target hit, thesis fully realized) and downside (thesis
   invalidated, stop hit, time decay).

Always output a complete execution plan as structured JSON.  The plan must be
actionable -- a human or automated system should be able to execute it directly.

Key principles:
- Position sizing should NEVER exceed portfolio risk limits
- Always have a defined stop-loss (even for long-term positions)
- Prefer limit orders over market orders for non-urgent entries
- Consider transaction costs and tax implications
- Account for correlation with existing portfolio positions
- For options, always specify expiration, strike, and type clearly
"""


class TradeExecutorAgent(BaseAgent):
    """Agent that constructs optimal trade execution plans.

    Takes validated ideas and portfolio context, and produces detailed
    execution plans including instrument selection, sizing, entry strategy,
    and risk management parameters.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Trade Executor",
            agent_type="idea",
            description=(
                "constructing optimal trade plans considering portfolio "
                "context, risk appetite, and market conditions"
            ),
        )

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def execute(
        self, input_data: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Create an execution plan for a validated investment idea.

        Args:
            input_data: Dictionary containing:
                - idea: The validated idea (including validation_result)
                - market_data: Current market data for the relevant tickers
                - risk_budget: Available risk budget for new positions
            context: Shared agent context with portfolio state.

        Returns:
            Dictionary with key ``execution_plan`` containing:
                - instruments: list of selected instruments with rationale
                - sizing: position sizing details
                - entry_plan: entry strategy and timing
                - stop_loss: stop-loss parameters
                - take_profit: take-profit parameters
                - exit_plan: conditions and strategy for exiting
                - estimated_costs: estimated transaction costs
                - risk_summary: summary of position risk
        """
        idea = input_data.get("idea", {})
        market_data = input_data.get("market_data", {})
        risk_budget = input_data.get("risk_budget", {})

        # Step 1: Select instruments
        instruments = await self._select_instruments(idea, context)

        # Step 2: Determine sizing
        sizing = await self._determine_sizing(idea, instruments, context, risk_budget)

        # Step 3: Plan entry strategy
        entry_plan = await self._plan_entry(idea, instruments, market_data, context)

        # Step 4: Set risk limits
        risk_limits = await self._set_risk_limits(idea, sizing, instruments, context)

        # Step 5: Build complete execution plan
        execution_plan = {
            "idea_title": idea.get("title", ""),
            "idea_thesis": idea.get("thesis", ""),
            "instruments": instruments,
            "sizing": sizing,
            "entry_plan": entry_plan,
            "stop_loss": risk_limits.get("stop_loss", {}),
            "take_profit": risk_limits.get("take_profit", {}),
            "exit_plan": risk_limits.get("exit_plan", {}),
            "max_holding_period": risk_limits.get("max_holding_period", ""),
            "estimated_costs": risk_limits.get("estimated_costs", {}),
            "risk_summary": risk_limits.get("risk_summary", ""),
        }

        await self.log_action(
            action="create_execution_plan",
            input_data={"idea_title": idea.get("title", "")},
            output_data={
                "instrument_count": len(instruments) if isinstance(instruments, list) else 0,
                "total_allocation": sizing.get("total_allocation_pct", 0) if isinstance(sizing, dict) else 0,
            },
        )

        return {"execution_plan": execution_plan}

    # ------------------------------------------------------------------
    # Private planning methods
    # ------------------------------------------------------------------

    async def _select_instruments(
        self, idea: dict[str, Any], context: AgentContext
    ) -> list[dict[str, Any]]:
        """Select the best instruments to express the investment thesis.

        Considers direct equity, ETFs, futures, options, and pairs trades.
        Evaluates liquidity, cost, and payoff profile of each option.

        Args:
            idea: The validated investment idea.
            context: Agent context with portfolio state.

        Returns:
            List of instrument dicts, each with ``symbol``, ``type``,
            ``rationale``, and ``details``.
        """
        if self._llm is None:
            return []

        tickers = idea.get("tickers", [])
        asset_class = idea.get("asset_class", "equity")
        timeframe = idea.get("timeframe", "tactical")
        portfolio_text = json.dumps(context.portfolio_state, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "SELECT INSTRUMENTS for the following idea:\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"SUGGESTED TICKERS: {tickers}\n"
                    f"ASSET CLASS: {asset_class}\n"
                    f"TIMEFRAME: {timeframe}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    "For each recommended instrument, consider:\n"
                    "- Direct equity vs ETF vs futures vs options\n"
                    "- Liquidity and bid-ask spreads\n"
                    "- If options: which strategy? (long call, put spread, etc.)\n"
                    "- If pairs trade: specify both legs\n"
                    "- Tax efficiency considerations\n\n"
                    "Return a JSON array of instrument objects with keys: "
                    "symbol, type (equity/etf/future/option/pair), direction "
                    "(long/short), rationale, details (object with specifics "
                    "like strike, expiry for options)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            instruments = json.loads(response.content)
            if isinstance(instruments, list):
                return instruments
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _determine_sizing(
        self,
        idea: dict[str, Any],
        instruments: list[dict[str, Any]],
        context: AgentContext,
        risk_budget: dict[str, Any],
    ) -> dict[str, Any]:
        """Determine position sizing based on risk parameters and portfolio.

        Uses conviction level, portfolio risk budget, instrument volatility,
        and correlation with existing holdings to calculate optimal size.

        Args:
            idea: The investment idea with confidence scores.
            instruments: Selected instruments.
            context: Agent context with portfolio state and preferences.
            risk_budget: Available risk budget for the trade.

        Returns:
            Dictionary with sizing details including per-instrument
            allocation, total allocation, and risk metrics.
        """
        if self._llm is None:
            return {"total_allocation_pct": 0, "per_instrument": []}

        portfolio_text = json.dumps(context.portfolio_state, default=str)
        preferences = json.dumps(context.user_preferences, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "POSITION SIZING for the following trade:\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"INSTRUMENTS:\n{json.dumps(instruments, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    f"USER PREFERENCES:\n{preferences}\n\n"
                    f"RISK BUDGET:\n{json.dumps(risk_budget, default=str)}\n\n"
                    "Determine optimal position sizing considering:\n"
                    "- Conviction level (from idea confidence)\n"
                    "- Portfolio-level risk budget and per-trade limits\n"
                    "- Correlation with existing holdings\n"
                    "- Instrument volatility\n"
                    "- Kelly criterion or similar optimal sizing framework\n\n"
                    "Return JSON with keys: total_allocation_pct (number), "
                    "total_dollar_amount (number or null), per_instrument "
                    "(array of {symbol, shares_or_contracts, allocation_pct, "
                    "rationale}), risk_per_trade_pct (number), "
                    "max_loss_estimate (number or null)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            sizing = json.loads(response.content)
            if isinstance(sizing, dict):
                return sizing
        except (json.JSONDecodeError, TypeError):
            pass

        return {"total_allocation_pct": 0, "per_instrument": []}

    async def _plan_entry(
        self,
        idea: dict[str, Any],
        instruments: list[dict[str, Any]],
        market_data: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Plan the entry strategy including timing and price levels.

        Considers whether to enter all at once, scale in, use limit orders,
        and which execution window to target.

        Args:
            idea: The investment idea.
            instruments: Selected instruments.
            market_data: Current market data for relevant tickers.
            context: Agent context.

        Returns:
            Dictionary with entry plan details.
        """
        if self._llm is None:
            return {"strategy": "unknown", "orders": []}

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "ENTRY PLANNING for the following trade:\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"INSTRUMENTS:\n{json.dumps(instruments, indent=2, default=str)}\n\n"
                    f"MARKET DATA:\n{json.dumps(market_data, indent=2, default=str)}\n\n"
                    "Plan the entry strategy:\n"
                    "- Should we enter at market or use limit orders?\n"
                    "- Scale in (e.g., 50% now, 25% on dip, 25% on confirmation) "
                    "or full size at once?\n"
                    "- Optimal execution window (avoid illiquid periods)\n"
                    "- Key price levels for entry\n"
                    "- Any urgency factors (catalyst timing, momentum decay)\n\n"
                    "Return JSON with keys: strategy (string), urgency "
                    "(high/medium/low), orders (array of {symbol, order_type, "
                    "limit_price, quantity_pct, condition}), scaling_plan "
                    "(object or null), notes (string)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            entry_plan = json.loads(response.content)
            if isinstance(entry_plan, dict):
                return entry_plan
        except (json.JSONDecodeError, TypeError):
            pass

        return {"strategy": "unknown", "orders": []}

    async def _set_risk_limits(
        self,
        idea: dict[str, Any],
        sizing: dict[str, Any],
        instruments: list[dict[str, Any]],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Set stop-loss, take-profit, and exit parameters.

        Defines the complete risk management framework for the trade
        including protective stops, profit targets, time-based exits,
        and thesis-invalidation triggers.

        Args:
            idea: The investment idea.
            sizing: Position sizing details.
            instruments: Selected instruments.
            context: Agent context.

        Returns:
            Dictionary with stop_loss, take_profit, exit_plan,
            max_holding_period, estimated_costs, and risk_summary.
        """
        if self._llm is None:
            return {
                "stop_loss": {},
                "take_profit": {},
                "exit_plan": {},
                "max_holding_period": "",
                "estimated_costs": {},
                "risk_summary": "",
            }

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "RISK LIMITS & EXIT PLAN for the following trade:\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"SIZING:\n{json.dumps(sizing, indent=2, default=str)}\n\n"
                    f"INSTRUMENTS:\n{json.dumps(instruments, indent=2, default=str)}\n\n"
                    f"USER RISK PREFERENCES:\n{json.dumps(context.user_preferences, default=str)}\n\n"
                    "Define comprehensive risk limits:\n\n"
                    "STOP LOSS:\n"
                    "- Where is the stop? (price level, % from entry, or ATR-based)\n"
                    "- Hard stop vs. mental stop vs. trailing stop?\n"
                    "- Stop methodology rationale\n\n"
                    "TAKE PROFIT:\n"
                    "- Primary target (where does the thesis say fair value is?)\n"
                    "- Scaling out plan (partial profits at milestones?)\n"
                    "- Trailing take-profit logic\n\n"
                    "EXIT PLAN:\n"
                    "- Thesis invalidation triggers (what kills the trade?)\n"
                    "- Time-based exit (max holding period)\n"
                    "- Regime change exit (what macro shift kills this?)\n\n"
                    "Return JSON with keys: stop_loss (object with type, level, "
                    "rationale), take_profit (object with targets array, scaling), "
                    "exit_plan (object with invalidation_triggers, regime_triggers), "
                    "max_holding_period (string), estimated_costs (object with "
                    "commissions, spread_cost, financing_cost), risk_summary (string)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            risk_limits = json.loads(response.content)
            if isinstance(risk_limits, dict):
                return risk_limits
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "stop_loss": {},
            "take_profit": {},
            "exit_plan": {},
            "max_holding_period": "",
            "estimated_costs": {},
            "risk_summary": "",
        }
