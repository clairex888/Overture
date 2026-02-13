"""Data Curator Agent for the Overture system.

This agent continuously ingests, processes, and organizes data from multiple
sources into the Overture knowledge library.  It categorizes information into
temporal layers (long-term secular, medium-term cyclical, short-term tactical),
maintains the market outlook, and builds a knowledge graph of relationships
between entities, events, and themes.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Data Curator Agent for Overture, an AI-driven
hedge fund assistant.  You are responsible for continuously ingesting,
processing, organizing, and maintaining the knowledge base that powers all
other agents.

Your role is analogous to a research librarian and information architect
combined.  You process raw data and transform it into structured, actionable
knowledge.

Knowledge layers you maintain:
1. SECULAR (Long-term, 5-10 years):
   - Structural economic trends (deglobalization, aging demographics, AI)
   - Regulatory regime shifts
   - Technology platform shifts
   - Climate and ESG structural changes
   - Geopolitical realignments

2. CYCLICAL (Medium-term, 1-3 years):
   - Business cycle positioning (expansion, peak, contraction, trough)
   - Credit cycle status
   - Earnings cycle trends
   - Monetary policy trajectory
   - Sector rotation patterns

3. TACTICAL (Short-term, days to months):
   - Earnings surprises and guidance changes
   - Central bank meetings and policy decisions
   - Geopolitical events and developments
   - Market sentiment shifts
   - Technical breakouts and breakdowns
   - Options flow and positioning data

Data processing principles:
- Extract structured facts from unstructured text
- Tag every entry with: source, reliability_score, temporal_layer, asset_classes,
  tickers, themes, sentiment, and timestamp
- Identify relationships between entities (companies, sectors, macro factors)
- Detect contradictions between sources and flag them
- Prioritize recency and source quality
- Remove duplicate information
- Track how knowledge entries evolve over time (thesis tracking)
"""


