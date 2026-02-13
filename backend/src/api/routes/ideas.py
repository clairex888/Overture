"""
Ideas API routes.

Manages the idea pipeline: generation, validation, execution planning,
and human injection of trading ideas into the Overture system.
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


class Ticker(BaseModel):
    symbol: str
    direction: str = Field(..., description="long or short")
    weight: float | None = Field(None, ge=0, le=1)


class IdeaCreate(BaseModel):
    """Schema for creating a new user-submitted idea."""
    title: str = Field(..., min_length=1, max_length=200)
    thesis: str = Field(..., min_length=1)
    asset_class: str = Field(..., description="equities, fixed_income, crypto, commodities, fx, multi_asset")
    timeframe: str = Field(..., description="short_term, medium_term, long_term")
    tickers: list[Ticker] = Field(default_factory=list)
    conviction: float = Field(0.5, ge=0, le=1, description="Conviction score 0-1")
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class IdeaUpdate(BaseModel):
    """Schema for updating an existing idea."""
    title: str | None = None
    thesis: str | None = None
    asset_class: str | None = None
    timeframe: str | None = None
    tickers: list[Ticker] | None = None
    conviction: float | None = Field(None, ge=0, le=1)
    tags: list[str] | None = None
    notes: str | None = None


class IdeaResponse(BaseModel):
    """Full idea representation returned by the API."""
    id: str
    title: str
    thesis: str
    asset_class: str
    timeframe: str
    tickers: list[Ticker]
    conviction: float
    status: str
    source: str
    tags: list[str]
    notes: str | None
    validation_result: dict[str, Any] | None
    execution_plan: dict[str, Any] | None
    created_at: str
    updated_at: str


class IdeaGenerateRequest(BaseModel):
    """Optional parameters when triggering idea generation."""
    asset_classes: list[str] | None = Field(None, description="Limit to specific asset classes")
    timeframe: str | None = None
    count: int = Field(3, ge=1, le=20, description="Number of ideas to generate")


class IdeaStatsResponse(BaseModel):
    """Pipeline statistics."""
    total: int
    by_status: dict[str, int]
    by_asset_class: dict[str, int]
    by_source: dict[str, int]
    avg_conviction: float


# ---------------------------------------------------------------------------
# In-memory store (swap for DB later)
# ---------------------------------------------------------------------------

_ideas_store: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _idea_to_response(idea: dict[str, Any]) -> IdeaResponse:
    return IdeaResponse(**idea)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=IdeaStatsResponse)
async def get_idea_stats():
    """Return pipeline statistics for all ideas."""
    ideas = list(_ideas_store.values())
    total = len(ideas)

    by_status: dict[str, int] = {}
    by_asset_class: dict[str, int] = {}
    by_source: dict[str, int] = {}
    conviction_sum = 0.0

    for idea in ideas:
        by_status[idea["status"]] = by_status.get(idea["status"], 0) + 1
        by_asset_class[idea["asset_class"]] = by_asset_class.get(idea["asset_class"], 0) + 1
        by_source[idea["source"]] = by_source.get(idea["source"], 0) + 1
        conviction_sum += idea["conviction"]

    return IdeaStatsResponse(
        total=total,
        by_status=by_status,
        by_asset_class=by_asset_class,
        by_source=by_source,
        avg_conviction=conviction_sum / total if total > 0 else 0.0,
    )


@router.get("/", response_model=list[IdeaResponse])
async def list_ideas(
    status: str | None = Query(None, description="Filter by status"),
    asset_class: str | None = Query(None, description="Filter by asset class"),
    timeframe: str | None = Query(None, description="Filter by timeframe"),
    source: str | None = Query(None, description="Filter by source (human, agent)"),
):
    """List all ideas with optional filters."""
    results = list(_ideas_store.values())

    if status:
        results = [i for i in results if i["status"] == status]
    if asset_class:
        results = [i for i in results if i["asset_class"] == asset_class]
    if timeframe:
        results = [i for i in results if i["timeframe"] == timeframe]
    if source:
        results = [i for i in results if i["source"] == source]

    results.sort(key=lambda i: i["created_at"], reverse=True)
    return [_idea_to_response(i) for i in results]


@router.get("/{idea_id}", response_model=IdeaResponse)
async def get_idea(idea_id: str):
    """Get a single idea by ID."""
    idea = _ideas_store.get(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")
    return _idea_to_response(idea)


@router.post("/", response_model=IdeaResponse, status_code=201)
async def create_idea(payload: IdeaCreate):
    """Create a new user-submitted idea (human injects idea into the loop)."""
    idea_id = str(uuid4())
    now = _now_iso()

    idea: dict[str, Any] = {
        "id": idea_id,
        "title": payload.title,
        "thesis": payload.thesis,
        "asset_class": payload.asset_class,
        "timeframe": payload.timeframe,
        "tickers": [t.model_dump() for t in payload.tickers],
        "conviction": payload.conviction,
        "status": "generated",
        "source": "human",
        "tags": payload.tags,
        "notes": payload.notes,
        "validation_result": None,
        "execution_plan": None,
        "created_at": now,
        "updated_at": now,
    }

    _ideas_store[idea_id] = idea
    return _idea_to_response(idea)


@router.post("/generate", response_model=list[IdeaResponse], status_code=201)
async def generate_ideas(payload: IdeaGenerateRequest | None = None):
    """Trigger the idea generation agent to produce new ideas.

    In the prototype this creates placeholder ideas.  In production this
    would invoke the IdeaGenerationAgent asynchronously.
    """
    if payload is None:
        payload = IdeaGenerateRequest()

    generated: list[IdeaResponse] = []
    now = _now_iso()

    for idx in range(payload.count):
        idea_id = str(uuid4())
        asset_class = (payload.asset_classes[idx % len(payload.asset_classes)]
                       if payload.asset_classes else "equities")
        timeframe = payload.timeframe or "medium_term"

        idea: dict[str, Any] = {
            "id": idea_id,
            "title": f"Agent-generated idea #{len(_ideas_store) + 1}",
            "thesis": "Auto-generated thesis pending agent execution.",
            "asset_class": asset_class,
            "timeframe": timeframe,
            "tickers": [],
            "conviction": 0.0,
            "status": "generated",
            "source": "agent",
            "tags": ["auto-generated"],
            "notes": None,
            "validation_result": None,
            "execution_plan": None,
            "created_at": now,
            "updated_at": now,
        }

        _ideas_store[idea_id] = idea
        generated.append(_idea_to_response(idea))

    return generated


@router.post("/{idea_id}/validate", response_model=IdeaResponse)
async def validate_idea(idea_id: str):
    """Trigger validation on a specific idea.

    In production this would invoke the ValidationAgent.  The prototype
    sets a placeholder validation result and moves status to 'validated'.
    """
    idea = _ideas_store.get(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    if idea["status"] not in ("generated",):
        raise HTTPException(
            status_code=400,
            detail=f"Idea must be in 'generated' status to validate, currently '{idea['status']}'",
        )

    idea["validation_result"] = {
        "score": 0.72,
        "risk_assessment": "moderate",
        "market_alignment": "aligned",
        "validated_at": _now_iso(),
        "agent": "validation_agent",
    }
    idea["status"] = "validated"
    idea["updated_at"] = _now_iso()

    return _idea_to_response(idea)


@router.post("/{idea_id}/execute", response_model=IdeaResponse)
async def execute_idea(idea_id: str):
    """Create an execution plan for a validated idea.

    In production this invokes the ExecutionAgent.  The prototype sets a
    placeholder execution plan.
    """
    idea = _ideas_store.get(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    if idea["status"] != "validated":
        raise HTTPException(
            status_code=400,
            detail=f"Idea must be 'validated' to execute, currently '{idea['status']}'",
        )

    idea["execution_plan"] = {
        "trades": [],
        "entry_strategy": "limit_order",
        "position_size_pct": 0.05,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.08,
        "planned_at": _now_iso(),
        "agent": "execution_agent",
    }
    idea["status"] = "executing"
    idea["updated_at"] = _now_iso()

    return _idea_to_response(idea)


@router.put("/{idea_id}", response_model=IdeaResponse)
async def update_idea(idea_id: str, payload: IdeaUpdate):
    """Update an existing idea (e.g., adjust thesis, tickers)."""
    idea = _ideas_store.get(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "tickers" in update_data and update_data["tickers"] is not None:
        update_data["tickers"] = [t.model_dump() if isinstance(t, Ticker) else t for t in update_data["tickers"]]

    for key, value in update_data.items():
        idea[key] = value

    idea["updated_at"] = _now_iso()
    return _idea_to_response(idea)


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(idea_id: str):
    """Delete (archive) an idea from the pipeline."""
    if idea_id not in _ideas_store:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    del _ideas_store[idea_id]
    return None
