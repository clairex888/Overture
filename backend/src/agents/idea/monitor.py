"""Trade Monitor Agent for the Overture system.

This agent continuously monitors open positions and makes recommendations
about whether to hold, close, or adjust each trade.  It checks price targets,
thesis validity, time decay, and market conditions to produce actionable
monitoring reports.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Trade Monitor Agent for Overture, an AI-driven
hedge fund assistant.  Your role is to continuously monitor open positions and
provide timely recommendations for trade management.

You monitor each open trade through four lenses:

1. PRICE TARGETS: Has the stop-loss or take-profit been hit?  Is the price
   approaching key levels?  Should the stop be trailed?
2. THESIS VALIDITY: Is the original investment thesis still intact?  Have new
   developments (earnings, news, macro changes) altered the thesis?  Has the
   catalyst played out?
3. TIME DECAY: Is the trade taking longer than expected?  For options, is theta
   decay eroding the position?  Has the expected timeframe elapsed?
4. MARKET CONDITIONS: Has the market regime changed?  Are correlations shifting?
   Is volatility expanding or contracting in a way that affects the position?

For each trade, you produce one of four recommendations:
- HOLD: Thesis intact, stay the course
- CLOSE: Exit the position (with reason: stop hit, target hit, thesis invalid)
- ADJUST: Modify the position (trail stop, take partial profits, roll options)
- ALERT: Flag something for the user's attention without a specific action

Always be precise about urgency:
- URGENT: Requires immediate action (stop hit, thesis broken)
- NORMAL: Review at next convenient time
- LOW: Informational only

Output structured JSON for each monitored trade.
"""


