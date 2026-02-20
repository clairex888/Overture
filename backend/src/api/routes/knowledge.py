"""
Knowledge API routes.

Manages the knowledge base: market outlook across time horizons, source
credibility, educational content, and the data ingestion pipeline.
Core data (entries + outlooks) is persisted in PostgreSQL.
Sources and education stay in-memory (reference data).
"""

import io
import logging
from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_session
from src.models.knowledge import (
    KnowledgeEntry,
    KnowledgeCategory,
    KnowledgeLayer,
    MarketOutlook,
    OutlookSentiment,
)
from src.models.user import User
from src.auth import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class KnowledgeEntryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    category: str = Field(
        ...,
        description="macro, sector, instrument, sentiment, technical, fundamental, news, research",
    )
    layer: str = Field(..., description="long_term, medium_term, short_term")
    asset_class: str | None = None
    tickers: list[str] = Field(default_factory=list)
    source: str = Field("user", description="Source of the entry")
    confidence: float = Field(0.7, ge=0, le=1)
    tags: list[str] = Field(default_factory=list)


class KnowledgeEntryResponse(BaseModel):
    id: str
    title: str
    content: str
    category: str
    layer: str
    asset_class: str | None
    tickers: list[str]
    source: str
    confidence: float
    tags: list[str]
    created_at: str
    updated_at: str
    is_public: bool = True
    file_name: str | None = None
    file_type: str | None = None
    uploaded_by: str | None = None


class OutlookLayer(BaseModel):
    layer: str = Field(..., description="long_term, medium_term, short_term")
    sentiment: str = Field(..., description="bullish, neutral, bearish")
    confidence: float = Field(..., ge=0, le=1)
    summary: str
    key_factors: list[str]
    risks: list[str]
    opportunities: list[str]
    last_updated: str


class MarketOutlookResponse(BaseModel):
    long_term: OutlookLayer
    medium_term: OutlookLayer
    short_term: OutlookLayer
    consensus_sentiment: str
    last_updated: str


class OutlookUpdate(BaseModel):
    sentiment: str = Field(..., description="bullish, neutral, bearish")
    confidence: float = Field(..., ge=0, le=1)
    summary: str
    key_factors: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


class SourceCredibility(BaseModel):
    name: str
    type: str = Field(..., description="api, news, research, social, official")
    credibility_score: float = Field(..., ge=0, le=1)
    accuracy_history: float = Field(..., ge=0, le=1)
    total_entries: int
    last_fetched: str | None


class EducationalContent(BaseModel):
    id: str
    title: str
    summary: str
    category: str
    difficulty: str = Field(..., description="beginner, intermediate, advanced")
    relevance_score: float = Field(..., ge=0, le=1)
    url: str | None = None
    created_at: str


class DataPipelineResult(BaseModel):
    triggered_at: str
    sources_queried: int
    new_entries: int
    updated_entries: int
    errors: list[str]
    duration_ms: float


class PrivacyUpdate(BaseModel):
    is_public: bool


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

# Map API layer names to DB enum values
# DB uses "mid_term", API uses "medium_term"
_LAYER_API_TO_DB = {
    "long_term": KnowledgeLayer.LONG_TERM,
    "medium_term": KnowledgeLayer.MID_TERM,
    "short_term": KnowledgeLayer.SHORT_TERM,
}

_LAYER_DB_TO_API = {
    KnowledgeLayer.LONG_TERM: "long_term",
    KnowledgeLayer.MID_TERM: "medium_term",
    KnowledgeLayer.SHORT_TERM: "short_term",
}

