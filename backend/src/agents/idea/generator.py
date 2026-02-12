"""Idea Generation Agent for the Overture system.

This agent is responsible for identifying investment opportunities from a wide
variety of sources: news feeds, market data anomalies, social media signals,
quantitative screens, and external research.  It produces structured idea
candidates that flow into the validation pipeline.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Idea Generation Agent for Overture, an AI-driven
hedge fund assistant.  You are an expert at identifying actionable investment
opportunities across all asset classes (equities, fixed income, commodities,
crypto, FX, and derivatives).

Your sources include:
- Real-time and historical news (earnings, macro events, geopolitics)
- Market data anomalies (unusual volume, price gaps, 10-sigma moves, options
  flow, cross-asset divergences)
- Social media signals (Reddit, X/Twitter, Substack, fintwit sentiment)
- Quantitative screens (valuation, momentum, factor exposures, relative
  strength)
- Broker and sell-side research reports

When generating ideas you MUST:
1. State a clear, falsifiable investment thesis.
2. Identify specific tickers / instruments.
3. Classify the asset class and expected timeframe (intraday, swing, tactical,
   strategic).
4. Cite the primary source and any corroborating data.
5. Assign an initial confidence score (0.0 - 1.0) based on signal strength and
   data quality.
6. Note potential risks and what would invalidate the thesis.

Output your ideas as a JSON array.  Each idea must contain the keys: title,
thesis, tickers, asset_class, timeframe, source, confidence, risks,
invalidation_triggers.
"""


