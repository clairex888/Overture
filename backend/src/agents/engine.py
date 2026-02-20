"""Agent Engine -- app-level singleton managing the OvertureCoordinator.

This module provides the ``agent_engine`` singleton which is initialized at
app startup and accessed by API routes.  It wraps the OvertureCoordinator
with database integration (persisting ideas, trades, agent logs) and
knowledge RAG context injection.

Usage in routes::

    from src.agents.engine import agent_engine

    @router.post("/idea-loop/start")
    async def start_idea_loop():
        await agent_engine.start_idea_loop()
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.agents.base import AgentContext
from src.agents.llm.router import llm_router
from src.agents.idea.parallel_generators import (
    run_parallel_generators,
    ALL_GENERATORS,
    MacroNewsAgent,
    IndustryNewsAgent,
    CryptoAgent,
    QuantSystematicAgent,
    CommoditiesAgent,
    SocialMediaAgent,
)
from src.agents.idea.parallel_validators import (
    validate_ideas_batch,
    ValidationThresholds,
    ValidationResult,
)
from src.agents.orchestrator.idea_loop import (
    run_idea_loop,
    run_continuous_idea_loop,
    IdeaLoopState,
)
from src.agents.orchestrator.portfolio_loop import (
    run_portfolio_loop,
    run_continuous_portfolio_loop,
    PortfolioLoopState,
)

logger = logging.getLogger(__name__)


class AgentEngine:
    """Singleton engine managing agent loops and providing API integration.

    The engine coordinates:
    - Idea loop (generation → validation → execution → monitoring)
    - Portfolio loop (assess → construct → risk → rebalance)
    - Knowledge RAG context injection
    - Database persistence of results
    - WebSocket notifications (future)
    """

    def __init__(self) -> None:
        self._idea_loop_task: asyncio.Task | None = None
        self._portfolio_loop_task: asyncio.Task | None = None
        self._idea_loop_running = False
        self._portfolio_loop_running = False
        self._idea_state: dict = {}
        self._portfolio_state: dict = {}
        self._iteration_counts = {"idea": 0, "portfolio": 0}
        self._started_at: dict[str, datetime | None] = {
            "idea": None, "portfolio": None,
        }
        self._agent_messages: list[dict] = []
        self._pending_approvals: list[dict] = []
        self._alerts: list[dict] = []

    # -----------------------------------------------------------------
    # Idea Loop Control
    # -----------------------------------------------------------------

    async def start_idea_loop(
        self,
        interval_seconds: int = 60,
        initial_data: dict | None = None,
    ) -> dict:
        """Start the continuous idea loop in the background."""
        if self._idea_loop_running:
            return {"status": "already_running", "iterations": self._iteration_counts["idea"]}

        self._idea_loop_running = True
        self._started_at["idea"] = datetime.now(timezone.utc)

        async def _on_iteration(state: dict) -> dict:
            """Callback after each idea loop iteration."""
            self._iteration_counts["idea"] += 1
            self._idea_state = dict(state)

            # Capture messages and approvals
            messages = state.get("agent_messages", [])
            if messages:
                self._agent_messages.extend(messages[-10:])
                self._agent_messages = self._agent_messages[-100:]

            pending = state.get("pending_approval", [])
            if pending:
                self._pending_approvals.extend(pending)

            alerts = state.get("trade_alerts", [])
            if alerts:
                self._alerts.extend(alerts)
                self._alerts = self._alerts[-200:]

            # Inject fresh knowledge context for next iteration
            knowledge_context = await self._get_knowledge_context("idea_generator")
            state["knowledge_context"] = knowledge_context

            # Keep loop running unless explicitly stopped
            if not self._idea_loop_running:
                state["should_continue"] = False

            return state

        initial_state = initial_data or {}
        # Inject knowledge context for first iteration
        knowledge_context = await self._get_knowledge_context("idea_generator")
        initial_state["knowledge_context"] = knowledge_context

        self._idea_loop_task = asyncio.create_task(
            run_continuous_idea_loop(
                interval_seconds=interval_seconds,
                initial_state=initial_state,
                on_iteration=_on_iteration,
            )
        )

        logger.info("Idea loop started (interval=%ds)", interval_seconds)
        return {"status": "started", "interval_seconds": interval_seconds}

    async def stop_idea_loop(self) -> dict:
        """Stop the idea loop."""
        self._idea_loop_running = False
        if self._idea_loop_task and not self._idea_loop_task.done():
            self._idea_loop_task.cancel()
            try:
                await self._idea_loop_task
            except (asyncio.CancelledError, Exception):
                pass
        self._idea_loop_task = None
        logger.info("Idea loop stopped")
        return {"status": "stopped", "iterations": self._iteration_counts["idea"]}

    # -----------------------------------------------------------------
    # Portfolio Loop Control
    # -----------------------------------------------------------------

    async def start_portfolio_loop(
        self,
        interval_seconds: int = 300,
        initial_data: dict | None = None,
    ) -> dict:
        """Start the continuous portfolio loop in the background."""
        if self._portfolio_loop_running:
            return {"status": "already_running", "iterations": self._iteration_counts["portfolio"]}

        self._portfolio_loop_running = True
        self._started_at["portfolio"] = datetime.now(timezone.utc)

        async def _on_iteration(state: dict) -> dict:
            self._iteration_counts["portfolio"] += 1
            self._portfolio_state = dict(state)

            messages = state.get("agent_messages", [])
            if messages:
                self._agent_messages.extend(messages[-10:])
                self._agent_messages = self._agent_messages[-100:]

            alerts = state.get("risk_alerts", [])
            if alerts:
                self._alerts.extend(alerts)
                self._alerts = self._alerts[-200:]

            # Cross-loop sync: forward validated ideas as incoming trades
            if self._idea_state.get("execution_plans"):
                state["incoming_trades"] = self._idea_state.get("execution_plans", [])

            if not self._portfolio_loop_running:
                state["should_continue"] = False

            return state

        self._portfolio_loop_task = asyncio.create_task(
            run_continuous_portfolio_loop(
                interval_seconds=interval_seconds,
                initial_state=initial_data,
                on_iteration=_on_iteration,
            )
        )

        logger.info("Portfolio loop started (interval=%ds)", interval_seconds)
        return {"status": "started", "interval_seconds": interval_seconds}

    async def stop_portfolio_loop(self) -> dict:
        """Stop the portfolio loop."""
        self._portfolio_loop_running = False
        if self._portfolio_loop_task and not self._portfolio_loop_task.done():
            self._portfolio_loop_task.cancel()
            try:
                await self._portfolio_loop_task
            except (asyncio.CancelledError, Exception):
                pass
        self._portfolio_loop_task = None
        logger.info("Portfolio loop stopped")
        return {"status": "stopped", "iterations": self._iteration_counts["portfolio"]}

    # -----------------------------------------------------------------
    # Single-shot: run one idea generation cycle
    # -----------------------------------------------------------------

    async def generate_ideas_once(
        self, input_data: dict | None = None
    ) -> list[dict]:
        """Run a single idea generation + validation cycle.

        This is called by the /api/ideas/generate endpoint for on-demand
        idea generation without running the full loop.
        """
        llm = llm_router.get_provider()

        knowledge_context = await self._get_knowledge_context("idea_generator")

        context = AgentContext(
            portfolio_state=self._idea_state.get("portfolio_state", {}),
            market_context=input_data.get("market_data", {}) if input_data else {},
            knowledge_context=knowledge_context,
        )

        # Determine which generators to run (domain filter)
        domain_to_cls = {
            "macro": MacroNewsAgent,
            "industry": IndustryNewsAgent,
            "crypto": CryptoAgent,
            "quant": QuantSystematicAgent,
            "commodities": CommoditiesAgent,
            "social": SocialMediaAgent,
        }
        selected_generators = None
        domains = (input_data or {}).get("domains")
        if domains:
            selected_generators = [
                domain_to_cls[d] for d in domains if d in domain_to_cls
            ] or None

        # Run parallel generators
        raw_ideas = await run_parallel_generators(
            input_data or {}, context, llm, generators=selected_generators
        )

        # Stamp ideas
        for idea in raw_ideas:
            idea.setdefault("id", str(uuid4()))
            idea.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            idea.setdefault("status", "raw")

        logger.info("Single-shot generation produced %d ideas", len(raw_ideas))
        return raw_ideas

    async def validate_ideas_once(
        self, ideas: list[dict], thresholds: dict | None = None
    ) -> list[tuple[dict, dict]]:
        """Run parallel validation on a list of ideas.

        Returns list of (idea, validation_result_dict) tuples.
        """
        llm = llm_router.get_provider()
        knowledge_context = await self._get_knowledge_context("idea_validator")

        context = AgentContext(
            portfolio_state=self._idea_state.get("portfolio_state", {}),
            knowledge_context=knowledge_context,
        )

        vt = ValidationThresholds()
        if thresholds:
            if "pass_score" in thresholds:
                vt.pass_score = thresholds["pass_score"]
            if "fail_score" in thresholds:
                vt.fail_score = thresholds["fail_score"]
            if "min_reasoning_score" in thresholds:
                vt.min_reasoning_score = thresholds["min_reasoning_score"]

        results = await validate_ideas_batch(ideas, context, llm, vt)

        output = []
        for idea, result in results:
            result_dict = {
                "verdict": result.verdict,
                "weighted_score": result.weighted_score,
                "scores": {
                    k: {"score": v.score, "analysis": v.analysis, "flags": v.flags}
                    for k, v in result.scores.items()
                },
                "reasoning": result.reasoning,
                "flags": result.flags,
            }
            output.append((idea, result_dict))

        return output

    # -----------------------------------------------------------------
    # Status and monitoring
    # -----------------------------------------------------------------

    def get_status(self) -> dict:
        """Return comprehensive system status."""
        now = datetime.now(timezone.utc)

        def _uptime(key: str) -> str:
            started = self._started_at.get(key)
            if not started:
                return "0s"
            delta = now - started
            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)
            return f"{hours}h {minutes}m"

        return {
            "idea_loop": {
                "running": self._idea_loop_running,
                "iterations": self._iteration_counts["idea"],
                "uptime": _uptime("idea"),
                "task_alive": self._idea_loop_task is not None
                    and not self._idea_loop_task.done()
                    if self._idea_loop_task else False,
            },
            "portfolio_loop": {
                "running": self._portfolio_loop_running,
                "iterations": self._iteration_counts["portfolio"],
                "uptime": _uptime("portfolio"),
                "task_alive": self._portfolio_loop_task is not None
                    and not self._portfolio_loop_task.done()
                    if self._portfolio_loop_task else False,
            },
            "pending_approvals": len(self._pending_approvals),
            "active_alerts": len(self._alerts),
            "recent_messages": self._agent_messages[-20:],
        }

    def get_agent_statuses(self) -> dict:
        """Return individual agent statuses for the frontend."""
        now_iso = datetime.now(timezone.utc).isoformat()
        idea_running = self._idea_loop_running
        portfolio_running = self._portfolio_loop_running

        def _agent_status(name: str, agent_type: str, running: bool) -> dict:
            return {
                "name": name,
                "type": agent_type,
                "status": "running" if running else "idle",
                "last_run": now_iso,
                "tasks_completed": self._iteration_counts.get(
                    "idea" if "idea" in agent_type or "generation" in agent_type
                    else "portfolio", 0
                ),
                "errors": 0,
            }

        agents = {
            "idea_generation": _agent_status(
                "Parallel Idea Generators", "idea_generation", idea_running
            ),
            "idea_validation": _agent_status(
                "Parallel Validators", "idea_validation", idea_running
            ),
            "trade_execution": _agent_status(
                "Trade Executor", "trade_execution", idea_running
            ),
            "trade_monitoring": _agent_status(
                "Trade Monitor", "trade_monitoring", idea_running
            ),
            "portfolio_management": _agent_status(
                "Portfolio Constructor", "portfolio_management", portfolio_running
            ),
            "risk_management": _agent_status(
                "Risk Manager", "risk_management", portfolio_running
            ),
            "knowledge": _agent_status(
                "Knowledge Curator", "knowledge", True  # always "on"
            ),
        }

        return {
            "agents": agents,
            "idea_loop_running": idea_running,
            "portfolio_loop_running": portfolio_running,
        }

    def get_logs(self, limit: int = 50) -> list[dict]:
        """Return recent agent messages as logs."""
        return self._agent_messages[-limit:]

    def get_pending_approvals(self) -> list[dict]:
        """Return pending human approvals."""
        return [p for p in self._pending_approvals if p.get("status") == "pending_approval"]

    def get_alerts(self) -> list[dict]:
        """Return active alerts."""
        return self._alerts

    def dismiss_alert(self, alert_id: str) -> bool:
        """Dismiss an alert by ID."""
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.get("id") != alert_id]
        return len(self._alerts) < before

    # -----------------------------------------------------------------
    # Approval handling
    # -----------------------------------------------------------------

    async def approve_trade(self, plan_id: str, adjustments: dict | None = None) -> dict:
        """Approve a pending trade plan."""
        for plan in self._pending_approvals:
            if plan.get("id") == plan_id:
                plan["status"] = "approved_human"
                plan["approved_at"] = datetime.now(timezone.utc).isoformat()
                if adjustments:
                    plan["adjustments"] = adjustments
                return plan
        return {"error": f"Plan {plan_id} not found"}

    async def reject_trade(self, plan_id: str, reason: str = "") -> dict:
        """Reject a pending trade plan."""
        for plan in self._pending_approvals:
            if plan.get("id") == plan_id:
                plan["status"] = "rejected_human"
                plan["rejected_at"] = datetime.now(timezone.utc).isoformat()
                plan["reject_reason"] = reason
                return plan
        return {"error": f"Plan {plan_id} not found"}

    # -----------------------------------------------------------------
    # Knowledge RAG integration
    # -----------------------------------------------------------------

    async def _get_knowledge_context(self, agent_type: str) -> list[dict]:
        """Retrieve knowledge context from RAG pipeline.

        Uses the knowledge_rag service to get relevant entries for the
        agent type. Falls back to empty list on errors.
        """
        try:
            from src.models.base import async_session_factory
            from src.services.knowledge_rag import get_context

            async with async_session_factory() as session:
                entries = await get_context(
                    session,
                    agent_type=agent_type,
                    max_entries=8,
                )
                return entries
        except Exception:
            logger.debug("Knowledge RAG context retrieval failed", exc_info=True)
            return []

    # -----------------------------------------------------------------
    # Shutdown
    # -----------------------------------------------------------------

    async def shutdown(self) -> None:
        """Gracefully stop all loops."""
        if self._idea_loop_running:
            await self.stop_idea_loop()
        if self._portfolio_loop_running:
            await self.stop_portfolio_loop()
        logger.info("Agent engine shut down")


# Module-level singleton
agent_engine = AgentEngine()
