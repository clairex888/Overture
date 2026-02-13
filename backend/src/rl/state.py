"""
State encoders for the Overture RL trading agents.

Each agent role observes a different slice of the environment.  The
:class:`StateEncoder` converts raw environment dictionaries into
structured, *normalised* representations that are suitable for RL
training (bounded numeric values, fixed-length vectors where possible,
and consistent key schemas).

Normalisation conventions used throughout:
* Prices are expressed as percentage changes relative to a reference
  (usually previous close or entry price).
* Volumes are expressed as multiples of a trailing average.
* Sentiment scores are already in [-1, 1].
* Boolean flags are encoded as 0.0 / 1.0.
* Missing values default to 0.0 with a companion ``*_valid`` flag set to 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper normalisation utilities
# ---------------------------------------------------------------------------

def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """Clip *value* to [*lo*, *hi*]."""
    return max(lo, min(hi, value))


def _safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Return *numerator / denominator*, or *default* when division is undefined."""
    if denominator == 0.0:
        return default
    return numerator / denominator


def _normalize_pct(value: float, scale: float = 100.0) -> float:
    """Convert a percentage to a [-1, 1] range given an expected *scale*."""
    return _clip(value / scale, -1.0, 1.0)


def _normalize_zscore(value: float, mean: float, std: float) -> float:
    """Standard z-score normalisation, clipped to [-3, 3]."""
    if std == 0.0:
        return 0.0
    return _clip((value - mean) / std, -3.0, 3.0)


# ---------------------------------------------------------------------------
# StateEncoder
# ---------------------------------------------------------------------------