class TradeMonitorAgent(BaseAgent):
    """Agent that monitors active trades and recommends management actions.

    Continuously evaluates open positions against their original execution
    plans and current market conditions, producing hold/close/adjust
    recommendations.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Trade Monitor",
            agent_type="idea",
            description=(
                "monitoring open positions and making exit or adjustment "
                "decisions based on price targets, thesis validity, and "
                "market conditions"
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
        """Monitor active trades and generate recommendations.

        Args:
            input_data: Dictionary containing:
                - trades: list of active trade dicts, each including the
                  execution plan, entry details, and current P&L
                - market_data: current market data for relevant tickers
                - news: recent news that may affect open positions
            context: Shared agent context.

        Returns:
            Dictionary with key ``monitoring_results`` containing a list of
            per-trade monitoring reports, each with status, alerts, and
            recommended actions.
        """
        trades = input_data.get("trades", [])
        market_data = input_data.get("market_data", {})
        news = input_data.get("news", [])

        monitoring_results: list[dict[str, Any]] = []

        for trade in trades:
            # Run all checks for this trade
            price_check = await self._check_price_targets(trade, market_data)
            thesis_check = await self._check_thesis_validity(trade, news, context)
            time_check = await self._check_time_decay(trade)

            # Synthesize a recommendation
            checks = {
                "price_targets": price_check,
                "thesis_validity": thesis_check,
                "time_decay": time_check,
            }
            recommendation = await self._recommend_action(trade, checks, context)

            monitoring_results.append({
                "trade_id": trade.get("id", "unknown"),
                "trade_title": trade.get("title", trade.get("idea_title", "unknown")),
                "status": recommendation.get("status", "monitoring"),
                "recommendation": recommendation.get("action", "HOLD"),
                "urgency": recommendation.get("urgency", "NORMAL"),
                "alerts": recommendation.get("alerts", []),
                "price_check": price_check,
                "thesis_check": thesis_check,
                "time_check": time_check,
                "reasoning": recommendation.get("reasoning", ""),
                "suggested_actions": recommendation.get("suggested_actions", []),
            })

        await self.log_action(
            action="monitor_trades",
            input_data={"trade_count": len(trades)},
            output_data={
                "results_count": len(monitoring_results),
                "actions": [r.get("recommendation") for r in monitoring_results],
            },
        )

        return {"monitoring_results": monitoring_results}

    # ------------------------------------------------------------------
    # Monitoring checks
    # ------------------------------------------------------------------

    async def _check_price_targets(
        self, trade: dict[str, Any], market_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Check if stop-loss or take-profit levels have been hit.

        Also evaluates proximity to key price levels and whether trailing
        stops should be adjusted.

        Args:
            trade: Active trade dict with execution plan and current price.
            market_data: Current market data snapshot.

        Returns:
            Dictionary with price check results including ``stop_hit``,
            ``target_hit``, ``proximity_alerts``, and ``trail_recommendation``.
        """
        if self._llm is None:
            return {
                "stop_hit": False,
                "target_hit": False,
                "proximity_alerts": [],
                "trail_recommendation": None,
            }

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PRICE TARGET CHECK\n\n"
                    f"TRADE:\n{json.dumps(trade, indent=2, default=str)}\n\n"
                    f"CURRENT MARKET DATA:\n{json.dumps(market_data, indent=2, default=str)}\n\n"
                    "Check:\n"
                    "1. Has the stop-loss been hit or breached?\n"
                    "2. Has any take-profit target been reached?\n"
                    "3. Is the price approaching key levels (within 2%)?\n"
                    "4. Should the trailing stop be adjusted?\n"
                    "5. What is the current P&L status?\n\n"
                    "Return JSON with keys: stop_hit (bool), target_hit (bool), "
                    "proximity_alerts (array of strings), "
                    "trail_recommendation (object with new_level and rationale, "
                    "or null), current_pnl_pct (number or null)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.2, max_tokens=1024
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "stop_hit": False,
            "target_hit": False,
            "proximity_alerts": [],
            "trail_recommendation": None,
        }

    async def _check_thesis_validity(
        self, trade: dict[str, Any], news: list[dict[str, Any]], context: AgentContext
    ) -> dict[str, Any]:
        """Check if the original investment thesis is still valid.

        Evaluates whether new information (news, earnings, macro changes)
        has confirmed, weakened, or invalidated the thesis.

        Args:
            trade: Active trade dict with the original thesis.
            news: Recent news items that may affect the trade.

        Returns:
            Dictionary with ``thesis_intact`` (bool), ``thesis_strength``
            (0-1), ``developments`` (list), and ``invalidation_risk``.
        """
        if self._llm is None:
            return {
                "thesis_intact": True,
                "thesis_strength": 0.5,
                "developments": [],
                "invalidation_risk": "unknown",
            }

        news_text = json.dumps(news[:20], indent=2, default=str) if news else "No recent news"

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "THESIS VALIDITY CHECK\n\n"
                    f"TRADE:\n{json.dumps(trade, indent=2, default=str)}\n\n"
                    f"RECENT NEWS:\n{news_text}\n\n"
                    f"MARKET CONTEXT:\n{json.dumps(context.market_context, default=str)}\n\n"
                    "Evaluate whether the original thesis is still valid:\n"
                    "1. Have any of the thesis invalidation triggers fired?\n"
                    "2. Has new information strengthened or weakened the thesis?\n"
                    "3. Has the expected catalyst occurred?  What was the result?\n"
                    "4. Has the competitive/macro landscape changed materially?\n"
                    "5. Is the market regime still supportive of this trade?\n\n"
                    "Return JSON with keys: thesis_intact (bool), "
                    "thesis_strength (0.0-1.0), developments (array of "
                    "relevant new developments), invalidation_risk "
                    "(low/medium/high)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=1024
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "thesis_intact": True,
            "thesis_strength": 0.5,
            "developments": [],
            "invalidation_risk": "unknown",
        }

    async def _check_time_decay(
        self, trade: dict[str, Any]
    ) -> dict[str, Any]:
        """Check if the trade is taking longer than expected.

        Evaluates whether the position has exceeded its intended timeframe
        and whether time-related factors (options theta, financing costs,
        opportunity cost) warrant action.

        Args:
            trade: Active trade dict with entry date, expected timeframe,
                and instrument details.

        Returns:
            Dictionary with ``within_timeframe`` (bool), ``days_held``,
            ``expected_days``, ``time_decay_impact``, and ``urgency``.
        """
        if self._llm is None:
            return {
                "within_timeframe": True,
                "days_held": 0,
                "expected_days": 0,
                "time_decay_impact": "none",
                "urgency": "LOW",
            }

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "TIME DECAY CHECK\n\n"
                    f"TRADE:\n{json.dumps(trade, indent=2, default=str)}\n\n"
                    "Evaluate time-related factors:\n"
                    "1. How long has the position been held vs. expected?\n"
                    "2. For options: what is the theta impact?  Days to expiry?\n"
                    "3. For any position: is the opportunity cost growing?\n"
                    "4. Is the expected catalyst timeline still realistic?\n"
                    "5. Should a time-based exit be triggered?\n\n"
                    "Return JSON with keys: within_timeframe (bool), "
                    "days_held (number), expected_days (number), "
                    "time_decay_impact (none/low/medium/high), "
                    "urgency (LOW/NORMAL/URGENT), notes (string)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.2, max_tokens=1024
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "within_timeframe": True,
            "days_held": 0,
            "expected_days": 0,
            "time_decay_impact": "none",
            "urgency": "LOW",
        }

    async def _recommend_action(
        self,
        trade: dict[str, Any],
        checks: dict[str, dict[str, Any]],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Synthesize all monitoring checks into a single recommendation.

        Combines price target, thesis validity, and time decay checks into
        an actionable recommendation: HOLD, CLOSE, ADJUST, or ALERT.

        Args:
            trade: The active trade.
            checks: Results from all monitoring checks.

        Returns:
            Dictionary with ``action`` (HOLD/CLOSE/ADJUST/ALERT),
            ``urgency`` (URGENT/NORMAL/LOW), ``status``, ``alerts``,
            ``reasoning``, and ``suggested_actions``.
        """
        if self._llm is None:
            return {
                "action": "HOLD",
                "urgency": "LOW",
                "status": "monitoring",
                "alerts": [],
                "reasoning": "LLM not available for recommendation",
                "suggested_actions": [],
            }

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "TRADE RECOMMENDATION SYNTHESIS\n\n"
                    f"TRADE:\n{json.dumps(trade, indent=2, default=str)}\n\n"
                    f"MONITORING CHECKS:\n{json.dumps(checks, indent=2, default=str)}\n\n"
                    "Based on all monitoring data, provide a recommendation:\n"
                    "- HOLD: Thesis intact, no action needed\n"
                    "- CLOSE: Exit the position (specify reason)\n"
                    "- ADJUST: Modify position (trail stop, partial close, roll)\n"
                    "- ALERT: Flag for user attention\n\n"
                    "Return JSON with keys: action (HOLD/CLOSE/ADJUST/ALERT), "
                    "urgency (URGENT/NORMAL/LOW), status (string), "
                    "alerts (array of alert strings), reasoning (string), "
                    "suggested_actions (array of specific action descriptions)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.2, max_tokens=1024
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {
            "action": "HOLD",
            "urgency": "LOW",
            "status": "monitoring",
            "alerts": [],
            "reasoning": response.content if hasattr(response, "content") else "",
            "suggested_actions": [],
        }
