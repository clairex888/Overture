"""
Agents API routes.

Provides visibility into and control over the autonomous agent system:
status monitoring, activity logs, loop control, and task management.

Connected to the real AgentEngine singleton which manages LangGraph-based
idea and portfolio loops with parallel specialized agents.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime, timezone
from uuid import uuid4

try:
    from src.agents.engine import agent_engine
    _engine_ok = True
except Exception:
    agent_engine = None  # type: ignore[assignment]
    _engine_ok = False

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AgentStatus(BaseModel):
    name: str
    display_name: str
    status: str = Field(..., description="running, idle, error, stopped")
    current_task: str | None
    last_run: str | None
    run_count: int
    error_count: int
    uptime_seconds: float


class AllAgentsStatus(BaseModel):
    agents: list[AgentStatus]
    idea_loop_running: bool
    portfolio_loop_running: bool
    last_updated: str


class AgentLogEntry(BaseModel):
    id: str
    timestamp: str
    agent_name: str
    action: str
    status: str = Field(..., description="started, completed, failed, skipped")
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class LoopControlResponse(BaseModel):
    loop: str
    action: str
    success: bool
    message: str
    timestamp: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat() + "Z"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _require_engine():
    """Raise 503 if agent engine is not available."""
    if not _engine_ok or agent_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Agent engine unavailable. Check server logs for dependency issues.",
        )


@router.get("/status", response_model=AllAgentsStatus)
async def get_agents_status():
    """Get the status of all agents."""
    if not _engine_ok or agent_engine is None:
        return AllAgentsStatus(
            agents=[],
            idea_loop_running=False,
            portfolio_loop_running=False,
            last_updated=_now_iso(),
        )
    engine_status = agent_engine.get_agent_statuses()
    agents_data = engine_status.get("agents", {})

    agents: list[AgentStatus] = []
    for key, data in agents_data.items():
        agents.append(AgentStatus(
            name=key,
            display_name=data.get("name", key),
            status=data.get("status", "idle"),
            current_task=data.get("current_task"),
            last_run=data.get("last_run"),
            run_count=data.get("tasks_completed", 0),
            error_count=data.get("errors", 0),
            uptime_seconds=data.get("uptime_seconds", 0.0),
        ))

    return AllAgentsStatus(
        agents=agents,
        idea_loop_running=engine_status.get("idea_loop_running", False),
        portfolio_loop_running=engine_status.get("portfolio_loop_running", False),
        last_updated=_now_iso(),
    )


@router.get("/logs", response_model=list[AgentLogEntry])
async def get_agent_logs(
    agent_type: str | None = Query(None, description="Filter by agent name"),
    action: str | None = Query(None, description="Filter by action type"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500),
):
    """Get recent agent activity logs."""
    logs = agent_engine.get_logs(limit=limit)

    results = []
    for msg in logs:
        entry = {
            "id": str(uuid4()),
            "timestamp": msg.get("timestamp", _now_iso()),
            "agent_name": msg.get("agent", "unknown"),
            "action": msg.get("node", msg.get("summary", "unknown")),
            "status": "completed",
            "details": {"summary": msg.get("summary", ""), "notes": msg.get("notes", "")},
            "duration_ms": None,
        }
        results.append(entry)

    if agent_type:
        results = [r for r in results if agent_type in r["agent_name"].lower()]
    if action:
        results = [r for r in results if action in r["action"]]
    if status:
        results = [r for r in results if r["status"] == status]

    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return [AgentLogEntry(**r) for r in results[:limit]]


@router.get("/logs/{agent_name}", response_model=list[AgentLogEntry])
async def get_agent_logs_by_name(
    agent_name: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Get logs for a specific agent."""
    logs = agent_engine.get_logs(limit=limit * 2)
    results = []
    for msg in logs:
        agent = msg.get("agent", "")
        if agent_name.lower() in agent.lower():
            results.append(AgentLogEntry(
                id=str(uuid4()),
                timestamp=msg.get("timestamp", _now_iso()),
                agent_name=agent,
                action=msg.get("node", ""),
                status="completed",
                details={"summary": msg.get("summary", "")},
                duration_ms=None,
            ))

    results.sort(key=lambda r: r.timestamp, reverse=True)
    return results[:limit]


