"""
Agents API routes.

Provides visibility into and control over the autonomous agent system:
status monitoring, activity logs, loop control, and task management.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

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


class AgentTask(BaseModel):
    id: str
    agent_name: str
    task_type: str
    status: str = Field(..., description="pending, running, completed, failed, cancelled")
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class LoopControlResponse(BaseModel):
    loop: str
    action: str
    success: bool
    message: str
    timestamp: str


class TaskCancelResponse(BaseModel):
    task_id: str
    previous_status: str
    new_status: str
    message: str


# ---------------------------------------------------------------------------
# In-memory stores (swap for DB / message bus later)
# ---------------------------------------------------------------------------

_loop_state: dict[str, bool] = {
    "idea_loop": False,
    "portfolio_loop": False,
}

_agent_statuses: dict[str, dict[str, Any]] = {
    "idea_generation": {
        "name": "idea_generation",
        "display_name": "Idea Generation Agent",
        "status": "idle",
        "current_task": None,
        "last_run": "2026-02-12T08:00:00Z",
        "run_count": 47,
        "error_count": 2,
        "uptime_seconds": 86400.0,
    },
    "validation": {
        "name": "validation",
        "display_name": "Validation Agent",
        "status": "idle",
        "current_task": None,
        "last_run": "2026-02-12T08:05:00Z",
        "run_count": 35,
        "error_count": 1,
        "uptime_seconds": 86400.0,
    },
    "risk_management": {
        "name": "risk_management",
        "display_name": "Risk Management Agent",
        "status": "idle",
        "current_task": None,
        "last_run": "2026-02-12T08:10:00Z",
        "run_count": 120,
        "error_count": 0,
        "uptime_seconds": 86400.0,
    },
    "execution": {
        "name": "execution",
        "display_name": "Execution Agent",
        "status": "idle",
        "current_task": None,
        "last_run": "2026-02-12T07:55:00Z",
        "run_count": 28,
        "error_count": 3,
        "uptime_seconds": 86400.0,
    },
    "portfolio_management": {
        "name": "portfolio_management",
        "display_name": "Portfolio Management Agent",
        "status": "idle",
        "current_task": None,
        "last_run": "2026-02-12T08:00:00Z",
        "run_count": 52,
        "error_count": 1,
        "uptime_seconds": 86400.0,
    },
    "knowledge": {
        "name": "knowledge",
        "display_name": "Knowledge Agent",
        "status": "idle",
        "current_task": None,
        "last_run": "2026-02-12T07:45:00Z",
        "run_count": 200,
        "error_count": 5,
        "uptime_seconds": 86400.0,
    },
}

_agent_logs: list[dict[str, Any]] = [
    {
        "id": str(uuid4()),
        "timestamp": "2026-02-12T08:10:00Z",
        "agent_name": "risk_management",
        "action": "portfolio_risk_check",
        "status": "completed",
        "details": {"var_95": 15200, "alerts": 0},
        "duration_ms": 1250.0,
    },
    {
        "id": str(uuid4()),
        "timestamp": "2026-02-12T08:05:00Z",
        "agent_name": "validation",
        "action": "validate_idea",
        "status": "completed",
        "details": {"idea_id": "sample-1", "score": 0.72},
        "duration_ms": 3400.0,
    },
    {
        "id": str(uuid4()),
        "timestamp": "2026-02-12T08:00:00Z",
        "agent_name": "idea_generation",
        "action": "generate_ideas",
        "status": "completed",
        "details": {"count": 3, "asset_classes": ["equities", "crypto"]},
        "duration_ms": 8500.0,
    },
    {
        "id": str(uuid4()),
        "timestamp": "2026-02-12T07:55:00Z",
        "agent_name": "execution",
        "action": "execute_trade",
        "status": "failed",
        "details": {"error": "Insufficient margin for position size"},
        "duration_ms": 450.0,
    },
]

_agent_tasks: dict[str, dict[str, Any]] = {}

# Seed a pending task
_sample_task_id = str(uuid4())
_agent_tasks[_sample_task_id] = {
    "id": _sample_task_id,
    "agent_name": "idea_generation",
    "task_type": "generate_ideas",
    "status": "pending",
    "payload": {"asset_classes": ["equities"], "count": 5},
    "result": None,
    "created_at": "2026-02-12T08:15:00Z",
    "started_at": None,
    "completed_at": None,
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=AllAgentsStatus)
async def get_agents_status():
    """Get the status of all agents (running, idle, error, stopped)."""
    return AllAgentsStatus(
        agents=[AgentStatus(**a) for a in _agent_statuses.values()],
        idea_loop_running=_loop_state["idea_loop"],
        portfolio_loop_running=_loop_state["portfolio_loop"],
        last_updated=_now_iso(),
    )


@router.get("/logs", response_model=list[AgentLogEntry])
async def get_agent_logs(
    agent_type: str | None = Query(None, description="Filter by agent name"),
    action: str | None = Query(None, description="Filter by action type"),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500),
):
    """Get recent agent activity logs with optional filters."""
    results = list(_agent_logs)

    if agent_type:
        results = [l for l in results if l["agent_name"] == agent_type]
    if action:
        results = [l for l in results if l["action"] == action]
    if status:
        results = [l for l in results if l["status"] == status]

    results.sort(key=lambda l: l["timestamp"], reverse=True)
    return [AgentLogEntry(**l) for l in results[:limit]]


@router.get("/logs/{agent_name}", response_model=list[AgentLogEntry])
async def get_agent_logs_by_name(
    agent_name: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Get logs for a specific agent."""
    if agent_name not in _agent_statuses:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")

    results = [l for l in _agent_logs if l["agent_name"] == agent_name]
    results.sort(key=lambda l: l["timestamp"], reverse=True)
    return [AgentLogEntry(**l) for l in results[:limit]]