class IdeaGeneratorAgent(BaseAgent):
    """Agent that scans multiple data sources to produce investment ideas.

    The generator casts a wide net -- it is intentionally over-inclusive.
    Downstream validation and risk agents are responsible for filtering
    low-quality ideas.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Idea Generator",
            agent_type="idea",
            description=(
                "identifying investment opportunities from news, market data, "
                "social media, screens, and quantitative signals"
            ),
        )

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def get_system_prompt(self) -> str:
        return SYSTEM_PROMPT

    def get_tools(self) -> list[dict]:
        """Return tool definitions for idea generation capabilities."""
        return [
            {
                "name": "search_news",
                "description": (
                    "Search recent news articles by keyword, ticker, or topic. "
                    "Returns headline, summary, source, and timestamp."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (keyword, ticker, or topic)",
                        },
                        "lookback_hours": {
                            "type": "integer",
                            "description": "How many hours back to search",
                            "default": 24,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 20,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "run_screen",
                "description": (
                    "Run a quantitative screen across a universe of securities. "
                    "Supports filters on valuation, momentum, volume, sector, "
                    "and factor exposures."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "universe": {
                            "type": "string",
                            "description": "Security universe (e.g. 'sp500', 'russell2000', 'global_etfs')",
                        },
                        "filters": {
                            "type": "object",
                            "description": "Key-value filter criteria",
                        },
                        "sort_by": {
                            "type": "string",
                            "description": "Metric to sort results by",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results",
                            "default": 25,
                        },
                    },
                    "required": ["universe", "filters"],
                },
            },
            {
                "name": "analyze_market_moves",
                "description": (
                    "Detect unusual market activity such as abnormal volume, "
                    "large price gaps, options flow anomalies, or cross-asset "
                    "divergences."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lookback_hours": {
                            "type": "integer",
                            "description": "Hours to look back for anomalies",
                            "default": 24,
                        },
                        "min_z_score": {
                            "type": "number",
                            "description": "Minimum z-score to flag as anomalous",
                            "default": 2.5,
                        },
                        "asset_classes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Asset classes to scan",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "search_social_signals",
                "description": (
                    "Search social media platforms (Reddit, X, Substack) for "
                    "emerging investment narratives and sentiment shifts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "platforms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Platforms to search (reddit, x, substack)",
                        },
                        "query": {
                            "type": "string",
                            "description": "Search query or topic",
                        },
                        "sentiment_threshold": {
                            "type": "number",
                            "description": "Min absolute sentiment score to include",
                            "default": 0.3,
                        },
                    },
                    "required": ["platforms"],
                },
            },
        ]

    async def execute(
        self, input_data: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Generate investment ideas from multiple sources.

        Args:
            input_data: Dictionary that may contain:
                - news_items: list of news articles / headlines
                - market_data: recent market data snapshots
                - social_signals: social media mentions and sentiment
                - screen_config: parameters for quantitative screening
                - external_sources: broker reports, substacks, etc.
            context: Shared agent context with portfolio and market state.

        Returns:
            Dictionary with key ``ideas`` containing a list of structured
            investment idea dictionaries.
        """
        ideas: list[dict[str, Any]] = []

        # 1. Analyze news for idea candidates
        news_items = input_data.get("news_items", [])
        if news_items:
            news_ideas = await self._analyze_news_for_ideas(news_items, context)
            ideas.extend(news_ideas)

        # 2. Detect unusual market moves
        market_data = input_data.get("market_data", {})
        if market_data:
            market_ideas = await self._analyze_market_moves(market_data, context)
            ideas.extend(market_ideas)

        # 3. Aggregate ideas from external / social sources
        social_signals = input_data.get("social_signals", [])
        external_sources = input_data.get("external_sources", [])
        combined_external = social_signals + external_sources
        if combined_external:
            external_ideas = await self._aggregate_external_ideas(
                combined_external, context
            )
            ideas.extend(external_ideas)

        # 4. Run quantitative screens
        screen_config = input_data.get("screen_config", {})
        if screen_config:
            screen_ideas = await self._run_screens(screen_config, context)
            ideas.extend(screen_ideas)

        # 5. If no specific sources were provided, ask the LLM to brainstorm
        #    based on the current market context alone.
        if not ideas and self._llm is not None:
            ideas = await self._brainstorm_from_context(context)

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique_ideas: list[dict[str, Any]] = []
        for idea in ideas:
            title = idea.get("title", "")
            if title not in seen_titles:
                seen_titles.add(title)
                unique_ideas.append(idea)

        await self.log_action(
            action="generate_ideas",
            input_data={"source_counts": {
                "news": len(news_items),
                "market_data": bool(market_data),
                "social_external": len(combined_external),
                "screens": bool(screen_config),
            }},
            output_data={"idea_count": len(unique_ideas)},
        )

        return {"ideas": unique_ideas}

    # ------------------------------------------------------------------
    # Private analysis methods
    # ------------------------------------------------------------------

    async def _analyze_news_for_ideas(
        self, news_items: list[dict[str, Any]], context: AgentContext
    ) -> list[dict[str, Any]]:
        """Analyze news articles and extract investment idea candidates.

        The LLM reads through news items, identifies those with potential
        investment implications, and structures them as idea candidates.

        Args:
            news_items: List of news article dicts with keys like ``headline``,
                ``summary``, ``source``, ``published_at``.

        Returns:
            List of raw idea candidate dictionaries.
        """
        if self._llm is None:
            return []

        news_text = json.dumps(news_items[:50], indent=2, default=str)
        portfolio_summary = json.dumps(context.portfolio_state, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "Analyze the following news items and extract actionable "
                    "investment ideas.  Consider the current portfolio context "
                    "when evaluating relevance.\n\n"
                    f"NEWS ITEMS:\n{news_text}\n\n"
                    f"PORTFOLIO CONTEXT:\n{portfolio_summary}\n\n"
                    "Return a JSON array of idea objects.  Each idea must have: "
                    "title, thesis, tickers (array), asset_class, timeframe, "
                    "source, confidence (0-1), risks (array), "
                    "invalidation_triggers (array)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.5, max_tokens=4096
        )

        try:
            ideas = json.loads(response.content)
            if isinstance(ideas, list):
                return ideas
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _analyze_market_moves(
        self, market_data: dict[str, Any], context: AgentContext
    ) -> list[dict[str, Any]]:
        """Identify ideas from unusual market activity.

        Looks for anomalies such as:
        - Multi-sigma price moves (e.g. silver moving 10 standard deviations)
        - Abnormal volume spikes
        - Cross-asset divergences (e.g. credit spreads widening while equities
          rally)
        - Options flow anomalies (large block trades, unusual put/call ratios)

        Args:
            market_data: Dictionary containing price data, volume data,
                options flow, and cross-asset snapshots.

        Returns:
            List of idea candidates derived from market anomalies.
        """
        if self._llm is None:
            return []

        market_text = json.dumps(market_data, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "Analyze the following market data for unusual activity and "
                    "generate investment ideas.  Focus on:\n"
                    "- Multi-sigma price moves (anything > 3 sigma is noteworthy, "
                    "> 5 sigma is extraordinary)\n"
                    "- Abnormal volume relative to 20-day average\n"
                    "- Cross-asset divergences or convergences\n"
                    "- Options flow anomalies (block trades, skew changes)\n"
                    "- Sector rotation signals\n\n"
                    f"MARKET DATA:\n{market_text}\n\n"
                    "Return a JSON array of idea objects with keys: title, "
                    "thesis, tickers, asset_class, timeframe, source, "
                    "confidence, risks, invalidation_triggers.\n"
                    "For the source field, use 'market_anomaly_detection'."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.4, max_tokens=4096
        )

        try:
            ideas = json.loads(response.content)
            if isinstance(ideas, list):
                return ideas
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _aggregate_external_ideas(
        self, sources: list[dict[str, Any]], context: AgentContext
    ) -> list[dict[str, Any]]:
        """Aggregate and structure ideas from external sources.

        Processes content from social media (Reddit, X/Twitter), Substack
        newsletters, broker research reports, and other third-party sources.
        The LLM extracts investable theses and normalizes them into the
        standard idea format.

        Args:
            sources: List of source dicts with keys like ``platform``,
                ``content``, ``author``, ``engagement_metrics``, ``url``.

        Returns:
            List of structured idea candidates.
        """
        if self._llm is None:
            return []

        sources_text = json.dumps(sources[:30], indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "Review the following external sources (social media posts, "
                    "broker reports, newsletters) and extract investment ideas "
                    "worth investigating.  Be critical -- filter out noise, "
                    "pump-and-dump schemes, and low-quality speculation.  Only "
                    "surface ideas with a genuine analytical foundation.\n\n"
                    f"EXTERNAL SOURCES:\n{sources_text}\n\n"
                    "Return a JSON array of idea objects.  Each idea must have: "
                    "title, thesis, tickers, asset_class, timeframe, source "
                    "(include platform and author), confidence, risks, "
                    "invalidation_triggers.\n"
                    "Apply a skeptical lens: ideas from anonymous social media "
                    "should start with lower confidence unless corroborated."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.5, max_tokens=4096
        )

        try:
            ideas = json.loads(response.content)
            if isinstance(ideas, list):
                return ideas
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _run_screens(
        self, screen_config: dict[str, Any], context: AgentContext
    ) -> list[dict[str, Any]]:
        """Generate ideas from systematic quantitative screening.

        Runs configurable screens across security universes to find
        candidates that match factor-based criteria such as:
        - Value (P/E, P/B, EV/EBITDA below thresholds)
        - Momentum (relative strength, trend following)
        - Quality (ROE, debt/equity, earnings stability)
        - Growth (revenue growth, earnings acceleration)
        - Volatility (low-vol anomaly, mean-reversion setups)

        Args:
            screen_config: Dictionary with keys:
                - universe: str (e.g. "sp500", "global_etfs")
                - filters: dict of filter criteria
                - sort_by: str metric to rank results
                - limit: int max results

        Returns:
            List of idea candidates from screening results.
        """
        if self._llm is None:
            return []

        config_text = json.dumps(screen_config, indent=2, default=str)
        market_context = json.dumps(context.market_context, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "Based on the following screen configuration and current "
                    "market context, generate investment ideas that a "
                    "quantitative screen would surface.  Think about what "
                    "factors are currently working and what the screen results "
                    "would imply.\n\n"
                    f"SCREEN CONFIG:\n{config_text}\n\n"
                    f"MARKET CONTEXT:\n{market_context}\n\n"
                    "Return a JSON array of idea objects with keys: title, "
                    "thesis, tickers, asset_class, timeframe, source "
                    "(use 'quantitative_screen'), confidence, risks, "
                    "invalidation_triggers."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.4, max_tokens=4096
        )

        try:
            ideas = json.loads(response.content)
            if isinstance(ideas, list):
                return ideas
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _brainstorm_from_context(
        self, context: AgentContext
    ) -> list[dict[str, Any]]:
        """Brainstorm ideas when no specific input sources are provided.

        Uses the current market context and portfolio state to generate
        ideas proactively.

        Args:
            context: Current agent context.

        Returns:
            List of idea candidates.
        """
        if self._llm is None:
            return []

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "No specific data sources were provided.  Based on the "
                    "current market context and portfolio state, brainstorm "
                    "2-5 investment ideas worth investigating.\n\n"
                    f"MARKET CONTEXT:\n{json.dumps(context.market_context, default=str)}\n\n"
                    f"PORTFOLIO STATE:\n{json.dumps(context.portfolio_state, default=str)}\n\n"
                    "Return a JSON array of idea objects with the standard "
                    "keys: title, thesis, tickers, asset_class, timeframe, "
                    "source, confidence, risks, invalidation_triggers."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.7, max_tokens=4096
        )

        try:
            ideas = json.loads(response.content)
            if isinstance(ideas, list):
                return ideas
        except (json.JSONDecodeError, TypeError):
            pass

        return []
