"""Knowledge RAG (Retrieval-Augmented Generation) service.

Provides context retrieval from the knowledge library for agent prompts.
Agents call `get_context()` to receive relevant knowledge entries that
enrich their decision-making with the latest research and market data.

Current implementation: keyword + ticker matching with recency weighting.
Future: vector embeddings for semantic similarity search.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.knowledge import KnowledgeEntry, KnowledgeCategory, KnowledgeLayer

logger = logging.getLogger(__name__)

# Map agent types to preferred knowledge categories
_AGENT_CATEGORY_PREFS: dict[str, list[KnowledgeCategory]] = {
    "idea_generator": [
        KnowledgeCategory.MACRO, KnowledgeCategory.EVENT,
        KnowledgeCategory.RESEARCH, KnowledgeCategory.TECHNICAL,
    ],
    "idea_validator": [
        KnowledgeCategory.FUNDAMENTAL, KnowledgeCategory.RESEARCH,
        KnowledgeCategory.TECHNICAL,
    ],
    "risk_manager": [
        KnowledgeCategory.MACRO, KnowledgeCategory.EVENT,
        KnowledgeCategory.TECHNICAL,
    ],
    "portfolio_constructor": [
        KnowledgeCategory.MACRO, KnowledgeCategory.RESEARCH,
        KnowledgeCategory.FUNDAMENTAL,
    ],
}

_LAYER_API_TO_DB = {
    "long_term": KnowledgeLayer.LONG_TERM,
    "medium_term": KnowledgeLayer.MID_TERM,
    "short_term": KnowledgeLayer.SHORT_TERM,
}


async def get_context(
    session: AsyncSession,
    *,
    tickers: list[str] | None = None,
    keywords: list[str] | None = None,
    layer: str | None = None,
    agent_type: str | None = None,
    max_entries: int = 10,
    max_age_days: int | None = None,
) -> list[dict]:
    """Retrieve relevant knowledge entries for agent context.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    tickers : list[str], optional
        Filter entries mentioning these ticker symbols.
    keywords : list[str], optional
        Search title and content for these keywords.
    layer : str, optional
        Filter by time horizon: long_term, medium_term, short_term.
    agent_type : str, optional
        Agent type requesting context (affects category preference).
    max_entries : int
        Maximum number of entries to return.
    max_age_days : int, optional
        Only return entries created within this many days.

    Returns
    -------
    list[dict]
        Knowledge entries formatted for agent consumption.
    """
    stmt = select(KnowledgeEntry).where(KnowledgeEntry.is_public.is_(True))

    # Layer filter
    if layer:
        layer_enum = _LAYER_API_TO_DB.get(layer)
        if layer_enum:
            stmt = stmt.where(KnowledgeEntry.layer == layer_enum)

    # Category preference for agent type
    if agent_type and agent_type in _AGENT_CATEGORY_PREFS:
        prefs = _AGENT_CATEGORY_PREFS[agent_type]
        stmt = stmt.where(KnowledgeEntry.category.in_(prefs))

    # Recency filter
    if max_age_days:
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        stmt = stmt.where(KnowledgeEntry.created_at >= cutoff)

    # Ticker filter — use JSON contains for the tickers array
    if tickers:
        ticker_conditions = [
            KnowledgeEntry.tickers.contains([t]) for t in tickers
        ]
        stmt = stmt.where(or_(*ticker_conditions))

    # Keyword search in title and content (simple ILIKE matching)
    if keywords:
        kw_conditions = []
        for kw in keywords:
            kw_conditions.append(KnowledgeEntry.title.ilike(f"%{kw}%"))
            kw_conditions.append(KnowledgeEntry.content.ilike(f"%{kw}%"))
        stmt = stmt.where(or_(*kw_conditions))

    # Order by credibility * recency, then limit
    stmt = stmt.order_by(
        desc(KnowledgeEntry.source_credibility_score),
        desc(KnowledgeEntry.created_at),
    ).limit(max_entries)

    result = await session.execute(stmt)
    entries = result.scalars().all()

    return [_entry_to_context(e) for e in entries]


def _entry_to_context(entry: KnowledgeEntry) -> dict:
    """Format a knowledge entry for agent context consumption."""
    return {
        "id": entry.id,
        "title": entry.title,
        "content": entry.content,
        "summary": entry.summary or entry.content[:300],
        "category": entry.category.value if entry.category else "research",
        "layer": entry.layer.value if entry.layer else "mid_term",
        "source": entry.source or "unknown",
        "confidence": entry.source_credibility_score or 0.5,
        "tickers": entry.tickers or [],
        "asset_classes": entry.asset_classes or [],
        "tags": entry.tags or [],
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def format_context_for_prompt(entries: list[dict], max_chars: int = 8000) -> str:
    """Format retrieved knowledge entries into a text block for LLM prompts.

    Parameters
    ----------
    entries : list[dict]
        Knowledge entries from `get_context()`.
    max_chars : int
        Maximum character count for the output text.

    Returns
    -------
    str
        Formatted knowledge context suitable for injection into agent prompts.
    """
    if not entries:
        return "No relevant knowledge entries found."

    sections = []
    total = 0

    for i, entry in enumerate(entries, 1):
        section = (
            f"[{i}] {entry['title']} "
            f"(source: {entry['source']}, confidence: {entry['confidence']:.0%}, "
            f"layer: {entry['layer']})\n"
            f"{entry['content']}\n"
            f"Tickers: {', '.join(entry['tickers']) if entry['tickers'] else 'N/A'}\n"
            f"Tags: {', '.join(entry['tags']) if entry['tags'] else 'N/A'}"
        )

        if total + len(section) > max_chars:
            # Truncate this section to fit
            remaining = max_chars - total - 50
            if remaining > 200:
                sections.append(section[:remaining] + "\n... (truncated)")
            break

        sections.append(section)
        total += len(section)

    header = f"=== Knowledge Context ({len(sections)} entries) ===\n\n"
    return header + "\n\n---\n\n".join(sections)


async def get_context_for_agent(
    session: AsyncSession,
    agent_type: str,
    *,
    tickers: list[str] | None = None,
    query: str | None = None,
) -> str:
    """High-level convenience: retrieve and format context for a specific agent.

    This is the primary entry point for agents needing knowledge context.
    """
    keywords = query.split() if query else None

    # Determine layer preference based on agent type
    layer = None
    if agent_type in ("trade_monitor", "trade_executor"):
        layer = "short_term"
    elif agent_type in ("portfolio_constructor", "rebalancer"):
        layer = "medium_term"

    entries = await get_context(
        session,
        tickers=tickers,
        keywords=keywords,
        layer=layer,
        agent_type=agent_type,
        max_entries=8,
    )

    # If no targeted results, fall back to recent high-confidence entries
    if not entries:
        entries = await get_context(
            session,
            agent_type=agent_type,
            max_entries=5,
        )

    return format_context_for_prompt(entries)
