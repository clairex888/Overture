"""Risk Manager Agent for the Overture system.

This agent monitors portfolio-level risk metrics and detects emerging risk
events.  It calculates correlation, concentration, drawdown, Value-at-Risk,
and other risk measures, and proposes hedging strategies when risk thresholds
are breached.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Risk Manager Agent for Overture, an AI-driven
hedge fund assistant.  You are the guardian of the portfolio's risk profile.
Your role is to continuously monitor risk metrics, detect emerging threats, and
propose hedging strategies.

Risk metrics you monitor:
1. PORTFOLIO VOLATILITY: Annualized volatility, rolling volatility, vol regime
2. VALUE AT RISK (VaR): 1-day and 10-day VaR at 95% and 99% confidence
3. DRAWDOWN: Current drawdown from peak, maximum drawdown, drawdown duration
4. CONCENTRATION: Single-name, sector, geographic, and factor concentration
   (Herfindahl index, top-N exposure)
5. CORRELATION: Pairwise position correlations, portfolio beta to benchmarks,
   correlation regime changes
6. TAIL RISK: Expected shortfall (CVaR), stress test results, scenario analysis
7. LIQUIDITY RISK: Days to liquidate, bid-ask spread impact, market impact
8. LEVERAGE: Gross and net exposure, margin utilization

Risk events you detect:
- Drawdown exceeding threshold (e.g., > 5% from peak)
- Correlation spike (positions becoming more correlated than expected)
- Concentration breach (single position or sector too large)
- Volatility regime change (from low-vol to high-vol)
- Macro stress indicators (yield curve inversion, credit spread widening)
- Liquidity deterioration

Hedging strategies you may propose:
- Index puts for tail risk protection
- Sector hedges (short sector ETFs or futures)
- VIX calls or variance swaps for volatility hedging
- Currency hedges for international exposure
- Pairs trades to reduce directional exposure
- Cash raise to reduce overall exposure

Always be quantitative and specific.  Do not just flag risks -- quantify them
and propose concrete actions with estimated cost and effectiveness.
"""


