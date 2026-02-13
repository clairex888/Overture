"""Idea Loop -- LangGraph orchestration for the investment idea pipeline.

This module implements the Idea Loop as a LangGraph StateGraph with four
primary nodes forming a continuous cycle:

    generate -> validate -> execute -> monitor -> (back to generate)

The loop ingests data from news, market feeds, social signals, and
quantitative screens.  It produces investment ideas, validates them, creates
execution plans (with human-in-the-loop approval gates), and monitors active
trades for exit signals or risk events.

The Idea Loop communicates with the Portfolio Loop via shared state:
execution plans are forwarded as ``incoming_trades`` for portfolio-level
checks, and portfolio-level risk limits / approvals flow back to constrain
idea execution.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.base import AgentContext
from src.agents.idea.generator import IdeaGeneratorAgent
from src.agents.llm.router import llm_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class IdeaLoopState(TypedDict):
    """State shared across all nodes of the idea loop.

    This TypedDict defines every key that flows through the LangGraph
    StateGraph.  Each node function receives the full state and returns a
    partial dictionary of the keys it wants to update.
    """

    # -- Input data --------------------------------------------------------
    news_items: list[dict]
    market_data: dict
    social_signals: list[dict]
    screen_results: list[dict]

    # -- Generated ideas ---------------------------------------------------
    raw_ideas: list[dict]
    validated_ideas: list[dict]
    rejected_ideas: list[dict]

    # -- Execution ---------------------------------------------------------
    execution_plans: list[dict]
    pending_approval: list[dict]

    # -- Active trades -----------------------------------------------------
    active_trades: list[dict]
    trade_alerts: list[dict]

    # -- Portfolio context (injected from the portfolio loop) ---------------
    portfolio_state: dict
    risk_limits: dict

    # -- Agent messages and coordination -----------------------------------
    agent_messages: list[dict]

    # -- Loop control ------------------------------------------------------
    iteration: int
    should_continue: bool


# ---------------------------------------------------------------------------
# Default / empty state factory
# ---------------------------------------------------------------------------

def _default_idea_loop_state() -> IdeaLoopState:
    """Return a minimal valid initial state for the idea loop."""
    return IdeaLoopState(
        news_items=[],
        market_data={},
        social_signals=[],
        screen_results=[],
        raw_ideas=[],
        validated_ideas=[],
        rejected_ideas=[],
        execution_plans=[],
        pending_approval=[],
        active_trades=[],
        trade_alerts=[],
        portfolio_state={},
        risk_limits={},
        agent_messages=[],
        iteration=0,
        should_continue=True,
    )


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

async def generate_node(state: IdeaLoopState) -> dict[str, Any]:
    """Node: generate investment ideas from data sources.

    Creates an ``IdeaGeneratorAgent``, feeds it the current data sources,
    and returns the raw ideas it produces.  The agent is given an LLM
    provider via the router so that it can call the appropriate model.
    """
    logger.info(
        "Idea Loop [generate] -- iteration %s, sources: news=%d market=%s social=%d screens=%d",
        state.get("iteration", 0),
        len(state.get("news_items", [])),
        bool(state.get("market_data")),
        len(state.get("social_signals", [])),
        len(state.get("screen_results", [])),
    )

    agent = IdeaGeneratorAgent()
    agent._llm = llm_router.get_provider()

    context = AgentContext(
        portfolio_state=state.get("portfolio_state", {}),
        market_context=state.get("market_data", {}),
    )

    input_data = {
        "news_items": state.get("news_items", []),
        "market_data": state.get("market_data", {}),
        "social_signals": state.get("social_signals", []),
        "screen_config": (
            {"results": state["screen_results"]}
            if state.get("screen_results")
            else {}
        ),
    }

    try:
        result = await agent.execute(input_data, context)
        raw_ideas = result.get("ideas", [])
    except Exception:
        logger.exception("IdeaGeneratorAgent failed")
        raw_ideas = []

    # Stamp each idea with metadata
    for idea in raw_ideas:
        idea.setdefault("id", str(uuid.uuid4()))
        idea.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        idea.setdefault("status", "raw")

    return {
        "raw_ideas": raw_ideas,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "IdeaGenerator",
                "node": "generate",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": f"Generated {len(raw_ideas)} raw ideas",
            }
        ],
    }


async def validate_node(state: IdeaLoopState) -> dict[str, Any]:
    """Node: validate and filter raw ideas.

    In the full system the ``IdeaValidatorAgent`` performs deep due-diligence
    on each raw idea -- cross-referencing fundamentals, checking for
    conflicting positions, and scoring risk/reward.  For the prototype we
    apply a confidence-threshold heuristic and delegate to the LLM for a
    quick sanity check.
    """
    raw_ideas = state.get("raw_ideas", [])
    risk_limits = state.get("risk_limits", {})
    portfolio_state = state.get("portfolio_state", {})

    logger.info(
        "Idea Loop [validate] -- %d raw ideas to validate",
        len(raw_ideas),
    )

    if not raw_ideas:
        return {
            "validated_ideas": [],
            "rejected_ideas": [],
            "agent_messages": state.get("agent_messages", []) + [
                {
                    "agent": "IdeaValidator",
                    "node": "validate",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": "No raw ideas to validate",
                }
            ],
        }

    # -- Prototype validation logic ----------------------------------------
    # A production system would instantiate an IdeaValidatorAgent here and
    # call agent.execute() with the LLM.  For now we apply rule-based
    # filtering plus an LLM sanity-check pass.

    validated: list[dict] = []
    rejected: list[dict] = []

    min_confidence = risk_limits.get("min_idea_confidence", 0.3)
    max_position_count = risk_limits.get("max_positions", 50)
    current_position_count = len(portfolio_state.get("positions", []))

    # Check if we have room for new positions
    position_room = max_position_count - current_position_count

    for idea in raw_ideas:
        reject_reasons: list[str] = []

        # Confidence gate
        confidence = idea.get("confidence", 0.0)
        if confidence < min_confidence:
            reject_reasons.append(
                f"Confidence {confidence:.2f} below threshold {min_confidence:.2f}"
            )

        # Check for blacklisted tickers
        blacklist = set(risk_limits.get("ticker_blacklist", []))
        idea_tickers = set(idea.get("tickers", []))
        blocked = idea_tickers & blacklist
        if blocked:
            reject_reasons.append(f"Tickers {blocked} are blacklisted")

        # Check for restricted asset classes
        restricted_classes = set(risk_limits.get("restricted_asset_classes", []))
        if idea.get("asset_class") in restricted_classes:
            reject_reasons.append(
                f"Asset class {idea.get('asset_class')} is restricted"
            )

        # Position capacity check
        if position_room <= 0 and not reject_reasons:
            reject_reasons.append("Portfolio at maximum position count")

        if reject_reasons:
            idea["status"] = "rejected"
            idea["reject_reasons"] = reject_reasons
            rejected.append(idea)
        else:
            idea["status"] = "validated"
            idea["validated_at"] = datetime.now(timezone.utc).isoformat()
            validated.append(idea)
            position_room -= 1  # optimistically reserve a slot

    # Optionally run an LLM sanity-check on validated ideas
    if validated:
        try:
            llm = llm_router.get_provider()
            from src.agents.llm.base import LLMMessage

            sanity_prompt = (
                "You are a senior portfolio manager reviewing the following "
                "investment ideas that passed initial screening.  For each idea, "
                "reply with a JSON array of objects containing the idea 'id' and "
                "a boolean 'pass' (true if the idea is reasonable, false if it "
                "has obvious flaws).  Be concise.\n\n"
                f"IDEAS:\n{_truncate_json(validated, max_chars=6000)}\n\n"
                f"PORTFOLIO CONTEXT:\n{_truncate_json(portfolio_state, max_chars=2000)}"
            )
            response = await llm.chat(
                messages=[LLMMessage(role="user", content=sanity_prompt)],
                temperature=0.2,
                max_tokens=2048,
            )

            import json
            try:
                sanity_results = json.loads(response.content)
                if isinstance(sanity_results, list):
                    failed_ids = {
                        r["id"]
                        for r in sanity_results
                        if not r.get("pass", True) and "id" in r
                    }
                    if failed_ids:
                        newly_rejected = [
                            i for i in validated if i.get("id") in failed_ids
                        ]
                        for r in newly_rejected:
                            r["status"] = "rejected"
                            r["reject_reasons"] = ["Failed LLM sanity check"]
                        rejected.extend(newly_rejected)
                        validated = [
                            i for i in validated if i.get("id") not in failed_ids
                        ]
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.debug("LLM sanity check returned unparseable response")
        except Exception:
            logger.debug("LLM sanity check skipped due to error", exc_info=True)

    logger.info(
        "Idea Loop [validate] -- validated=%d rejected=%d",
        len(validated),
        len(rejected),
    )

    return {
        "validated_ideas": validated,
        "rejected_ideas": state.get("rejected_ideas", []) + rejected,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "IdeaValidator",
                "node": "validate",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Validated {len(validated)} ideas, "
                    f"rejected {len(rejected)} ideas"
                ),
            }
        ],
    }


async def execute_node(state: IdeaLoopState) -> dict[str, Any]:
    """Node: create execution plans for validated ideas.

    In the full system the ``TradeExecutorAgent`` determines optimal order
    types, sizing, timing, and venue selection.  For the prototype we
    construct structured execution plans and route them through the approval
    gate.
    """
    validated_ideas = state.get("validated_ideas", [])
    portfolio_state = state.get("portfolio_state", {})
    risk_limits = state.get("risk_limits", {})

    logger.info(
        "Idea Loop [execute] -- %d validated ideas to plan",
        len(validated_ideas),
    )

    if not validated_ideas:
        return {
            "execution_plans": [],
            "pending_approval": state.get("pending_approval", []),
            "agent_messages": state.get("agent_messages", []) + [
                {
                    "agent": "TradeExecutor",
                    "node": "execute",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": "No validated ideas to execute",
                }
            ],
        }

    # -- Build execution plans ---------------------------------------------
    execution_plans: list[dict] = []
    needs_approval: list[dict] = []

    # Position sizing parameters
    max_single_position_pct = risk_limits.get("max_single_position_pct", 0.05)
    portfolio_value = portfolio_state.get("total_value", 100_000)

    for idea in validated_ideas:
        plan_id = str(uuid.uuid4())

        # Determine basic sizing
        confidence = idea.get("confidence", 0.5)
        # Size proportional to confidence, capped at max single position
        target_pct = min(confidence * 0.10, max_single_position_pct)
        target_notional = portfolio_value * target_pct

        plan = {
            "id": plan_id,
            "idea_id": idea.get("id"),
            "idea_title": idea.get("title", "Untitled"),
            "tickers": idea.get("tickers", []),
            "asset_class": idea.get("asset_class", "equity"),
            "direction": "long",  # default; a smarter agent would infer
            "timeframe": idea.get("timeframe", "swing"),
            "target_allocation_pct": round(target_pct * 100, 2),
            "target_notional": round(target_notional, 2),
            "order_type": "limit",
            "urgency": _classify_urgency(idea),
            "stop_loss_pct": _default_stop_loss(idea),
            "take_profit_pct": _default_take_profit(idea),
            "thesis": idea.get("thesis", ""),
            "risks": idea.get("risks", []),
            "status": "pending_approval",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        execution_plans.append(plan)

        # Auto-approve small / low-risk trades; require human approval for
        # larger ones.
        auto_approve_threshold = risk_limits.get(
            "auto_approve_notional", 5_000
        )
        if target_notional <= auto_approve_threshold:
            plan["status"] = "approved_auto"
        else:
            needs_approval.append(plan)

    logger.info(
        "Idea Loop [execute] -- created %d plans, %d need approval",
        len(execution_plans),
        len(needs_approval),
    )

    return {
        "execution_plans": execution_plans,
        "pending_approval": state.get("pending_approval", []) + needs_approval,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "TradeExecutor",
                "node": "execute",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Created {len(execution_plans)} execution plans, "
                    f"{len(needs_approval)} awaiting human approval"
                ),
            }
        ],
    }


async def await_approval_node(state: IdeaLoopState) -> dict[str, Any]:
    """Node: pause and surface items that require human approval.

    This node does not block indefinitely -- it simply marks the items as
    awaiting approval and returns.  The coordinator is responsible for
    collecting approvals asynchronously and injecting them back into the
    state before the next iteration.
    """
    pending = state.get("pending_approval", [])

    logger.info(
        "Idea Loop [await_approval] -- %d items awaiting human decision",
        len(pending),
    )

    # In a real system this would publish to a queue or websocket.
    # For the prototype we simply pass through -- the coordinator polls
    # ``pending_approval`` and surfaces it to the UI.
    return {
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "ApprovalGate",
                "node": "await_approval",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": f"{len(pending)} items awaiting human approval",
            }
        ],
    }


async def monitor_node(state: IdeaLoopState) -> dict[str, Any]:
    """Node: monitor active trades and generate alerts.

    In the full system the ``TradeMonitorAgent`` watches live P&L, checks
    stop-loss / take-profit levels, monitors news for thesis-changing events,
    and flags positions for review.  For the prototype we apply rule-based
    checks.
    """
    active_trades = state.get("active_trades", [])
    market_data = state.get("market_data", {})

    logger.info(
        "Idea Loop [monitor] -- monitoring %d active trades",
        len(active_trades),
    )

    alerts: list[dict] = []

    for trade in active_trades:
        trade_alerts = _check_trade_health(trade, market_data)
        alerts.extend(trade_alerts)

    # Increment iteration counter
    current_iteration = state.get("iteration", 0)

    return {
        "trade_alerts": state.get("trade_alerts", []) + alerts,
        "iteration": current_iteration + 1,
        "agent_messages": state.get("agent_messages", []) + [
            {
                "agent": "TradeMonitor",
                "node": "monitor",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"Monitored {len(active_trades)} trades, "
                    f"generated {len(alerts)} alerts"
                ),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def _should_await_approval(state: IdeaLoopState) -> str:
    """After execution, decide whether to go through approval gate.

    Returns:
        ``"await_approval"`` if there are items pending human review,
        ``"monitor"`` otherwise.
    """
    pending = state.get("pending_approval", [])
    # Only route to approval node if there are NEW pending items
    has_new_pending = any(
        p.get("status") == "pending_approval" for p in pending
    )
    if has_new_pending:
        return "await_approval"
    return "monitor"


def _should_continue_loop(state: IdeaLoopState) -> str:
    """After monitoring, decide whether to loop back or stop.

    Returns:
        ``"generate"`` to continue the cycle, or ``"__end__"`` to stop.
    """
    if not state.get("should_continue", True):
        return END
    return "generate"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_idea_loop_graph() -> StateGraph:
    """Build and compile the Idea Loop as a LangGraph StateGraph.

    The graph has the following topology::

        generate -> validate -> execute
                                  |
                          [conditional]
                         /             \\
                await_approval      monitor
                        \\             |
                         \\    [conditional]
                          \\   /          \\
                        generate         END

    Returns:
        A compiled LangGraph ``StateGraph`` ready to be invoked.
    """
    graph = StateGraph(IdeaLoopState)

    # -- Register nodes ----------------------------------------------------
    graph.add_node("generate", generate_node)
    graph.add_node("validate", validate_node)
    graph.add_node("execute", execute_node)
    graph.add_node("await_approval", await_approval_node)
    graph.add_node("monitor", monitor_node)

    # -- Set entry point ---------------------------------------------------
    graph.set_entry_point("generate")

    # -- Linear edges ------------------------------------------------------
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", "execute")

    # -- Conditional: execute -> await_approval | monitor ------------------
    graph.add_conditional_edges(
        "execute",
        _should_await_approval,
        {
            "await_approval": "await_approval",
            "monitor": "monitor",
        },
    )

    # -- await_approval always proceeds to monitor -------------------------
    graph.add_edge("await_approval", "monitor")

    # -- Conditional: monitor -> generate (loop) | END ---------------------
    graph.add_conditional_edges(
        "monitor",
        _should_continue_loop,
        {
            "generate": "generate",
            END: END,
        },
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Convenience runners
# ---------------------------------------------------------------------------

async def run_idea_loop(initial_state: dict | None = None) -> dict:
    """Run a single iteration of the idea loop.

    This is a convenience wrapper that builds the graph, merges the provided
    state with sensible defaults, sets ``should_continue=False`` so the loop
    executes exactly one cycle, and returns the final state.

    Args:
        initial_state: Partial state dict.  Missing keys are filled with
            defaults.

    Returns:
        The final ``IdeaLoopState`` after one full iteration.
    """
    graph = build_idea_loop_graph()

    state = _default_idea_loop_state()
    if initial_state:
        state.update(initial_state)

    # Force single iteration
    state["should_continue"] = False

    result = await graph.ainvoke(state)
    return result


async def run_continuous_idea_loop(
    interval_seconds: int = 60,
    initial_state: dict | None = None,
    on_iteration: Any | None = None,
) -> None:
    """Run the idea loop continuously with a delay between iterations.

    The loop runs until ``should_continue`` is set to ``False`` in the state
    (e.g. by the coordinator calling ``stop()``).

    Args:
        interval_seconds: Seconds to sleep between iterations.
        initial_state: Initial state dict.
        on_iteration: Optional async callback ``(state) -> state`` invoked
            after each iteration, allowing the coordinator to inject fresh
            data or modify control flags.
    """
    graph = build_idea_loop_graph()

    state = _default_idea_loop_state()
    if initial_state:
        state.update(initial_state)

    state["should_continue"] = True
    iteration = 0

    logger.info(
        "Starting continuous idea loop with %ds interval", interval_seconds
    )

    while state.get("should_continue", True):
        iteration += 1
        state["iteration"] = iteration
        # Each invocation should stop after one cycle so we can sleep
        state["should_continue"] = False

        logger.info("Idea Loop -- starting iteration %d", iteration)

        try:
            state = await graph.ainvoke(state)
        except Exception:
            logger.exception("Idea loop iteration %d failed", iteration)

        # Allow coordinator to inject data / flip control flags
        if on_iteration is not None:
            state = await on_iteration(state)

        # Re-enable loop unless the callback disabled it
        if state.get("should_continue", True) is not False:
            state["should_continue"] = True
        else:
            # The on_iteration callback explicitly stopped the loop
            logger.info("Idea loop stopped by callback after iteration %d", iteration)
            break

        # Reset should_continue for next graph invocation
        state["should_continue"] = True

        await asyncio.sleep(interval_seconds)

    logger.info("Continuous idea loop exited after %d iterations", iteration)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classify_urgency(idea: dict) -> str:
    """Classify trade urgency based on idea timeframe and confidence."""
    timeframe = idea.get("timeframe", "swing")
    confidence = idea.get("confidence", 0.5)

    if timeframe == "intraday" or confidence >= 0.9:
        return "high"
    elif timeframe == "swing" and confidence >= 0.7:
        return "medium"
    return "low"


def _default_stop_loss(idea: dict) -> float:
    """Return a default stop-loss percentage based on asset class."""
    asset_class = idea.get("asset_class", "equity")
    defaults = {
        "equity": 5.0,
        "crypto": 10.0,
        "commodity": 7.0,
        "fx": 2.0,
        "fixed_income": 3.0,
    }
    return defaults.get(asset_class, 5.0)


def _default_take_profit(idea: dict) -> float:
    """Return a default take-profit percentage based on asset class."""
    asset_class = idea.get("asset_class", "equity")
    defaults = {
        "equity": 15.0,
        "crypto": 30.0,
        "commodity": 20.0,
        "fx": 5.0,
        "fixed_income": 8.0,
    }
    return defaults.get(asset_class, 15.0)


def _check_trade_health(trade: dict, market_data: dict) -> list[dict]:
    """Run health checks on an active trade and return any alerts.

    This is a prototype implementation.  A production system would pull
    real-time quotes and compute actual P&L.

    Args:
        trade: Active trade dictionary.
        market_data: Current market data snapshot.

    Returns:
        List of alert dictionaries (may be empty).
    """
    alerts: list[dict] = []
    trade_id = trade.get("id", "unknown")

    # Check if trade has exceeded its intended holding period
    created_at_str = trade.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str)
            age_hours = (
                datetime.now(timezone.utc) - created_at
            ).total_seconds() / 3600

            timeframe = trade.get("timeframe", "swing")
            max_hours = {
                "intraday": 8,
                "swing": 5 * 24,
                "tactical": 30 * 24,
                "strategic": 180 * 24,
            }
            limit = max_hours.get(timeframe, 5 * 24)

            if age_hours > limit:
                alerts.append({
                    "id": str(uuid.uuid4()),
                    "trade_id": trade_id,
                    "type": "holding_period_exceeded",
                    "severity": "warning",
                    "message": (
                        f"Trade '{trade.get('idea_title', trade_id)}' has been "
                        f"open for {age_hours:.0f}h, exceeding the "
                        f"{timeframe} limit of {limit}h"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except (ValueError, TypeError):
            pass

    # Check unrealized P&L against stop-loss / take-profit
    unrealized_pnl_pct = trade.get("unrealized_pnl_pct")
    if unrealized_pnl_pct is not None:
        stop_loss = trade.get("stop_loss_pct", 5.0)
        take_profit = trade.get("take_profit_pct", 15.0)

        if unrealized_pnl_pct <= -stop_loss:
            alerts.append({
                "id": str(uuid.uuid4()),
                "trade_id": trade_id,
                "type": "stop_loss_hit",
                "severity": "critical",
                "message": (
                    f"Trade '{trade.get('idea_title', trade_id)}' hit "
                    f"stop-loss: {unrealized_pnl_pct:+.2f}% "
                    f"(limit: -{stop_loss:.2f}%)"
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif unrealized_pnl_pct >= take_profit:
            alerts.append({
                "id": str(uuid.uuid4()),
                "trade_id": trade_id,
                "type": "take_profit_hit",
                "severity": "info",
                "message": (
                    f"Trade '{trade.get('idea_title', trade_id)}' hit "
                    f"take-profit: {unrealized_pnl_pct:+.2f}% "
                    f"(target: +{take_profit:.2f}%)"
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    return alerts


def _truncate_json(obj: Any, max_chars: int = 4000) -> str:
    """JSON-serialize an object and truncate if too long."""
    import json
    text = json.dumps(obj, indent=2, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "\n... [truncated]"
    return text
