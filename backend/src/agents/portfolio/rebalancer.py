"""Rebalancer Agent for the Overture system.

This agent determines when the portfolio has drifted from its target allocation
and generates the trades needed to bring it back into alignment.  It considers
transaction costs, tax implications, and market conditions when planning
rebalance trades.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Rebalancer Agent for Overture, an AI-driven
hedge fund assistant.  You determine when and how to rebalance the portfolio
to maintain alignment with target allocations.

Rebalancing triggers:
1. CALENDAR-BASED: Periodic rebalancing (monthly, quarterly)
2. THRESHOLD-BASED: When any asset class drifts beyond a defined band
   (e.g., +/- 5% from target)
3. EVENT-DRIVEN: After significant market moves, large cash inflows/outflows,
   or changes to the investment policy

Rebalancing considerations:
- TRANSACTION COSTS: Minimize turnover; only rebalance when the benefit
  exceeds the cost (commissions, spreads, market impact)
- TAX EFFICIENCY: Prefer selling losers over winners (tax-loss harvesting);
  be aware of wash sale rules; consider short-term vs long-term gains
- MARKET CONDITIONS: Avoid rebalancing into illiquid markets; consider
  whether current volatility makes rebalancing timing critical
- GRADUAL vs IMMEDIATE: For large drifts, consider phased rebalancing to
  reduce market impact
- CASH FLOW REBALANCING: Use incoming dividends, contributions, or
  withdrawals to rebalance opportunistically without forced selling

Output a specific rebalance plan with:
- Which positions to increase or decrease
- Order type and timing recommendations
- Estimated transaction costs
- Expected tax impact
- Priority ordering (most important rebalances first)
"""


class RebalancerAgent(BaseAgent):
    """Agent that monitors allocation drift and generates rebalancing plans.

    Determines when rebalancing is warranted and produces trade lists that
    bring the portfolio back to target allocations while minimizing cost
    and tax impact.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Rebalancer",
            agent_type="portfolio",
            description=(
                "determining when and how to rebalance the portfolio to "
                "maintain target allocations while minimizing costs and "
                "tax impact"
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
        """Evaluate portfolio drift and generate a rebalance plan if needed.

        Args:
            input_data: Dictionary containing:
                - targets: target allocation dict (asset_class -> target_pct)
                - drift_threshold: max acceptable drift percentage (default 5.0)
                - cash_flows: upcoming cash inflows/outflows
                - tax_context: tax lot information for tax-aware rebalancing
            context: Shared agent context with current portfolio state.

        Returns:
            Dictionary with key ``rebalance_plan`` containing drift analysis,
            proposed trades, and execution recommendations.
        """
        targets = input_data.get("targets", {})
        drift_threshold = input_data.get("drift_threshold", 5.0)
        cash_flows = input_data.get("cash_flows", {})
        tax_context = input_data.get("tax_context", {})

        # Step 1: Check drift
        drift_analysis = await self._check_drift(targets, drift_threshold, context)

        # Step 2: Generate rebalance trades if drift warrants action
        rebalance_trades: list[dict[str, Any]] = []
        needs_rebalance = drift_analysis.get("needs_rebalance", False)

        if needs_rebalance:
            rebalance_trades = await self._generate_rebalance_trades(
                drift_analysis, cash_flows, tax_context, context
            )

        rebalance_plan = {
            "needs_rebalance": needs_rebalance,
            "drift_analysis": drift_analysis,
            "proposed_trades": rebalance_trades,
            "trade_count": len(rebalance_trades),
            "estimated_turnover_pct": drift_analysis.get("total_drift_pct", 0) / 2,
        }

        await self.log_action(
            action="rebalance_check",
            input_data={"drift_threshold": drift_threshold},
            output_data={
                "needs_rebalance": needs_rebalance,
                "trade_count": len(rebalance_trades),
            },
        )

        return {"rebalance_plan": rebalance_plan}

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _check_drift(
        self,
        targets: dict[str, Any],
        drift_threshold: float,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Check how far the portfolio has drifted from target allocations.

        Compares current allocation to targets across asset classes, sectors,
        and any other defined allocation dimensions.

        Args:
            targets: Target allocation percentages.
            drift_threshold: Maximum acceptable drift before rebalancing.
            context: Agent context with current portfolio state.

        Returns:
            Dictionary with per-dimension drift, total drift, and whether
            rebalancing is recommended.
        """
        if self._llm is None:
            return {"needs_rebalance": False, "total_drift_pct": 0, "drifts": []}

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "CHECK ALLOCATION DRIFT\n\n"
                    f"TARGET ALLOCATION:\n{json.dumps(targets, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    f"DRIFT THRESHOLD: {drift_threshold}%\n\n"
                    "For each allocation dimension (asset class, sector, etc.):\n"
                    "1. What is the current allocation?\n"
                    "2. What is the target?\n"
                    "3. What is the drift (current - target)?\n"
                    "4. Does it exceed the threshold?\n\n"
                    "Return JSON with keys: needs_rebalance (bool), "
                    "total_drift_pct (number -- sum of absolute drifts), "
                    "drifts (array of {dimension, current_pct, target_pct, "
                    "drift_pct, exceeds_threshold}), max_drift_dimension "
                    "(string), urgency (low/medium/high)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.2, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"needs_rebalance": False, "total_drift_pct": 0, "drifts": []}

    async def _generate_rebalance_trades(
        self,
        drift_analysis: dict[str, Any],
        cash_flows: dict[str, Any],
        tax_context: dict[str, Any],
        context: AgentContext,
    ) -> list[dict[str, Any]]:
        """Generate specific trades to rebalance the portfolio.

        Produces an ordered list of trades that bring the portfolio back
        to target, considering transaction costs, tax efficiency, and
        market conditions.

        Args:
            drift_analysis: Results from drift checking.
            cash_flows: Expected cash inflows/outflows.
            tax_context: Tax lot information for tax-aware decisions.
            context: Agent context.

        Returns:
            List of rebalance trade dicts, each with ``symbol``,
            ``action`` (buy/sell), ``quantity``, ``rationale``,
            ``priority``, and ``tax_notes``.
        """
        if self._llm is None:
            return []

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "GENERATE REBALANCE TRADES\n\n"
                    f"DRIFT ANALYSIS:\n{json.dumps(drift_analysis, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    f"CASH FLOWS:\n{json.dumps(cash_flows, indent=2, default=str)}\n\n"
                    f"TAX CONTEXT:\n{json.dumps(tax_context, indent=2, default=str)}\n\n"
                    "Generate specific rebalance trades:\n"
                    "1. Which positions to sell (reduce overweight allocations)\n"
                    "2. Which positions to buy (increase underweight allocations)\n"
                    "3. Can we use incoming cash flows instead of selling?\n"
                    "4. Tax-loss harvesting opportunities?\n"
                    "5. Priority ordering (most impactful first)\n"
                    "6. Order type recommendations (market vs limit)\n\n"
                    "Return a JSON array of trade objects with keys: symbol, "
                    "action (buy/sell), quantity_or_pct (number), order_type "
                    "(market/limit), limit_price (number or null), priority "
                    "(1=highest), rationale (string), tax_notes (string), "
                    "estimated_cost (number)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            trades = json.loads(response.content)
            if isinstance(trades, list):
                return trades
        except (json.JSONDecodeError, TypeError):
            pass

        return []