@router.post("/idea-loop/start", response_model=LoopControlResponse)
async def start_idea_loop():
    """Start the autonomous idea generation/validation loop.

    In production this starts a background asyncio task that periodically
    runs the IdeaGenerationAgent and ValidationAgent.
    """
    if _loop_state["idea_loop"]:
        return LoopControlResponse(
            loop="idea_loop",
            action="start",
            success=False,
            message="Idea loop is already running.",
            timestamp=_now_iso(),
        )

    _loop_state["idea_loop"] = True
    _agent_statuses["idea_generation"]["status"] = "running"
    _agent_statuses["validation"]["status"] = "running"

    log_entry = {
        "id": str(uuid4()),
        "timestamp": _now_iso(),
        "agent_name": "idea_generation",
        "action": "loop_started",
        "status": "completed",
        "details": {"loop": "idea_loop"},
        "duration_ms": None,
    }
    _agent_logs.insert(0, log_entry)

    return LoopControlResponse(
        loop="idea_loop",
        action="start",
        success=True,
        message="Idea loop started successfully.",
        timestamp=_now_iso(),
    )


@router.post("/idea-loop/stop", response_model=LoopControlResponse)
async def stop_idea_loop():
    """Stop the idea generation/validation loop."""
    if not _loop_state["idea_loop"]:
        return LoopControlResponse(
            loop="idea_loop",
            action="stop",
            success=False,
            message="Idea loop is not running.",
            timestamp=_now_iso(),
        )

    _loop_state["idea_loop"] = False
    _agent_statuses["idea_generation"]["status"] = "idle"
    _agent_statuses["validation"]["status"] = "idle"

    log_entry = {
        "id": str(uuid4()),
        "timestamp": _now_iso(),
        "agent_name": "idea_generation",
        "action": "loop_stopped",
        "status": "completed",
        "details": {"loop": "idea_loop"},
        "duration_ms": None,
    }
    _agent_logs.insert(0, log_entry)

    return LoopControlResponse(
        loop="idea_loop",
        action="stop",
        success=True,
        message="Idea loop stopped successfully.",
        timestamp=_now_iso(),
    )


@router.post("/portfolio-loop/start", response_model=LoopControlResponse)
async def start_portfolio_loop():
    """Start the portfolio management/risk monitoring loop."""
    if _loop_state["portfolio_loop"]:
        return LoopControlResponse(
            loop="portfolio_loop",
            action="start",
            success=False,
            message="Portfolio loop is already running.",
            timestamp=_now_iso(),
        )

    _loop_state["portfolio_loop"] = True
    _agent_statuses["portfolio_management"]["status"] = "running"
    _agent_statuses["risk_management"]["status"] = "running"

    log_entry = {
        "id": str(uuid4()),
        "timestamp": _now_iso(),
        "agent_name": "portfolio_management",
        "action": "loop_started",
        "status": "completed",
        "details": {"loop": "portfolio_loop"},
        "duration_ms": None,
    }
    _agent_logs.insert(0, log_entry)

    return LoopControlResponse(
        loop="portfolio_loop",
        action="start",
        success=True,
        message="Portfolio loop started successfully.",
        timestamp=_now_iso(),
    )


@router.post("/portfolio-loop/stop", response_model=LoopControlResponse)
async def stop_portfolio_loop():
    """Stop the portfolio management/risk monitoring loop."""
    if not _loop_state["portfolio_loop"]:
        return LoopControlResponse(
            loop="portfolio_loop",
            action="stop",
            success=False,
            message="Portfolio loop is not running.",
            timestamp=_now_iso(),
        )

    _loop_state["portfolio_loop"] = False
    _agent_statuses["portfolio_management"]["status"] = "idle"
    _agent_statuses["risk_management"]["status"] = "idle"

    log_entry = {
        "id": str(uuid4()),
        "timestamp": _now_iso(),
        "agent_name": "portfolio_management",
        "action": "loop_stopped",
        "status": "completed",
        "details": {"loop": "portfolio_loop"},
        "duration_ms": None,
    }
    _agent_logs.insert(0, log_entry)

    return LoopControlResponse(
        loop="portfolio_loop",
        action="stop",
        success=True,
        message="Portfolio loop stopped successfully.",
        timestamp=_now_iso(),
    )


@router.get("/tasks", response_model=list[AgentTask])
async def get_agent_tasks(
    status: str | None = Query(None, description="Filter by task status"),
):
    """Get pending and running agent tasks."""
    tasks = list(_agent_tasks.values())

    if status:
        tasks = [t for t in tasks if t["status"] == status]
    else:
        # Default: show pending and running only
        tasks = [t for t in tasks if t["status"] in ("pending", "running")]

    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    return [AgentTask(**t) for t in tasks]


@router.post("/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_agent_task(task_id: str):
    """Cancel a pending or running agent task."""
    task = _agent_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    cancellable = {"pending", "running"}
    if task["status"] not in cancellable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task in '{task['status']}' status",
        )

    previous = task["status"]
    task["status"] = "cancelled"
    task["completed_at"] = _now_iso()

    return TaskCancelResponse(
        task_id=task_id,
        previous_status=previous,
        new_status="cancelled",
        message=f"Task {task_id} cancelled successfully.",
    )
