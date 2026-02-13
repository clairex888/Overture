"""Educator Agent for the Overture system.

This agent proactively creates learning experiences, educational content, and
contextual alerts for the user.  It identifies opportunities to teach
investment concepts, explain market events, and aggregate questions trending
in the broader investing community.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Educator Agent for Overture, an AI-driven hedge
fund assistant.  Your mission is to help the user become a better investor
through proactive education, contextual learning, and curated content.

Your responsibilities:

1. IDENTIFY LEARNING OPPORTUNITIES:
   - When the user makes a trade, explain the relevant concepts (e.g., if they
     buy a put spread, explain how the Greeks affect the position)
   - When a market event occurs, explain its significance and historical context
   - When portfolio metrics change, explain what the numbers mean
   - Detect knowledge gaps from user questions and trading patterns

2. CURATE EDUCATIONAL CONTENT:
   - Create concise, actionable explanations (not academic textbook style)
   - Use the user's actual portfolio and trades as examples when possible
   - Provide historical analogues ("The last time this happened was...")
   - Link concepts to practical decision-making
   - Adapt to the user's sophistication level

3. AGGREGATE TRENDING QUESTIONS:
   - What are retail and institutional investors asking about right now?
   - What concepts are trending due to current market events?
   - What are common misconceptions in the current market environment?

Content types you produce:
- CONCEPT EXPLAINERS: Brief explanations of investment concepts
- MARKET CONTEXT: "What just happened and why it matters"
- HISTORICAL PARALLELS: "Here is when something similar occurred"
- DECISION FRAMEWORKS: "How to think about X" checklists
- MISTAKE PATTERNS: "Common mistakes when X happens"
- TRENDING TOPICS: What the investing community is discussing

Tone and style:
- Conversational but precise -- like a knowledgeable friend
- Use analogies and real examples
- Always tie concepts back to actionable implications
- Avoid jargon unless you immediately explain it
- Be honest about uncertainty ("this is debated" vs "this is established")
"""