@router.post("/idea-loop/start", response_model=LoopControlResponse)
async def start_idea_loop():
    """Start the autonomous idea generation loop with parallel agents.

    This starts:
    - 4 parallel generators (macro, industry, crypto, quant)
    - 4 parallel validators (backtest, fundamental, reasoning, data)
    - Trade execution planning
    - Active trade monitoring
    """
    _require_engine()
    result = await agent_engine.start_idea_loop()

    already_running = result.get("status") == "already_running"
    return LoopControlResponse(
        loop="idea_loop",
        action="start",
        success=not already_running,
        message=(
            "Idea loop is already running." if already_running
            else f"Idea loop started (interval={result.get('interval_seconds', 60)}s). "
                 "4 parallel generators + 4 parallel validators active."
        ),
        timestamp=_now_iso(),
    )


@router.post("/idea-loop/stop", response_model=LoopControlResponse)
async def stop_idea_loop():
    """Stop the idea generation loop."""
    _require_engine()
    result = await agent_engine.stop_idea_loop()

    return LoopControlResponse(
        loop="idea_loop",
        action="stop",
        success=True,
        message=f"Idea loop stopped after {result.get('iterations', 0)} iterations.",
        timestamp=_now_iso(),
    )


@router.post("/portfolio-loop/start", response_model=LoopControlResponse)
async def start_portfolio_loop():
    """Start the portfolio management loop.

    This starts:
    - Portfolio assessment and allocation
    - Risk monitoring and alert generation
    - Drift detection and rebalancing
    - Cross-loop sync with idea loop
    """
    _require_engine()
    result = await agent_engine.start_portfolio_loop()

    already_running = result.get("status") == "already_running"
    return LoopControlResponse(
        loop="portfolio_loop",
        action="start",
        success=not already_running,
        message=(
            "Portfolio loop is already running." if already_running
            else f"Portfolio loop started (interval={result.get('interval_seconds', 300)}s)."
        ),
        timestamp=_now_iso(),
    )


@router.post("/portfolio-loop/stop", response_model=LoopControlResponse)
async def stop_portfolio_loop():
    """Stop the portfolio management loop."""
    _require_engine()
    result = await agent_engine.stop_portfolio_loop()

    return LoopControlResponse(
        loop="portfolio_loop",
        action="stop",
        success=True,
        message=f"Portfolio loop stopped after {result.get('iterations', 0)} iterations.",
        timestamp=_now_iso(),
    )


@router.get("/system-status")
async def get_system_status():
    """Get comprehensive system status including both loops."""
    return agent_engine.get_status()


@router.get("/pending-approvals")
async def get_pending_approvals():
    """Get trade plans awaiting human approval."""
    return agent_engine.get_pending_approvals()


@router.post("/approve/{plan_id}")
async def approve_trade_plan(plan_id: str, adjustments: dict[str, Any] | None = None):
    """Approve a pending trade plan."""
    result = await agent_engine.approve_trade(plan_id, adjustments)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/reject/{plan_id}")
async def reject_trade_plan(plan_id: str, reason: str = ""):
    """Reject a pending trade plan."""
    result = await agent_engine.reject_trade(plan_id, reason)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/alerts")
async def get_agent_alerts():
    """Get active alerts from agent loops."""
    return agent_engine.get_alerts()


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_agent_alert(alert_id: str):
    """Dismiss an agent alert."""
    dismissed = agent_engine.dismiss_alert(alert_id)
    if not dismissed:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return {"status": "dismissed", "alert_id": alert_id}
