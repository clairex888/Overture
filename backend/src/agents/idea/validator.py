"""Idea Validation Agent for the Overture system.

This agent critically evaluates investment ideas produced by the Idea
Generator.  It applies multiple validation lenses -- backtesting,
fundamental analysis, logical reasoning, source credibility, and risk
assessment -- to determine whether an idea should proceed to execution
planning.
"""

from __future__ import annotations

import json
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Idea Validation Agent for Overture, an AI-driven
hedge fund assistant.  Your role is to critically evaluate investment theses
using rigorous analytical frameworks.  You are the quality gate -- your job is
to REJECT bad ideas and only pass ideas that withstand scrutiny.

You evaluate every idea through five lenses:

1. BACKTESTING: Would this thesis have worked historically?  What is the base
   rate for similar setups?  Are there analogous past situations?
2. FUNDAMENTAL ANALYSIS: Do the numbers support the thesis?  Are valuations
   reasonable?  Is the catalyst real and material?
3. REASONING CHECK: Is the logic sound?  Are there logical fallacies, anchoring
   biases, or narrative-driven reasoning?  Could this be a value trap, a
   pump-and-dump, or recency bias?
4. SOURCE CREDIBILITY: How reliable is the source?  Does the author have a
   track record?  Are there conflicts of interest?
5. RISK ASSESSMENT: What could go wrong?  What is the downside scenario?  Is
   the risk/reward asymmetry favorable?

For each lens, provide:
- A score from 0.0 to 1.0 (1.0 = passes with flying colors)
- A brief explanation of your reasoning
- Any red flags or concerns

Final verdict: PASS, FAIL, or NEEDS_MORE_DATA with an overall confidence score
and clear explanation.

