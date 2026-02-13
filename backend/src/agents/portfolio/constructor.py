"""Portfolio Constructor Agent for the Overture system.

This agent is responsible for building and maintaining the overall portfolio
structure.  It takes user preferences (goals, risk appetite, allocation targets,
core macro views) and the current market outlook to propose and maintain optimal
portfolio allocations across asset classes and strategies.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Portfolio Constructor Agent for Overture, an
AI-driven hedge fund assistant.  You are an expert at building and maintaining
diversified investment portfolios that align with the user's goals, risk
appetite, and market views.

Your responsibilities:
1. ASSESS the current portfolio allocation across asset classes, sectors,
   geographies, factors, and strategies.
2. PROPOSE target allocations based on the user's investment policy, current
   market outlook (long-term secular, medium-term cyclical, and short-term
   tactical layers), and risk budget.
3. EVALUATE new trades for compatibility with the overall portfolio construction
   before they are executed.
4. MAINTAIN the portfolio construction framework as market conditions evolve.

Portfolio construction principles:
- Diversification across uncorrelated return streams
- Risk parity considerations (balance risk contribution, not just capital)
- Core-satellite approach: stable core holdings + tactical satellite positions
- Respect the user's maximum allocation constraints per asset class/sector
- Consider both strategic (long-term) and tactical (short-term) allocation
- Account for the full spectrum: equities, fixed income, commodities, real
  assets, alternatives, cash
- Factor exposure management: balance value, growth, momentum, quality, size
- Liquidity tiering: ensure sufficient liquid assets for rebalancing and
  redemptions

Market outlook layers:
- SECULAR (5-10 year): structural trends, demographics, technology shifts
- CYCLICAL (1-3 year): business cycle positioning, credit cycle, earnings cycle
- TACTICAL (1-12 months): near-term opportunities, event-driven, momentum

Always output structured JSON with clear rationale for every allocation decision.
"""


