"""Portfolio Loop -- LangGraph orchestration for portfolio management.

This module implements the Portfolio Loop as a LangGraph StateGraph with four
primary nodes forming a continuous cycle:

    assess -> construct -> monitor_risk -> rebalance -> (back to assess)

The loop maintains the portfolio at the strategic level: it assesses the
current state, proposes allocation changes, monitors risk metrics, and
triggers rebalancing when drift exceeds thresholds.

The Portfolio Loop communicates with the Idea Loop via shared state:
``incoming_trades`` arrive from the idea loop's execution plans, and the
portfolio loop returns ``trade_approvals`` (with sizing adjustments) and
``risk_limits`` that constrain the idea loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.base import AgentContext
from src.agents.llm.router import llm_router
from src.agents.llm.base import LLMMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class PortfolioLoopState(TypedDict):
    """State shared across all nodes of the portfolio loop.

    This TypedDict defines every key that flows through the portfolio
    LangGraph StateGraph.
    """

    # -- Portfolio ---------------------------------------------------------
    portfolio: dict
    positions: list[dict]
    preferences: dict  # user goals, risk appetite, views

    # -- Assessment --------------------------------------------------------
    current_allocation: dict
    target_allocation: dict
    drift: dict

    # -- Risk --------------------------------------------------------------
    risk_metrics: dict
    risk_alerts: list[dict]

    # -- Rebalancing -------------------------------------------------------
    rebalance_needed: bool
    rebalance_trades: list[dict]

    # -- Market outlook (from knowledge layer) -----------------------------
    market_outlook: dict  # long / mid / short term views

    # -- From idea loop ----------------------------------------------------
    incoming_trades: list[dict]  # new trades from idea loop needing check
    trade_approvals: list[dict]

    # -- Agent messages ----------------------------------------------------
    agent_messages: list[dict]

    # -- Control -----------------------------------------------------------
    iteration: int
    should_continue: bool


# ---------------------------------------------------------------------------
# Default / empty state factory
# ---------------------------------------------------------------------------

def _default_portfolio_loop_state() -> PortfolioLoopState:
    """Return a minimal valid initial state for the portfolio loop."""
    return PortfolioLoopState(
        portfolio={},
        positions=[],
        preferences={},
        current_allocation={},
        target_allocation={},
        drift={},
        risk_metrics={},
        risk_alerts=[],
        rebalance_needed=False,
        rebalance_trades=[],
        market_outlook={},
        incoming_trades=[],
        trade_approvals=[],
        agent_messages=[],
        iteration=0,
        should_continue=True,
    )


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

async def assess_node(state: PortfolioLoopState) -> dict[str, Any]:
    """Node: assess current portfolio state and compute allocation drift.

    In the full system the ``PortfolioConstructorAgent`` performs deep
    portfolio analytics -- factor exposures, sector breakdowns, liquidity
    profiling, and correlation analysis.  For the prototype we compute basic
    allocation percentages and drift from target.
    """
    portfolio = state.get("portfolio", {})
    positions = state.get("positions", [])
    preferences = state.get("preferences", {})

    logger.info(
        "Portfolio Loop [assess] -- iteration %s, %d positions",
        state.get("iteration", 0),
        len(positions),
    )

    total_value = portfolio.get("total_value", 0.0)

    # -- Compute current allocation by asset class -------------------------
    current_allocation: dict[str, float] = {}
    if total_value > 0:
        for pos in positions:
            asset_class = pos.get("asset_class", "other")
            market_value = pos.get("market_value", 0.0)
            current_allocation[asset_class] = (
                current_allocation.get(asset_class, 0.0) + market_value
            )
        # Convert to percentages
        current_allocation = {
            k: round(v / total_value * 100, 2)
            for k, v in current_allocation.items()
        }

    # -- Determine target allocation ---------------------------------------
    # Use user preferences if available, otherwise apply a sensible default
    target_allocation = preferences.get("target_allocation", {})
    if not target_allocation:
        risk_appetite = preferences.get("risk_appetite", "moderate")
        target_allocation = _default_target_allocation(risk_appetite)

    # -- Compute drift -----------------------------------------------------
    drift: dict[str, float] = {}
    all_classes = set(list(current_allocation.keys()) + list(target_allocation.keys()))
    for ac in all_classes:
        current_pct = current_allocation.get(ac, 0.0)
        target_pct = target_allocation.get(ac, 0.0)
        drift[ac] = round(current_pct - target_pct, 2)

    # -- Optionally use LLM for deeper assessment -------------------------
    assessment_notes = ""
    if positions and total_value > 0:
        try:
            llm = llm_router.get_provider()
            assessment_prompt = (
                "You are a portfolio analyst.  Given the following portfolio "
                "summary, provide a brief (2-3 sentence) assessment of the "
                "current positioning and any concerns.\n\n"
                f"Total value: ${total_value:,.2f}\n"
                f"Current allocation: {current_allocation}\n"
                f"Target allocation: {target_allocation}\n"
                f"Drift: {drift}\n"
                f"Number of positions: {len(positions)}\n"
                f"Risk appetite: {preferences.get('risk_appetite', 'moderate')}"
            )
            response = await llm.chat(
                messages=[LLMMessage(role="user", content=assessment_prompt)],
                temperature=0.3,
                max_tokens=512,
            )
            assessment_notes = response.content
        except Exception:
            logger.debug("LLM assessment skipped", exc_info=True)

    return {
        "current_allocation": current_allocation,
        "target_allocation": target_allocation,
        "drift": drift,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "PortfolioConstructor",
                "node": "assess",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Assessed portfolio: {len(positions)} positions, "
                    f"max drift {_max_abs_drift(drift):.1f}%"
                ),
                "notes": assessment_notes,
            }
        ],
    }


async def construct_node(state: PortfolioLoopState) -> dict[str, Any]:
    """Node: propose allocation changes and process incoming trades.

    Reviews incoming trades from the idea loop against portfolio constraints
    (concentration limits, correlation, sector exposure) and either approves,
    adjusts, or rejects them.  Also proposes target allocation changes based
    on market outlook and user preferences.
    """
    incoming_trades = state.get("incoming_trades", [])
    current_allocation = state.get("current_allocation", {})
    target_allocation = state.get("target_allocation", {})
    preferences = state.get("preferences", {})
    market_outlook = state.get("market_outlook", {})
    portfolio = state.get("portfolio", {})
    positions = state.get("positions", [])

    logger.info(
        "Portfolio Loop [construct] -- %d incoming trades to review",
        len(incoming_trades),
    )

    # -- Review incoming trades from idea loop -----------------------------
    trade_approvals: list[dict] = []
    total_value = portfolio.get("total_value", 100_000)
    max_single_position_pct = preferences.get("max_single_position_pct", 5.0)
    max_sector_concentration = preferences.get("max_sector_concentration_pct", 25.0)

    # Build sector exposure map from current positions
    sector_exposure: dict[str, float] = {}
    for pos in positions:
        sector = pos.get("sector", pos.get("asset_class", "other"))
        mv = pos.get("market_value", 0.0)
        sector_exposure[sector] = sector_exposure.get(sector, 0.0) + mv

    for trade in incoming_trades:
        approval: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "trade_plan_id": trade.get("id"),
            "idea_title": trade.get("idea_title", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        reject_reasons: list[str] = []
        adjustments: dict[str, Any] = {}

        # Check single position concentration
        target_pct = trade.get("target_allocation_pct", 0.0)
        if target_pct > max_single_position_pct:
            adjustments["target_allocation_pct"] = max_single_position_pct
            adjustments["target_notional"] = round(
                total_value * max_single_position_pct / 100, 2
            )
            adjustments["reason"] = (
                f"Sized down from {target_pct:.1f}% to "
                f"{max_single_position_pct:.1f}% (concentration limit)"
            )

        # Check sector concentration
        trade_sector = trade.get("asset_class", "other")
        existing_sector_pct = (
            sector_exposure.get(trade_sector, 0.0) / total_value * 100
            if total_value > 0
            else 0.0
        )
        new_sector_pct = existing_sector_pct + trade.get(
            "target_allocation_pct", 0.0
        )
        if new_sector_pct > max_sector_concentration:
            remaining_room = max(
                0, max_sector_concentration - existing_sector_pct
            )
            if remaining_room < 1.0:
                reject_reasons.append(
                    f"Sector {trade_sector} at {existing_sector_pct:.1f}% "
                    f"exceeds {max_sector_concentration:.1f}% limit"
                )
            else:
                adjustments["target_allocation_pct"] = round(remaining_room, 2)
                adjustments["target_notional"] = round(
                    total_value * remaining_room / 100, 2
                )
                adjustments.setdefault("reason", "")
                adjustments["reason"] += (
                    f"; sector-capped to {remaining_room:.1f}%"
                )

        if reject_reasons:
            approval["status"] = "rejected"
            approval["reasons"] = reject_reasons
        elif adjustments:
            approval["status"] = "approved_with_adjustments"
            approval["adjustments"] = adjustments
        else:
            approval["status"] = "approved"

        trade_approvals.append(approval)

    # -- Propose target allocation updates based on outlook ----------------
    updated_target = dict(target_allocation)
    if market_outlook:
        updated_target = _adjust_target_for_outlook(
            target_allocation, market_outlook, preferences
        )

    return {
        "trade_approvals": state.get("trade_approvals", []) + trade_approvals,
        "target_allocation": updated_target,
        "incoming_trades": [],  # clear processed trades
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "PortfolioConstructor",
                "node": "construct",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Reviewed {len(incoming_trades)} incoming trades: "
                    f"{sum(1 for a in trade_approvals if a.get('status') == 'approved')} approved, "
                    f"{sum(1 for a in trade_approvals if 'adjustment' in a.get('status', ''))} adjusted, "
                    f"{sum(1 for a in trade_approvals if a.get('status') == 'rejected')} rejected"
                ),
            }
        ],
    }


async def monitor_risk_node(state: PortfolioLoopState) -> dict[str, Any]:
    """Node: monitor portfolio risk metrics and generate alerts.

    In the full system the ``RiskManagerAgent`` computes VaR, expected
    shortfall, factor exposures, Greeks, correlation matrices, and stress
    tests.  For the prototype we compute simplified risk metrics and check
    them against thresholds.
    """
    portfolio = state.get("portfolio", {})
    positions = state.get("positions", [])
    preferences = state.get("preferences", {})
    current_allocation = state.get("current_allocation", {})
    drift = state.get("drift", {})

    logger.info(
        "Portfolio Loop [monitor_risk] -- computing risk metrics for %d positions",
        len(positions),
    )

    total_value = portfolio.get("total_value", 0.0)
    risk_appetite = preferences.get("risk_appetite", "moderate")

    # -- Compute risk metrics (simplified) ---------------------------------
    risk_metrics: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_value": total_value,
        "position_count": len(positions),
        "risk_appetite": risk_appetite,
    }

    # Portfolio concentration (Herfindahl index)
    if positions and total_value > 0:
        weights = [
            (pos.get("market_value", 0.0) / total_value) ** 2
            for pos in positions
        ]
        hhi = sum(weights)
        risk_metrics["herfindahl_index"] = round(hhi, 4)
        risk_metrics["effective_positions"] = (
            round(1.0 / hhi, 1) if hhi > 0 else 0
        )
    else:
        risk_metrics["herfindahl_index"] = 0.0
        risk_metrics["effective_positions"] = 0

    # Maximum single-position weight
    if positions and total_value > 0:
        max_weight = max(
            pos.get("market_value", 0.0) / total_value for pos in positions
        )
        risk_metrics["max_position_weight_pct"] = round(max_weight * 100, 2)
    else:
        risk_metrics["max_position_weight_pct"] = 0.0

    # Maximum allocation drift
    risk_metrics["max_allocation_drift_pct"] = _max_abs_drift(drift)

    # Aggregate unrealized P&L
    total_pnl = sum(pos.get("unrealized_pnl", 0.0) for pos in positions)
    risk_metrics["total_unrealized_pnl"] = round(total_pnl, 2)
    if total_value > 0:
        risk_metrics["total_unrealized_pnl_pct"] = round(
            total_pnl / total_value * 100, 2
        )
    else:
        risk_metrics["total_unrealized_pnl_pct"] = 0.0

    # -- Generate risk alerts ---------------------------------------------
    alerts: list[dict] = []
    thresholds = _risk_thresholds(risk_appetite)

    # Concentration alert
    if risk_metrics["max_position_weight_pct"] > thresholds["max_position_pct"]:
        alerts.append({
            "id": str(uuid.uuid4()),
            "type": "concentration",
            "severity": "warning",
            "message": (
                f"Largest position is "
                f"{risk_metrics['max_position_weight_pct']:.1f}% of portfolio "
                f"(limit: {thresholds['max_position_pct']:.1f}%)"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Drift alert
    if risk_metrics["max_allocation_drift_pct"] > thresholds["max_drift_pct"]:
        alerts.append({
            "id": str(uuid.uuid4()),
            "type": "allocation_drift",
            "severity": "warning",
            "message": (
                f"Maximum allocation drift is "
                f"{risk_metrics['max_allocation_drift_pct']:.1f}% "
                f"(threshold: {thresholds['max_drift_pct']:.1f}%)"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Drawdown alert
    if risk_metrics["total_unrealized_pnl_pct"] < -thresholds["max_drawdown_pct"]:
        alerts.append({
            "id": str(uuid.uuid4()),
            "type": "drawdown",
            "severity": "critical",
            "message": (
                f"Portfolio drawdown "
                f"{risk_metrics['total_unrealized_pnl_pct']:.1f}% "
                f"exceeds limit of -{thresholds['max_drawdown_pct']:.1f}%"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # Under-diversification alert
    if (
        risk_metrics["effective_positions"] > 0
        and risk_metrics["effective_positions"] < thresholds["min_effective_positions"]
    ):
        alerts.append({
            "id": str(uuid.uuid4()),
            "type": "diversification",
            "severity": "info",
            "message": (
                f"Effective positions ({risk_metrics['effective_positions']:.0f}) "
                f"below recommended minimum "
                f"({thresholds['min_effective_positions']})"
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    logger.info(
        "Portfolio Loop [monitor_risk] -- %d risk alerts generated",
        len(alerts),
    )

    return {
        "risk_metrics": risk_metrics,
        "risk_alerts": state.get("risk_alerts", []) + alerts,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "RiskManager",
                "node": "monitor_risk",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Risk check: HHI={risk_metrics.get('herfindahl_index', 0):.4f}, "
                    f"max drift={risk_metrics['max_allocation_drift_pct']:.1f}%, "
                    f"{len(alerts)} alerts"
                ),
            }
        ],
    }


async def rebalance_node(state: PortfolioLoopState) -> dict[str, Any]:
    """Node: determine if rebalancing is needed and propose trades.

    In the full system the ``RebalancerAgent`` uses an optimiser to compute
    the minimum-transaction-cost set of trades to bring the portfolio back to
    target.  For the prototype we propose simple proportional adjustments.
    """
    drift = state.get("drift", {})
    current_allocation = state.get("current_allocation", {})
    target_allocation = state.get("target_allocation", {})
    portfolio = state.get("portfolio", {})
    preferences = state.get("preferences", {})
    risk_alerts = state.get("risk_alerts", [])

    logger.info("Portfolio Loop [rebalance] -- evaluating rebalance need")

    total_value = portfolio.get("total_value", 0.0)
    risk_appetite = preferences.get("risk_appetite", "moderate")
    thresholds = _risk_thresholds(risk_appetite)
    rebalance_trigger_pct = thresholds.get("rebalance_trigger_pct", 5.0)

    # -- Determine if rebalance is needed ----------------------------------
    max_drift = _max_abs_drift(drift)
    has_critical_alerts = any(
        a.get("severity") == "critical" for a in risk_alerts
    )
    rebalance_needed = max_drift > rebalance_trigger_pct or has_critical_alerts

    rebalance_trades: list[dict] = []

    if rebalance_needed and total_value > 0:
        logger.info(
            "Portfolio Loop [rebalance] -- rebalance triggered "
            "(max_drift=%.1f%%, critical_alerts=%s)",
            max_drift,
            has_critical_alerts,
        )

        # Compute rebalance trades
        for asset_class, drift_pct in drift.items():
            if abs(drift_pct) < 1.0:
                # Skip negligible drift
                continue

            trade_notional = abs(drift_pct) / 100 * total_value
            direction = "sell" if drift_pct > 0 else "buy"

            rebalance_trades.append({
                "id": str(uuid.uuid4()),
                "type": "rebalance",
                "asset_class": asset_class,
                "direction": direction,
                "notional": round(trade_notional, 2),
                "drift_pct": drift_pct,
                "from_allocation_pct": current_allocation.get(asset_class, 0.0),
                "to_allocation_pct": target_allocation.get(asset_class, 0.0),
                "status": "pending_approval",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        # Use LLM to sanity-check and annotate the rebalance proposal
        if rebalance_trades:
            try:
                llm = llm_router.get_provider()
                rebalance_prompt = (
                    "You are a portfolio manager reviewing a proposed rebalance. "
                    "Given the following trades, provide a brief (2-3 sentence) "
                    "rationale and flag any concerns. Reply as plain text.\n\n"
                    f"Current allocation: {current_allocation}\n"
                    f"Target allocation: {target_allocation}\n"
                    f"Drift: {drift}\n"
                    f"Proposed trades: {rebalance_trades}\n"
                    f"Risk appetite: {risk_appetite}"
                )
                response = await llm.chat(
                    messages=[LLMMessage(role="user", content=rebalance_prompt)],
                    temperature=0.3,
                    max_tokens=512,
                )
                for trade in rebalance_trades:
                    trade["llm_rationale"] = response.content
            except Exception:
                logger.debug("LLM rebalance review skipped", exc_info=True)

    else:
        logger.info(
            "Portfolio Loop [rebalance] -- no rebalance needed "
            "(max_drift=%.1f%%, trigger=%.1f%%)",
            max_drift,
            rebalance_trigger_pct,
        )

    # Increment iteration counter
    current_iteration = state.get("iteration", 0)

    return {
        "rebalance_needed": rebalance_needed,
        "rebalance_trades": rebalance_trades,
        "iteration": current_iteration + 1,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "Rebalancer",
                "node": "rebalance",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Rebalance {'triggered' if rebalance_needed else 'not needed'}: "
                    f"{len(rebalance_trades)} trades proposed"
                ),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def _should_continue_loop(state: PortfolioLoopState) -> str:
    """After rebalancing, decide whether to loop back or stop.

    Returns:
        ``"assess"`` to continue the cycle, or ``"__end__"`` to stop.
    """
    if not state.get("should_continue", True):
        return END
    return "assess"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_portfolio_loop_graph() -> StateGraph:
    """Build and compile the Portfolio Loop as a LangGraph StateGraph.

    The graph has the following topology::

        assess -> construct -> monitor_risk -> rebalance
                                                  |
                                           [conditional]
                                           /           \\
                                        assess          END

    Returns:
        A compiled LangGraph ``StateGraph`` ready to be invoked.
    """
    graph = StateGraph(PortfolioLoopState)

    # -- Register nodes ----------------------------------------------------
    graph.add_node("assess", assess_node)
    graph.add_node("construct", construct_node)
    graph.add_node("monitor_risk", monitor_risk_node)
    graph.add_node("rebalance", rebalance_node)

    # -- Set entry point ---------------------------------------------------
    graph.set_entry_point("assess")

    # -- Linear edges ------------------------------------------------------
    graph.add_edge("assess", "construct")
    graph.add_edge("construct", "monitor_risk")
    graph.add_edge("monitor_risk", "rebalance")

    # -- Conditional: rebalance -> assess (loop) | END ---------------------
    graph.add_conditional_edges(
        "rebalance",
        _should_continue_loop,
        {
            "assess": "assess",
            END: END,
        },
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Convenience runners
# ---------------------------------------------------------------------------

async def run_portfolio_loop(initial_state: dict | None = None) -> dict:
    """Run a single iteration of the portfolio loop.

    This is a convenience wrapper that builds the graph, merges the provided
    state with sensible defaults, sets ``should_continue=False`` so the loop
    executes exactly one cycle, and returns the final state.

    Args:
        initial_state: Partial state dict.  Missing keys are filled with
            defaults.

    Returns:
        The final ``PortfolioLoopState`` after one full iteration.
    """
    graph = build_portfolio_loop_graph()

    state = _default_portfolio_loop_state()
    if initial_state:
        state.update(initial_state)

    # Force single iteration
    state["should_continue"] = False

    result = await graph.ainvoke(state)
    return result


async def run_continuous_portfolio_loop(
    interval_seconds: int = 300,
    initial_state: dict | None = None,
    on_iteration: Any | None = None,
) -> None:
    """Run the portfolio loop continuously with a delay between iterations.

    The portfolio loop typically runs less frequently than the idea loop
    (e.g. every 5 minutes vs every 1 minute) because portfolio-level
    decisions are inherently slower.

    Args:
        interval_seconds: Seconds to sleep between iterations (default 300).
        initial_state: Initial state dict.
        on_iteration: Optional async callback ``(state) -> state`` invoked
            after each iteration, allowing the coordinator to inject fresh
            data or modify control flags.
    """
    graph = build_portfolio_loop_graph()

    state = _default_portfolio_loop_state()
    if initial_state:
        state.update(initial_state)

    state["should_continue"] = True
    iteration = 0

    logger.info(
        "Starting continuous portfolio loop with %ds interval",
        interval_seconds,
    )

    while state.get("should_continue", True):
        iteration += 1
        state["iteration"] = iteration
        # Each invocation should stop after one cycle so we can sleep
        state["should_continue"] = False

        logger.info("Portfolio Loop -- starting iteration %d", iteration)

        try:
            state = await graph.ainvoke(state)
        except Exception:
            logger.exception("Portfolio loop iteration %d failed", iteration)

        # Allow coordinator to inject data / flip control flags
        if on_iteration is not None:
            state = await on_iteration(state)

        # Re-enable loop unless the callback disabled it
        if state.get("should_continue", True) is not False:
            state["should_continue"] = True
        else:
            logger.info(
                "Portfolio loop stopped by callback after iteration %d",
                iteration,
            )
            break

        # Reset should_continue for next graph invocation
        state["should_continue"] = True

        await asyncio.sleep(interval_seconds)

    logger.info(
        "Continuous portfolio loop exited after %d iterations", iteration
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _max_abs_drift(drift: dict[str, float]) -> float:
    """Return the maximum absolute drift across all asset classes."""
    if not drift:
        return 0.0
    return max(abs(v) for v in drift.values())


def _default_target_allocation(risk_appetite: str) -> dict[str, float]:
    """Return a default target allocation based on risk appetite.

    These are illustrative allocations for a balanced multi-asset portfolio.

    Args:
        risk_appetite: One of ``"conservative"``, ``"moderate"``,
            ``"aggressive"``.

    Returns:
        Dict mapping asset class names to target percentage weights.
    """
    allocations = {
        "conservative": {
            "equity": 30.0,
            "fixed_income": 45.0,
            "commodity": 5.0,
            "cash": 15.0,
            "alternative": 5.0,
        },
        "moderate": {
            "equity": 50.0,
            "fixed_income": 25.0,
            "commodity": 10.0,
            "cash": 5.0,
            "alternative": 10.0,
        },
        "aggressive": {
            "equity": 70.0,
            "fixed_income": 5.0,
            "commodity": 10.0,
            "cash": 0.0,
            "alternative": 15.0,
        },
    }
    return allocations.get(risk_appetite, allocations["moderate"])


def _risk_thresholds(risk_appetite: str) -> dict[str, float]:
    """Return risk thresholds calibrated to the user's risk appetite.

    Args:
        risk_appetite: One of ``"conservative"``, ``"moderate"``,
            ``"aggressive"``.

    Returns:
        Dict with threshold values for various risk metrics.
    """
    thresholds = {
        "conservative": {
            "max_position_pct": 5.0,
            "max_drift_pct": 3.0,
            "max_drawdown_pct": 5.0,
            "min_effective_positions": 15,
            "rebalance_trigger_pct": 3.0,
        },
        "moderate": {
            "max_position_pct": 10.0,
            "max_drift_pct": 5.0,
            "max_drawdown_pct": 10.0,
            "min_effective_positions": 10,
            "rebalance_trigger_pct": 5.0,
        },
        "aggressive": {
            "max_position_pct": 20.0,
            "max_drift_pct": 10.0,
            "max_drawdown_pct": 20.0,
            "min_effective_positions": 5,
            "rebalance_trigger_pct": 10.0,
        },
    }
    return thresholds.get(risk_appetite, thresholds["moderate"])


def _adjust_target_for_outlook(
    current_target: dict[str, float],
    outlook: dict[str, Any],
    preferences: dict[str, Any],
) -> dict[str, float]:
    """Adjust target allocation based on market outlook.

    Applies tactical tilts to the strategic allocation based on the
    knowledge layer's market outlook.  Tilts are bounded to prevent
    excessive deviation from the strategic target.

    Args:
        current_target: Current target allocation percentages.
        outlook: Market outlook dict with keys like ``short_term``,
            ``mid_term``, ``long_term``, each containing sentiment scores.
        preferences: User preferences including max tilt constraints.

    Returns:
        Adjusted target allocation percentages (sums to ~100%).
    """
    adjusted = dict(current_target)
    max_tilt = preferences.get("max_tactical_tilt_pct", 5.0)

    # Short-term outlook tilts
    short_term = outlook.get("short_term", {})
    equity_sentiment = short_term.get("equity_sentiment", 0.0)

    # Positive sentiment -> tilt toward equity, away from fixed income
    if abs(equity_sentiment) > 0.2:
        tilt = min(abs(equity_sentiment) * max_tilt, max_tilt)
        if equity_sentiment > 0:
            adjusted["equity"] = adjusted.get("equity", 0.0) + tilt
            adjusted["fixed_income"] = max(
                0, adjusted.get("fixed_income", 0.0) - tilt
            )
        else:
            adjusted["equity"] = max(
                0, adjusted.get("equity", 0.0) - tilt
            )
            adjusted["fixed_income"] = adjusted.get("fixed_income", 0.0) + tilt

    # Normalize to sum to 100%
    total = sum(adjusted.values())
    if total > 0 and abs(total - 100.0) > 0.01:
        factor = 100.0 / total
        adjusted = {k: round(v * factor, 2) for k, v in adjusted.items()}

    return adjusted
