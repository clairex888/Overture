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

    # Canonical agent keys — shared with frontend stage definitions
    AGENT_KEYS = [
        "idea_generator", "idea_validator", "trade_executor",
        "trade_monitor", "portfolio_manager", "risk_manager", "knowledge",
    ]

    def __init__(self) -> None:
        self._idea_loop_task: asyncio.Task | None = None
        self._portfolio_loop_task: asyncio.Task | None = None
        self._idea_loop_running = False
        self._portfolio_loop_running = False
        self._idea_state: dict = {}
        self._portfolio_state: dict = {}
        self._iteration_counts = {"idea": 0, "portfolio": 0}
        self._engine_started_at = datetime.now(timezone.utc)
        self._started_at: dict[str, datetime | None] = {
            "idea": None, "portfolio": None,
        }
        self._agent_messages: list[dict] = []
        self._pending_approvals: list[dict] = []
        self._alerts: list[dict] = []

        # Per-agent tracking
        self._agent_stats: dict[str, dict] = {
            key: {
                "tasks_completed": 0,
                "errors": 0,
                "last_run": None,
                "current_task": None,
            }
            for key in self.AGENT_KEYS
        }

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

            # Record per-agent activity from this iteration
            raw = state.get("raw_ideas", [])
            validated = state.get("validated_ideas", [])
            plans = state.get("execution_plans", [])
            alerts_count = len(state.get("trade_alerts", []))
            if raw:
                self._record_agent_run("idea_generator", f"Generated {len(raw)} ideas")
            if validated or state.get("rejected_ideas"):
                self._record_agent_run("idea_validator", f"Validated {len(validated)} ideas")
            if plans:
                self._record_agent_run("trade_executor", f"Created {len(plans)} plans")
            self._record_agent_run("trade_monitor", f"Monitored, {alerts_count} alerts")

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

        The workflow mirrors an investment firm's analyst briefing:
        1. Research desk collects data (DataPipeline)
        2. Analysts receive the briefing packet (DataSnapshot → agents)
        3. Each analyst generates ideas from their domain expertise
        4. Ideas are stamped and returned for validation
        """
        llm = llm_router.get_provider()

        # ── Step 1: Collect live market data via the centralized pipeline ──
        # This is the "research desk" — gathers news, market data, social
        # signals, and screen results into a single consistent snapshot.
        enriched_data: dict = dict(input_data or {})
        try:
            from src.services.data_pipeline import data_pipeline

            if data_pipeline is not None:
                logger.info("Data pipeline: collecting live data for idea generation")
                snapshot = await data_pipeline.collect()
                agent_input = snapshot.to_agent_input()

                # Merge pipeline data with any data already in input_data
                # (pipeline data fills in what's missing, doesn't overwrite)
                if agent_input.get("news_items") and not enriched_data.get("news_items"):
                    enriched_data["news_items"] = agent_input["news_items"]
                if agent_input.get("market_data") and not enriched_data.get("market_data"):
                    enriched_data["market_data"] = agent_input["market_data"]
                if agent_input.get("social_signals") and not enriched_data.get("social_signals"):
                    enriched_data["social_signals"] = agent_input["social_signals"]
                if agent_input.get("screen_results") and not enriched_data.get("screen_results"):
                    enriched_data["screen_results"] = agent_input["screen_results"]

                logger.info(
                    "Data pipeline collected: news=%d, market_tickers=%d, social=%d, screens=%d",
                    len(enriched_data.get("news_items", [])),
                    len(enriched_data.get("market_data", {}).get("prices", {})),
                    len(enriched_data.get("social_signals", [])),
                    len(enriched_data.get("screen_results", [])),
                )
            else:
                logger.warning("Data pipeline not available — agents will use general knowledge")
        except Exception:
            logger.warning("Data pipeline collection failed — agents will use general knowledge", exc_info=True)

        # ── Step 2: Build analyst context ──
        knowledge_context = await self._get_knowledge_context("idea_generator")

        context = AgentContext(
            portfolio_state=self._idea_state.get("portfolio_state", {}),
            market_context=enriched_data.get("market_data", {}),
            knowledge_context=knowledge_context,
        )

        # ── Step 3: Determine which analysts (generators) to brief ──
        domain_to_cls = {
            "macro": MacroNewsAgent,
            "industry": IndustryNewsAgent,
            "crypto": CryptoAgent,
            "quant": QuantSystematicAgent,
            "commodities": CommoditiesAgent,
            "social": SocialMediaAgent,
        }
        selected_generators = None
        domains = enriched_data.get("domains")
        if domains:
            selected_generators = [
                domain_to_cls[d] for d in domains if d in domain_to_cls
            ] or None

        # ── Step 4: Run parallel analysts ──
        self._set_agent_task("idea_generator", "Generating ideas from live data")
        try:
            raw_ideas = await run_parallel_generators(
                enriched_data, context, llm, generators=selected_generators
            )
            self._record_agent_run("idea_generator", f"Generated {len(raw_ideas)} ideas")
        except Exception:
            self._record_agent_run("idea_generator", error=True)
            raise

        # ── Step 5: Stamp ideas with IDs and timestamps ──
        for idea in raw_ideas:
            idea.setdefault("id", str(uuid4()))
            idea.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            idea.setdefault("status", "raw")

        logger.info("Single-shot generation produced %d ideas", len(raw_ideas))

        # Log to agent messages for activity feed
        self._agent_messages.append({
            "agent": "idea_generator",
            "node": "generate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"On-demand generation produced {len(raw_ideas)} ideas",
        })
        self._agent_messages = self._agent_messages[-200:]

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

        self._set_agent_task("idea_validator", f"Validating {len(ideas)} ideas")
        try:
            results = await validate_ideas_batch(ideas, context, llm, vt)
            self._record_agent_run("idea_validator", f"Validated {len(ideas)} ideas")
        except Exception:
            self._record_agent_run("idea_validator", error=True)
            raise

        # Log to agent messages
        self._agent_messages.append({
            "agent": "idea_validator",
            "node": "validate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": f"On-demand validation completed for {len(ideas)} ideas",
        })
        self._agent_messages = self._agent_messages[-200:]

        output = []
        for idea, result in results:
            result_dict = {
                "verdict": result.verdict,
                "weighted_score": result.weighted_score,
                "scores": {
                    k: {
                        "score": v.score,
                        "analysis": v.analysis,
                        "flags": v.flags,
                        "details": v.details,
                    }
                    for k, v in result.scores.items()
                },
                "reasoning": result.reasoning,
                "flags": result.flags,
                "chain_of_thought": [
                    s.to_dict() for s in getattr(result, "chain_of_thought", [])
                ],
                "key_findings": getattr(result, "key_findings", []),
                "suggested_actions": getattr(result, "suggested_actions", []),
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

    def _record_agent_run(self, agent_key: str, task_desc: str | None = None, error: bool = False) -> None:
        """Record an agent task completion or error, and persist to DB."""
        stats = self._agent_stats.get(agent_key)
        if not stats:
            return
        stats["last_run"] = datetime.now(timezone.utc).isoformat()
        if error:
            stats["errors"] += 1
        else:
            stats["tasks_completed"] += 1
        stats["current_task"] = task_desc

        # Fire-and-forget DB persistence (non-blocking)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_agent_log(
                agent_key, task_desc or ("error" if error else "task"), error,
            ))
        except RuntimeError:
            pass  # No running event loop — skip persistence

    def _set_agent_task(self, agent_key: str, task_desc: str | None) -> None:
        """Set the current task description for an agent."""
        stats = self._agent_stats.get(agent_key)
        if stats:
            stats["current_task"] = task_desc

    async def _persist_agent_log(self, agent_key: str, action: str, is_error: bool) -> None:
        """Persist an agent log entry to the database."""
        try:
            from src.models.base import async_session_factory
            from src.models.agent_state import AgentLog, AgentLogStatus, AgentType

            # Map agent key to AgentType enum
            type_map = {
                "idea_generator": AgentType.IDEA_GENERATOR,
                "idea_validator": AgentType.IDEA_VALIDATOR,
                "trade_executor": AgentType.TRADE_EXECUTOR,
                "trade_monitor": AgentType.TRADE_MONITOR,
                "portfolio_manager": AgentType.PORTFOLIO_CONSTRUCTOR,
                "risk_manager": AgentType.RISK_MANAGER,
                "knowledge": AgentType.KNOWLEDGE_CURATOR,
            }
            agent_type = type_map.get(agent_key, AgentType.IDEA_GENERATOR)
            status = AgentLogStatus.FAILURE if is_error else AgentLogStatus.SUCCESS

            async with async_session_factory() as session:
                log = AgentLog(
                    id=str(uuid4()),
                    agent_name=agent_key,
                    agent_type=agent_type,
                    action=action,
                    status=status,
                )
                session.add(log)
                await session.commit()
        except Exception:
            logger.warning("Failed to persist agent log", exc_info=True)

    def get_agent_statuses(self) -> dict:
        """Return individual agent statuses for the frontend.

        Agent keys match the canonical AGENT_KEYS used by the frontend
        stage definitions so status resolution works correctly.
        """
        idea_running = self._idea_loop_running
        portfolio_running = self._portfolio_loop_running

        _AGENT_META = {
            "idea_generator": ("Parallel Idea Generators", idea_running),
            "idea_validator": ("Parallel Validators", idea_running),
            "trade_executor": ("Trade Executor", idea_running),
            "trade_monitor": ("Trade Monitor", idea_running),
            "portfolio_manager": ("Portfolio Constructor", portfolio_running),
            "risk_manager": ("Risk Manager", portfolio_running),
            "knowledge": ("Knowledge Curator", True),
        }

        agents = {}
        for key in self.AGENT_KEYS:
            display_name, running = _AGENT_META[key]
            stats = self._agent_stats[key]
            # Compute uptime from loop start time (knowledge uses engine start)
            if key == "knowledge":
                started = self._engine_started_at
            else:
                loop_key = "idea" if key in ("idea_generator", "idea_validator", "trade_executor", "trade_monitor") else "portfolio"
                started = self._started_at.get(loop_key)
            uptime = 0.0
            if running and started:
                uptime = (datetime.now(timezone.utc) - started).total_seconds()

            agents[key] = {
                "name": display_name,
                "type": key,
                "status": "running" if running else "idle",
                "last_run": stats["last_run"],
                "tasks_completed": stats["tasks_completed"],
                "errors": stats["errors"],
                "current_task": stats["current_task"],
                "uptime_seconds": round(uptime, 1),
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