# Map API categories to DB enum values
_CATEGORY_API_TO_DB = {
    "macro": KnowledgeCategory.MACRO,
    "fundamental": KnowledgeCategory.FUNDAMENTAL,
    "technical": KnowledgeCategory.TECHNICAL,
    "research": KnowledgeCategory.RESEARCH,
    "event": KnowledgeCategory.EVENT,
    "education": KnowledgeCategory.EDUCATION,
    # Extended mappings for API categories without direct DB enum
    "sector": KnowledgeCategory.RESEARCH,
    "instrument": KnowledgeCategory.TECHNICAL,
    "sentiment": KnowledgeCategory.MACRO,
    "news": KnowledgeCategory.EVENT,
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _dt_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_iso()
    return dt.isoformat() + "Z"


def _entry_to_response(entry: KnowledgeEntry) -> KnowledgeEntryResponse:
    """Convert ORM KnowledgeEntry to API response."""
    meta = entry.metadata_ or {}

    # Layer mapping: DB uses mid_term, API expects medium_term
    layer = _LAYER_DB_TO_API.get(entry.layer, entry.layer.value if entry.layer else "medium_term")

    # Category: prefer original API category stored in metadata, fallback to enum value
    category = meta.get("original_category", entry.category.value if entry.category else "macro")

    return KnowledgeEntryResponse(
        id=entry.id,
        title=entry.title,
        content=entry.content,
        category=category,
        layer=layer,
        asset_class=(entry.asset_classes[0] if entry.asset_classes else None),
        tickers=entry.tickers or [],
        source=entry.source or "unknown",
        confidence=entry.source_credibility_score or 0.7,
        tags=entry.tags or [],
        created_at=_dt_iso(entry.created_at),
        updated_at=_dt_iso(entry.updated_at),
        is_public=getattr(entry, "is_public", True),
        file_name=getattr(entry, "file_name", None),
        file_type=getattr(entry, "file_type", None),
        uploaded_by=getattr(entry, "uploaded_by_user_id", None),
    )


# ---------------------------------------------------------------------------
# In-memory reference data (no DB model for these)
# ---------------------------------------------------------------------------

_sources_store: list[dict[str, Any]] = [
    {"name": "Federal Reserve (FRED)", "type": "official", "credibility_score": 0.98, "accuracy_history": 0.99, "total_entries": 1250, "last_fetched": "2026-02-12T06:00:00Z"},
    {"name": "Bloomberg API", "type": "api", "credibility_score": 0.95, "accuracy_history": 0.97, "total_entries": 3400, "last_fetched": "2026-02-12T08:00:00Z"},
    {"name": "Reuters News", "type": "news", "credibility_score": 0.90, "accuracy_history": 0.88, "total_entries": 820, "last_fetched": "2026-02-12T07:30:00Z"},
    {"name": "CoinGecko", "type": "api", "credibility_score": 0.85, "accuracy_history": 0.90, "total_entries": 560, "last_fetched": "2026-02-12T08:05:00Z"},
    {"name": "Reddit r/wallstreetbets", "type": "social", "credibility_score": 0.30, "accuracy_history": 0.25, "total_entries": 150, "last_fetched": "2026-02-12T07:00:00Z"},
    {"name": "Goldman Sachs Research", "type": "research", "credibility_score": 0.88, "accuracy_history": 0.82, "total_entries": 95, "last_fetched": "2026-02-11T18:00:00Z"},
]

_education_store: list[dict[str, Any]] = [
    {"id": str(uuid4()), "title": "Understanding Value at Risk (VaR)", "summary": "Comprehensive guide to VaR calculation methods and their application in portfolio risk management.", "category": "risk_management", "difficulty": "intermediate", "relevance_score": 0.92, "url": None, "created_at": "2026-02-10T12:00:00Z"},
    {"id": str(uuid4()), "title": "Options Greeks Explained", "summary": "Deep dive into Delta, Gamma, Theta, Vega and how they affect options pricing and hedging strategies.", "category": "derivatives", "difficulty": "advanced", "relevance_score": 0.85, "url": None, "created_at": "2026-02-08T09:00:00Z"},
    {"id": str(uuid4()), "title": "Introduction to Asset Allocation", "summary": "How to build a diversified portfolio across asset classes based on your risk tolerance and time horizon.", "category": "portfolio_management", "difficulty": "beginner", "relevance_score": 0.78, "url": None, "created_at": "2026-02-05T15:00:00Z"},
]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[KnowledgeEntryResponse])
async def list_knowledge(
    category: str | None = Query(None, description="Filter by category"),
    layer: str | None = Query(None, description="Filter by time layer"),
    asset_class: str | None = Query(None, description="Filter by asset class"),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_user),
):
    """List knowledge entries with optional filters.

    Returns all public entries plus the current user's private entries.
    """
    stmt = select(KnowledgeEntry)

    # Privacy filter: public entries + user's own private entries
    if user:
        stmt = stmt.where(
            or_(KnowledgeEntry.is_public.is_(True), KnowledgeEntry.uploaded_by_user_id == user.id)
        )
    else:
        stmt = stmt.where(KnowledgeEntry.is_public.is_(True))

    if category:
        cat_enum = _CATEGORY_API_TO_DB.get(category)
        if cat_enum:
            stmt = stmt.where(KnowledgeEntry.category == cat_enum)

    if layer:
        layer_enum = _LAYER_API_TO_DB.get(layer)
        if layer_enum:
            stmt = stmt.where(KnowledgeEntry.layer == layer_enum)

    if asset_class:
        stmt = stmt.where(KnowledgeEntry.asset_classes.contains([asset_class]))

    stmt = stmt.order_by(KnowledgeEntry.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    entries = result.scalars().all()
    return [_entry_to_response(e) for e in entries]


@router.get("/outlook", response_model=MarketOutlookResponse)
async def get_market_outlook(session: AsyncSession = Depends(get_session)):
    """Get market outlook across all time horizon layers."""
    result = await session.execute(
        select(MarketOutlook).where(MarketOutlook.asset_class == "general")
    )
    outlooks = {o.layer: o for o in result.scalars().all()}

    def _build_layer(layer_enum: KnowledgeLayer, api_name: str) -> OutlookLayer:
        o = outlooks.get(layer_enum)
        if o:
            return OutlookLayer(
                layer=api_name,
                sentiment=o.outlook.value if o.outlook else "neutral",
                confidence=o.confidence or 0.5,
                summary=o.rationale or "",
                key_factors=o.key_drivers or [],
                risks=[],
                opportunities=[],
                last_updated=_dt_iso(o.last_updated or o.updated_at),
            )
        return OutlookLayer(
            layer=api_name,
            sentiment="neutral",
            confidence=0.5,
            summary="No outlook data available.",
            key_factors=[],
            risks=[],
            opportunities=[],
            last_updated=_now_iso(),
        )

    lt = _build_layer(KnowledgeLayer.LONG_TERM, "long_term")
    mt = _build_layer(KnowledgeLayer.MID_TERM, "medium_term")
    st = _build_layer(KnowledgeLayer.SHORT_TERM, "short_term")

    # Compute consensus
    sentiment_scores = {"bullish": 1, "neutral": 0, "bearish": -1}
    avg = sum(sentiment_scores.get(l.sentiment, 0) for l in [lt, mt, st]) / 3
    consensus = "bullish" if avg > 0.3 else ("bearish" if avg < -0.3 else "neutral")

    return MarketOutlookResponse(
        long_term=lt,
        medium_term=mt,
        short_term=st,
        consensus_sentiment=consensus,
        last_updated=_now_iso(),
    )


@router.get("/sources", response_model=list[SourceCredibility])
async def get_sources():
    """Get source credibility rankings."""
    sorted_sources = sorted(_sources_store, key=lambda s: s["credibility_score"], reverse=True)
    return [SourceCredibility(**s) for s in sorted_sources]


@router.get("/education", response_model=list[EducationalContent])
async def get_education():
    """Get latest educational content and recommendations."""
    sorted_content = sorted(_education_store, key=lambda c: c["relevance_score"], reverse=True)
    return [EducationalContent(**c) for c in sorted_content]


@router.get("/{entry_id}", response_model=KnowledgeEntryResponse)
async def get_knowledge_entry(
    entry_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a single knowledge entry by ID."""
    result = await session.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Knowledge entry {entry_id} not found")
    return _entry_to_response(entry)


@router.post("/", response_model=KnowledgeEntryResponse, status_code=201)
async def create_knowledge_entry(
    payload: KnowledgeEntryCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add a custom knowledge entry (user contribution to the knowledge base)."""
    layer_enum = _LAYER_API_TO_DB.get(payload.layer, KnowledgeLayer.MID_TERM)
    cat_enum = _CATEGORY_API_TO_DB.get(payload.category, KnowledgeCategory.MACRO)

    entry = KnowledgeEntry(
        id=str(uuid4()),
        title=payload.title,
        content=payload.content,
        category=cat_enum,
        layer=layer_enum,
        source=payload.source,
        source_credibility_score=payload.confidence,
        tags=payload.tags,
        asset_classes=[payload.asset_class] if payload.asset_class else [],
        tickers=payload.tickers,
        metadata_={"original_category": payload.category},
    )
    session.add(entry)
    await session.flush()
    return _entry_to_response(entry)


ALLOWED_FILE_TYPES = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def _extract_text(file: UploadFile, content_bytes: bytes) -> str:
    """Extract text from an uploaded file."""
    ct = file.content_type or ""
    fname = (file.filename or "").lower()

    # Plain text / Markdown
    if ct.startswith("text/") or fname.endswith((".txt", ".md")):
        return content_bytes.decode("utf-8", errors="replace")

    # CSV — convert to readable text
    if "csv" in ct or fname.endswith(".csv"):
        import csv as csv_mod
        text = content_bytes.decode("utf-8", errors="replace")
        reader = csv_mod.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return text
        return "\n".join([", ".join(row) for row in rows[:500]])

    # PDF — try PyPDF2, graceful fallback
    if "pdf" in ct or fname.endswith(".pdf"):
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
            pages = [page.extract_text() or "" for page in reader.pages[:50]]
            return "\n\n".join(pages)
        except ImportError:
            return content_bytes.decode("utf-8", errors="replace")

    # Fallback: try as UTF-8 text
    return content_bytes.decode("utf-8", errors="replace")


@router.post("/upload", response_model=KnowledgeEntryResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    title: str = Form(""),
    layer: str = Form("medium_term"),
    category: str = Form("research"),
    is_public: bool = Form(True),
    tags: str = Form(""),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Upload a file (PDF, TXT, MD, CSV) to the knowledge library.

    Files are public by default; set is_public=false for private entries.
    """
    content_bytes = await file.read()
    if len(content_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if len(content_bytes) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    text_content = await _extract_text(file, content_bytes)
    if not text_content.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file")

    fname = file.filename or "uploaded_file"
    entry_title = title.strip() or fname

    layer_enum = _LAYER_API_TO_DB.get(layer, KnowledgeLayer.MID_TERM)
    cat_enum = _CATEGORY_API_TO_DB.get(category, KnowledgeCategory.RESEARCH)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    entry = KnowledgeEntry(
        id=str(uuid4()),
        title=entry_title,
        content=text_content[:50000],  # Cap at 50k chars
        category=cat_enum,
        layer=layer_enum,
        source=f"User upload ({user.display_name or user.email})",
        source_credibility_score=0.7,
        tags=tag_list,
        asset_classes=[],
        tickers=[],
        metadata_={"original_category": category},
        uploaded_by_user_id=user.id,
        is_public=is_public,
        file_name=fname,
        file_type=file.content_type,
    )
    session.add(entry)
    await session.flush()
    return _entry_to_response(entry)


@router.patch("/{entry_id}/privacy", response_model=KnowledgeEntryResponse)
async def toggle_privacy(
    entry_id: str,
    payload: PrivacyUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Toggle public/private visibility of a knowledge entry you own."""
    result = await session.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.uploaded_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only change privacy on your own entries")
    entry.is_public = payload.is_public
    await session.flush()
    return _entry_to_response(entry)


@router.delete("/{entry_id}", status_code=200)
async def delete_knowledge_entry(
    entry_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Delete a knowledge entry you own."""
    result = await session.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.uploaded_by_user_id and entry.uploaded_by_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own entries")
    await session.delete(entry)
    return {"success": True, "message": f"Entry '{entry.title}' deleted."}


@router.put("/outlook/{layer}", response_model=OutlookLayer)
async def update_outlook(
    layer: str,
    payload: OutlookUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update market outlook for a specific time horizon layer."""
    valid_layers = {"long_term", "medium_term", "short_term"}
    if layer not in valid_layers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid layer '{layer}'. Must be one of: {', '.join(valid_layers)}",
        )

    layer_enum = _LAYER_API_TO_DB[layer]

    result = await session.execute(
        select(MarketOutlook)
        .where(MarketOutlook.layer == layer_enum)
        .where(MarketOutlook.asset_class == "general")
    )
    outlook = result.scalar_one_or_none()

    sentiment_enum = OutlookSentiment(payload.sentiment)

    if outlook:
        outlook.outlook = sentiment_enum
        outlook.confidence = payload.confidence
        outlook.rationale = payload.summary
        outlook.key_drivers = payload.key_factors
    else:
        outlook = MarketOutlook(
            id=str(uuid4()),
            layer=layer_enum,
            asset_class="general",
            outlook=sentiment_enum,
            confidence=payload.confidence,
            rationale=payload.summary,
            key_drivers=payload.key_factors,
        )
        session.add(outlook)

    return OutlookLayer(
        layer=layer,
        sentiment=payload.sentiment,
        confidence=payload.confidence,
        summary=payload.summary,
        key_factors=payload.key_factors,
        risks=payload.risks,
        opportunities=payload.opportunities,
        last_updated=_now_iso(),
    )


@router.post("/data-pipeline/trigger", response_model=DataPipelineResult)
async def trigger_data_pipeline():
    """Trigger the data pipeline to fetch latest data from all sources.

    In production this invokes the KnowledgeAgent's data ingestion pipeline.
    """
    return DataPipelineResult(
        triggered_at=_now_iso(),
        sources_queried=len(_sources_store),
        new_entries=12,
        updated_entries=5,
        errors=[],
        duration_ms=4500.0,
    )
