"""Parallel Validation Agents.

Multiple specialized validators run concurrently on each idea, each scoring
from a different analytical lens. Their scores are aggregated into a final
verdict (PASS / FAIL / NEEDS_MORE_DATA).

Architecture:
    For each idea:
        BacktestValidator ─────────┐
        FundamentalValidator ──────┤
        ReasoningValidator ────────┼──→ aggregate scores → verdict
        DataAnalysisValidator ─────┘

Score aggregation uses configurable weights:
    backtest=0.20, fundamental=0.25, reasoning=0.25, data_analysis=0.30

Thresholds (human-adjustable):
    PASS: weighted_score >= 0.60 AND reasoning >= 0.45
    FAIL: weighted_score < 0.35 OR reasoning < 0.25
    NEEDS_MORE_DATA: otherwise
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------

@dataclass
class ValidationScore:
    """Score from a single validation lens."""
    lens: str
    score: float  # 0.0 - 1.0
    analysis: str = ""
    flags: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationThresholds:
    """Human-adjustable thresholds for idea validation."""
    pass_score: float = 0.60
    fail_score: float = 0.35
    min_reasoning_score: float = 0.45
    min_reasoning_fail: float = 0.25

    # Weights for each validation lens
    weights: dict[str, float] = field(default_factory=lambda: {
        "backtest": 0.20,
        "fundamental": 0.25,
        "reasoning": 0.25,
        "data_analysis": 0.30,
    })


DEFAULT_THRESHOLDS = ValidationThresholds()


@dataclass
class ValidationResult:
    """Aggregated validation result across all lenses."""
    verdict: str  # PASS, FAIL, NEEDS_MORE_DATA
    weighted_score: float
    scores: dict[str, ValidationScore]
    reasoning: str
    flags: list[str]
    thresholds_used: dict[str, float]


# ---------------------------------------------------------------------------
# Base validator
# ---------------------------------------------------------------------------

class BaseValidator(BaseAgent):
    """Base class for validation agents."""

    def __init__(self, name: str, description: str, lens: str) -> None:
        super().__init__(name=name, agent_type="validation", description=description)
        self.lens = lens

    async def validate(
        self, idea: dict, context: AgentContext
    ) -> ValidationScore:
        """Validate an idea and return a score. Subclasses must implement."""
        raise NotImplementedError

    async def execute(
        self, input_data: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        idea = input_data.get("idea", {})
        score = await self.validate(idea, context)
        return {"score": score}

    def _parse_score(self, content: str) -> dict:
        """Parse LLM response into score dict."""
        try:
            result = json.loads(content)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        # Try extracting from code block
        if "```json" in content:
            start = content.index("```json") + 7
            end = content.index("```", start)
            try:
                return json.loads(content[start:end])
            except (json.JSONDecodeError, ValueError):
                pass
        elif "```" in content:
            start = content.index("```") + 3
            end = content.index("```", start)
            try:
                return json.loads(content[start:end])
            except (json.JSONDecodeError, ValueError):
                pass

        # Try finding object in text
        for i, ch in enumerate(content):
            if ch == "{":
                try:
                    return json.loads(content[i:])
                except json.JSONDecodeError:
                    pass

        return {"score": 0.5, "analysis": content[:500], "flags": []}


# ---------------------------------------------------------------------------
# Backtest Validator
# ---------------------------------------------------------------------------

class BacktestValidator(BaseValidator):
    """Validates ideas by checking historical base rates and backtest evidence."""

    def __init__(self) -> None:
        super().__init__(
            name="Backtest Validator",
            description="historical backtesting and base rate analysis",
            lens="backtest",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="backtest", score=0.5)

        prompt = (
            "You are a quantitative analyst evaluating an investment idea through "
            "a historical backtest lens. Analyze:\n\n"
            "1. HISTORICAL BASE RATE: How often has this type of trade worked "
            "historically? What's the win rate for similar setups?\n"
            "2. BACKTEST EVIDENCE: If you were to backtest this thesis over the "
            "last 5-10 years, what would the approximate results be?\n"
            "3. REGIME SENSITIVITY: Does this strategy work in all market regimes "
            "or only specific conditions? Are we in the right regime now?\n"
            "4. SAMPLE SIZE: Is there enough historical data to have confidence?\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n\n"
            f"MARKET CONTEXT: {json.dumps(context.market_context, default=str)}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"historical_win_rate\": 0.0-1.0, \"regime_match\": true/false, "
            "\"flags\": [\"list of concerns\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.3, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            return ValidationScore(
                lens="backtest",
                score=min(max(float(result.get("score", 0.5)), 0.0), 1.0),
                analysis=result.get("analysis", ""),
                flags=result.get("flags", []),
                details=result,
            )
        except Exception:
            logger.exception("BacktestValidator failed")
            return ValidationScore(lens="backtest", score=0.5, flags=["validation_error"])


# ---------------------------------------------------------------------------
# Fundamental Validator
# ---------------------------------------------------------------------------

class FundamentalValidator(BaseValidator):
    """Validates ideas using fundamental analysis and valuation checks."""

    def __init__(self) -> None:
        super().__init__(
            name="Fundamental Validator",
            description="fundamental analysis and valuation assessment",
            lens="fundamental",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="fundamental", score=0.5)

        knowledge_text = ""
        if context.knowledge_context:
            fund_k = [k for k in context.knowledge_context
                      if k.get("category") in ("fundamental", "research")]
            if fund_k:
                knowledge_text = f"\nKNOWLEDGE:\n{json.dumps(fund_k[:3], default=str)}"

        prompt = (
            "You are a fundamental equity analyst evaluating an investment idea. "
            "Analyze:\n\n"
            "1. VALUATION: Is the current valuation reasonable given the thesis? "
            "What P/E, EV/EBITDA, or other metrics are relevant?\n"
            "2. CATALYST: Is the catalyst specific, material, and time-bound? "
            "Could it move the stock meaningfully?\n"
            "3. EARNINGS IMPACT: How would this thesis affect earnings? "
            "Is the market already pricing this in?\n"
            "4. COMPETITIVE DYNAMICS: What are the competitive moats or threats?\n"
            "5. FINANCIAL HEALTH: Debt levels, cash flow, and balance sheet risk?\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n"
            f"{knowledge_text}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"valuation_assessment\": \"...\", \"catalyst_strength\": \"...\", "
            "\"flags\": [\"list of concerns\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.3, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            return ValidationScore(
                lens="fundamental",
                score=min(max(float(result.get("score", 0.5)), 0.0), 1.0),
                analysis=result.get("analysis", ""),
                flags=result.get("flags", []),
                details=result,
            )
        except Exception:
            logger.exception("FundamentalValidator failed")
            return ValidationScore(lens="fundamental", score=0.5, flags=["validation_error"])


# ---------------------------------------------------------------------------
# Reasoning Validator
# ---------------------------------------------------------------------------

class ReasoningValidator(BaseValidator):
    """Checks for logical fallacies, cognitive biases, and narrative traps."""

    def __init__(self) -> None:
        super().__init__(
            name="Reasoning Validator",
            description="logic checking, bias detection, and reasoning quality",
            lens="reasoning",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="reasoning", score=0.5)

        prompt = (
            "You are a critical thinking expert evaluating an investment thesis "
            "for logical flaws and cognitive biases. Be adversarial. Your job is "
            "to find weaknesses. Check for:\n\n"
            "1. LOGICAL FALLACIES: Post hoc reasoning, false causation, "
            "survivorship bias, anchoring, confirmation bias, narrative fallacy.\n"
            "2. INFORMATION QUALITY: Is the thesis based on verified facts or "
            "rumors? Is the source credible? Is the data cherry-picked?\n"
            "3. CONSENSUS TRAP: Is this just restating consensus? If everyone "
            "agrees, where's the edge?\n"
            "4. SECOND-ORDER EFFECTS: What could go wrong that the thesis "
            "doesn't consider? What are the unintended consequences?\n"
            "5. THESIS CLARITY: Is the thesis falsifiable? Can you define "
            "what would prove it wrong?\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"biases_detected\": [\"list\"], \"logical_issues\": [\"list\"], "
            "\"reasoning_quality\": \"poor|fair|good|excellent\", "
            "\"flags\": [\"list of red flags\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.2, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            return ValidationScore(
                lens="reasoning",
                score=min(max(float(result.get("score", 0.5)), 0.0), 1.0),
                analysis=result.get("analysis", ""),
                flags=result.get("flags", []) + result.get("biases_detected", []),
                details=result,
            )
        except Exception:
            logger.exception("ReasoningValidator failed")
            return ValidationScore(lens="reasoning", score=0.5, flags=["validation_error"])


# ---------------------------------------------------------------------------
# Data Analysis Validator
# ---------------------------------------------------------------------------

class DataAnalysisValidator(BaseValidator):
    """Validates ideas with statistical analysis and data quality checks."""

    def __init__(self) -> None:
        super().__init__(
            name="Data Analysis Validator",
            description="statistical analysis, data quality, and quantitative verification",
            lens="data_analysis",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="data_analysis", score=0.5)

        knowledge_text = ""
        if context.knowledge_context:
            knowledge_text = f"\nKNOWLEDGE:\n{json.dumps(context.knowledge_context[:3], default=str)}"

        prompt = (
            "You are a data scientist evaluating an investment idea through "
            "quantitative analysis. Check:\n\n"
            "1. DATA QUALITY: Are the facts and numbers in the thesis accurate? "
            "Are there obvious data errors or misinterpretations?\n"
            "2. STATISTICAL SIGNIFICANCE: Is the signal strong enough to act on? "
            "What's the approximate p-value or z-score of the claimed pattern?\n"
            "3. RISK/REWARD MATH: Does the expected value calculation make sense? "
            "What's the approximate Sharpe ratio or risk/reward ratio?\n"
            "4. CORRELATION ANALYSIS: How correlated is this trade with the "
            "existing portfolio? Would it add diversification?\n"
            "5. MARKET MICROSTRUCTURE: Liquidity, bid-ask spreads, market impact "
            "for the proposed position size.\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n"
            f"PORTFOLIO: {json.dumps(context.portfolio_state, default=str)}\n"
            f"{knowledge_text}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"data_quality\": \"poor|fair|good\", "
            "\"estimated_risk_reward\": 0.0, "
            "\"portfolio_correlation\": \"low|moderate|high\", "
            "\"flags\": [\"list of data concerns\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.3, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            return ValidationScore(
                lens="data_analysis",
                score=min(max(float(result.get("score", 0.5)), 0.0), 1.0),
                analysis=result.get("analysis", ""),
                flags=result.get("flags", []),
                details=result,
            )
        except Exception:
            logger.exception("DataAnalysisValidator failed")
            return ValidationScore(lens="data_analysis", score=0.5, flags=["validation_error"])


# ---------------------------------------------------------------------------
# Parallel validation runner
# ---------------------------------------------------------------------------

ALL_VALIDATORS: list[type[BaseValidator]] = [
    BacktestValidator,
    FundamentalValidator,
    ReasoningValidator,
    DataAnalysisValidator,
]


async def validate_idea_parallel(
    idea: dict[str, Any],
    context: AgentContext,
    llm_provider: Any,
    thresholds: ValidationThresholds | None = None,
    validators: list[type[BaseValidator]] | None = None,
) -> ValidationResult:
    """Run all validators in parallel on a single idea and aggregate scores.

    Args:
        idea: The investment idea to validate.
        context: Shared agent context.
        llm_provider: LLM provider to inject.
        thresholds: Human-adjustable validation thresholds.
        validators: Validator classes to use. Defaults to all.

    Returns:
        Aggregated ValidationResult with verdict.
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    validator_classes = validators or ALL_VALIDATORS

    # Instantiate and inject LLM
    agents: list[BaseValidator] = []
    for cls in validator_classes:
        agent = cls()
        agent._llm = llm_provider
        agents.append(agent)

    logger.info(
        "Running %d parallel validators on idea '%s'",
        len(agents),
        idea.get("title", "Untitled"),
    )

    # Run all validators concurrently
    tasks = [agent.validate(idea, context) for agent in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect scores
    scores: dict[str, ValidationScore] = {}
    all_flags: list[str] = []

    for agent, result in zip(agents, results):
        if isinstance(result, Exception):
            logger.error("%s failed: %s", agent.name, result)
            scores[agent.lens] = ValidationScore(
                lens=agent.lens, score=0.5, flags=["validator_crashed"]
            )
        else:
            scores[agent.lens] = result
            all_flags.extend(result.flags)

    # Calculate weighted score
    weighted_score = 0.0
    total_weight = 0.0
    for lens, weight in thresholds.weights.items():
        if lens in scores:
            weighted_score += scores[lens].score * weight
            total_weight += weight

    if total_weight > 0:
        weighted_score /= total_weight
    else:
        weighted_score = 0.5

    # Determine verdict
    reasoning_score = scores.get("reasoning", ValidationScore(lens="reasoning", score=0.5)).score

    if weighted_score >= thresholds.pass_score and reasoning_score >= thresholds.min_reasoning_score:
        verdict = "PASS"
    elif weighted_score < thresholds.fail_score or reasoning_score < thresholds.min_reasoning_fail:
        verdict = "FAIL"
    else:
        verdict = "NEEDS_MORE_DATA"

    # Build reasoning summary
    score_summary = ", ".join(
        f"{lens}={s.score:.2f}" for lens, s in scores.items()
    )
    reasoning = (
        f"Weighted score: {weighted_score:.2f}. "
        f"Individual scores: {score_summary}. "
        f"Verdict: {verdict}."
    )
    if all_flags:
        reasoning += f" Flags: {'; '.join(all_flags[:5])}"

    logger.info(
        "Validation result for '%s': %s (score=%.2f)",
        idea.get("title", "Untitled"),
        verdict,
        weighted_score,
    )

    return ValidationResult(
        verdict=verdict,
        weighted_score=round(weighted_score, 4),
        scores=scores,
        reasoning=reasoning,
        flags=all_flags,
        thresholds_used={
            "pass_score": thresholds.pass_score,
            "fail_score": thresholds.fail_score,
            "min_reasoning_score": thresholds.min_reasoning_score,
            "weights": thresholds.weights,
        },
    )


async def validate_ideas_batch(
    ideas: list[dict[str, Any]],
    context: AgentContext,
    llm_provider: Any,
    thresholds: ValidationThresholds | None = None,
    max_concurrent: int = 3,
) -> list[tuple[dict, ValidationResult]]:
    """Validate a batch of ideas, running validations concurrently.

    Args:
        ideas: List of ideas to validate.
        context: Shared context.
        llm_provider: LLM provider.
        thresholds: Validation thresholds.
        max_concurrent: Max ideas to validate simultaneously.

    Returns:
        List of (idea, ValidationResult) tuples.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _validate_one(idea: dict) -> tuple[dict, ValidationResult]:
        async with semaphore:
            result = await validate_idea_parallel(
                idea, context, llm_provider, thresholds
            )
            return idea, result

    tasks = [_validate_one(idea) for idea in ideas]
    return await asyncio.gather(*tasks)
