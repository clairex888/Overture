"""Librarian Agent for the Overture system.

This agent maintains the knowledge library structure and quality.  It
organizes entries for efficient retrieval, prunes stale or low-value
information, and continuously updates source reliability rankings so
that downstream agents always work with the highest-quality data.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Knowledge Librarian Agent for Overture, an
AI-driven hedge fund assistant.  You are an expert knowledge librarian
specializing in financial data, research, and market intelligence.

Your mission is to maintain the highest-quality, best-organized knowledge
library possible so that every other agent in the system can find accurate,
relevant, and timely information instantly.

Your responsibilities:

1. ORGANIZE THE LIBRARY:
   - Maintain a clear taxonomy: asset class, sector, geography, temporal
     layer (secular / cyclical / tactical), theme, and source type.
   - Ensure every entry has complete metadata: tags, timestamps, source,
     reliability score, and cross-references to related entries.
   - Create and maintain indices for fast lookup by ticker, theme, date
     range, and relevance score.
   - Merge duplicate entries and reconcile conflicting information.
   - Maintain a "chain of custody" for each piece of information so
     agents can trace conclusions back to primary sources.

2. PRUNE STALE ENTRIES:
   - Tactical entries older than 30 days with no ongoing relevance should
     be archived or removed.
   - Cyclical entries should be reviewed quarterly for continued validity.
   - Secular entries should be reviewed semi-annually.
   - Entries whose source has been downgraded in reliability should be
     flagged for re-verification.
   - Contradicted entries should be marked and eventually removed if the
     contradicting evidence is strong.

3. UPDATE SOURCE RANKINGS:
   - Track the historical accuracy of each data source.
   - Sources that consistently provide actionable, accurate information
     should be ranked higher.
   - Sources with a history of inaccurate or misleading data should be
     downgraded.
   - Maintain separate rankings for different domains (e.g., a source
     may be excellent for macro but poor for individual stock analysis).
   - Factor in timeliness: sources that break news early should be
     ranked higher than those that lag.

Quality standards:
- Every entry must be attributable to at least one named source.
- Quantitative claims must include units, time period, and methodology
  when available.
- Forecasts and opinions must be clearly labeled as such (not presented
  as facts).
- Confidence levels should be explicit: "high confidence (multiple
  independent sources)" vs "low confidence (single unverified source)".

When evaluating entries, apply these heuristics:
- Recency: more recent data is generally more valuable (for tactical).
- Source diversity: conclusions supported by multiple independent sources
  are stronger.
- Track record: sources with a history of accuracy are more reliable.
- Specificity: precise, falsifiable claims are more useful than vague
  directional commentary.
- Relevance: entries directly tied to portfolio holdings or active
  theses are higher priority.
"""


