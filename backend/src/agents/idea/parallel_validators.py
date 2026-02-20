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
# Helpers
# ---------------------------------------------------------------------------

import re

def _extract_tickers(idea: dict) -> list[str]:
    """Extract ticker symbols from an idea dict.

    Handles multiple formats:
    - List of dicts: [{"symbol": "SPY", "direction": "long"}]
    - List of strings: ["SPY", "QQQ"]
    - Comma-separated string: "SPY,QQQ"
    - Single ticker: "SPY"
    - Falls back to scanning thesis/title for $TICKER patterns.
    """
    tickers: list[str] = []

    # Explicit tickers field
    raw = idea.get("tickers", idea.get("ticker", []))
    if isinstance(raw, str):
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, list):
        for t in raw:
            if isinstance(t, dict):
                # Handle {"symbol": "SPY", "direction": "long", "weight": 1.0}
                sym = t.get("symbol", "").strip().upper()
                if sym:
                    tickers.append(sym)
            elif isinstance(t, str) and t.strip():
                tickers.append(t.strip().upper())

    # Scan thesis / title for $TICKER patterns
    if not tickers:
        text = f"{idea.get('title', '')} {idea.get('thesis', '')}"
        found = re.findall(r"\$([A-Z]{1,5})\b", text)
        tickers = list(dict.fromkeys(found))  # dedupe, preserve order

    return tickers[:10]  # cap at 10


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
    """Validates ideas using real backtests and LLM analysis.

    Step 1: LLM decides WHICH backtest to run and what defines success
    Step 2: Tools execute the actual backtest computation
    Step 3: LLM interprets results and scores the idea
    """

    def __init__(self) -> None:
        super().__init__(
            name="Backtest Validator",
            description="historical backtesting and base rate analysis",
            lens="backtest",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="backtest", score=0.5)

        tickers = _extract_tickers(idea)

        # Step 1: Run real backtests using tools (if we have tickers)
        tool_results: list[dict] = []
        if tickers:
            try:
                from src.services.validation_tools import (
                    backtest_momentum, backtest_mean_revert, get_price_levels
                )

                timeframe = idea.get("timeframe", "medium_term")
                # Choose backtest type based on thesis characteristics
                thesis = idea.get("thesis", "").lower()

                tasks = []
                if any(w in thesis for w in ("momentum", "trend", "breakout", "rally")):
                    tasks.append(backtest_momentum(tickers, entry_rule="price_above_sma_50"))
                if any(w in thesis for w in ("oversold", "revert", "bounce", "dip", "value")):
                    tasks.append(backtest_mean_revert(tickers))
                if not tasks:
                    # Default: run both
                    tasks.append(backtest_momentum(tickers))
                    tasks.append(backtest_mean_revert(tickers))

                # Always get price levels for context
                tasks.append(get_price_levels(tickers[0]))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if not isinstance(r, Exception) and r.success:
                        tool_results.append(r.to_dict())
            except ImportError:
                pass
            except Exception:
                logger.debug("Backtest tools failed", exc_info=True)

        # Step 2: LLM interprets real data + applies reasoning
        tool_context = ""
        if tool_results:
            tool_context = f"\nREAL BACKTEST RESULTS (from tools):\n{json.dumps(tool_results, default=str, indent=2)}\n"

        prompt = (
            "You are a quantitative analyst evaluating an investment idea. "
            "You have access to real backtest results from tools.\n\n"
            "Analyze critically:\n"
            "1. BACKTEST EVIDENCE: What do the actual numbers show? Win rate, "
            "Sharpe, max drawdown. Is the edge statistically significant?\n"
            "2. What SPECIFIC METRICS define success for this type of trade? "
            "(e.g., momentum trade needs >55% win rate and >1.5 Sharpe)\n"
            "3. REGIME SENSITIVITY: Does this work in current conditions?\n"
            "4. SAMPLE SIZE: Enough trades to be confident?\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n"
            f"{tool_context}\n"
            f"MARKET CONTEXT: {json.dumps(context.market_context, default=str)}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"success_metrics\": {\"metric_name\": \"threshold\"}, "
            "\"backtest_summary\": \"what the data actually shows\", "
            "\"flags\": [\"list of concerns\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.3, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            result["tool_results"] = tool_results  # Preserve for inspection
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
    """Validates ideas using real fundamental data + LLM analysis.

    Step 1: Fetch REAL fundamentals (P/E, EPS, margins) from tools
    Step 2: LLM decides what valuation metrics matter for this thesis
    Step 3: LLM scores the idea against the real data
    """

    def __init__(self) -> None:
        super().__init__(
            name="Fundamental Validator",
            description="fundamental analysis and valuation assessment",
            lens="fundamental",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="fundamental", score=0.5)

        tickers = _extract_tickers(idea)

        # Step 1: Fetch real fundamental data
        tool_results: list[dict] = []
        if tickers:
            try:
                from src.services.validation_tools import (
                    get_fundamentals, get_valuation_multiples, check_short_interest
                )
                tasks = [get_fundamentals(tickers)]
                if len(tickers) == 1:
                    tasks.append(get_valuation_multiples(tickers[0]))
                    tasks.append(check_short_interest(tickers[0]))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if not isinstance(r, Exception) and r.success:
                        tool_results.append(r.to_dict())
            except ImportError:
                pass
            except Exception:
                logger.debug("Fundamental tools failed", exc_info=True)

        # Step 2: LLM analyzes with real data
        tool_context = ""
        if tool_results:
            tool_context = f"\nREAL FUNDAMENTAL DATA (from tools):\n{json.dumps(tool_results, default=str, indent=2)}\n"

        knowledge_text = ""
        if context.knowledge_context:
            fund_k = [k for k in context.knowledge_context
                      if k.get("category") in ("fundamental", "research")]
            if fund_k:
                knowledge_text = f"\nKNOWLEDGE:\n{json.dumps(fund_k[:3], default=str)}"

        prompt = (
            "You are a fundamental equity analyst. You have REAL financial data "
            "from tools. Critically analyze:\n\n"
            "1. VALUATION: Given the actual P/E, EPS, and multiples, is this "
            "fairly valued? SPECIFY which metrics matter most for this thesis "
            "(e.g., 'for a growth story, forward P/E < 30 and revenue growth > 20% "
            "would make this attractive').\n"
            "2. CATALYST: Is the catalyst specific, material, and time-bound?\n"
            "3. FINANCIAL HEALTH: Real debt/equity, margins, ROE from data.\n"
            "4. What SPECIFIC fundamental thresholds define success? "
            "(e.g., 'EPS growth > 15%' or 'P/E expansion from 12x to 15x')\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n"
            f"{tool_context}"
            f"{knowledge_text}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"key_metrics\": {\"metric\": \"actual_value vs threshold\"}, "
            "\"valuation_verdict\": \"cheap|fair|expensive\", "
            "\"flags\": [\"list of concerns\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.3, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            result["tool_results"] = tool_results
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
    """Validates ideas with real statistical analysis and data quality checks.

    Step 1: Fetch REAL volatility, correlation, and risk/reward from tools
    Step 2: LLM interprets quantitative evidence and checks data quality
    Step 3: LLM scores the idea against the real statistics
    """

    def __init__(self) -> None:
        super().__init__(
            name="Data Analysis Validator",
            description="statistical analysis, data quality, and quantitative verification",
            lens="data_analysis",
        )

    async def validate(self, idea: dict, context: AgentContext) -> ValidationScore:
        if self._llm is None:
            return ValidationScore(lens="data_analysis", score=0.5)

        tickers = _extract_tickers(idea)

        # Step 1: Fetch real quantitative data
        tool_results: list[dict] = []
        if tickers:
            try:
                from src.services.validation_tools import (
                    get_historical_vol, check_correlation, calculate_risk_reward
                )

                tasks: list = [get_historical_vol(tickers)]

                # Check correlation with portfolio if we have holdings
                portfolio_tickers = []
                if context.portfolio_state:
                    positions = context.portfolio_state.get("positions", [])
                    portfolio_tickers = [
                        p.get("ticker", "") for p in positions
                        if isinstance(p, dict) and p.get("ticker")
                    ]
                if portfolio_tickers:
                    tasks.append(check_correlation(tickers, portfolio_tickers))

                # Calculate R:R if entry/stop/target provided
                entry = idea.get("entry_price") or idea.get("entry")
                stop = idea.get("stop_loss") or idea.get("stop")
                target = idea.get("target_price") or idea.get("target")
                if entry and stop and target:
                    try:
                        tasks.append(calculate_risk_reward(
                            float(entry), float(stop), float(target),
                            float(idea.get("position_size_pct", 5.0)),
                        ))
                    except (ValueError, TypeError):
                        pass

                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if not isinstance(r, Exception) and r.success:
                        tool_results.append(r.to_dict())
            except ImportError:
                pass
            except Exception:
                logger.debug("Data analysis tools failed", exc_info=True)

        # Step 2: LLM interprets real data
        tool_context = ""
        if tool_results:
            tool_context = f"\nREAL QUANTITATIVE DATA (from tools):\n{json.dumps(tool_results, default=str, indent=2)}\n"

        knowledge_text = ""
        if context.knowledge_context:
            knowledge_text = f"\nKNOWLEDGE:\n{json.dumps(context.knowledge_context[:3], default=str)}"

        prompt = (
            "You are a data scientist evaluating an investment idea. You have "
            "REAL quantitative data from tools (volatility, correlation, R:R). "
            "Critically analyze:\n\n"
            "1. DATA QUALITY: Are the facts in the thesis accurate? "
            "Do the real numbers from tools match the thesis claims?\n"
            "2. VOLATILITY: Given the actual vol, is the position sized correctly? "
            "Is the expected move realistic for the timeframe?\n"
            "3. RISK/REWARD: If R:R data available, is it attractive? "
            "DEFINE what R:R is needed for this trade type.\n"
            "4. CORRELATION: Does this trade add diversification or "
            "pile onto existing exposure? Use real correlation data.\n"
            "5. STATISTICAL SIGNIFICANCE: Is the signal strong enough? "
            "Estimate p-value or z-score.\n\n"
            f"IDEA: {json.dumps(idea, default=str)}\n"
            f"PORTFOLIO: {json.dumps(context.portfolio_state, default=str)}\n"
            f"{tool_context}"
            f"{knowledge_text}\n\n"
            "Respond with JSON: {\"score\": 0.0-1.0, \"analysis\": \"...\", "
            "\"data_quality\": \"poor|fair|good\", "
            "\"estimated_risk_reward\": 0.0, "
            "\"portfolio_correlation\": \"low|moderate|high\", "
            "\"vol_assessment\": \"low|normal|high|extreme\", "
            "\"flags\": [\"list of data concerns\"]}"
        )

        try:
            response = await self._llm.chat(
                [LLMMessage(role="user", content=prompt)],
                temperature=0.3, max_tokens=1024,
            )
            result = self._parse_score(response.content)
            result["tool_results"] = tool_results
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
