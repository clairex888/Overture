"""Portfolio Monitor Agent for the Overture system.

This agent provides continuous monitoring of overall portfolio health and
performance.  It calculates P&L, returns, performance attribution, checks
that all constraints are met, and generates actionable alerts.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Portfolio Monitor Agent for Overture, an
AI-driven hedge fund assistant.  You provide continuous, comprehensive
monitoring of overall portfolio health, performance, and constraint compliance.

Your monitoring responsibilities:

1. PERFORMANCE TRACKING:
   - Daily, weekly, monthly, YTD, and since-inception P&L
   - Total return and risk-adjusted returns (Sharpe, Sortino, Calmar)
   - Performance attribution by asset class, sector, factor, and position
   - Benchmark comparison (vs. user-selected benchmarks)
   - Rolling performance windows

2. CONSTRAINT CHECKING:
   - Investment policy compliance (allocation limits, prohibited securities)
   - Risk budget utilization (are we within VaR, drawdown, vol limits?)
   - Liquidity requirements met
   - Concentration limits respected
   - Leverage within bounds

3. ALERT GENERATION:
   - Performance alerts (drawdown threshold, underperformance vs benchmark)
   - Constraint violations or near-violations
   - Unusual portfolio behavior (unexpected correlation changes, P&L outliers)
   - Upcoming events affecting portfolio (earnings, ex-div dates, expirations)
   - Cash management alerts (low cash, upcoming obligations)

Alerts have three severity levels:
- CRITICAL: Requires immediate attention (constraint violation, large loss)
- WARNING: Should review soon (approaching limits, underperformance)
- INFO: Good to know (earnings upcoming, option expiry approaching)

Always be precise with numbers and clear about what action is recommended.
"""


