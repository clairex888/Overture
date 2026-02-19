"""
Ideas API routes.

Manages the idea pipeline: generation, validation, execution planning,
and human injection of trading ideas into the Overture system.
All data is persisted in PostgreSQL via SQLAlchemy async models.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.idea import Idea, IdeaSource, IdeaStatus, Timeframe

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas (match frontend expectations)
# ---------------------------------------------------------------------------


class Ticker(BaseModel):
    symbol: str
    direction: str = Field(..., description="long or short")
    weight: float | None = Field(None, ge=0, le=1)


class IdeaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    thesis: str = Field(..., min_length=1)
    asset_class: str = Field(..., description="equities, fixed_income, crypto, commodities, fx, multi_asset")
    timeframe: str = Field(..., description="short_term, medium_term, long_term")
    tickers: list[Ticker] = Field(default_factory=list)
    conviction: float = Field(0.5, ge=0, le=1, description="Conviction score 0-1")
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class IdeaUpdate(BaseModel):
    title: str | None = None
    thesis: str | None = None
    asset_class: str | None = None
    timeframe: str | None = None
    tickers: list[Ticker] | None = None
    conviction: float | None = Field(None, ge=0, le=1)
    tags: list[str] | None = None
    notes: str | None = None


class IdeaResponse(BaseModel):
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
    asset_classes: list[str] | None = Field(None, description="Limit to specific asset classes")
    timeframe: str | None = None
    count: int = Field(3, ge=1, le=20, description="Number of ideas to generate")


class IdeaStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_asset_class: dict[str, int]
    by_source: dict[str, int]
    avg_conviction: float


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

_SOURCE_TO_API = {
    IdeaSource.USER: "human",
    IdeaSource.AGENT: "agent",
    IdeaSource.NEWS: "news",
    IdeaSource.SCREEN: "screen",
    IdeaSource.AGGREGATED: "aggregated",
}

_API_TO_SOURCE = {v: k for k, v in _SOURCE_TO_API.items()}

_TIMEFRAME_MAP = {
    "short_term": Timeframe.SHORT_TERM,
    "medium_term": Timeframe.MEDIUM_TERM,
    "long_term": Timeframe.LONG_TERM,
    "intraday": Timeframe.INTRADAY,
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _dt_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_iso()
    return dt.isoformat() + "Z"


def _idea_to_response(idea: Idea) -> IdeaResponse:
    """Convert ORM Idea to API response."""
    meta = idea.metadata_ or {}

    # Tickers stored as JSON list of {symbol, direction, weight}
    raw_tickers = idea.tickers or []
    tickers = []
    for t in raw_tickers:
        if isinstance(t, dict):
            tickers.append(Ticker(**t))
        elif isinstance(t, str):
            tickers.append(Ticker(symbol=t, direction="long", weight=1.0))

    source_str = _SOURCE_TO_API.get(idea.source, idea.source.value if idea.source else "agent")
    tf = idea.timeframe.value if idea.timeframe else "medium_term"

    return IdeaResponse(
        id=idea.id,
        title=idea.title,
        thesis=idea.thesis or idea.description or "",
        asset_class=idea.asset_class or "equities",
        timeframe=tf,
        tickers=tickers,
        conviction=idea.confidence_score or 0.0,
        status=idea.status.value if idea.status else "generated",
        source=source_str,
        tags=meta.get("tags", []),
        notes=meta.get("notes"),
        validation_result=idea.validation_results,
        execution_plan=meta.get("execution_plan"),
        created_at=_dt_iso(idea.created_at),
        updated_at=_dt_iso(idea.updated_at),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=IdeaStatsResponse)
async def get_idea_stats(session: AsyncSession = Depends(get_session)):
    """Return pipeline statistics for all ideas."""
    result = await session.execute(select(Idea))
    ideas = result.scalars().all()

    total = len(ideas)
    by_status: dict[str, int] = {}
    by_asset_class: dict[str, int] = {}
    by_source: dict[str, int] = {}
    conviction_sum = 0.0

    for idea in ideas:
        status = idea.status.value if idea.status else "generated"
        by_status[status] = by_status.get(status, 0) + 1

        ac = idea.asset_class or "unknown"
        by_asset_class[ac] = by_asset_class.get(ac, 0) + 1

        source = _SOURCE_TO_API.get(idea.source, "agent")
        by_source[source] = by_source.get(source, 0) + 1

        conviction_sum += idea.confidence_score or 0

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
    session: AsyncSession = Depends(get_session),
):
    """List all ideas with optional filters."""
    stmt = select(Idea)

    if status:
        try:
            status_enum = IdeaStatus(status)
            stmt = stmt.where(Idea.status == status_enum)
        except ValueError:
            pass

    if asset_class:
        stmt = stmt.where(Idea.asset_class == asset_class)

    if timeframe:
        tf_enum = _TIMEFRAME_MAP.get(timeframe)
        if tf_enum:
            stmt = stmt.where(Idea.timeframe == tf_enum)

    if source:
        src_enum = _API_TO_SOURCE.get(source)
        if src_enum:
            stmt = stmt.where(Idea.source == src_enum)

    stmt = stmt.order_by(Idea.created_at.desc())
    result = await session.execute(stmt)
    ideas = result.scalars().all()
    return [_idea_to_response(i) for i in ideas]


@router.get("/{idea_id}", response_model=IdeaResponse)
async def get_idea(idea_id: str, session: AsyncSession = Depends(get_session)):
    """Get a single idea by ID."""
    result = await session.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")
    return _idea_to_response(idea)


@router.post("/", response_model=IdeaResponse, status_code=201)
async def create_idea(
    payload: IdeaCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new user-submitted idea (human injects idea into the loop)."""
    tf_enum = _TIMEFRAME_MAP.get(payload.timeframe, Timeframe.MEDIUM_TERM)

    idea = Idea(
        id=str(uuid4()),
        title=payload.title,
        thesis=payload.thesis,
        description=payload.thesis,
        source=IdeaSource.USER,
        asset_class=payload.asset_class,
        tickers=[t.model_dump() for t in payload.tickers],
        status=IdeaStatus.GENERATED,
        confidence_score=payload.conviction,
        timeframe=tf_enum,
        metadata_={
            "tags": payload.tags,
            "notes": payload.notes,
        },
    )
    session.add(idea)
    await session.flush()
    return _idea_to_response(idea)


