"""Reasoning-First Validation Engine.

Replaces the old "4 parallel LLM validators" approach with a robust,
tool-first pipeline that ALWAYS produces meaningful results:

    1. **Plan**  – A reasoning step decides what needs to be validated
                   and which tools to run (rule-based, no LLM required).
    2. **Execute** – Deterministic tools (backtest, fundamentals, vol,
                     price levels, correlation) run concurrently.
    3. **Score**  – Tool outputs are scored with transparent, rule-based
                    rubrics so validation NEVER returns a blank 50%.
    4. **Synthesize** – If an LLM is available, it writes a rich
                        chain-of-thought narrative.  If not, a structured
                        template is generated from tool data.

The full chain-of-thought (plan -> tool data -> scoring -> synthesis) is
returned to the frontend so users can inspect every step.

Interactive hooks:
    - Users can provide feedback after seeing results.
    - Users can suggest additional analysis or override methodology.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChainOfThoughtStep:
    """One step in the validation reasoning chain."""
    step: str          # planning, tool_execution, scoring, synthesis
    title: str         # Human-readable title
    content: str       # The reasoning / result text
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"step": self.step, "title": self.title, "content": self.content, "data": self.data}


@dataclass
class ValidationScore:
    """Score from a single validation lens."""
    lens: str
    score: float
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

    weights: dict[str, float] = field(default_factory=lambda: {
        "backtest": 0.20,
        "fundamental": 0.25,
        "reasoning": 0.25,
        "data_analysis": 0.30,
    })


DEFAULT_THRESHOLDS = ValidationThresholds()


@dataclass
class ValidationResult:
    """Full validation result with chain-of-thought."""
    verdict: str
    weighted_score: float
    scores: dict[str, ValidationScore]
    reasoning: str
    flags: list[str]
    thresholds_used: dict[str, float]
    chain_of_thought: list[ChainOfThoughtStep] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    suggested_actions: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ticker extraction
# ---------------------------------------------------------------------------

def _extract_tickers(idea: dict) -> list[str]:
    """Extract ticker symbols from an idea dict (handles all formats)."""
    tickers: list[str] = []
    raw = idea.get("tickers", idea.get("ticker", []))

    if isinstance(raw, str):
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
    elif isinstance(raw, list):
        for t in raw:
            if isinstance(t, dict):
                sym = t.get("symbol", "").strip().upper()
                if sym:
                    tickers.append(sym)
            elif isinstance(t, str) and t.strip():
                tickers.append(t.strip().upper())

    if not tickers:
        text = f"{idea.get('title', '')} {idea.get('thesis', '')}"
        found = re.findall(r"\$([A-Z]{1,5})\b", text)
        tickers = list(dict.fromkeys(found))

    return tickers[:10]


# ---------------------------------------------------------------------------
# Tool-based scoring rubrics
# ---------------------------------------------------------------------------

def _score_backtest(tool_results: list[dict]) -> ValidationScore:
    """Score idea based on actual backtest tool results."""
    if not tool_results:
        return ValidationScore(
            lens="backtest", score=0.4,
            analysis="No backtest data available — no historical price data could be fetched for the specified tickers.",
            flags=["no_backtest_data"],
        )

    all_win_rates: list[float] = []
    all_sharpes: list[float] = []
    all_trade_counts: list[int] = []
    findings: list[str] = []
    flags: list[str] = []

    for tr in tool_results:
        data = tr.get("data", {})
        results = data.get("results", {})
        for ticker, stats in results.items():
            if isinstance(stats, dict) and "win_rate" in stats:
                all_win_rates.append(stats["win_rate"])
                all_sharpes.append(stats.get("sharpe_ratio", 0))
                all_trade_counts.append(stats.get("trade_count", 0))
                findings.append(
                    f"{ticker}: {stats['trade_count']} trades, "
                    f"{stats['win_rate']:.0%} win rate, "
                    f"Sharpe {stats.get('sharpe_ratio', 0):.2f}, "
                    f"avg return {stats.get('avg_return_pct', 0):.1f}%"
                )
            elif isinstance(stats, dict) and stats.get("trade_count", 0) == 0:
                findings.append(f"{ticker}: No trading signals triggered in backtest period")
                flags.append(f"no_signals_{ticker}")

    if not all_win_rates:
        return ValidationScore(
            lens="backtest", score=0.4,
            analysis="Backtest ran but produced no trades. The entry conditions were never met in the historical period.",
            flags=["no_backtest_trades"],
            details={"tool_results": tool_results},
        )

    avg_win = sum(all_win_rates) / len(all_win_rates)
    avg_sharpe = sum(all_sharpes) / len(all_sharpes)
    avg_trades = sum(all_trade_counts) / len(all_trade_counts)

    score = 0.5
    analysis_parts: list[str] = []

    if avg_win >= 0.65:
        score += 0.2
        analysis_parts.append(f"Strong win rate of {avg_win:.0%}")
    elif avg_win >= 0.55:
        score += 0.1
        analysis_parts.append(f"Decent win rate of {avg_win:.0%}")
    elif avg_win < 0.45:
        score -= 0.15
        analysis_parts.append(f"Weak win rate of {avg_win:.0%}")
        flags.append("low_win_rate")

    if avg_sharpe >= 1.5:
        score += 0.15
        analysis_parts.append(f"Excellent risk-adjusted returns (Sharpe {avg_sharpe:.2f})")
    elif avg_sharpe >= 0.5:
        score += 0.05
        analysis_parts.append(f"Acceptable Sharpe ratio of {avg_sharpe:.2f}")
    elif avg_sharpe < 0:
        score -= 0.15
        analysis_parts.append(f"Negative Sharpe ratio ({avg_sharpe:.2f}) — poor risk-adjusted returns")
        flags.append("negative_sharpe")

    if avg_trades < 10:
        score -= 0.1
        analysis_parts.append(f"Small sample size ({avg_trades:.0f} trades) — results may not be reliable")
        flags.append("small_sample")
    elif avg_trades >= 30:
        score += 0.05
        analysis_parts.append(f"Good sample size ({avg_trades:.0f} trades)")

    score = max(0.0, min(1.0, score))

    analysis = ". ".join(analysis_parts) + "."
    if findings:
        analysis += "\n\nDetailed results:\n" + "\n".join(f"  - {f}" for f in findings)

    return ValidationScore(
        lens="backtest", score=round(score, 3),
        analysis=analysis,
        flags=flags,
        details={"tool_results": tool_results, "avg_win_rate": round(avg_win, 3),
                 "avg_sharpe": round(avg_sharpe, 2), "avg_trade_count": round(avg_trades, 1)},
    )


def _score_fundamental(tool_results: list[dict]) -> ValidationScore:
    """Score idea based on fundamental data tool results."""
    if not tool_results:
        return ValidationScore(
            lens="fundamental", score=0.4,
            analysis="No fundamental data available for the specified tickers.",
            flags=["no_fundamental_data"],
        )

    score = 0.5
    analysis_parts: list[str] = []
    flags: list[str] = []
    key_metrics: dict[str, Any] = {}

    for tr in tool_results:
        data = tr.get("data", {})
        tool_name = tr.get("tool", "")

        if tool_name == "get_fundamentals":
            for ticker, info in data.get("fundamentals", {}).items():
                if isinstance(info, dict) and "error" not in info:
                    pe = info.get("pe_ratio")
                    fwd_pe = info.get("forward_pe")
                    rev_growth = info.get("revenue_growth")
                    roe = info.get("roe")
                    debt_eq = info.get("debt_to_equity")
                    margin = info.get("profit_margin")

                    key_metrics[ticker] = {}

                    if pe is not None:
                        key_metrics[ticker]["P/E"] = f"{pe:.1f}"
                        if pe < 15:
                            score += 0.08
                            analysis_parts.append(f"{ticker} P/E of {pe:.1f} suggests value")
                        elif pe > 40:
                            score -= 0.05
                            analysis_parts.append(f"{ticker} P/E of {pe:.1f} is elevated")
                            flags.append(f"high_pe_{ticker}")

                    if rev_growth is not None:
                        key_metrics[ticker]["Revenue Growth"] = f"{rev_growth:.1%}"
                        if rev_growth > 0.20:
                            score += 0.1
                            analysis_parts.append(f"{ticker} strong revenue growth of {rev_growth:.1%}")
                        elif rev_growth < 0:
                            score -= 0.1
                            analysis_parts.append(f"{ticker} negative revenue growth ({rev_growth:.1%})")
                            flags.append(f"declining_revenue_{ticker}")

                    if roe is not None:
                        key_metrics[ticker]["ROE"] = f"{roe:.1%}"
                        if roe > 0.15:
                            score += 0.05
                        elif roe < 0:
                            score -= 0.05
                            flags.append(f"negative_roe_{ticker}")

                    if margin is not None:
                        key_metrics[ticker]["Profit Margin"] = f"{margin:.1%}"
                        if margin > 0.20:
                            score += 0.05
                        elif margin < 0:
                            flags.append(f"unprofitable_{ticker}")

                    if debt_eq is not None:
                        key_metrics[ticker]["Debt/Equity"] = f"{debt_eq:.1f}"
                        if debt_eq > 200:
                            score -= 0.05
                            flags.append(f"high_leverage_{ticker}")

        elif tool_name == "get_valuation_multiples":
            ev_ebitda = data.get("ev_to_ebitda")
            peg = data.get("peg_ratio")
            if ev_ebitda is not None:
                if ev_ebitda < 10:
                    score += 0.05
                    analysis_parts.append(f"EV/EBITDA of {ev_ebitda:.1f} looks attractive")
                elif ev_ebitda > 25:
                    score -= 0.05
                    analysis_parts.append(f"EV/EBITDA of {ev_ebitda:.1f} is stretched")
            if peg is not None and peg > 0:
                if peg < 1.0:
                    score += 0.05
                    analysis_parts.append(f"PEG ratio of {peg:.1f} — undervalued relative to growth")
                elif peg > 2.5:
                    score -= 0.05

        elif tool_name == "check_short_interest":
            short_pct = data.get("short_pct_float")
            if short_pct is not None:
                if short_pct > 20:
                    analysis_parts.append(f"High short interest ({short_pct:.1f}%) — squeeze risk")
                    flags.append("high_short_interest")

    score = max(0.0, min(1.0, score))
    analysis = ". ".join(analysis_parts) + "." if analysis_parts else "Fundamental data collected but no strong signals detected."

    return ValidationScore(
        lens="fundamental", score=round(score, 3),
        analysis=analysis,
        flags=flags,
        details={"tool_results": tool_results, "key_metrics": key_metrics},
    )


def _score_data_analysis(tool_results: list[dict], idea: dict) -> ValidationScore:
    """Score based on volatility, correlation, price levels, and risk/reward."""
    if not tool_results:
        return ValidationScore(
            lens="data_analysis", score=0.4,
            analysis="No quantitative data available for the specified tickers.",
            flags=["no_quant_data"],
        )

    score = 0.5
    analysis_parts: list[str] = []
    flags: list[str] = []

    for tr in tool_results:
        data = tr.get("data", {})
        tool_name = tr.get("tool", "")

        if tool_name == "get_historical_vol":
            for ticker, vol_data in data.get("volatility", {}).items():
                vol_30 = vol_data.get("vol_30d_ann_pct")
                if vol_30 is not None:
                    if vol_30 > 60:
                        score -= 0.1
                        analysis_parts.append(f"{ticker} extremely volatile ({vol_30:.0f}% annualized)")
                        flags.append(f"extreme_vol_{ticker}")
                    elif vol_30 > 35:
                        analysis_parts.append(f"{ticker} elevated volatility ({vol_30:.0f}%)")
                    elif vol_30 < 15:
                        score += 0.05
                        analysis_parts.append(f"{ticker} low volatility ({vol_30:.0f}%)")

        elif tool_name == "get_price_levels":
            trend = data.get("trend", "neutral")
            current = data.get("current", 0)
            high_52w = data.get("52w_high", 0)

            thesis_lower = idea.get("thesis", "").lower()
            is_bullish = any(w in thesis_lower for w in ("long", "buy", "bullish", "rally", "breakout", "momentum"))
            is_bearish = any(w in thesis_lower for w in ("short", "sell", "bearish", "decline", "crash"))

            if trend == "bullish" and is_bullish:
                score += 0.1
                analysis_parts.append("Price trend confirms bullish thesis (above SMA 50 & 200)")
            elif trend == "bearish" and is_bearish:
                score += 0.1
                analysis_parts.append("Price trend confirms bearish thesis (below SMA 50)")
            elif trend == "bullish" and is_bearish:
                score -= 0.1
                analysis_parts.append("WARNING: Bearish thesis contradicts current bullish price trend")
                flags.append("trend_contradiction")
            elif trend == "bearish" and is_bullish:
                score -= 0.1
                analysis_parts.append("WARNING: Bullish thesis contradicts current bearish price trend")
                flags.append("trend_contradiction")

            if high_52w and current and high_52w > 0:
                pct_from_high = (current - high_52w) / high_52w * 100
                if pct_from_high > -5:
                    analysis_parts.append(f"Trading near 52-week high ({pct_from_high:+.1f}%)")
                elif pct_from_high < -30:
                    analysis_parts.append(f"Significantly below 52-week high ({pct_from_high:+.1f}%)")

        elif tool_name == "check_correlation":
            correlations = data.get("correlations", {})
            for ticker, corr_map in correlations.items():
                high_corr = [f"{pt}: {c:.2f}" for pt, c in corr_map.items() if abs(c) > 0.7]
                if high_corr:
                    score -= 0.05
                    analysis_parts.append(f"{ticker} highly correlated with portfolio: {', '.join(high_corr)}")
                    flags.append("high_correlation")

        elif tool_name == "calculate_risk_reward":
            rr = data.get("risk_reward_ratio", 0)
            if rr >= 3:
                score += 0.15
                analysis_parts.append(f"Excellent risk/reward ratio of {rr:.1f}:1")
            elif rr >= 2:
                score += 0.1
                analysis_parts.append(f"Good risk/reward ratio of {rr:.1f}:1")
            elif rr < 1:
                score -= 0.1
                analysis_parts.append(f"Poor risk/reward ratio of {rr:.1f}:1")
                flags.append("poor_risk_reward")

    score = max(0.0, min(1.0, score))
    analysis = ". ".join(analysis_parts) + "." if analysis_parts else "Quantitative data collected but no strong signals."

    return ValidationScore(
        lens="data_analysis", score=round(score, 3),
        analysis=analysis,
        flags=flags,
        details={"tool_results": tool_results},
    )


def _score_reasoning(idea: dict) -> ValidationScore:
    """Score the quality of the thesis reasoning itself (rule-based)."""
    thesis = idea.get("thesis", "")
    risks = idea.get("risks", [])
    tickers = _extract_tickers(idea)

    score = 0.5
    analysis_parts: list[str] = []
    flags: list[str] = []
    biases: list[str] = []

    word_count = len(thesis.split())
    if word_count >= 100:
        score += 0.1
        analysis_parts.append(f"Detailed thesis ({word_count} words)")
    elif word_count >= 50:
        score += 0.05
        analysis_parts.append(f"Moderate thesis detail ({word_count} words)")
    elif word_count < 20:
        score -= 0.15
        analysis_parts.append(f"Very brief thesis ({word_count} words) — lacks detail")
        flags.append("thin_thesis")

    catalyst_words = ["earnings", "fda", "fed ", "rate ", "merger", "acquisition",
                      "launch", "approval", "regulation", "election", "tariff",
                      "inventory", "supply", "demand", "guidance"]
    has_catalyst = any(w in thesis.lower() for w in catalyst_words)
    if has_catalyst:
        score += 0.1
        analysis_parts.append("Contains specific catalyst")
    else:
        analysis_parts.append("No clear catalyst identified")

    numbers = re.findall(r'\d+\.?\d*%|\$\d+\.?\d*|\d+x', thesis)
    if len(numbers) >= 3:
        score += 0.1
        analysis_parts.append(f"Quantitatively specific ({len(numbers)} data points)")
    elif len(numbers) == 0:
        score -= 0.05
        analysis_parts.append("Lacks quantitative specificity")
        flags.append("no_numbers")

    time_words = ["week", "month", "quarter", "year", "2025", "2026", "q1", "q2", "q3", "q4"]
    has_timeframe = any(w in thesis.lower() for w in time_words)
    if has_timeframe:
        score += 0.05
        analysis_parts.append("Has specific time horizon")

    if risks and len(risks) >= 2:
        score += 0.1
        analysis_parts.append(f"Identifies {len(risks)} risk factors")
    elif not risks:
        score -= 0.05
        analysis_parts.append("No risk factors identified")
        flags.append("no_risks_stated")

    vague_phrases = ["i think", "i believe", "probably", "maybe", "could be", "might"]
    for phrase in vague_phrases:
        if phrase in thesis.lower():
            biases.append(f"Vague language: '{phrase}'")
            score -= 0.03

    certainty_phrases = ["guaranteed", "definitely", "always", "never", "can't fail",
                         "sure thing", "100%", "no risk", "free money"]
    for phrase in certainty_phrases:
        if phrase in thesis.lower():
            biases.append(f"Overconfidence: '{phrase}'")
            score -= 0.1
            flags.append("overconfidence")

    if len(tickers) == 0:
        score -= 0.1
        flags.append("no_tickers")
    elif len(tickers) == 1:
        analysis_parts.append("Single-ticker concentrated bet")

    falsifiable_words = ["if ", "unless", "would invalidate", "stop loss",
                         "exit if", "the thesis fails if"]
    is_falsifiable = any(w in thesis.lower() for w in falsifiable_words)
    if is_falsifiable:
        score += 0.05
        analysis_parts.append("Thesis is falsifiable — has exit conditions")

    score = max(0.0, min(1.0, score))
    analysis = ". ".join(analysis_parts) + "."
    if biases:
        analysis += "\n\nBiases detected:\n" + "\n".join(f"  - {b}" for b in biases)

    return ValidationScore(
        lens="reasoning", score=round(score, 3),
        analysis=analysis,
        flags=flags + biases[:3],
        details={"biases_detected": biases, "word_count": word_count,
                 "has_catalyst": has_catalyst, "num_datapoints": len(numbers),
                 "is_falsifiable": is_falsifiable},
    )


# ---------------------------------------------------------------------------
# Main validation runner
# ---------------------------------------------------------------------------

async def validate_idea_parallel(
    idea: dict[str, Any],
    context: Any,
    llm_provider: Any,
    thresholds: ValidationThresholds | None = None,
    user_guidance: str | None = None,
) -> ValidationResult:
    """Run the full reasoning-first validation pipeline.

    1. Plan: Decide what tools to run
    2. Execute: Run tools concurrently (deterministic)
    3. Score: Score from tool results (rule-based)
    4. Synthesize: Build chain-of-thought narrative (LLM optional)
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    chain: list[ChainOfThoughtStep] = []
    tickers = _extract_tickers(idea)

    # ===================== STEP 1: PLANNING =====================

    thesis = idea.get("thesis", "").lower()
    plan_parts: list[str] = []
    tools_to_run: list[str] = []

    thesis_type = "general"
    if any(w in thesis for w in ("momentum", "trend", "breakout", "rally", "uptrend")):
        thesis_type = "momentum"
    elif any(w in thesis for w in ("oversold", "revert", "bounce", "dip", "value", "cheap")):
        thesis_type = "mean_reversion"
    elif any(w in thesis for w in ("earnings", "growth", "revenue", "margin", "fundamental")):
        thesis_type = "fundamental"

    plan_parts.append(f"Thesis type identified: **{thesis_type}**")

    portfolio_tickers: list[str] = []

    if tickers:
        plan_parts.append(f"Tickers to analyze: {', '.join(tickers)}")
        tools_to_run.extend(["get_price_levels", "get_historical_vol", "get_fundamentals"])

        if thesis_type == "momentum":
            tools_to_run.append("backtest_momentum")
            plan_parts.append("Running momentum backtest (price above SMA 50)")
        elif thesis_type == "mean_reversion":
            tools_to_run.append("backtest_mean_revert")
            plan_parts.append("Running mean-reversion backtest (Z-score entry)")
        else:
            tools_to_run.extend(["backtest_momentum", "backtest_mean_revert"])
            plan_parts.append("Running both momentum and mean-reversion backtests")

        if len(tickers) == 1:
            tools_to_run.extend(["get_valuation_multiples", "check_short_interest"])
            plan_parts.append("Running valuation multiples and short interest check")

        portfolio_state = getattr(context, 'portfolio_state', None) or {}
        if portfolio_state:
            positions = portfolio_state.get("positions", [])
            portfolio_tickers = [p.get("ticker", "") for p in positions if isinstance(p, dict) and p.get("ticker")]
        if portfolio_tickers:
            tools_to_run.append("check_correlation")
            plan_parts.append(f"Checking correlation with portfolio holdings: {', '.join(portfolio_tickers[:5])}")
    else:
        plan_parts.append("No tickers found — will validate thesis reasoning only")

    if user_guidance:
        plan_parts.append(f"User guidance: {user_guidance}")

    chain.append(ChainOfThoughtStep(
        step="planning",
        title="Validation Plan",
        content="\n".join(f"- {p}" for p in plan_parts),
        data={"tools_to_run": tools_to_run, "thesis_type": thesis_type, "tickers": tickers},
    ))

    logger.info(
        "Validation plan for '%s': %d tools, thesis_type=%s, tickers=%s",
        idea.get("title", "Untitled"), len(tools_to_run), thesis_type, tickers,
    )

    # ===================== STEP 2: TOOL EXECUTION =====================

    backtest_results: list[dict] = []
    fundamental_results: list[dict] = []
    quant_results: list[dict] = []

    if tickers and tools_to_run:
        try:
            from src.services.validation_tools import (
                backtest_momentum, backtest_mean_revert, get_fundamentals,
                get_valuation_multiples, get_historical_vol, get_price_levels,
                check_correlation, check_short_interest,
            )

            tasks: list[tuple[str, Any]] = []
            for tool_name in tools_to_run:
                if tool_name == "backtest_momentum":
                    entry_rule = "price_above_sma_50"
                    if "52w_high" in thesis or "new high" in thesis:
                        entry_rule = "new_52w_high"
                    tasks.append(("backtest", backtest_momentum(tickers, entry_rule=entry_rule)))
                elif tool_name == "backtest_mean_revert":
                    tasks.append(("backtest", backtest_mean_revert(tickers)))
                elif tool_name == "get_fundamentals":
                    tasks.append(("fundamental", get_fundamentals(tickers)))
                elif tool_name == "get_valuation_multiples":
                    tasks.append(("fundamental", get_valuation_multiples(tickers[0])))
                elif tool_name == "check_short_interest":
                    tasks.append(("fundamental", check_short_interest(tickers[0])))
                elif tool_name == "get_historical_vol":
                    tasks.append(("quant", get_historical_vol(tickers)))
                elif tool_name == "get_price_levels":
                    tasks.append(("quant", get_price_levels(tickers[0])))
                elif tool_name == "check_correlation":
                    tasks.append(("quant", check_correlation(tickers, portfolio_tickers)))

            coros = [t[1] for t in tasks]
            categories = [t[0] for t in tasks]
            results = await asyncio.gather(*coros, return_exceptions=True)

            tool_summaries: list[str] = []
            for category, result in zip(categories, results):
                if isinstance(result, Exception):
                    tool_summaries.append(f"Tool error: {result}")
                    continue
                if not result.success:
                    tool_summaries.append(f"{result.tool_name}: FAILED — {result.error}")
                    continue

                result_dict = result.to_dict()
                tool_summaries.append(f"**{result.tool_name}**: {result.methodology}")

                if category == "backtest":
                    backtest_results.append(result_dict)
                elif category == "fundamental":
                    fundamental_results.append(result_dict)
                else:
                    quant_results.append(result_dict)

            chain.append(ChainOfThoughtStep(
                step="tool_execution",
                title="Tool Results",
                content="\n".join(f"- {s}" for s in tool_summaries),
                data={
                    "backtest_results": backtest_results,
                    "fundamental_results": fundamental_results,
                    "quant_results": quant_results,
                    "tools_succeeded": sum(1 for r in results if not isinstance(r, Exception) and r.success),
                    "tools_total": len(results),
                },
            ))

        except ImportError:
            chain.append(ChainOfThoughtStep(
                step="tool_execution", title="Tool Results",
                content="Validation tools not available (yfinance not installed)",
            ))
        except Exception as e:
            logger.exception("Tool execution failed")
            chain.append(ChainOfThoughtStep(
                step="tool_execution", title="Tool Results",
                content=f"Tool execution encountered an error: {e}",
            ))

    # ===================== STEP 3: SCORING =====================

    backtest_score = _score_backtest(backtest_results)
    fundamental_score = _score_fundamental(fundamental_results)
    data_analysis_score = _score_data_analysis(quant_results, idea)
    reasoning_score = _score_reasoning(idea)

    scores = {
        "backtest": backtest_score,
        "fundamental": fundamental_score,
        "reasoning": reasoning_score,
        "data_analysis": data_analysis_score,
    }

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

    rs = reasoning_score.score
    if weighted_score >= thresholds.pass_score and rs >= thresholds.min_reasoning_score:
        verdict = "PASS"
    elif weighted_score < thresholds.fail_score or rs < thresholds.min_reasoning_fail:
        verdict = "FAIL"
    else:
        verdict = "NEEDS_MORE_DATA"

    all_flags: list[str] = []
    for s in scores.values():
        all_flags.extend(s.flags)

    scoring_summary_parts = []
    for lens, s in scores.items():
        scoring_summary_parts.append(f"**{lens.replace('_', ' ').title()}**: {s.score:.0%}")
    scoring_summary = " | ".join(scoring_summary_parts)

    chain.append(ChainOfThoughtStep(
        step="scoring",
        title="Score Breakdown",
        content=(
            f"Individual scores: {scoring_summary}\n"
            f"Weighted score: **{weighted_score:.0%}** -> Verdict: **{verdict}**"
        ),
        data={
            "scores": {k: {"score": v.score, "flags": v.flags} for k, v in scores.items()},
            "weighted_score": weighted_score,
            "verdict": verdict,
        },
    ))

    # ===================== STEP 4: SYNTHESIS =====================

    key_findings: list[str] = []
    for s in scores.values():
        if s.analysis:
            first_sentence = s.analysis.split(". ")[0]
            if first_sentence:
                key_findings.append(first_sentence)

    synthesis_text = ""
    if llm_provider is not None:
        try:
            from src.agents.llm.base import LLMMessage

            tool_data_summary = json.dumps({
                "backtest_results": backtest_results[:2],
                "fundamental_results": fundamental_results[:2],
                "quant_results": quant_results[:2],
            }, default=str, indent=2)

            synthesis_prompt = (
                "You are a senior investment analyst writing a validation summary. "
                "You have REAL data from tools. Write a concise, structured analysis.\n\n"
                f"IDEA: {idea.get('title', '')}\n"
                f"THESIS: {idea.get('thesis', '')}\n\n"
                f"TOOL DATA:\n{tool_data_summary}\n\n"
                f"SCORES: backtest={backtest_score.score:.2f}, "
                f"fundamental={fundamental_score.score:.2f}, "
                f"reasoning={reasoning_score.score:.2f}, "
                f"data_analysis={data_analysis_score.score:.2f}\n"
                f"VERDICT: {verdict} ({weighted_score:.0%})\n\n"
                "Write 3-4 sentences synthesizing the key findings. "
                "Be specific — cite actual numbers from the data. "
                "End with the strongest argument FOR and AGAINST the thesis."
            )

            response = await llm_provider.chat(
                [LLMMessage(role="user", content=synthesis_prompt)],
                temperature=0.3, max_tokens=500,
            )
            synthesis_text = response.content
        except Exception:
            logger.debug("LLM synthesis failed, using template", exc_info=True)

    if not synthesis_text:
        synthesis_parts = []
        synthesis_parts.append(
            f"The idea \"{idea.get('title', '')}\" received a weighted validation "
            f"score of {weighted_score:.0%}, resulting in a **{verdict}** verdict."
        )
        if key_findings:
            synthesis_parts.append("Key findings: " + "; ".join(key_findings[:3]) + ".")
        if all_flags:
            synthesis_parts.append("Concerns: " + ", ".join(all_flags[:5]) + ".")
        synthesis_text = " ".join(synthesis_parts)

    chain.append(ChainOfThoughtStep(
        step="synthesis",
        title="Analysis Summary",
        content=synthesis_text,
    ))

    score_summary = ", ".join(f"{lens}={s.score:.2f}" for lens, s in scores.items())
    reasoning = (
        f"Weighted score: {weighted_score:.2f}. "
        f"Individual scores: {score_summary}. "
        f"Verdict: {verdict}."
    )
    if all_flags:
        reasoning += f" Flags: {'; '.join(all_flags[:5])}"

    suggested_actions: list[dict[str, str]] = []
    if verdict == "NEEDS_MORE_DATA":
        suggested_actions.append({
            "action": "provide_guidance",
            "label": "Provide additional context",
            "description": "Share more details about the thesis for deeper analysis",
        })
    if backtest_score.score < 0.5:
        suggested_actions.append({
            "action": "extend_backtest",
            "label": "Run extended backtest",
            "description": "Test with different entry rules or longer time period",
        })
    if fundamental_score.score < 0.5 and tickers:
        suggested_actions.append({
            "action": "sector_comparison",
            "label": "Compare vs sector peers",
            "description": "Deep dive into sector-relative valuation",
        })

    logger.info(
        "Validation complete for '%s': %s (score=%.2f)",
        idea.get("title", "Untitled"), verdict, weighted_score,
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
        chain_of_thought=chain,
        key_findings=key_findings,
        suggested_actions=suggested_actions,
    )


async def validate_ideas_batch(
    ideas: list[dict[str, Any]],
    context: Any,
    llm_provider: Any,
    thresholds: ValidationThresholds | None = None,
    max_concurrent: int = 3,
) -> list[tuple[dict, ValidationResult]]:
    """Validate a batch of ideas concurrently."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _validate_one(idea: dict) -> tuple[dict, ValidationResult]:
        async with semaphore:
            result = await validate_idea_parallel(
                idea, context, llm_provider, thresholds
            )
            return idea, result

    tasks = [_validate_one(idea) for idea in ideas]
    return await asyncio.gather(*tasks)
