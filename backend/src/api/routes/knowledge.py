"""
Knowledge API routes.

Manages the knowledge base: market outlook across time horizons, source
credibility, educational content, and the data ingestion pipeline.
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


class KnowledgeEntryCreate(BaseModel):
    """Schema for creating a new knowledge entry."""
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


class OutlookLayer(BaseModel):
    layer: str = Field(..., description="long_term, medium_term, short_term")
    sentiment: str = Field(..., description="bullish, neutral, bearish")
    confidence: float = Field(..., ge=0, le=1)
    summary: str
    key_factors: list[str]
    risks: list[str]
    opportunities: list[str]
    last_updated: str


class MarketOutlook(BaseModel):
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


# ---------------------------------------------------------------------------
# In-memory stores (swap for DB later)
# ---------------------------------------------------------------------------

_knowledge_store: dict[str, dict[str, Any]] = {}

_outlook_store: dict[str, dict[str, Any]] = {
    "long_term": {
        "layer": "long_term",
        "sentiment": "bullish",
        "confidence": 0.65,
        "summary": "Structural AI/tech adoption and easing cycle support multi-year equity growth. Fixed income attractive at current yields.",
        "key_factors": [
            "AI productivity revolution",
            "Global easing cycle underway",
            "Strong US corporate earnings trajectory",
            "Demographics shifting in emerging markets",
        ],
        "risks": [
            "Geopolitical fragmentation",
            "Debt sustainability concerns",
            "AI regulation overshoot",
        ],
        "opportunities": [
            "AI infrastructure buildout",
            "Green energy transition",
            "Emerging market consumption growth",
        ],
        "last_updated": "2026-02-12T06:00:00Z",
    },
    "medium_term": {
        "layer": "medium_term",
        "sentiment": "neutral",
        "confidence": 0.55,
        "summary": "Mixed signals: earnings growth solid but valuations stretched. Watching Fed trajectory and geopolitical developments.",
        "key_factors": [
            "Fed rate path uncertainty",
            "Q4 earnings season results",
            "Geopolitical tensions in multiple regions",
            "Credit spreads tightening",
        ],
        "risks": [
            "Sticky inflation resurgence",
            "Liquidity withdrawal acceleration",
            "Earnings growth deceleration",
        ],
        "opportunities": [
            "Sector rotation into value",
            "Fixed income duration extension",
            "Commodity supercycle continuation",
        ],
        "last_updated": "2026-02-12T06:00:00Z",
    },
    "short_term": {
        "layer": "short_term",
        "sentiment": "bearish",
        "confidence": 0.60,
        "summary": "Near-term caution warranted. Technical overbought signals, upcoming CPI data, and options expiration could trigger volatility.",
        "key_factors": [
            "SPX at technical resistance",
            "VIX suppressed to extreme lows",
            "CPI release this week",
            "Large options expiration Friday",
        ],
        "risks": [
            "CPI upside surprise",
            "VIX spike from compressed levels",
            "Crowded positioning unwind",
        ],
        "opportunities": [
            "Volatility selling on spike",
            "Hedging at low cost",
            "Crypto momentum continuation",
        ],
        "last_updated": "2026-02-12T08:00:00Z",
    },
}

_sources_store: list[dict[str, Any]] = [
    {
        "name": "Federal Reserve (FRED)",
        "type": "official",
        "credibility_score": 0.98,
        "accuracy_history": 0.99,
        "total_entries": 1250,
        "last_fetched": "2026-02-12T06:00:00Z",
    },
    {
        "name": "Bloomberg API",
        "type": "api",
        "credibility_score": 0.95,
        "accuracy_history": 0.97,
        "total_entries": 3400,
        "last_fetched": "2026-02-12T08:00:00Z",
    },
    {
        "name": "Reuters News",
        "type": "news",
        "credibility_score": 0.90,
        "accuracy_history": 0.88,
        "total_entries": 820,
        "last_fetched": "2026-02-12T07:30:00Z",
    },
    {
        "name": "CoinGecko",
        "type": "api",
        "credibility_score": 0.85,
        "accuracy_history": 0.90,
        "total_entries": 560,
        "last_fetched": "2026-02-12T08:05:00Z",
    },
    {
        "name": "Reddit r/wallstreetbets",
        "type": "social",
        "credibility_score": 0.30,
        "accuracy_history": 0.25,
        "total_entries": 150,
        "last_fetched": "2026-02-12T07:00:00Z",
    },
    {
        "name": "Goldman Sachs Research",
        "type": "research",
        "credibility_score": 0.88,
        "accuracy_history": 0.82,
        "total_entries": 95,
        "last_fetched": "2026-02-11T18:00:00Z",
    },
]

_education_store: list[dict[str, Any]] = [
    {
        "id": str(uuid4()),
        "title": "Understanding Value at Risk (VaR)",
        "summary": "Comprehensive guide to VaR calculation methods and their application in portfolio risk management.",
        "category": "risk_management",
        "difficulty": "intermediate",
        "relevance_score": 0.92,
        "url": None,
        "created_at": "2026-02-10T12:00:00Z",
    },
    {
        "id": str(uuid4()),
        "title": "Options Greeks Explained",
        "summary": "Deep dive into Delta, Gamma, Theta, Vega and how they affect options pricing and hedging strategies.",
        "category": "derivatives",
        "difficulty": "advanced",
        "relevance_score": 0.85,
        "url": None,
        "created_at": "2026-02-08T09:00:00Z",
    },
    {
        "id": str(uuid4()),
        "title": "Introduction to Asset Allocation",
        "summary": "How to build a diversified portfolio across asset classes based on your risk tolerance and time horizon.",
        "category": "portfolio_management",
        "difficulty": "beginner",
        "relevance_score": 0.78,
        "url": None,
        "created_at": "2026-02-05T15:00:00Z",
    },
]

# Seed a few knowledge entries
_seed_entries = [
    {
        "id": str(uuid4()),
        "title": "Fed signals patience on rate cuts amid persistent services inflation",
        "content": "Federal Reserve minutes from January meeting reveal committee members prefer to wait for more data before cutting rates further. Services inflation remains sticky at 3.8% annualized.",
        "category": "macro",
        "layer": "medium_term",
        "asset_class": None,
        "tickers": [],
        "source": "reuters",
        "confidence": 0.92,
        "tags": ["fed", "rates", "inflation"],
        "created_at": "2026-02-11T14:00:00Z",
        "updated_at": "2026-02-11T14:00:00Z",
    },
    {
        "id": str(uuid4()),
        "title": "NVIDIA earnings beat expectations, guidance strong on AI demand",
        "content": "NVIDIA reported Q4 earnings of $5.16 per share vs $4.80 expected. Revenue guidance for Q1 2026 at $28B, above consensus of $26.5B. Data center revenue grew 85% YoY.",
        "category": "fundamental",
        "layer": "short_term",
        "asset_class": "equities",
        "tickers": ["NVDA"],
        "source": "bloomberg",
        "confidence": 0.98,
        "tags": ["earnings", "ai", "semiconductors"],
        "created_at": "2026-02-10T21:00:00Z",
        "updated_at": "2026-02-10T21:00:00Z",
    },
    {
        "id": str(uuid4()),
        "title": "Bitcoin ETF inflows accelerate to record levels",
        "content": "Spot Bitcoin ETFs saw $2.1B in net inflows last week, the highest since launch. BlackRock's IBIT leads with $890M. Institutional adoption metrics continue to climb.",
        "category": "sentiment",
        "layer": "medium_term",
        "asset_class": "crypto",
        "tickers": ["BTC-USD"],
        "source": "coingecko",
        "confidence": 0.88,
        "tags": ["bitcoin", "etf", "institutional"],
        "created_at": "2026-02-09T10:00:00Z",
        "updated_at": "2026-02-09T10:00:00Z",
    },
]
for entry in _seed_entries:
    _knowledge_store[entry["id"]] = entry


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[KnowledgeEntryResponse])
async def list_knowledge(
    category: str | None = Query(None, description="Filter by category"),
    layer: str | None = Query(None, description="Filter by time layer"),
    asset_class: str | None = Query(None, description="Filter by asset class"),
    limit: int = Query(50, ge=1, le=500),
):
    """List knowledge entries with optional filters."""
    results = list(_knowledge_store.values())

    if category:
        results = [e for e in results if e["category"] == category]
    if layer:
        results = [e for e in results if e["layer"] == layer]
    if asset_class:
        results = [e for e in results if e.get("asset_class") == asset_class]

    results.sort(key=lambda e: e["created_at"], reverse=True)
    return [KnowledgeEntryResponse(**e) for e in results[:limit]]


@router.get("/outlook", response_model=MarketOutlook)
async def get_market_outlook():
    """Get market outlook across all time horizon layers (long/mid/short term)."""
    sentiments = [_outlook_store[l]["sentiment"] for l in ("long_term", "medium_term", "short_term")]
    sentiment_scores = {"bullish": 1, "neutral": 0, "bearish": -1}
    avg_score = sum(sentiment_scores.get(s, 0) for s in sentiments) / len(sentiments)

    if avg_score > 0.3:
        consensus = "bullish"
    elif avg_score < -0.3:
        consensus = "bearish"
    else:
        consensus = "neutral"

    return MarketOutlook(
        long_term=OutlookLayer(**_outlook_store["long_term"]),
        medium_term=OutlookLayer(**_outlook_store["medium_term"]),
        short_term=OutlookLayer(**_outlook_store["short_term"]),
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
async def get_knowledge_entry(entry_id: str):
    """Get a single knowledge entry by ID."""
    entry = _knowledge_store.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Knowledge entry {entry_id} not found")
    return KnowledgeEntryResponse(**entry)


@router.post("/", response_model=KnowledgeEntryResponse, status_code=201)
async def create_knowledge_entry(payload: KnowledgeEntryCreate):
    """Add a custom knowledge entry (user contribution to the knowledge base)."""
    entry_id = str(uuid4())
    now = _now_iso()

    entry: dict[str, Any] = {
        "id": entry_id,
        "title": payload.title,
        "content": payload.content,
        "category": payload.category,
        "layer": payload.layer,
        "asset_class": payload.asset_class,
        "tickers": payload.tickers,
        "source": payload.source,
        "confidence": payload.confidence,
        "tags": payload.tags,
        "created_at": now,
        "updated_at": now,
    }

    _knowledge_store[entry_id] = entry
    return KnowledgeEntryResponse(**entry)


@router.put("/outlook/{layer}", response_model=OutlookLayer)
async def update_outlook(layer: str, payload: OutlookUpdate):
    """Update market outlook for a specific time horizon layer."""
    valid_layers = {"long_term", "medium_term", "short_term"}
    if layer not in valid_layers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid layer '{layer}'. Must be one of: {', '.join(valid_layers)}",
        )

    outlook = _outlook_store[layer]
    outlook["sentiment"] = payload.sentiment
    outlook["confidence"] = payload.confidence
    outlook["summary"] = payload.summary
    outlook["key_factors"] = payload.key_factors
    outlook["risks"] = payload.risks
    outlook["opportunities"] = payload.opportunities
    outlook["last_updated"] = _now_iso()

    return OutlookLayer(**outlook)


@router.post("/data-pipeline/trigger", response_model=DataPipelineResult)
async def trigger_data_pipeline():
    """Trigger the data pipeline to fetch latest data from all sources.

    In production this invokes the KnowledgeAgent's data ingestion pipeline.
    The prototype returns a representative placeholder result.
    """
    return DataPipelineResult(
        triggered_at=_now_iso(),
        sources_queried=len(_sources_store),
        new_entries=12,
        updated_entries=5,
        errors=[],
        duration_ms=4500.0,
    )