class RiskManagerAgent(BaseAgent):
    """Agent that monitors portfolio risk and proposes hedging strategies.

    Continuously evaluates risk metrics and detects conditions that
    warrant protective action or user notification.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Risk Manager",
            agent_type="portfolio",
            description=(
                "monitoring portfolio risk metrics including correlation, "
                "concentration, drawdown, and VaR, and proposing hedging "
                "strategies"
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
        """Generate a comprehensive risk report for the portfolio.

        Args:
            input_data: Dictionary containing:
                - market_data: current market data and volatility surface
                - risk_thresholds: user-defined risk limits
                - stress_scenarios: optional custom stress scenarios to run
            context: Shared agent context with portfolio state.

        Returns:
            Dictionary with key ``risk_report`` containing metrics,
            detected events, alerts, and hedging recommendations.
        """
        market_data = input_data.get("market_data", {})
        risk_thresholds = input_data.get("risk_thresholds", {})
        stress_scenarios = input_data.get("stress_scenarios", [])

        # Step 1: Calculate comprehensive risk metrics
        risk_metrics = await self._calculate_risk_metrics(context)

        # Step 2: Detect risk events
        risk_events = await self._detect_risk_events(
            risk_metrics, market_data, risk_thresholds, context
        )

        # Step 3: Propose hedges if there are risk events
        hedge_recommendations: list[dict[str, Any]] = []
        if risk_events.get("events", []):
            hedge_recommendations = await self._propose_hedges(
                risk_events, context
            )

        risk_report = {
            "metrics": risk_metrics,
            "risk_events": risk_events,
            "alerts": risk_events.get("alerts", []),
            "hedge_recommendations": hedge_recommendations,
            "overall_risk_level": risk_events.get("overall_risk_level", "moderate"),
        }

        await self.log_action(
            action="risk_assessment",
            input_data={"has_market_data": bool(market_data)},
            output_data={
                "event_count": len(risk_events.get("events", [])),
                "hedge_count": len(hedge_recommendations),
                "risk_level": risk_report["overall_risk_level"],
            },
        )

        return {"risk_report": risk_report}

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _calculate_risk_metrics(
        self, context: AgentContext
    ) -> dict[str, Any]:
        """Calculate comprehensive risk metrics for the portfolio.

        Computes volatility, VaR, drawdown, concentration, correlation,
        and liquidity metrics based on the current portfolio state.

        Args:
            context: Agent context with portfolio state.

        Returns:
            Dictionary with all risk metrics organized by category.
        """
        if self._llm is None:
            return {"status": "llm_unavailable"}

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)
        market_text = json.dumps(context.market_context, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "CALCULATE RISK METRICS\n\n"
                    f"PORTFOLIO STATE:\n{portfolio_text}\n\n"
                    f"MARKET CONTEXT:\n{market_text}\n\n"
                    "Calculate the following risk metrics:\n"
                    "1. Portfolio volatility (annualized, 30-day rolling)\n"
                    "2. Value at Risk (1-day 95%, 1-day 99%, 10-day 95%)\n"
                    "3. Current drawdown from peak and max drawdown\n"
                    "4. Concentration metrics (Herfindahl, top-5 weight)\n"
                    "5. Average pairwise correlation\n"
                    "6. Portfolio beta to major indices (SPY, AGG, DXY)\n"
                    "7. Liquidity score (estimated days to liquidate 90%)\n"
                    "8. Gross and net exposure\n\n"
                    "Return JSON with keys: volatility (object with annualized, "
                    "rolling_30d), var (object with d1_95, d1_99, d10_95), "
                    "drawdown (object with current_pct, max_pct, duration_days), "
                    "concentration (object with herfindahl, top5_weight_pct), "
                    "correlation (object with avg_pairwise, regime), "
                    "beta (object with spy, agg, dxy), liquidity_days (number), "
                    "exposure (object with gross_pct, net_pct)."
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

        return {"raw_analysis": response.content}

    async def _detect_risk_events(
        self,
        risk_metrics: dict[str, Any],
        market_data: dict[str, Any],
        risk_thresholds: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Detect risk events that warrant attention or action.

        Compares calculated risk metrics against thresholds and monitors
        for regime changes in volatility, correlation, and macro indicators.

        Args:
            risk_metrics: Calculated portfolio risk metrics.
            market_data: Current market data.
            risk_thresholds: User-defined risk limits.
            context: Agent context.

        Returns:
            Dictionary with ``events`` (list of detected risk events),
            ``alerts`` (list of alert messages), and ``overall_risk_level``.
        """
        if self._llm is None:
            return {"events": [], "alerts": [], "overall_risk_level": "unknown"}

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "DETECT RISK EVENTS\n\n"
                    f"RISK METRICS:\n{json.dumps(risk_metrics, indent=2, default=str)}\n\n"
                    f"MARKET DATA:\n{json.dumps(market_data, indent=2, default=str)}\n\n"
                    f"RISK THRESHOLDS:\n{json.dumps(risk_thresholds, indent=2, default=str)}\n\n"
                    "Identify any risk events or threshold breaches:\n"
                    "1. Is the drawdown approaching or exceeding limits?\n"
                    "2. Is portfolio volatility spiking?\n"
                    "3. Are correlations breaking down or spiking?\n"
                    "4. Are concentration limits breached?\n"
                    "5. Any macro stress signals (credit spreads, yield curve, "
                    "VIX level)?\n"
                    "6. Liquidity concerns?\n\n"
                    "Return JSON with keys: events (array of {type, severity, "
                    "description, metric_value, threshold}), alerts (array of "
                    "human-readable alert strings), overall_risk_level "
                    "(low/moderate/elevated/high/critical)."
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

        return {"events": [], "alerts": [], "overall_risk_level": "unknown"}

    async def _propose_hedges(
        self,
        risk_events: dict[str, Any],
        context: AgentContext,
    ) -> list[dict[str, Any]]:
        """Propose hedging strategies for detected risk events.

        Designs specific, actionable hedge trades with estimated cost and
        effectiveness for each material risk event.

        Args:
            risk_events: Detected risk events from the monitoring step.
            context: Agent context with portfolio state.

        Returns:
            List of hedge recommendation dicts, each with ``event_addressed``,
            ``strategy``, ``instruments``, ``estimated_cost``,
            ``estimated_effectiveness``, and ``rationale``.
        """
        if self._llm is None:
            return []

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PROPOSE HEDGING STRATEGIES\n\n"
                    f"RISK EVENTS:\n{json.dumps(risk_events, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    "For each material risk event, propose a specific hedge:\n"
                    "1. What instrument(s) to use?\n"
                    "2. What is the estimated cost (as % of portfolio)?\n"
                    "3. How effective would it be (% of risk mitigated)?\n"
                    "4. What are the trade-offs?\n\n"
                    "Consider: index puts, sector shorts, VIX calls, "
                    "currency hedges, pairs trades, cash raising.\n\n"
                    "Return a JSON array of hedge objects with keys: "
                    "event_addressed (string), strategy (string), "
                    "instruments (array of {symbol, type, direction, size}), "
                    "estimated_cost_pct (number), estimated_effectiveness_pct "
                    "(number), rationale (string), trade_offs (array of strings)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            hedges = json.loads(response.content)
            if isinstance(hedges, list):
                return hedges
        except (json.JSONDecodeError, TypeError):
            pass

        return []