@router.post("/generate", response_model=list[IdeaResponse], status_code=201)
async def generate_ideas(
    payload: IdeaGenerateRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Trigger the idea generation agent to produce new ideas.

    In the prototype this creates placeholder ideas. In production this
    would invoke the IdeaGenerationAgent asynchronously.
    """
    if payload is None:
        payload = IdeaGenerateRequest()

    count_result = await session.execute(select(func.count()).select_from(Idea))
    existing_count = count_result.scalar() or 0

    generated: list[IdeaResponse] = []
    for idx in range(payload.count):
        asset_class = (
            payload.asset_classes[idx % len(payload.asset_classes)]
            if payload.asset_classes
            else "equities"
        )
        tf_enum = _TIMEFRAME_MAP.get(payload.timeframe or "medium_term", Timeframe.MEDIUM_TERM)

        idea = Idea(
            id=str(uuid4()),
            title=f"Agent-generated idea #{existing_count + idx + 1}",
            thesis="Auto-generated thesis pending agent execution.",
            description="Auto-generated thesis pending agent execution.",
            source=IdeaSource.AGENT,
            asset_class=asset_class,
            tickers=[],
            status=IdeaStatus.GENERATED,
            confidence_score=0.0,
            timeframe=tf_enum,
            metadata_={"tags": ["auto-generated"]},
        )
        session.add(idea)
        await session.flush()
        generated.append(_idea_to_response(idea))

    return generated


@router.post("/{idea_id}/validate", response_model=IdeaResponse)
async def validate_idea(
    idea_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Trigger validation on a specific idea."""
    result = await session.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    if idea.status != IdeaStatus.GENERATED:
        raise HTTPException(
            status_code=400,
            detail=f"Idea must be in 'generated' status to validate, currently '{idea.status.value}'",
        )

    idea.validation_results = {
        "score": 0.72,
        "risk_assessment": "moderate",
        "market_alignment": "aligned",
        "validated_at": _now_iso(),
        "agent": "validation_agent",
    }
    idea.status = IdeaStatus.VALIDATED
    return _idea_to_response(idea)


@router.post("/{idea_id}/execute", response_model=IdeaResponse)
async def execute_idea(
    idea_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Create an execution plan for a validated idea."""
    result = await session.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    if idea.status != IdeaStatus.VALIDATED:
        raise HTTPException(
            status_code=400,
            detail=f"Idea must be 'validated' to execute, currently '{idea.status.value}'",
        )

    meta = dict(idea.metadata_ or {})
    meta["execution_plan"] = {
        "trades": [],
        "entry_strategy": "limit_order",
        "position_size_pct": 0.05,
        "stop_loss_pct": 0.03,
        "take_profit_pct": 0.08,
        "planned_at": _now_iso(),
        "agent": "execution_agent",
    }
    idea.metadata_ = meta
    idea.status = IdeaStatus.EXECUTING
    return _idea_to_response(idea)


@router.put("/{idea_id}", response_model=IdeaResponse)
async def update_idea(
    idea_id: str,
    payload: IdeaUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update an existing idea (e.g., adjust thesis, tickers)."""
    result = await session.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "title" in update_data:
        idea.title = update_data["title"]
    if "thesis" in update_data:
        idea.thesis = update_data["thesis"]
        idea.description = update_data["thesis"]
    if "asset_class" in update_data:
        idea.asset_class = update_data["asset_class"]
    if "timeframe" in update_data:
        tf_enum = _TIMEFRAME_MAP.get(update_data["timeframe"], Timeframe.MEDIUM_TERM)
        idea.timeframe = tf_enum
    if "tickers" in update_data and update_data["tickers"] is not None:
        idea.tickers = [
            t.model_dump() if isinstance(t, Ticker) else t
            for t in update_data["tickers"]
        ]
    if "conviction" in update_data:
        idea.confidence_score = update_data["conviction"]

    meta = dict(idea.metadata_ or {})
    if "tags" in update_data:
        meta["tags"] = update_data["tags"]
    if "notes" in update_data:
        meta["notes"] = update_data["notes"]
    idea.metadata_ = meta

    return _idea_to_response(idea)


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(
    idea_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Delete (archive) an idea from the pipeline."""
    result = await session.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")

    await session.delete(idea)
    return None
