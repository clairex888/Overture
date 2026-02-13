"""Overture Coordinator -- master orchestrator for the multi-agent system.

This module contains the ``OvertureCoordinator``, the single entry-point
that the FastAPI application layer uses to interact with the agent system.
It:

* Manages the Idea Loop and Portfolio Loop as compiled LangGraph graphs.
* Routes messages between the two loops via shared state:
  - Idea Loop ``execution_plans`` -> Portfolio Loop ``incoming_trades``
  - Portfolio Loop ``trade_approvals`` / ``risk_limits`` -> Idea Loop
* Manages human-in-the-loop approval queues for trade plans and rebalances.
* Exposes a clean async API for the REST/WebSocket layer.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.agents.orchestrator.idea_loop import (
    IdeaLoopState,
    build_idea_loop_graph,
    _default_idea_loop_state,
)
from src.agents.orchestrator.portfolio_loop import (
    PortfolioLoopState,
    build_portfolio_loop_graph,
    _default_portfolio_loop_state,
)

logger = logging.getLogger(__name__)


class OvertureCoordinator:
    """Master coordinator for the Overture multi-agent system.

    Manages the Idea Loop and Portfolio Loop, coordinates between them, and
    handles human-in-the-loop interactions.  The coordinator is designed to
    be instantiated once per application process and shared across requests.

    Usage::

        coordinator = OvertureCoordinator()
        await coordinator.start({"risk_appetite": "moderate"})

        # Run one idea iteration with fresh data
        result = await coordinator.run_idea_iteration({
            "news_items": [...],
            "market_data": {...},
        })

        # Check for pending approvals
        approvals = await coordinator.get_pending_approvals()
    """

    def __init__(self) -> None:
        # Compiled LangGraph graphs
        self.idea_loop = build_idea_loop_graph()
        self.portfolio_loop = build_portfolio_loop_graph()

        # Shared mutable state for each loop
        self._idea_state: IdeaLoopState = _default_idea_loop_state()
        self._portfolio_state: PortfolioLoopState = _default_portfolio_loop_state()

        # Cross-loop shared state
        self.shared_state: dict[str, Any] = {}

        # Control flags
        self._running = False
        self._idea_loop_task: asyncio.Task | None = None
        self._portfolio_loop_task: asyncio.Task | None = None

        # Human-in-the-loop queues
        self._approval_queue: list[dict] = []
        self._alert_queue: list[dict] = []

        # Iteration counters
        self._idea_iterations = 0
        self._portfolio_iterations = 0

        logger.info("OvertureCoordinator initialised")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(
        self,
        portfolio_preferences: dict,
        idea_interval: int = 60,
        portfolio_interval: int = 300,
    ) -> None:
        """Start both loops running continuously in the background.

        Args:
            portfolio_preferences: User preferences dict containing keys
                like ``risk_appetite``, ``target_allocation``,
                ``max_single_position_pct``, etc.
            idea_interval: Seconds between idea loop iterations.
            portfolio_interval: Seconds between portfolio loop iterations.
        """
        if self._running:
            logger.warning("Coordinator is already running")
            return

        self._running = True

        # Initialise portfolio loop state with user preferences
        self._portfolio_state["preferences"] = portfolio_preferences
        self._portfolio_state["should_continue"] = True

        # Derive risk limits from preferences for the idea loop
        self._idea_state["risk_limits"] = self._derive_risk_limits(
            portfolio_preferences
        )
        self._idea_state["should_continue"] = True

        logger.info(
            "Starting coordinator -- idea_interval=%ds, portfolio_interval=%ds",
            idea_interval,
            portfolio_interval,
        )

        # Launch background tasks
        self._idea_loop_task = asyncio.create_task(
            self._run_idea_loop_continuous(idea_interval),
            name="overture-idea-loop",
        )
        self._portfolio_loop_task = asyncio.create_task(
            self._run_portfolio_loop_continuous(portfolio_interval),
            name="overture-portfolio-loop",
        )

    async def stop(self) -> None:
        """Stop all loops gracefully."""
        if not self._running:
            return

        logger.info("Stopping coordinator")
        self._running = False

        # Cancel background tasks
        for task in (self._idea_loop_task, self._portfolio_loop_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._idea_loop_task = None
        self._portfolio_loop_task = None
        logger.info("Coordinator stopped")

    # ------------------------------------------------------------------ #
    # Single-iteration runners (called by background tasks or directly)
    # ------------------------------------------------------------------ #

    async def run_idea_iteration(self, data_input: dict) -> dict:
        """Run one iteration of the idea loop with fresh data.

        This is the primary way to feed new data into the system.  The
        method merges ``data_input`` into the current idea state, runs the
        graph, synchronises cross-loop state, and returns the result.

        Args:
            data_input: Dict with optional keys ``news_items``,
                ``market_data``, ``social_signals``, ``screen_results``.

        Returns:
            The idea loop state after this iteration.
        """
        # Inject fresh data
        for key in ("news_items", "market_data", "social_signals", "screen_results"):
            if key in data_input:
                self._idea_state[key] = data_input[key]

        # Inject latest portfolio context from portfolio loop
        self._idea_state["portfolio_state"] = self._portfolio_state.get(
            "portfolio", {}
        )

        # Inject any trade approvals from portfolio loop
        portfolio_approvals = self._portfolio_state.get("trade_approvals", [])
        if portfolio_approvals:
            self._idea_state["agent_messages"] = self._idea_state.get(
                "agent_messages", []
            ) + [
                {
                    "agent": "Coordinator",
                    "node": "cross_loop",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": (
                        f"Injected {len(portfolio_approvals)} trade approvals "
                        "from portfolio loop"
                    ),
                }
            ]

        # Force single iteration
        self._idea_state["should_continue"] = False

        # Clear previous iteration outputs
        self._idea_state["raw_ideas"] = []
        self._idea_state["validated_ideas"] = []
        self._idea_state["execution_plans"] = []

        logger.info(
            "Running idea iteration %d", self._idea_iterations + 1
        )

        try:
            result = await self.idea_loop.ainvoke(dict(self._idea_state))
            self._idea_state.update(result)
            self._idea_iterations += 1
        except Exception:
            logger.exception("Idea loop iteration failed")
            return dict(self._idea_state)

        # -- Cross-loop sync: idea -> portfolio ----------------------------
        await self._sync_idea_to_portfolio()

        # -- Surface approvals and alerts ----------------------------------
        await self._collect_approvals_and_alerts()

        return dict(self._idea_state)

    async def run_portfolio_iteration(self) -> dict:
        """Run one iteration of the portfolio loop.

        Typically called on a slower cadence than the idea loop.  Picks up
        any ``incoming_trades`` that were forwarded from the idea loop.

        Returns:
            The portfolio loop state after this iteration.
        """
        # Force single iteration
        self._portfolio_state["should_continue"] = False

        logger.info(
            "Running portfolio iteration %d",
            self._portfolio_iterations + 1,
        )

        try:
            result = await self.portfolio_loop.ainvoke(
                dict(self._portfolio_state)
            )
            self._portfolio_state.update(result)
            self._portfolio_iterations += 1
        except Exception:
            logger.exception("Portfolio loop iteration failed")
            return dict(self._portfolio_state)

        # -- Cross-loop sync: portfolio -> idea ----------------------------
        await self._sync_portfolio_to_idea()

        # -- Surface approvals and alerts ----------------------------------
        await self._collect_approvals_and_alerts()

        return dict(self._portfolio_state)

    # ------------------------------------------------------------------ #
    # Human-in-the-loop
    # ------------------------------------------------------------------ #

    async def submit_approval(
        self,
        item_id: str,
        approved: bool,
        adjustments: dict | None = None,
    ) -> dict:
        """Human approves or rejects a pending item.

        This handles both trade execution plans (from the idea loop) and
        rebalance proposals (from the portfolio loop).

        Args:
            item_id: The ``id`` of the pending item.
            approved: Whether the human approves the item.
            adjustments: Optional dict of adjustments (e.g. revised sizing).

        Returns:
            Dict with the updated item and its new status.
        """
        # Search idea loop pending approvals
        for item in self._idea_state.get("pending_approval", []):
            if item.get("id") == item_id:
                if approved:
                    item["status"] = "approved_human"
                    if adjustments:
                        item.update(adjustments)
                else:
                    item["status"] = "rejected_human"
                # Remove from approval queue
                self._approval_queue = [
                    a for a in self._approval_queue if a.get("id") != item_id
                ]
                logger.info(
                    "Trade plan %s %s by human",
                    item_id,
                    "approved" if approved else "rejected",
                )
                return {"item": item, "status": item["status"]}

        # Search portfolio loop rebalance trades
        for item in self._portfolio_state.get("rebalance_trades", []):
            if item.get("id") == item_id:
                if approved:
                    item["status"] = "approved_human"
                    if adjustments:
                        item.update(adjustments)
                else:
                    item["status"] = "rejected_human"
                self._approval_queue = [
                    a for a in self._approval_queue if a.get("id") != item_id
                ]
                logger.info(
                    "Rebalance trade %s %s by human",
                    item_id,
                    "approved" if approved else "rejected",
                )
                return {"item": item, "status": item["status"]}

        logger.warning("Approval item %s not found", item_id)
        return {"item": None, "status": "not_found"}

    async def get_pending_approvals(self) -> list[dict]:
        """Get all items waiting for human approval.

        Returns:
            List of pending items from both loops, each annotated with its
            source loop and type.
        """
        pending: list[dict] = []

        # Idea loop trade plans
        for item in self._idea_state.get("pending_approval", []):
            if item.get("status") == "pending_approval":
                pending.append({
                    **item,
                    "source_loop": "idea",
                    "approval_type": "trade_plan",
                })

        # Portfolio loop rebalance trades
        for item in self._portfolio_state.get("rebalance_trades", []):
            if item.get("status") == "pending_approval":
                pending.append({
                    **item,
                    "source_loop": "portfolio",
                    "approval_type": "rebalance",
                })

        return pending

    async def get_alerts(self) -> list[dict]:
        """Get alerts for the human from both loops.

        Returns a combined, deduplicated list of alerts sorted by severity
        (critical first).

        Returns:
            List of alert dicts.
        """
        alerts: list[dict] = []

        # Trade alerts from idea loop
        for alert in self._idea_state.get("trade_alerts", []):
            alerts.append({**alert, "source_loop": "idea"})

        # Risk alerts from portfolio loop
        for alert in self._portfolio_state.get("risk_alerts", []):
            alerts.append({**alert, "source_loop": "portfolio"})

        # Add queued alerts
        alerts.extend(self._alert_queue)

        # Deduplicate by id
        seen: set[str] = set()
        unique: list[dict] = []
        for alert in alerts:
            aid = alert.get("id", str(uuid.uuid4()))
            if aid not in seen:
                seen.add(aid)
                unique.append(alert)

        # Sort: critical > warning > info
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        unique.sort(
            key=lambda a: severity_order.get(a.get("severity", "info"), 99)
        )

        return unique

    async def dismiss_alert(self, alert_id: str) -> bool:
        """Dismiss an alert by its ID.

        Args:
            alert_id: The alert ID to dismiss.

        Returns:
            ``True`` if the alert was found and dismissed.
        """
        # Remove from idea loop trade alerts
        idea_alerts = self._idea_state.get("trade_alerts", [])
        before = len(idea_alerts)
        self._idea_state["trade_alerts"] = [
            a for a in idea_alerts if a.get("id") != alert_id
        ]
        if len(self._idea_state["trade_alerts"]) < before:
            return True

        # Remove from portfolio loop risk alerts
        risk_alerts = self._portfolio_state.get("risk_alerts", [])
        before = len(risk_alerts)
        self._portfolio_state["risk_alerts"] = [
            a for a in risk_alerts if a.get("id") != alert_id
        ]
        if len(self._portfolio_state["risk_alerts"]) < before:
            return True

        # Remove from general alert queue
        before = len(self._alert_queue)
        self._alert_queue = [
            a for a in self._alert_queue if a.get("id") != alert_id
        ]
        return len(self._alert_queue) < before

    # ------------------------------------------------------------------ #
    # User interactions
    # ------------------------------------------------------------------ #

    async def inject_user_idea(self, idea: dict) -> dict:
        """Allow the human to inject their own idea into the idea loop.

        The idea is stamped with metadata and inserted into ``raw_ideas`` so
        it flows through validation and execution like any machine-generated
        idea.

        Args:
            idea: Dict with at least ``title`` and ``thesis``.  Other fields
                (``tickers``, ``confidence``, etc.) are optional and will be
                defaulted.

        Returns:
            The stamped idea dict.
        """
        stamped_idea = {
            "id": str(uuid.uuid4()),
            "title": idea.get("title", "User Idea"),
            "thesis": idea.get("thesis", ""),
            "tickers": idea.get("tickers", []),
            "asset_class": idea.get("asset_class", "equity"),
            "timeframe": idea.get("timeframe", "swing"),
            "source": "user_injected",
            "confidence": idea.get("confidence", 0.7),
            "risks": idea.get("risks", []),
            "invalidation_triggers": idea.get("invalidation_triggers", []),
            "status": "raw",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_injected": True,
        }

        # Add to raw_ideas so the next validate pass picks it up
        self._idea_state["raw_ideas"] = self._idea_state.get(
            "raw_ideas", []
        ) + [stamped_idea]

        logger.info("User injected idea: %s", stamped_idea["title"])

        return stamped_idea

    async def update_preferences(self, preferences: dict) -> dict:
        """Update portfolio preferences and risk appetite.

        Triggers a re-derivation of risk limits for the idea loop.

        Args:
            preferences: Dict of updated preferences.  Merged with existing
                preferences (new values override).

        Returns:
            The full merged preferences dict.
        """
        current = self._portfolio_state.get("preferences", {})
        current.update(preferences)
        self._portfolio_state["preferences"] = current

        # Re-derive idea loop risk limits
        self._idea_state["risk_limits"] = self._derive_risk_limits(current)

        logger.info("Preferences updated: %s", list(preferences.keys()))

        return current

    async def update_portfolio(self, portfolio: dict, positions: list[dict]) -> None:
        """Update the portfolio snapshot used by both loops.

        This is called when fresh portfolio data arrives from the broker or
        database.

        Args:
            portfolio: Portfolio summary dict (``total_value``, ``cash``, etc.).
            positions: List of position dicts.
        """
        self._portfolio_state["portfolio"] = portfolio
        self._portfolio_state["positions"] = positions

        # Also make it available to the idea loop
        self._idea_state["portfolio_state"] = portfolio

        logger.info(
            "Portfolio updated: value=$%s, %d positions",
            portfolio.get("total_value", "N/A"),
            len(positions),
        )

    # ------------------------------------------------------------------ #
    # System status
    # ------------------------------------------------------------------ #

    async def get_system_status(self) -> dict:
        """Get status of all agents and loops.

        Returns a comprehensive snapshot of the coordinator's state
        including loop health, queue sizes, and recent agent messages.

        Returns:
            Status dict suitable for JSON serialization.
        """
        return {
            "running": self._running,
            "idea_loop": {
                "iterations": self._idea_iterations,
                "current_iteration": self._idea_state.get("iteration", 0),
                "task_alive": (
                    self._idea_loop_task is not None
                    and not self._idea_loop_task.done()
                )
                if self._idea_loop_task
                else False,
                "raw_ideas_count": len(
                    self._idea_state.get("raw_ideas", [])
                ),
                "validated_ideas_count": len(
                    self._idea_state.get("validated_ideas", [])
                ),
                "execution_plans_count": len(
                    self._idea_state.get("execution_plans", [])
                ),
                "active_trades_count": len(
                    self._idea_state.get("active_trades", [])
                ),
                "pending_approval_count": len(
                    self._idea_state.get("pending_approval", [])
                ),
                "trade_alerts_count": len(
                    self._idea_state.get("trade_alerts", [])
                ),
            },
            "portfolio_loop": {
                "iterations": self._portfolio_iterations,
                "current_iteration": self._portfolio_state.get("iteration", 0),
                "task_alive": (
                    self._portfolio_loop_task is not None
                    and not self._portfolio_loop_task.done()
                )
                if self._portfolio_loop_task
                else False,
                "positions_count": len(
                    self._portfolio_state.get("positions", [])
                ),
                "risk_alerts_count": len(
                    self._portfolio_state.get("risk_alerts", [])
                ),
                "rebalance_needed": self._portfolio_state.get(
                    "rebalance_needed", False
                ),
                "rebalance_trades_count": len(
                    self._portfolio_state.get("rebalance_trades", [])
                ),
                "incoming_trades_count": len(
                    self._portfolio_state.get("incoming_trades", [])
                ),
            },
            "queues": {
                "pending_approvals": len(self._approval_queue),
                "alerts": len(self._alert_queue),
            },
            "risk_metrics": self._portfolio_state.get("risk_metrics", {}),
            "current_allocation": self._portfolio_state.get(
                "current_allocation", {}
            ),
            "target_allocation": self._portfolio_state.get(
                "target_allocation", {}
            ),
            "drift": self._portfolio_state.get("drift", {}),
            "recent_messages": self._get_recent_messages(limit=20),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_agent_messages(
        self, limit: int = 50, loop: str | None = None
    ) -> list[dict]:
        """Get recent agent coordination messages.

        Args:
            limit: Maximum number of messages to return.
            loop: Filter by loop (``"idea"`` or ``"portfolio"``).

        Returns:
            List of message dicts, most recent first.
        """
        messages: list[dict] = []

        if loop is None or loop == "idea":
            for msg in self._idea_state.get("agent_messages", []):
                messages.append({**msg, "loop": "idea"})

        if loop is None or loop == "portfolio":
            for msg in self._portfolio_state.get("agent_messages", []):
                messages.append({**msg, "loop": "portfolio"})

        # Sort by timestamp descending
        messages.sort(
            key=lambda m: m.get("timestamp", ""),
            reverse=True,
        )

        return messages[:limit]

    # ------------------------------------------------------------------ #
    # Cross-loop synchronisation (private)
    # ------------------------------------------------------------------ #

    async def _sync_idea_to_portfolio(self) -> None:
        """Forward execution plans from idea loop to portfolio loop.

        Approved execution plans (both auto-approved and human-approved) are
        sent to the portfolio loop as ``incoming_trades`` for portfolio-level
        review (concentration limits, sector exposure, etc.).
        """
        plans = self._idea_state.get("execution_plans", [])
        approved_plans = [
            p
            for p in plans
            if p.get("status") in ("approved_auto", "approved_human")
        ]

        if approved_plans:
            existing_incoming = self._portfolio_state.get(
                "incoming_trades", []
            )
            self._portfolio_state["incoming_trades"] = (
                existing_incoming + approved_plans
            )
            logger.info(
                "Synced %d approved plans from idea loop to portfolio loop",
                len(approved_plans),
            )

    async def _sync_portfolio_to_idea(self) -> None:
        """Feed portfolio approvals and risk limits back to idea loop.

        Trade approvals from the portfolio loop are injected into the idea
        loop state.  Updated risk limits constrain future idea generation.
        """
        # Push trade approvals
        approvals = self._portfolio_state.get("trade_approvals", [])
        if approvals:
            self._idea_state["agent_messages"] = self._idea_state.get(
                "agent_messages", []
            ) + [
                {
                    "agent": "Coordinator",
                    "node": "cross_loop_sync",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": (
                        f"Received {len(approvals)} trade approvals from "
                        "portfolio loop"
                    ),
                    "details": approvals,
                }
            ]

        # Update risk limits based on latest risk metrics
        risk_metrics = self._portfolio_state.get("risk_metrics", {})
        if risk_metrics:
            risk_limits = self._idea_state.get("risk_limits", {})
            # Tighten limits if portfolio is under stress
            drawdown = risk_metrics.get("total_unrealized_pnl_pct", 0.0)
            if drawdown < -5.0:
                risk_limits["min_idea_confidence"] = max(
                    risk_limits.get("min_idea_confidence", 0.3), 0.6
                )
                risk_limits["auto_approve_notional"] = min(
                    risk_limits.get("auto_approve_notional", 5000), 2000
                )
                logger.info(
                    "Tightened idea loop risk limits due to %.1f%% drawdown",
                    drawdown,
                )
            self._idea_state["risk_limits"] = risk_limits

        # Push portfolio state for idea loop context
        self._idea_state["portfolio_state"] = self._portfolio_state.get(
            "portfolio", {}
        )

    async def _collect_approvals_and_alerts(self) -> None:
        """Collect new pending approvals and alerts from both loops.

        Scans both loop states for items that need human attention and adds
        them to the coordinator-level queues.
        """
        # Collect pending approvals from idea loop
        for item in self._idea_state.get("pending_approval", []):
            if item.get("status") == "pending_approval":
                item_id = item.get("id")
                if not any(
                    a.get("id") == item_id for a in self._approval_queue
                ):
                    self._approval_queue.append({
                        **item,
                        "source_loop": "idea",
                        "approval_type": "trade_plan",
                    })

        # Collect pending approvals from portfolio loop (rebalance trades)
        for item in self._portfolio_state.get("rebalance_trades", []):
            if item.get("status") == "pending_approval":
                item_id = item.get("id")
                if not any(
                    a.get("id") == item_id for a in self._approval_queue
                ):
                    self._approval_queue.append({
                        **item,
                        "source_loop": "portfolio",
                        "approval_type": "rebalance",
                    })

        # Collect trade alerts
        for alert in self._idea_state.get("trade_alerts", []):
            aid = alert.get("id")
            if not any(a.get("id") == aid for a in self._alert_queue):
                self._alert_queue.append({
                    **alert, "source_loop": "idea"
                })

        # Collect risk alerts
        for alert in self._portfolio_state.get("risk_alerts", []):
            aid = alert.get("id")
            if not any(a.get("id") == aid for a in self._alert_queue):
                self._alert_queue.append({
                    **alert, "source_loop": "portfolio"
                })

    # ------------------------------------------------------------------ #
    # Continuous loop runners (private)
    # ------------------------------------------------------------------ #

    async def _run_idea_loop_continuous(self, interval: int) -> None:
        """Background task that runs the idea loop on a timer.

        Args:
            interval: Seconds between iterations.
        """
        logger.info("Idea loop background task started (interval=%ds)", interval)

        while self._running:
            try:
                await self.run_idea_iteration({})
            except Exception:
                logger.exception("Idea loop background iteration failed")

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Idea loop background task exited")

    async def _run_portfolio_loop_continuous(self, interval: int) -> None:
        """Background task that runs the portfolio loop on a timer.

        Args:
            interval: Seconds between iterations.
        """
        logger.info(
            "Portfolio loop background task started (interval=%ds)", interval
        )

        while self._running:
            try:
                await self.run_portfolio_iteration()
            except Exception:
                logger.exception("Portfolio loop background iteration failed")

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

        logger.info("Portfolio loop background task exited")

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _derive_risk_limits(self, preferences: dict) -> dict:
        """Derive idea-loop risk limits from portfolio preferences.

        Translates user-facing preferences (risk appetite, position limits)
        into the concrete thresholds that the idea loop's validation and
        execution nodes use.

        Args:
            preferences: Portfolio preferences dict.

        Returns:
            Risk limits dict for the idea loop.
        """
        risk_appetite = preferences.get("risk_appetite", "moderate")

        appetite_params = {
            "conservative": {
                "min_idea_confidence": 0.5,
                "max_positions": 30,
                "max_single_position_pct": 0.03,
                "auto_approve_notional": 2_000,
                "ticker_blacklist": preferences.get("ticker_blacklist", []),
                "restricted_asset_classes": preferences.get(
                    "restricted_asset_classes", []
                ),
            },
            "moderate": {
                "min_idea_confidence": 0.3,
                "max_positions": 50,
                "max_single_position_pct": 0.05,
                "auto_approve_notional": 5_000,
                "ticker_blacklist": preferences.get("ticker_blacklist", []),
                "restricted_asset_classes": preferences.get(
                    "restricted_asset_classes", []
                ),
            },
            "aggressive": {
                "min_idea_confidence": 0.2,
                "max_positions": 100,
                "max_single_position_pct": 0.10,
                "auto_approve_notional": 10_000,
                "ticker_blacklist": preferences.get("ticker_blacklist", []),
                "restricted_asset_classes": preferences.get(
                    "restricted_asset_classes", []
                ),
            },
        }

        limits = appetite_params.get(risk_appetite, appetite_params["moderate"])

        # Override with explicit preferences if provided
        for key in (
            "min_idea_confidence",
            "max_positions",
            "max_single_position_pct",
            "auto_approve_notional",
        ):
            if key in preferences:
                limits[key] = preferences[key]

        return limits

    def _get_recent_messages(self, limit: int = 20) -> list[dict]:
        """Get recent agent messages from both loops, sorted by time.

        Args:
            limit: Max messages to return.

        Returns:
            List of message dicts.
        """
        messages: list[dict] = []

        for msg in self._idea_state.get("agent_messages", []):
            messages.append({**msg, "loop": "idea"})

        for msg in self._portfolio_state.get("agent_messages", []):
            messages.append({**msg, "loop": "portfolio"})

        messages.sort(
            key=lambda m: m.get("timestamp", ""),
            reverse=True,
        )

        return messages[:limit]