class EducatorAgent(BaseAgent):
    """Agent that creates proactive learning experiences for the user.

    Monitors user activity, market events, and community discussions to
    identify opportunities for educational content that improves the
    user's investment decision-making.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Educator",
            agent_type="knowledge",
            description=(
                "proactively creating learning experiences, educational "
                "content, and contextual alerts to help the user become "
                "a better investor"
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
        """Generate educational content and learning opportunities.

        Args:
            input_data: Dictionary containing:
                - user_activity: recent user actions and trades
                - market_events: notable market events
                - platform_data: trending questions and discussions
                - user_level: user's self-reported sophistication level
                  (beginner, intermediate, advanced)
            context: Shared agent context.

        Returns:
            Dictionary with key ``educational_content`` containing
            identified learning opportunities and curated content.
        """
        user_activity = input_data.get("user_activity", [])
        market_events = input_data.get("market_events", [])
        platform_data = input_data.get("platform_data", {})
        user_level = input_data.get("user_level", "intermediate")

        # Step 1: Identify learning opportunities
        opportunities = await self._identify_learning_opportunities(
            user_activity, market_events, context
        )

        # Step 2: Curate content for top opportunities
        content_pieces: list[dict[str, Any]] = []
        for opportunity in opportunities[:5]:  # Top 5 opportunities
            content = await self._curate_content(opportunity, user_level, context)
            if content:
                content_pieces.append(content)

        # Step 3: Aggregate trending questions
        trending = await self._aggregate_trending_questions(
            platform_data, market_events
        )

        result = {
            "educational_content": {
                "learning_opportunities": opportunities,
                "content_pieces": content_pieces,
                "trending_questions": trending,
                "user_level": user_level,
            }
        }

        await self.log_action(
            action="generate_education",
            input_data={
                "activity_count": len(user_activity),
                "event_count": len(market_events),
            },
            output_data={
                "opportunity_count": len(opportunities),
                "content_count": len(content_pieces),
            },
        )

        return result

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    async def _identify_learning_opportunities(
        self,
        user_activity: list[dict[str, Any]],
        market_events: list[dict[str, Any]],
        context: AgentContext,
    ) -> list[dict[str, Any]]:
        """Identify what the user should learn right now.

        Analyzes user activity (trades, questions, portfolio changes) and
        current market events to find the most relevant teaching moments.

        Args:
            user_activity: Recent user actions and trades.
            market_events: Notable recent market events.
            context: Agent context.

        Returns:
            List of learning opportunity dicts, each with ``topic``,
            ``trigger``, ``relevance``, ``type``, and ``priority``.
        """
        if self._llm is None:
            return []

        activity_text = json.dumps(user_activity[:20], indent=2, default=str)
        events_text = json.dumps(market_events[:15], indent=2, default=str)
        portfolio_text = json.dumps(context.portfolio_state, indent=2, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "IDENTIFY LEARNING OPPORTUNITIES\n\n"
                    f"USER ACTIVITY:\n{activity_text}\n\n"
                    f"MARKET EVENTS:\n{events_text}\n\n"
                    f"PORTFOLIO STATE:\n{portfolio_text}\n\n"
                    "Based on what the user is doing and what is happening in "
                    "the market, identify the most valuable learning "
                    "opportunities right now:\n"
                    "1. Concepts relevant to their recent trades\n"
                    "2. Market events that deserve explanation\n"
                    "3. Portfolio patterns that could be teachable moments\n"
                    "4. Common mistakes to warn about given current conditions\n"
                    "5. Historical context that would be valuable\n\n"
                    "Return a JSON array of opportunity objects with keys: "
                    "topic (string), trigger (what prompted this -- a trade, "
                    "event, or pattern), relevance (why this matters now), "
                    "type (concept_explainer/market_context/historical_parallel/"
                    "decision_framework/mistake_pattern), priority (1=highest)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.5, max_tokens=2048
        )

        try:
            opportunities = json.loads(response.content)
            if isinstance(opportunities, list):
                return opportunities
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    async def _curate_content(
        self,
        opportunity: dict[str, Any],
        user_level: str,
        context: AgentContext,
    ) -> dict[str, Any] | None:
        """Create educational content for a specific learning opportunity.

        Generates content adapted to the user's sophistication level, using
        their actual portfolio as examples where relevant.

        Args:
            opportunity: The learning opportunity to create content for.
            user_level: User's sophistication level.
            context: Agent context with portfolio for examples.

        Returns:
            Educational content dict with ``title``, ``type``, ``content``,
            ``key_takeaways``, ``related_to_portfolio``, and ``further_reading``.
            Returns None if content generation fails.
        """
        if self._llm is None:
            return None

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "CREATE EDUCATIONAL CONTENT\n\n"
                    f"OPPORTUNITY:\n{json.dumps(opportunity, indent=2, default=str)}\n\n"
                    f"USER LEVEL: {user_level}\n\n"
                    f"PORTFOLIO CONTEXT:\n{json.dumps(context.portfolio_state, indent=2, default=str)}\n\n"
                    f"Adapt the content for a {user_level} investor.  "
                    "Use their portfolio as examples where relevant.\n\n"
                    "Guidelines:\n"
                    "- Keep it concise (2-4 paragraphs max)\n"
                    "- Lead with why it matters, then explain the concept\n"
                    "- Include a practical 'so what' -- how should this "
                    "affect their decisions?\n"
                    "- Use an analogy if the concept is abstract\n"
                    "- End with 2-3 key takeaways\n\n"
                    "Return JSON with keys: title (string), type (string "
                    "matching opportunity type), content (string -- the actual "
                    "educational text), key_takeaways (array of 2-3 strings), "
                    "related_to_portfolio (bool), further_reading (array of "
                    "topic suggestions for deeper learning)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.6, max_tokens=2048
        )

        try:
            content = json.loads(response.content)
            if isinstance(content, dict):
                return content
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    async def _aggregate_trending_questions(
        self,
        platform_data: dict[str, Any],
        market_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Aggregate questions trending in the investing community.

        Identifies what retail and institutional investors are discussing,
        what misconceptions are common, and what questions are most relevant
        given current market conditions.

        Args:
            platform_data: Data from investment platforms and communities.
            market_events: Recent market events that may drive questions.

        Returns:
            List of trending question dicts, each with ``question``,
            ``context``, ``frequency``, ``platforms``, and ``brief_answer``.
        """
        if self._llm is None:
            return []

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "AGGREGATE TRENDING INVESTMENT QUESTIONS\n\n"
                    f"PLATFORM DATA:\n{json.dumps(platform_data, indent=2, default=str)}\n\n"
                    f"MARKET EVENTS:\n{json.dumps(market_events[:10], indent=2, default=str)}\n\n"
                    "Identify the top questions investors are asking right now:\n"
                    "1. What concepts are people confused about?\n"
                    "2. What market events are generating the most questions?\n"
                    "3. What common misconceptions are circulating?\n"
                    "4. What are sophisticated investors debating?\n\n"
                    "Return a JSON array of question objects with keys: "
                    "question (string), context (why this is being asked now), "
                    "frequency (how common -- high/medium/low), platforms "
                    "(array of where it is trending), brief_answer (1-2 sentence "
                    "answer), common_misconception (string or null)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.5, max_tokens=2048
        )

        try:
            questions = json.loads(response.content)
            if isinstance(questions, list):
                return questions
        except (json.JSONDecodeError, TypeError):
            pass

        return []