class StateEncoder:
    """Converts raw environment state dicts into structured, normalised
    observation dicts for each agent role.

    Each ``encode_*`` method accepts the relevant raw data and returns
    a flat-ish dict whose values are floats or short lists of floats,
    ready for consumption by an RL policy or value network.

    The encoder is stateless -- all normalisation parameters (means,
    stds, reference prices) must be present in the input data or in
    the optional ``config`` dict passed at construction time.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

        # Default reference values for normalisation
        self._sentiment_scale: float = self.config.get("sentiment_scale", 1.0)
        self._volume_avg_window: int = self.config.get("volume_avg_window", 20)
        self._max_positions: int = self.config.get("max_positions", 50)
        self._max_sectors: int = self.config.get("max_sectors", 11)  # GICS sectors

    # ==================================================================
    # 1.  Idea Generator
    # ==================================================================

    def encode_idea_generator_state(
        self,
        market_state: dict[str, Any],
        knowledge_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Encode the observation for the **idea-generator** agent.

        The idea generator needs a broad view of the market to spot
        opportunities: recent news, market regime, sector momentum,
        unusual moves, and trending social topics.

        Returns a dict with keys:
        - ``recent_news_embeddings``: list of embedding vectors (or
          empty list if unavailable).
        - ``market_regime``: dict with normalised regime indicators.
        - ``sector_momentum``: dict mapping sector names to momentum z-scores.
        - ``unusual_moves``: list of dicts describing anomalous tickers.
        - ``trending_topics``: list of topic strings with associated scores.
        """
        # -- recent news embeddings (pass through; downstream can truncate) --
        raw_news = knowledge_state.get("recent_news", [])
        news_embeddings: list[list[float]] = []
        for item in raw_news[:20]:  # cap at 20 items
            emb = item.get("embedding")
            if emb and isinstance(emb, list):
                news_embeddings.append(emb)

        # -- market regime --
        regime = market_state.get("regime", {})
        market_regime = {
            "vix_level": _normalize_pct(regime.get("vix", 20.0) - 20.0, scale=30.0),
            "trend_strength": _clip(regime.get("trend_strength", 0.0), -1.0, 1.0),
            "breadth": _clip(regime.get("breadth", 0.5), 0.0, 1.0),
            "volatility_regime": _clip(regime.get("volatility_regime", 0.0), -1.0, 1.0),
            "momentum_regime": _clip(regime.get("momentum_regime", 0.0), -1.0, 1.0),
            "risk_on": 1.0 if regime.get("risk_on", True) else 0.0,
        }

        # -- sector momentum --
        raw_sectors = market_state.get("sector_performance", {})
        sector_momentum: dict[str, float] = {}
        for sector, data in raw_sectors.items():
            if isinstance(data, dict):
                mom = data.get("momentum_1m", 0.0)
            else:
                mom = float(data) if data is not None else 0.0
            sector_momentum[sector] = _normalize_pct(mom, scale=10.0)

        # -- unusual moves --
        raw_moves = market_state.get("unusual_moves", [])
        unusual_moves: list[dict[str, Any]] = []
        for move in raw_moves[:10]:
            unusual_moves.append({
                "ticker": move.get("ticker", ""),
                "change_pct_norm": _normalize_pct(move.get("change_pct", 0.0), scale=20.0),
                "volume_ratio": _clip(move.get("volume_ratio", 1.0), 0.0, 10.0) / 10.0,
                "has_news": 1.0 if move.get("has_news", False) else 0.0,
            })

        # -- trending topics --
        raw_topics = knowledge_state.get("trending_topics", [])
        trending_topics: list[dict[str, Any]] = []
        for topic in raw_topics[:10]:
            if isinstance(topic, dict):
                trending_topics.append({
                    "topic": topic.get("topic", ""),
                    "score": _clip(topic.get("score", 0.0), 0.0, 1.0),
                    "sentiment": _clip(topic.get("sentiment", 0.0), -1.0, 1.0),
                })
            elif isinstance(topic, str):
                trending_topics.append({
                    "topic": topic,
                    "score": 0.5,
                    "sentiment": 0.0,
                })

        return {
            "recent_news_embeddings": news_embeddings,
            "market_regime": market_regime,
            "sector_momentum": sector_momentum,
            "unusual_moves": unusual_moves,
            "trending_topics": trending_topics,
            "has_news": 1.0 if news_embeddings else 0.0,
            "has_anomalies": 1.0 if unusual_moves else 0.0,
            "has_social": 1.0 if trending_topics else 0.0,
        }

    # ==================================================================
    # 2.  Idea Validator
    # ==================================================================

    def encode_idea_validator_state(
        self,
        idea: dict[str, Any],
        market_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Encode the observation for the **idea-validator** agent.

        The validator needs detailed information about the idea itself
        together with historical context to judge quality.

        Returns a dict with keys:
        - ``idea_features``: normalised numeric features of the idea.
        - ``historical_similar_ideas``: summary stats of past similar ideas.
        - ``backtest_summary``: key backtest metrics (if available).
        - ``source_score``: reliability score of the idea source.
        - ``market_context``: compact market-regime features.
        """
        # -- idea features --
        idea_features = {
            "confidence_score": _clip(idea.get("confidence_score", 0.5), 0.0, 1.0),
            "expected_return_norm": _normalize_pct(idea.get("expected_return", 0.0), scale=50.0),
            "risk_level_encoded": _encode_risk_level(idea.get("risk_level", "medium")),
            "timeframe_encoded": _encode_timeframe(idea.get("timeframe", "medium_term")),
            "num_tickers": _clip(len(idea.get("tickers", [])) / 5.0, 0.0, 1.0),
            "has_thesis": 1.0 if idea.get("thesis") else 0.0,
            "source_encoded": _encode_idea_source(idea.get("source", "agent")),
        }

        # -- historical similar ideas --
        similar = idea.get("similar_historical_ideas", [])
        if similar:
            win_rate = sum(1 for s in similar if s.get("profitable", False)) / len(similar)
            avg_return = sum(s.get("return_pct", 0.0) for s in similar) / len(similar)
            count = len(similar)
        else:
            win_rate = 0.5
            avg_return = 0.0
            count = 0

        historical_similar_ideas = {
            "count_norm": _clip(count / 20.0, 0.0, 1.0),
            "win_rate": _clip(win_rate, 0.0, 1.0),
            "avg_return_norm": _normalize_pct(avg_return, scale=20.0),
        }

        # -- backtest summary --
        bt = idea.get("backtest_results", {})
        backtest_summary = {
            "sharpe": _clip(bt.get("sharpe", 0.0) / 3.0, -1.0, 1.0),
            "max_drawdown_norm": _clip(bt.get("max_drawdown_pct", 0.0) / -50.0, -1.0, 0.0),
            "win_rate": _clip(bt.get("win_rate", 0.5), 0.0, 1.0),
            "profit_factor": _clip(bt.get("profit_factor", 1.0) / 3.0, 0.0, 1.0),
            "available": 1.0 if bt else 0.0,
        }

        # -- source score --
        source_reliability = {
            "news": 0.7,
            "screen": 0.6,
            "agent": 0.5,
            "user": 0.8,
            "aggregated": 0.75,
        }
        source_score = source_reliability.get(idea.get("source", "agent"), 0.5)

        # -- market context (compact) --
        regime = market_state.get("regime", {})
        market_context = {
            "vix_level": _normalize_pct(regime.get("vix", 20.0) - 20.0, scale=30.0),
            "trend_strength": _clip(regime.get("trend_strength", 0.0), -1.0, 1.0),
            "risk_on": 1.0 if regime.get("risk_on", True) else 0.0,
        }

        return {
            "idea_features": idea_features,
            "historical_similar_ideas": historical_similar_ideas,
            "backtest_summary": backtest_summary,
            "source_score": source_score,
            "market_context": market_context,
        }

    # ==================================================================
    # 3.  Trade Executor
    # ==================================================================

    def encode_trade_executor_state(
        self,
        validated_idea: dict[str, Any],
        portfolio_state: dict[str, Any],
        market_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Encode the observation for the **trade-executor** agent.

        The executor needs the validated idea's parameters, the current
        portfolio exposure, correlations with existing positions,
        available instruments, and liquidity information.

        Returns a dict with keys:
        - ``idea_params``: normalised idea parameters.
        - ``portfolio_exposure``: current sector / factor exposures.
        - ``correlation_with_existing``: similarity to open positions.
        - ``available_instruments``: list of instruments to trade.
        - ``liquidity_metrics``: bid-ask, volume, market-impact estimates.
        """
        # -- idea params --
        idea_params = {
            "expected_return_norm": _normalize_pct(
                validated_idea.get("expected_return", 0.0), scale=50.0
            ),
            "confidence": _clip(validated_idea.get("confidence_score", 0.5), 0.0, 1.0),
            "risk_level_encoded": _encode_risk_level(
                validated_idea.get("risk_level", "medium")
            ),
            "timeframe_encoded": _encode_timeframe(
                validated_idea.get("timeframe", "medium_term")
            ),
            "suggested_direction": 1.0 if validated_idea.get("direction", "long") == "long" else -1.0,
        }

        # -- portfolio exposure --
        positions = portfolio_state.get("positions", [])
        total_value = max(portfolio_state.get("total_value", 1.0), 1.0)
        invested = portfolio_state.get("invested", 0.0)
        cash = portfolio_state.get("cash", 0.0)

        sector_exposure: dict[str, float] = {}
        for pos in positions:
            sector = pos.get("asset_class", "unknown")
            weight = pos.get("weight", 0.0)
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + weight

        portfolio_exposure = {
            "invested_pct": _clip(invested / total_value, 0.0, 1.5),
            "cash_pct": _clip(cash / total_value, 0.0, 1.0),
            "num_positions_norm": _clip(len(positions) / self._max_positions, 0.0, 1.0),
            "sector_exposure": {k: _clip(v, 0.0, 1.0) for k, v in sector_exposure.items()},
        }

        # -- correlation with existing --
        idea_tickers = set(validated_idea.get("tickers", []))
        overlap_count = 0
        max_corr = 0.0
        for pos in positions:
            if pos.get("ticker") in idea_tickers:
                overlap_count += 1
            corr = pos.get("correlation_to_idea", 0.0)
            max_corr = max(max_corr, abs(corr))

        correlation_with_existing = {
            "ticker_overlap_norm": _clip(overlap_count / max(len(idea_tickers), 1), 0.0, 1.0),
            "max_correlation": _clip(max_corr, 0.0, 1.0),
            "avg_portfolio_correlation": _clip(
                portfolio_state.get("avg_correlation", 0.0), 0.0, 1.0
            ),
        }

        # -- available instruments --
        raw_instruments = market_state.get("available_instruments", [])
        available_instruments: list[dict[str, Any]] = []
        for inst in raw_instruments[:10]:
            available_instruments.append({
                "symbol": inst.get("symbol", ""),
                "type": inst.get("type", "equity"),
                "liquidity_score": _clip(inst.get("liquidity_score", 0.5), 0.0, 1.0),
                "spread_bps_norm": _clip(inst.get("spread_bps", 5.0) / 50.0, 0.0, 1.0),
            })

        # -- liquidity metrics --
        primary_ticker = (validated_idea.get("tickers") or [""])[0]
        ticker_data = market_state.get("ticker_data", {}).get(primary_ticker, {})
        avg_volume = max(ticker_data.get("avg_volume", 1.0), 1.0)

        liquidity_metrics = {
            "bid_ask_spread_bps_norm": _clip(
                ticker_data.get("bid_ask_spread_bps", 5.0) / 50.0, 0.0, 1.0
            ),
            "volume_ratio": _clip(
                ticker_data.get("volume", avg_volume) / avg_volume, 0.0, 5.0
            ) / 5.0,
            "market_impact_bps_norm": _clip(
                ticker_data.get("estimated_impact_bps", 2.0) / 20.0, 0.0, 1.0
            ),
        }

        return {
            "idea_params": idea_params,
            "portfolio_exposure": portfolio_exposure,
            "correlation_with_existing": correlation_with_existing,
            "available_instruments": available_instruments,
            "liquidity_metrics": liquidity_metrics,
        }

    # ==================================================================
    # 4.  Trade Monitor
    # ==================================================================

    def encode_trade_monitor_state(
        self,
        trade: dict[str, Any],
        market_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Encode the observation for the **trade-monitor** agent.

        The monitor needs the current trade P&L, elapsed time, thesis
        validity signals, stop distance, and market regime.

        Returns a dict with keys:
        - ``trade_pnl``: normalised P&L metrics for the trade.
        - ``time_elapsed``: normalised time since entry.
        - ``thesis_signals``: current status of the original thesis.
        - ``stop_distance``: normalised distance to stop and target.
        - ``market_regime``: compact regime features.
        """
        entry_price = max(trade.get("entry_price", 1.0), 0.01)
        current_price = trade.get("current_price", entry_price)
        stop_loss = trade.get("stop_loss", 0.0)
        take_profit = trade.get("take_profit", 0.0)
        direction = trade.get("direction", "long")

        # P&L calculation
        if direction == "long":
            pnl_pct = (current_price - entry_price) / entry_price * 100.0
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100.0

        trade_pnl = {
            "pnl_pct_norm": _normalize_pct(pnl_pct, scale=20.0),
            "pnl_dollar_norm": _normalize_pct(trade.get("pnl", 0.0), scale=10000.0),
            "unrealised_pnl_pct": _normalize_pct(pnl_pct, scale=20.0),
            "max_favorable_excursion_norm": _normalize_pct(
                trade.get("max_favorable_excursion_pct", 0.0), scale=20.0
            ),
            "max_adverse_excursion_norm": _normalize_pct(
                trade.get("max_adverse_excursion_pct", 0.0), scale=20.0
            ),
        }

        # Time elapsed
        total_expected_seconds = max(trade.get("expected_duration_seconds", 86400.0), 1.0)
        elapsed_seconds = trade.get("elapsed_seconds", 0.0)
        time_elapsed = {
            "fraction_of_expected": _clip(elapsed_seconds / total_expected_seconds, 0.0, 3.0) / 3.0,
            "hours_norm": _clip(elapsed_seconds / 3600.0 / 168.0, 0.0, 1.0),  # cap at 1 week
            "is_overdue": 1.0 if elapsed_seconds > total_expected_seconds else 0.0,
        }

        # Thesis signals
        signals = trade.get("thesis_signals", {})
        thesis_signals = {
            "thesis_intact": 1.0 if signals.get("intact", True) else 0.0,
            "catalyst_occurred": 1.0 if signals.get("catalyst_occurred", False) else 0.0,
            "sentiment_shift": _clip(signals.get("sentiment_shift", 0.0), -1.0, 1.0),
            "fundamental_change": 1.0 if signals.get("fundamental_change", False) else 0.0,
        }

        # Stop distance
        if direction == "long":
            stop_dist = (current_price - stop_loss) / entry_price * 100.0 if stop_loss > 0 else 0.0
            target_dist = (take_profit - current_price) / entry_price * 100.0 if take_profit > 0 else 0.0
        else:
            stop_dist = (stop_loss - current_price) / entry_price * 100.0 if stop_loss > 0 else 0.0
            target_dist = (current_price - take_profit) / entry_price * 100.0 if take_profit > 0 else 0.0

        stop_distance = {
            "stop_distance_pct_norm": _normalize_pct(stop_dist, scale=10.0),
            "target_distance_pct_norm": _normalize_pct(target_dist, scale=10.0),
            "risk_reward_ratio": _clip(
                _safe_div(target_dist, abs(stop_dist) if stop_dist else 1.0), 0.0, 5.0
            ) / 5.0,
            "stop_breached": 1.0 if stop_dist < 0 else 0.0,
        }

        # Market regime (compact)
        regime = market_state.get("regime", {})
        market_regime = {
            "vix_level": _normalize_pct(regime.get("vix", 20.0) - 20.0, scale=30.0),
            "trend_strength": _clip(regime.get("trend_strength", 0.0), -1.0, 1.0),
            "risk_on": 1.0 if regime.get("risk_on", True) else 0.0,
        }

        return {
            "trade_pnl": trade_pnl,
            "time_elapsed": time_elapsed,
            "thesis_signals": thesis_signals,
            "stop_distance": stop_distance,
            "market_regime": market_regime,
        }

    # ==================================================================
    # 5.  Portfolio Constructor / Risk Manager shared
    # ==================================================================

    def encode_portfolio_state(
        self,
        portfolio: dict[str, Any],
        market_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Encode the observation for the **portfolio-constructor** and
        **risk-manager** agents.

        Both agents need a comprehensive view of the portfolio including
        allocation, risk metrics, recent performance, market outlook,
        and drift from target weights.

        Returns a dict with keys:
        - ``allocation``: current allocation breakdown.
        - ``risk_metrics``: normalised risk metrics.
        - ``performance``: recent return / Sharpe / drawdown stats.
        - ``market_outlook``: forward-looking regime indicators.
        - ``drift_from_target``: deviation of current weights from targets.
        """
        total_value = max(portfolio.get("total_value", 1.0), 1.0)
        positions = portfolio.get("positions", [])

        # -- allocation --
        sector_alloc: dict[str, float] = {}
        for pos in positions:
            sector = pos.get("asset_class", "unknown")
            weight = pos.get("weight", 0.0)
            sector_alloc[sector] = sector_alloc.get(sector, 0.0) + weight

        allocation = {
            "cash_weight": _clip(portfolio.get("cash", 0.0) / total_value, 0.0, 1.0),
            "invested_weight": _clip(portfolio.get("invested", 0.0) / total_value, 0.0, 1.5),
            "num_positions_norm": _clip(len(positions) / self._max_positions, 0.0, 1.0),
            "sector_weights": {k: _clip(v, 0.0, 1.0) for k, v in sector_alloc.items()},
            "top_position_weight": max((pos.get("weight", 0.0) for pos in positions), default=0.0),
        }

        # -- risk metrics --
        risk = portfolio.get("risk_metrics", {})
        risk_metrics = {
            "portfolio_var_norm": _normalize_pct(risk.get("var_95_pct", 2.0), scale=10.0),
            "portfolio_cvar_norm": _normalize_pct(risk.get("cvar_95_pct", 3.0), scale=15.0),
            "beta_norm": _clip(risk.get("beta", 1.0) / 2.0, -1.0, 1.0),
            "max_sector_exposure_norm": _clip(
                max(sector_alloc.values(), default=0.0) / 0.4, 0.0, 1.0
            ),
            "leverage": _clip(risk.get("leverage", 1.0) / 3.0, 0.0, 1.0),
            "correlation_avg": _clip(risk.get("avg_correlation", 0.3), 0.0, 1.0),
        }

        # -- performance --
        perf = portfolio.get("performance", {})
        performance = {
            "return_1d_norm": _normalize_pct(perf.get("return_1d_pct", 0.0), scale=5.0),
            "return_1w_norm": _normalize_pct(perf.get("return_1w_pct", 0.0), scale=10.0),
            "return_1m_norm": _normalize_pct(perf.get("return_1m_pct", 0.0), scale=20.0),
            "sharpe_norm": _clip(perf.get("sharpe", 0.0) / 3.0, -1.0, 1.0),
            "drawdown_norm": _clip(perf.get("current_drawdown_pct", 0.0) / -30.0, -1.0, 0.0),
            "pnl_total_norm": _normalize_pct(portfolio.get("pnl_pct", 0.0), scale=50.0),
        }

        # -- market outlook --
        regime = market_state.get("regime", {})
        outlook = market_state.get("outlook", {})
        market_outlook = {
            "vix_level": _normalize_pct(regime.get("vix", 20.0) - 20.0, scale=30.0),
            "trend_strength": _clip(regime.get("trend_strength", 0.0), -1.0, 1.0),
            "risk_on": 1.0 if regime.get("risk_on", True) else 0.0,
            "recession_prob": _clip(outlook.get("recession_probability", 0.1), 0.0, 1.0),
            "rate_direction": _clip(outlook.get("rate_direction", 0.0), -1.0, 1.0),
        }

        # -- drift from target --
        target_alloc = portfolio.get("target_allocation", {})
        drift: dict[str, float] = {}
        for sector, target_weight in target_alloc.items():
            current_weight = sector_alloc.get(sector, 0.0)
            drift[sector] = _clip(current_weight - target_weight, -0.5, 0.5)

        drift_from_target = {
            "sector_drift": drift,
            "total_drift_abs": _clip(
                sum(abs(v) for v in drift.values()), 0.0, 2.0
            ) / 2.0,
            "max_drift": _clip(
                max((abs(v) for v in drift.values()), default=0.0), 0.0, 0.5
            ) / 0.5,
        }

        return {
            "allocation": allocation,
            "risk_metrics": risk_metrics,
            "performance": performance,
            "market_outlook": market_outlook,
            "drift_from_target": drift_from_target,
        }


# ---------------------------------------------------------------------------
# Categorical encoding helpers
# ---------------------------------------------------------------------------

_RISK_LEVEL_MAP: dict[str, float] = {
    "low": 0.0,
    "medium": 0.33,
    "high": 0.67,
    "extreme": 1.0,
}

_TIMEFRAME_MAP: dict[str, float] = {
    "intraday": 0.0,
    "short_term": 0.33,
    "medium_term": 0.67,
    "long_term": 1.0,
}

_SOURCE_MAP: dict[str, float] = {
    "news": 0.0,
    "screen": 0.25,
    "agent": 0.5,
    "user": 0.75,
    "aggregated": 1.0,
}


def _encode_risk_level(level: str) -> float:
    """Encode a risk-level string as a normalised float in [0, 1]."""
    return _RISK_LEVEL_MAP.get(level, 0.33)


def _encode_timeframe(tf: str) -> float:
    """Encode a timeframe string as a normalised float in [0, 1]."""
    return _TIMEFRAME_MAP.get(tf, 0.67)


def _encode_idea_source(source: str) -> float:
    """Encode an idea-source string as a normalised float in [0, 1]."""
    return _SOURCE_MAP.get(source, 0.5)