class DataCuratorAgent(BaseAgent):
    """Agent that ingests, processes, and organizes data into knowledge layers.

    Serves as the information backbone of the Overture system, maintaining
    a structured, queryable knowledge base that other agents draw upon.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Data Curator",
            agent_type="knowledge",
            description=(
                "continuously ingesting, processing, and organizing data "
                "from multiple sources into structured knowledge layers"
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
        """Process incoming data and update the knowledge library.

        Args:
            input_data: Dictionary containing:
                - news_sources: list of raw news articles
                - market_data: market data snapshots
                - social_data: social media content
                - research_reports: broker/analyst reports
                - existing_library: current knowledge library state
            context: Shared agent context.

        Returns:
            Dictionary with key ``curated_entries`` containing processed
            and categorized knowledge entries ready for the library.
        """
        news_sources = input_data.get("news_sources", [])
        market_data = input_data.get("market_data", {})
        social_data = input_data.get("social_data", [])
        research_reports = input_data.get("research_reports", [])
        existing_library = input_data.get("existing_library", {})

        all_entries: list[dict[str, Any]] = []

        # Step 1: Ingest and process news
        if news_sources:
            news_entries = await self._ingest_news(news_sources)
            all_entries.extend(news_entries)

        # Step 2: Process market data into knowledge entries
        if market_data:
            market_entries = await self._ingest_market_data(market_data)
            all_entries.extend(market_entries)

        # Step 3: Process social and research data
        combined_sources = social_data + research_reports
        if combined_sources:
            external_entries = await self._ingest_external(combined_sources)
            all_entries.extend(external_entries)

        # Step 4: Categorize into knowledge layers
        if all_entries:
            categorized = await self._update_knowledge_layers(all_entries)
        else:
            categorized = {"secular": [], "cyclical": [], "tactical": []}

        # Step 5: Update market outlook based on new data
        outlook_update = await self._maintain_market_outlook(categorized, context)

        # Step 6: Build/update knowledge graph
        graph_updates = await self._build_knowledge_graph(all_entries, context)

        result = {
            "curated_entries": all_entries,
            "categorized": categorized,
            "outlook_update": outlook_update,
            "graph_updates": graph_updates,
            "entry_count": len(all_entries),
        }

        await self.log_action(
            action="curate_data",
            input_data={
                "news_count": len(news_sources),
                "has_market_data": bool(market_data),
                "external_count": len(combined_sources),
            },
            output_data={"entry_count": len(all_entries)},
        )

        return result

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _ingest_news(
        self, sources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process raw news articles into structured knowledge entries.

        Extracts key facts, identifies affected tickers and themes,
        assigns sentiment and reliability scores, and determines the
        appropriate temporal layer.

        Args:
            sources: List of raw news article dicts with ``headline``,
                ``body``, ``source``, ``published_at``.

        Returns:
            List of structured knowledge entry dicts.
        """
        if self._llm is None:
            return []

        news_text = json.dumps(sources[:30], indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PROCESS NEWS ARTICLES\n\n"
                    f"RAW NEWS:\n{news_text}\n\n"
                    "For each article, extract a structured knowledge entry:\n"
                    "1. Key facts (what happened, who is affected)\n"
                    "2. Affected tickers and asset classes\n"
                    "3. Themes (e.g., 'AI capex', 'rate cuts', 'geopolitical risk')\n"
                    "4. Sentiment (bullish/bearish/neutral with score -1 to 1)\n"
                    "5. Temporal layer (secular/cyclical/tactical)\n"
                    "6. Source reliability score (0-1)\n"
                    "7. Actionability (is this immediately tradeable?)\n\n"
                    "Return a JSON array of entry objects with keys: title, "
                    "summary, facts (array), tickers (array), asset_classes "
                    "(array), themes (array), sentiment (object with direction "
                    "and score), temporal_layer, source, reliability_score, "
                    "actionability (low/medium/high), timestamp."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=4096
        )

        try:
            entries = json.loads(response.content)
            if isinstance(entries, list):
                return entries
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _ingest_market_data(
        self, market_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Process market data snapshots into knowledge entries.

        Identifies notable moves, regime changes, and cross-asset signals
        from raw market data.

        Args:
            market_data: Market data snapshot with prices, volumes, and
                derived metrics.

        Returns:
            List of structured knowledge entries from market observations.
        """
        if self._llm is None:
            return []

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PROCESS MARKET DATA INTO KNOWLEDGE ENTRIES\n\n"
                    f"MARKET DATA:\n{json.dumps(market_data, indent=2, default=str)}\n\n"
                    "Extract notable observations as knowledge entries:\n"
                    "1. Significant price moves and what they might signal\n"
                    "2. Volume anomalies and their implications\n"
                    "3. Cross-asset signals (e.g., bonds vs equities divergence)\n"
                    "4. Volatility regime observations\n"
                    "5. Sector rotation patterns\n\n"
                    "Return a JSON array of entry objects with the standard "
                    "knowledge entry keys: title, summary, facts, tickers, "
                    "asset_classes, themes, sentiment, temporal_layer, source "
                    "('market_data'), reliability_score, actionability, timestamp."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            entries = json.loads(response.content)
            if isinstance(entries, list):
                return entries
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _ingest_external(
        self, sources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process external sources (social media, research reports).

        Args:
            sources: Combined list of social media posts and research reports.

        Returns:
            List of structured knowledge entries.
        """
        if self._llm is None:
            return []

        sources_text = json.dumps(sources[:25], indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "PROCESS EXTERNAL SOURCES\n\n"
                    f"SOURCES:\n{sources_text}\n\n"
                    "Process these external sources into knowledge entries. "
                    "Apply extra scrutiny to social media sources -- assign "
                    "lower reliability scores to unverified claims.  For "
                    "professional research reports, extract key conclusions "
                    "and price targets.\n\n"
                    "Return a JSON array of entry objects with the standard "
                    "knowledge entry keys: title, summary, facts, tickers, "
                    "asset_classes, themes, sentiment, temporal_layer, source, "
                    "reliability_score, actionability, timestamp."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            entries = json.loads(response.content)
            if isinstance(entries, list):
                return entries
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _update_knowledge_layers(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Categorize knowledge entries into temporal layers.

        Assigns each entry to the appropriate knowledge layer (secular,
        cyclical, tactical) and ensures proper tagging.

        Args:
            entries: List of processed knowledge entries.

        Returns:
            Dictionary with keys ``secular``, ``cyclical``, ``tactical``,
            each containing a list of entries for that layer.
        """
        if self._llm is None:
            return {"secular": [], "cyclical": [], "tactical": entries}

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "CATEGORIZE INTO KNOWLEDGE LAYERS\n\n"
                    f"ENTRIES:\n{json.dumps(entries[:40], indent=2, default=str)}\n\n"
                    "Categorize each entry into the appropriate layer:\n"
                    "- SECULAR: structural, multi-year trends\n"
                    "- CYCLICAL: business cycle, 1-3 year timeframe\n"
                    "- TACTICAL: short-term, days to months\n\n"
                    "Some entries may be relevant to multiple layers.\n\n"
                    "Return JSON with keys: secular (array of entries), "
                    "cyclical (array of entries), tactical (array of entries). "
                    "Use the entry titles to identify them."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=4096
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"secular": [], "cyclical": [], "tactical": entries}

    async def _maintain_market_outlook(
        self,
        categorized: dict[str, list[dict[str, Any]]],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Update the market outlook based on newly categorized knowledge.

        Synthesizes new information into an updated view across all three
        temporal layers.

        Args:
            categorized: Newly categorized knowledge entries by layer.
            context: Agent context with existing market context.

        Returns:
            Dictionary with updated outlook for each layer.
        """
        if self._llm is None:
            return {"status": "llm_unavailable"}

        existing_outlook = json.dumps(context.market_context, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "UPDATE MARKET OUTLOOK\n\n"
                    f"EXISTING OUTLOOK:\n{existing_outlook}\n\n"
                    f"NEW SECULAR DATA:\n{json.dumps(categorized.get('secular', []), indent=2, default=str)}\n\n"
                    f"NEW CYCLICAL DATA:\n{json.dumps(categorized.get('cyclical', []), indent=2, default=str)}\n\n"
                    f"NEW TACTICAL DATA:\n{json.dumps(categorized.get('tactical', []), indent=2, default=str)}\n\n"
                    "Based on the new data, update the market outlook:\n"
                    "1. Has the secular view changed? Any new structural trends?\n"
                    "2. Has the cyclical positioning shifted? Business cycle update?\n"
                    "3. What are the key tactical considerations right now?\n"
                    "4. Have any previous views been confirmed or contradicted?\n\n"
                    "Return JSON with keys: secular_outlook (object with themes, "
                    "direction, conviction), cyclical_outlook (object with "
                    "cycle_phase, key_indicators, direction), tactical_outlook "
                    "(object with opportunities, risks, key_events), "
                    "changes_from_previous (array of what changed and why)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.4, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"raw_outlook": response.content}

    async def _build_knowledge_graph(
        self, entries: list[dict[str, Any]], context: AgentContext
    ) -> dict[str, Any]:
        """Build or update the knowledge graph with relationships.

        Identifies connections between entities (companies, sectors, themes,
        macro factors) mentioned in knowledge entries and maintains a
        relationship graph.

        Args:
            entries: New knowledge entries to integrate into the graph.
            context: Agent context with existing knowledge context.

        Returns:
            Dictionary with new nodes, edges, and updated relationships.
        """
        if self._llm is None:
            return {"nodes": [], "edges": [], "updates": []}

        if not entries:
            return {"nodes": [], "edges": [], "updates": []}

        entries_text = json.dumps(entries[:30], indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "BUILD KNOWLEDGE GRAPH UPDATES\n\n"
                    f"NEW ENTRIES:\n{entries_text}\n\n"
                    "Extract entities and relationships for the knowledge graph:\n"
                    "1. ENTITIES: Companies, sectors, themes, macro indicators, "
                    "people, countries\n"
                    "2. RELATIONSHIPS: 'competes_with', 'supplies_to', "
                    "'benefits_from', 'harmed_by', 'correlated_with', "
                    "'inversely_correlated_with', 'part_of_theme'\n"
                    "3. STRENGTH: How strong is the relationship? (0-1)\n\n"
                    "Return JSON with keys: nodes (array of {id, type, name, "
                    "attributes}), edges (array of {source, target, "
                    "relationship, strength, evidence}), updates (array of "
                    "changes to existing relationships)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=2048
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"nodes": [], "edges": [], "updates": []}