Be especially skeptical of:
- Ideas based solely on price momentum without fundamental support
- Overcrowded trades where positioning is extreme
- Theses that depend on a single catalyst with binary outcomes
- Ideas from anonymous or unverified sources
- Any thesis that sounds too good to be true
"""


class IdeaValidatorAgent(BaseAgent):
    """Agent that validates investment ideas through multiple analytical lenses.

    Acts as a quality gate in the idea pipeline, filtering out ideas that
    do not withstand rigorous scrutiny before they reach execution planning.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Idea Validator",
            agent_type="idea",
            description=(
                "critically evaluating investment theses using backtesting, "
                "fundamental analysis, logical reasoning, and risk assessment"
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
        """Validate an investment idea through multiple analytical lenses.

        Args:
            input_data: Dictionary containing:
                - idea: The structured idea dict from the generator
                - supplemental_data: Optional additional data for validation
            context: Shared agent context.

        Returns:
            Dictionary with key ``validation_result`` containing:
                - verdict: "PASS", "FAIL", or "NEEDS_MORE_DATA"
                - confidence_score: float 0.0 - 1.0
                - backtest_results: dict with score and analysis
                - fundamental_results: dict with score and analysis
                - reasoning_results: dict with score and analysis
                - source_credibility: dict with score and analysis
                - risk_assessment: dict with score and analysis
                - risk_flags: list of identified risks
                - reasoning: str overall explanation
                - original_idea: the input idea (passed through)
        """
        idea = input_data.get("idea", {})
        supplemental_data = input_data.get("supplemental_data", {})

        # Run all validation lenses
        backtest_results = await self._backtest_thesis(idea, context)
        fundamental_results = await self._fundamental_analysis(idea, context)
        reasoning_results = await self._reasoning_check(idea, context)
        source_results = await self._source_credibility_check(idea, context)
        risk_results = await self._risk_assessment(idea, context)

        # Aggregate scores
        scores = {
            "backtest": backtest_results.get("score", 0.5),
            "fundamental": fundamental_results.get("score", 0.5),
            "reasoning": reasoning_results.get("score", 0.5),
            "source_credibility": source_results.get("score", 0.5),
            "risk": risk_results.get("score", 0.5),
        }

        # Weighted average (reasoning and risk get higher weight)
        weights = {
            "backtest": 0.20,
            "fundamental": 0.25,
            "reasoning": 0.25,
            "source_credibility": 0.10,
            "risk": 0.20,
        }
        confidence_score = sum(
            scores[k] * weights[k] for k in scores
        )

        # Determine verdict
        risk_flags = risk_results.get("risk_flags", [])
        if confidence_score >= 0.65 and reasoning_results.get("score", 0) >= 0.5:
            verdict = "PASS"
        elif confidence_score < 0.4 or reasoning_results.get("score", 0) < 0.3:
            verdict = "FAIL"
        else:
            verdict = "NEEDS_MORE_DATA"

        # Generate overall reasoning summary
        reasoning_summary = await self._synthesize_verdict(
            idea, scores, risk_flags, verdict, confidence_score, context
        )

        validation_result = {
            "verdict": verdict,
            "confidence_score": round(confidence_score, 3),
            "scores": scores,
            "backtest_results": backtest_results,
            "fundamental_results": fundamental_results,
            "reasoning_results": reasoning_results,
            "source_credibility": source_results,
            "risk_assessment": risk_results,
            "risk_flags": risk_flags,
            "reasoning": reasoning_summary,
            "original_idea": idea,
        }

        await self.log_action(
            action="validate_idea",
            input_data={"idea_title": idea.get("title", "unknown")},
            output_data={
                "verdict": verdict,
                "confidence_score": confidence_score,
            },
        )

        return {"validation_result": validation_result}

    # ------------------------------------------------------------------
    # Validation lenses
    # ------------------------------------------------------------------

    async def _backtest_thesis(
        self, idea: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Evaluate the idea against historical patterns and backtesting.

        Asks the LLM to reason about historical base rates for similar
        setups, analogous past situations, and what backtesting such a
        thesis would reveal.

        Args:
            idea: The investment idea to validate.

        Returns:
            Dictionary with ``score`` (0-1), ``analysis``, and
            ``historical_analogues``.
        """
        if self._llm is None:
            return {"score": 0.5, "analysis": "LLM not available", "historical_analogues": []}

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "BACKTEST EVALUATION\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    "Evaluate this thesis from a backtesting perspective:\n"
                    "1. What is the historical base rate for similar setups?\n"
                    "2. Are there analogous past situations? What happened?\n"
                    "3. If you backtested this exact thesis over the past 10-20 "
                    "years, what would the hit rate and risk/reward be?\n"
                    "4. Are there survivorship bias or data-mining concerns?\n\n"
                    "Return JSON with keys: score (0.0-1.0), analysis (string), "
                    "historical_analogues (array of strings)."
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

        return {"score": 0.5, "analysis": response.content, "historical_analogues": []}

    async def _fundamental_analysis(
        self, idea: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Evaluate the fundamental validity of the investment thesis.

        Checks whether valuations, earnings, catalysts, and macro
        conditions support the thesis.

        Args:
            idea: The investment idea to validate.

        Returns:
            Dictionary with ``score`` (0-1), ``analysis``,
            ``valuation_assessment``, and ``catalyst_assessment``.
        """
        if self._llm is None:
            return {
                "score": 0.5,
                "analysis": "LLM not available",
                "valuation_assessment": "",
                "catalyst_assessment": "",
            }

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "FUNDAMENTAL ANALYSIS EVALUATION\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"MARKET CONTEXT:\n{json.dumps(context.market_context, default=str)}\n\n"
                    "Evaluate this thesis from a fundamental perspective:\n"
                    "1. Are the valuations of the referenced securities "
                    "reasonable for the thesis?\n"
                    "2. Is there a real, material catalyst? When is it expected?\n"
                    "3. Do earnings, revenue, or macro data support the thesis?\n"
                    "4. Is this thesis already priced in?\n"
                    "5. What is the fundamental bear case?\n\n"
                    "Return JSON with keys: score (0.0-1.0), analysis (string), "
                    "valuation_assessment (string), catalyst_assessment (string)."
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

        return {
            "score": 0.5,
            "analysis": response.content,
            "valuation_assessment": "",
            "catalyst_assessment": "",
        }

    async def _reasoning_check(
        self, idea: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Evaluate the logical soundness of the investment thesis.

        Looks for cognitive biases, logical fallacies, and narrative traps
        that could make a bad idea sound compelling.

        Args:
            idea: The investment idea to validate.

        Returns:
            Dictionary with ``score`` (0-1), ``analysis``,
            ``biases_detected`` (list), and ``logical_issues`` (list).
        """
        if self._llm is None:
            return {
                "score": 0.5,
                "analysis": "LLM not available",
                "biases_detected": [],
                "logical_issues": [],
            }

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "REASONING & LOGIC CHECK\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    "Critically evaluate the logical soundness of this thesis. "
                    "Look for:\n"
                    "1. Confirmation bias - is the thesis cherry-picking data?\n"
                    "2. Recency bias - is it extrapolating recent trends?\n"
                    "3. Anchoring - is it anchored to an arbitrary price level?\n"
                    "4. Narrative fallacy - is it a compelling story without "
                    "substance?\n"
                    "5. Survivorship bias - are we only seeing the winners?\n"
                    "6. Crowded trade risk - is everyone already in this?\n"
                    "7. Value trap - cheap for a reason?\n"
                    "8. Pump and dump signals\n"
                    "9. Correlation vs causation confusion\n"
                    "10. Missing the base rate (how often does this actually work?)\n\n"
                    "Return JSON with keys: score (0.0-1.0), analysis (string), "
                    "biases_detected (array of strings), "
                    "logical_issues (array of strings)."
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

        return {
            "score": 0.5,
            "analysis": response.content,
            "biases_detected": [],
            "logical_issues": [],
        }

    async def _source_credibility_check(
        self, idea: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Evaluate the reliability of the idea's source.

        Considers track record, potential conflicts of interest,
        expertise in the relevant domain, and whether the source has
        skin in the game.

        Args:
            idea: The investment idea to validate.

        Returns:
            Dictionary with ``score`` (0-1), ``analysis``, and
            ``credibility_flags`` (list).
        """
        if self._llm is None:
            return {"score": 0.5, "analysis": "LLM not available", "credibility_flags": []}

        source = idea.get("source", "unknown")

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "SOURCE CREDIBILITY CHECK\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"SOURCE: {source}\n\n"
                    "Evaluate the credibility of this idea's source:\n"
                    "1. Is the source identified and verifiable?\n"
                    "2. Does the source have relevant domain expertise?\n"
                    "3. What is the source's historical track record?\n"
                    "4. Are there potential conflicts of interest?\n"
                    "5. Is the source likely to have skin in the game?\n"
                    "6. Could this be promotional content or a pump scheme?\n\n"
                    "Return JSON with keys: score (0.0-1.0), analysis (string), "
                    "credibility_flags (array of strings describing concerns)."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=1024
        )

        try:
            result = json.loads(response.content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        return {"score": 0.5, "analysis": response.content, "credibility_flags": []}

    async def _risk_assessment(
        self, idea: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        """Assess the potential risks of the investment idea.

        Considers downside scenarios, tail risks, liquidity concerns,
        correlation to existing portfolio, and risk/reward asymmetry.

        Args:
            idea: The investment idea to validate.

        Returns:
            Dictionary with ``score`` (0-1), ``analysis``,
            ``risk_flags`` (list), and ``risk_reward_ratio``.
        """
        if self._llm is None:
            return {
                "score": 0.5,
                "analysis": "LLM not available",
                "risk_flags": [],
                "risk_reward_ratio": None,
            }

        portfolio_text = json.dumps(context.portfolio_state, default=str)

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "RISK ASSESSMENT\n\n"
                    f"IDEA:\n{json.dumps(idea, indent=2, default=str)}\n\n"
                    f"CURRENT PORTFOLIO:\n{portfolio_text}\n\n"
                    "Assess the risks of this idea:\n"
                    "1. What is the worst-case downside scenario?\n"
                    "2. What tail risks exist (liquidity, gap risk, regulatory)?\n"
                    "3. How correlated is this to existing portfolio positions?\n"
                    "4. What is the estimated risk/reward ratio?\n"
                    "5. Is there asymmetry in the payoff (capped upside vs "
                    "unlimited downside or vice versa)?\n"
                    "6. What market regime change would hurt this position?\n\n"
                    "Return JSON with keys: score (0.0-1.0 where 1.0 means "
                    "acceptable risk), analysis (string), risk_flags (array "
                    "of risk descriptions), risk_reward_ratio (number or null)."
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

        return {
            "score": 0.5,
            "analysis": response.content,
            "risk_flags": [],
            "risk_reward_ratio": None,
        }

    async def _synthesize_verdict(
        self,
        idea: dict[str, Any],
        scores: dict[str, float],
        risk_flags: list[str],
        verdict: str,
        confidence_score: float,
        context: AgentContext,
    ) -> str:
        """Synthesize a human-readable summary of the validation verdict.

        Args:
            idea: The original idea.
            scores: Scores from each validation lens.
            risk_flags: Identified risk flags.
            verdict: The determined verdict.
            confidence_score: The overall confidence score.

        Returns:
            A concise reasoning summary string.
        """
        if self._llm is None:
            return f"Verdict: {verdict} (confidence: {confidence_score:.2f})"

        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(
                role="user",
                content=(
                    "Synthesize a 2-3 sentence summary explaining the "
                    "validation verdict for this idea.\n\n"
                    f"IDEA TITLE: {idea.get('title', 'N/A')}\n"
                    f"VERDICT: {verdict}\n"
                    f"CONFIDENCE: {confidence_score:.3f}\n"
                    f"SCORES: {json.dumps(scores)}\n"
                    f"RISK FLAGS: {json.dumps(risk_flags)}\n\n"
                    "Write a clear, concise explanation suitable for an "
                    "investment committee.  Do not use JSON -- just plain text."
                ),
            ),
        ]

        response: LLMResponse = await self._llm.chat(
            messages, temperature=0.3, max_tokens=512
        )

        return response.content