class LibrarianAgent(BaseAgent):
    """Agent that maintains the knowledge library structure and quality.

    The Librarian ensures the knowledge base stays organized, current,
    and reliable by continuously curating entries, pruning stale data,
    and ranking information sources.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Knowledge Librarian",
            agent_type="knowledge",
            description=(
                "maintaining the knowledge library structure, quality, "
                "and source reliability rankings for the Overture system"
            ),
        )

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    async def execute(
        self, input_data: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Maintain the knowledge library: organize, prune, and rank.

        Args:
            input_data: Dictionary containing:
                - library: current state of the knowledge library
                  (dict mapping categories to lists of entries)
                - new_entries: recently curated entries to integrate
                - source_feedback: feedback on source accuracy from
                  downstream agents (list of dicts with source, outcome,
                  accuracy_score)
            context: Shared agent context.

        Returns:
            Dictionary with keys ``organized_library``,
            ``pruned_entries``, ``source_rankings``, and ``stats``.
        """
        library = input_data.get("library", {})
        new_entries = input_data.get("new_entries", [])
        source_feedback = input_data.get("source_feedback", [])

        # Step 1: Organize new entries into the library
        organized = await self._organize_library(new_entries)

        # Step 2: Prune stale entries from the existing library
        pruned = await self._prune_stale_entries(library)

        # Step 3: Update source reliability rankings
        rankings = await self._update_source_rankings(
            new_entries + source_feedback
        )

        result = {
            "organized_library": organized,
            "pruned_entries": pruned,
            "source_rankings": rankings,
            "stats": {
                "new_entries_processed": len(new_entries),
                "entries_pruned": len(pruned.get("removed", [])),
                "entries_archived": len(pruned.get("archived", [])),
                "sources_ranked": len(rankings.get("rankings", [])),
            },
        }

        await self.log_action(
            action="maintain_library",
            input_data={
                "library_size": sum(
                    len(v) if isinstance(v, list) else 0
                    for v in library.values()
                ),
                "new_entry_count": len(new_entries),
                "feedback_count": len(source_feedback),
            },
            output_data=result["stats"],
        )

        return result

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _organize_library(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Organize new entries into the library taxonomy.

        Assigns categories, ensures metadata completeness, merges
        duplicates, and creates cross-references between related entries.

        Args:
            entries: New knowledge entries to organize.

        Returns:
            Dictionary with organized entries grouped by category and
            a list of cross-references discovered.
        """
        if not entries:
            return {"categories": {}, "cross_references": [], "merged_duplicates": []}

        if self._llm is None:
            return {"categories": {}, "cross_references": [], "merged_duplicates": []}

        entries_text = json.dumps(entries[:40], indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "ORGANIZE LIBRARY ENTRIES\n\n"
                    f"NEW ENTRIES:\n{entries_text}\n\n"
                    "For each entry:\n"
                    "1. Assign to one or more categories from the taxonomy: "
                    "asset_class, sector, geography, temporal_layer, theme, "
                    "source_type\n"
                    "2. Verify metadata completeness (flag entries missing "
                    "key fields)\n"
                    "3. Identify potential duplicates among the entries\n"
                    "4. Create cross-references between related entries\n\n"
                    "Return JSON with keys:\n"
                    "- categories: dict mapping category names to arrays of "
                    "entry titles\n"
                    "- cross_references: array of {source_entry, related_entry, "
                    "relationship_type}\n"
                    "- merged_duplicates: array of {kept, removed, reason}\n"
                    "- metadata_warnings: array of {entry_title, missing_fields}"
                ),
            ),
        ]

        response = await self._llm.chat(
            messages, temperature=0.3, max_tokens=4096
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"categories": {}, "cross_references": [], "merged_duplicates": []}

    async def _prune_stale_entries(
        self, library: dict[str, Any]
    ) -> dict[str, Any]:
        """Identify and prune stale or low-value entries from the library.

        Applies temporal decay rules: tactical entries older than 30 days
        are candidates for removal, cyclical entries are reviewed
        quarterly, and secular entries semi-annually.  Entries from
        downgraded sources are flagged for re-verification.

        Args:
            library: Current knowledge library state, mapping categories
                to lists of entries.

        Returns:
            Dictionary with ``removed`` (entries to delete),
            ``archived`` (entries to move to cold storage), and
            ``flagged`` (entries needing re-verification).
        """
        if not library:
            return {"removed": [], "archived": [], "flagged": []}

        if self._llm is None:
            return {"removed": [], "archived": [], "flagged": []}

        library_text = json.dumps(library, indent=2, default=str)
        # Truncate to avoid excessively large prompts
        if len(library_text) > 15000:
            library_text = library_text[:15000] + "\n... (truncated)"

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PRUNE STALE LIBRARY ENTRIES\n\n"
                    f"CURRENT LIBRARY:\n{library_text}\n\n"
                    "Apply the following pruning rules:\n"
                    "1. TACTICAL entries older than 30 days with no ongoing "
                    "relevance -> REMOVE\n"
                    "2. TACTICAL entries older than 30 days but still "
                    "relevant -> ARCHIVE\n"
                    "3. CYCLICAL entries not reviewed in 90+ days -> FLAG "
                    "for review\n"
                    "4. SECULAR entries not reviewed in 180+ days -> FLAG "
                    "for review\n"
                    "5. Entries from sources with reliability_score < 0.3 "
                    "-> FLAG for re-verification\n"
                    "6. Entries contradicted by newer information -> REMOVE\n\n"
                    "Return JSON with keys:\n"
                    "- removed: array of {title, reason}\n"
                    "- archived: array of {title, reason}\n"
                    "- flagged: array of {title, reason, action_needed}"
                ),
            ),
        ]

        response = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"removed": [], "archived": [], "flagged": []}

    async def _update_source_rankings(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Update source reliability rankings based on recent entries
        and feedback from downstream agents.

        Tracks historical accuracy, timeliness, and domain expertise of
        each source.  Rankings are maintained per domain (macro, equity,
        sector, etc.).

        Args:
            entries: Combined list of new entries and source feedback
                dicts containing source identifiers and accuracy signals.

        Returns:
            Dictionary with ``rankings`` (list of source ranking dicts)
            and ``changes`` (list of ranking changes from previous period).
        """
        if not entries:
            return {"rankings": [], "changes": []}

        if self._llm is None:
            return {"rankings": [], "changes": []}

        entries_text = json.dumps(entries[:30], indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "UPDATE SOURCE RELIABILITY RANKINGS\n\n"
                    f"RECENT ENTRIES AND FEEDBACK:\n{entries_text}\n\n"
                    "Based on these entries and any accuracy feedback:\n"
                    "1. Identify all unique sources\n"
                    "2. Assess each source's reliability based on:\n"
                    "   - Accuracy of past claims (if feedback available)\n"
                    "   - Timeliness of information\n"
                    "   - Specificity and actionability\n"
                    "   - Consistency across entries\n"
                    "3. Assign updated reliability scores (0.0 to 1.0)\n"
                    "4. Note any significant ranking changes\n\n"
                    "Return JSON with keys:\n"
                    "- rankings: array of {source, reliability_score, "
                    "domain_scores (dict of domain -> score), "
                    "sample_size, notes}\n"
                    "- changes: array of {source, old_score, new_score, "
                    "reason}\n"
                    "- flagged_sources: array of sources needing attention"
                ),
            ),
        ]

        response = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"rankings": [], "changes": []}