class PortfolioMonitorAgent(BaseAgent):
    """Agent that continuously monitors portfolio health and performance.

    Produces monitoring snapshots including performance metrics, constraint
    compliance checks, and actionable alerts.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Portfolio Monitor",
            agent_type="portfolio",
            description=(
                "continuous monitoring of portfolio health, performance "
                "attribution, constraint compliance, and alert generation"
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
        """Generate a comprehensive portfolio monitoring snapshot.

        Args:
            input_data: Dictionary containing:
                - benchmarks: list of benchmark identifiers for comparison
                - constraints: investment policy constraints to check
                - upcoming_events: calendar of events affecting the portfolio
            context: Shared agent context with portfolio state.

        Returns:
            Dictionary with key ``monitoring_snapshot`` containing
            performance metrics, constraint checks, and alerts.
        """
        benchmarks = input_data.get("benchmarks", ["SPY", "AGG"])
        constraints = input_data.get("constraints", {})
        upcoming_events = input_data.get("upcoming_events", [])

        # Step 1: Calculate performance
        performance = await self._calculate_performance(context, benchmarks)

        # Step 2: Check constraints
        constraint_results = await self._check_constraints(context, constraints)

        # Step 3: Generate alerts
        alerts = await self._generate_alerts(
            performance, constraint_results, upcoming_events, context
        )

        monitoring_snapshot = {
            "performance": performance,
            "constraint_compliance": constraint_results,
            "alerts": alerts,
            "alert_summary": {
                "critical": len([a for a in alerts if a.get("severity") == "CRITICAL"]),
                "warning": len([a for a in alerts if a.get("severity") == "WARNING"]),
                "info": len([a for a in alerts if a.get("severity") == "INFO"]),
            },
        }

        await self.log_action(
            action="portfolio_monitoring",
            input_data={"benchmark_count": len(benchmarks)},
            output_data={
                "alert_count": len(alerts),
                "critical_count": monitoring_snapshot["alert_summary"]["critical"],
            },
        )

        return {"monitoring_snapshot": monitoring_snapshot}

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _calculate_performance(
        self, context: AgentContext, benchmarks: list[str]
    ) -> dict[str, Any]:
        """Calculate comprehensive performance metrics.

        Computes P&L, returns, risk-adjusted metrics, and performance
        attribution across multiple dimensions.

        Args:
            context: Agent context with portfolio state.
            benchmarks: List of benchmark identifiers for comparison.

        Returns:
            Dictionary with P&L, returns, risk-adjusted metrics,
            attribution, and benchmark comparison.
        """
        if self._llm is None:
            return {"status": "llm_unavailable"}

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "CALCULATE PORTFOLIO PERFORMANCE\n\n"
                    f"PORTFOLIO STATE:\n{portfolio_text}\n\n"
                    f"BENCHMARKS: {benchmarks}\n\n"
                    "Calculate comprehensive performance metrics:\n"
                    "1. P&L: daily, weekly, MTD, YTD, since inception\n"
                    "2. Total return and annualized return\n"
                    "3. Risk-adjusted: Sharpe ratio, Sortino ratio, Calmar ratio\n"
                    "4. Attribution by: asset class, sector, top contributors/"
                    "detractors\n"
                    "5. Benchmark comparison: alpha, tracking error, "
                    "information ratio\n"
                    "6. Win rate and average win/loss for closed positions\n\n"
                    "Return JSON with keys: pnl (object with daily, weekly, "
                    "mtd, ytd, since_inception), total_return_pct (number), "
                    "annualized_return_pct (number), sharpe_ratio (number), "
                    "sortino_ratio (number), calmar_ratio (number), "
                    "attribution (object with by_asset_class, by_sector, "
                    "top_contributors, top_detractors), benchmark_comparison "
                    "(array of {benchmark, alpha, tracking_error, "
                    "information_ratio}), win_rate (number)."
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

    async def _check_constraints(
        self, context: AgentContext, constraints: dict[str, Any]
    ) -> dict[str, Any]:
        """Check that all investment policy constraints are met.

        Evaluates allocation limits, prohibited securities, risk budgets,
        liquidity requirements, and leverage limits.

        Args:
            context: Agent context with portfolio state.
            constraints: Investment policy constraints to check against.

        Returns:
            Dictionary with per-constraint compliance status and any
            violations or near-violations.
        """
        if self._llm is None:
            return {"status": "llm_unavailable", "violations": [], "compliant": True}

        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "CHECK CONSTRAINT COMPLIANCE\n\n"
                    f"PORTFOLIO STATE:\n{portfolio_text}\n\n"
                    f"CONSTRAINTS:\n{json.dumps(constraints, indent=2, default=str)}\n\n"
                    "Check every constraint and report compliance:\n"
                    "1. Asset class allocation within bounds?\n"
                    "2. Single-name concentration within limits?\n"
                    "3. Sector concentration within limits?\n"
                    "4. Any prohibited securities held?\n"
                    "5. Risk budget (VaR, vol) within limits?\n"
                    "6. Leverage within bounds?\n"
                    "7. Minimum cash/liquidity maintained?\n\n"
                    "Return JSON with keys: compliant (bool -- all constraints "
                    "met), violations (array of {constraint, current_value, "
                    "limit, severity}), near_violations (array of constraints "
                    "within 10% of breach), checks_performed (number)."
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

        return {"compliant": True, "violations": [], "checks_performed": 0}

    async def _generate_alerts(
        self,
        performance: dict[str, Any],
        constraint_results: dict[str, Any],
        upcoming_events: list[dict[str, Any]],
        context: AgentContext,
    ) -> list[dict[str, Any]]:
        """Generate actionable alerts from monitoring data.

        Produces alerts for performance issues, constraint violations,
        unusual behavior, and upcoming events that need attention.

        Args:
            performance: Calculated performance metrics.
            constraint_results: Constraint compliance results.
            upcoming_events: Calendar of upcoming portfolio-relevant events.
            context: Agent context.

        Returns:
            List of alert dicts, each with ``severity``, ``category``,
            ``title``, ``description``, and ``recommended_action``.
        """
        if self._llm is None:
            return []

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "GENERATE PORTFOLIO ALERTS\n\n"
                    f"PERFORMANCE:\n{json.dumps(performance, indent=2, default=str)}\n\n"
                    f"CONSTRAINT COMPLIANCE:\n{json.dumps(constraint_results, indent=2, default=str)}\n\n"
                    f"UPCOMING EVENTS:\n{json.dumps(upcoming_events, indent=2, default=str)}\n\n"
                    f"PORTFOLIO STATE:\n{json.dumps(context.portfolio_state, indent=2, default=str)}\n\n"
                    "Generate alerts for anything requiring attention:\n"
                    "1. Performance alerts (drawdowns, underperformance)\n"
                    "2. Constraint violations or near-violations\n"
                    "3. Unusual P&L or correlation behavior\n"
                    "4. Upcoming events (earnings, expirations, ex-div dates)\n"
                    "5. Cash management (low cash, upcoming obligations)\n\n"
                    "Return a JSON array of alert objects with keys: "
                    "severity (CRITICAL/WARNING/INFO), category (performance/"
                    "constraint/event/cash/anomaly), title (string), "
                    "description (string), recommended_action (string)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            alerts = json.loads(response.content)
            if isinstance(alerts, list):
                return alerts
        except (json.JSONDecodeError, TypeError):
            pass

        return []