class PortfolioConstructorAgent(BaseAgent):
    """Agent that constructs and maintains optimal portfolio allocations.

    Integrates user preferences, market outlook, and risk constraints to
    build a coherent portfolio framework that individual trades must fit
    within.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Portfolio Constructor",
            agent_type="portfolio",
            description=(
                "building and maintaining diversified portfolio allocations "
                "aligned with user goals, risk appetite, and market outlook"
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
        """Construct or update the portfolio allocation plan.

        Args:
            input_data: Dictionary containing:
                - action: "construct", "evaluate_trade", or "update"
                - preferences: user investment preferences and constraints
                - outlook: market outlook across secular/cyclical/tactical layers
                - trade_plan: (for evaluate_trade) the proposed trade to evaluate
            context: Shared agent context with current portfolio state.

        Returns:
            Dictionary with key ``construction_plan`` containing the full
            portfolio construction output appropriate to the requested action.
        """
        action = input_data.get("action", "construct")
        preferences = input_data.get("preferences", context.user_preferences)
        outlook = input_data.get("outlook", context.market_context)

        if action == "evaluate_trade":
            trade_plan = input_data.get("trade_plan", {})
            result = await self._evaluate_new_trade(trade_plan, context)
        elif action == "update":
            current_assessment = await self._assess_current_allocation(context)
            proposed = await self._propose_allocation(preferences, outlook, context)
            result = {
                "current_assessment": current_assessment,
                "proposed_allocation": proposed,
                "action": "update",
            }
        else:
            # Full construction
            current_assessment = await self._assess_current_allocation(context)
            proposed = await self._propose_allocation(preferences, outlook, context)
            result = {
                "current_assessment": current_assessment,
                "proposed_allocation": proposed,
                "action": "construct",
            }

        await self.log_action(
            action=f"portfolio_{action}",
            input_data={"action": action},
            output_data={"has_result": bool(result)},
        )

        return {"construction_plan": result}

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _assess_current_allocation(
        self, context: AgentContext
    ) -> dict[str, Any]:
        """Analyze the current state of the portfolio allocation.

        Evaluates asset class breakdown, sector exposure, geographic
        distribution, factor tilts, and concentration metrics.

        Args:
            context: Agent context with current portfolio state.

        Returns:
            Dictionary with current allocation analysis including breakdowns
            by asset class, sector, geography, and factor exposure.
        """
        if self._llm is None:
            return {"status": "llm_unavailable"}

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "ASSESS CURRENT PORTFOLIO ALLOCATION\n\n"
                    f"PORTFOLIO STATE:\n{portfolio_text}\n\n"
                    "Provide a comprehensive analysis of the current allocation:\n"
                    "1. Asset class breakdown (equities, bonds, commodities, "
                    "cash, alternatives)\n"
                    "2. Sector exposure and concentration\n"
                    "3. Geographic distribution\n"
                    "4. Factor tilts (value, growth, momentum, quality, size)\n"
                    "5. Liquidity profile\n"
                    "6. Largest single-name concentrations\n"
                    "7. Correlation structure (are positions correlated?)\n\n"
                    "Return JSON with keys: asset_class_breakdown (object), "
                    "sector_breakdown (object), geographic_breakdown (object), "
                    "factor_exposures (object), liquidity_profile (object), "
                    "top_concentrations (array), correlation_concerns (array), "
                    "overall_assessment (string)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"overall_assessment": response.content}

    async def _propose_allocation(
        self,
        preferences: dict[str, Any],
        outlook: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Propose target allocation based on preferences and market outlook.

        Integrates user goals, risk appetite, investment policy constraints,
        and multi-layer market outlook to build an optimal target allocation.

        Args:
            preferences: User investment preferences and constraints.
            outlook: Market outlook across secular, cyclical, and tactical layers.
            context: Agent context.

        Returns:
            Dictionary with proposed allocation including targets per asset
            class, rationale, and implementation notes.
        """
        if self._llm is None:
            return {"status": "llm_unavailable"}

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PROPOSE TARGET ALLOCATION\n\n"
                    f"USER PREFERENCES:\n{json.dumps(preferences, indent=2, default=str)}\n\n"
                    f"MARKET OUTLOOK:\n{json.dumps(outlook, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    "Propose a target portfolio allocation considering:\n"
                    "1. User's risk appetite and return objectives\n"
                    "2. Secular outlook (5-10yr structural themes)\n"
                    "3. Cyclical outlook (where are we in the business cycle?)\n"
                    "4. Tactical outlook (near-term opportunities/risks)\n"
                    "5. Current portfolio vs. target gaps\n\n"
                    "Structure the allocation into:\n"
                    "- CORE (60-80%): long-term strategic holdings\n"
                    "- SATELLITE (15-30%): tactical positions\n"
                    "- CASH BUFFER (5-15%): dry powder and liquidity\n\n"
                    "Return JSON with keys: core_allocation (object mapping "
                    "asset_class to target_pct), satellite_allocation (object), "
                    "cash_buffer_pct (number), total_equity_pct (number), "
                    "total_fixed_income_pct (number), total_alternatives_pct "
                    "(number), rationale (string), implementation_notes (array)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.4, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"rationale": response.content}

    async def _evaluate_new_trade(
        self,
        trade_plan: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Evaluate whether a proposed trade fits within the portfolio framework.

        Checks that the trade does not violate allocation constraints,
        concentration limits, or risk budget, and assesses its
        complementarity with existing positions.

        Args:
            trade_plan: The proposed execution plan from the Trade Executor.
            context: Agent context with current portfolio state.

        Returns:
            Dictionary with ``approved`` (bool), ``compatibility_score``
            (0-1), ``concerns`` (list), ``adjustments`` (list), and
            ``rationale`` (string).
        """
        if self._llm is None:
            return {
                "approved": False,
                "compatibility_score": 0.0,
                "concerns": ["LLM unavailable for evaluation"],
                "adjustments": [],
                "rationale": "Cannot evaluate without LLM",
            }

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)
        preferences_text = json.dumps(context.user_preferences, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "EVALUATE NEW TRADE FOR PORTFOLIO COMPATIBILITY\n\n"
                    f"PROPOSED TRADE:\n{json.dumps(trade_plan, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    f"USER PREFERENCES & CONSTRAINTS:\n{preferences_text}\n\n"
                    "Evaluate this trade against the portfolio framework:\n"
                    "1. Does it violate any asset class allocation limits?\n"
                    "2. Does it create excessive sector/name concentration?\n"
                    "3. Is the position size appropriate given the risk budget?\n"
                    "4. How correlated is it with existing positions?\n"
                    "5. Does it complement or conflict with the portfolio thesis?\n"
                    "6. Would you recommend any adjustments to the trade or "
                    "existing positions to accommodate it?\n\n"
                    "Return JSON with keys: approved (bool), "
                    "compatibility_score (0.0-1.0), concerns (array of strings), "
                    "adjustments (array of suggested modifications), "
                    "rationale (string)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "approved": False,
            "compatibility_score": 0.0,
            "concerns": ["Failed to parse evaluation"],
            "adjustments": [],
            "rationale": response.content,
        }
