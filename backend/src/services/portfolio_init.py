"""
Portfolio Initialization & Proposal Service.

Handles the full workflow:
1. Initialize a portfolio with a dollar amount
2. Generate an optimal allocation using deterministic rules + agent knowledge
3. Fetch last close prices for proposed holdings
4. Calculate trading costs (slippage + commissions)
5. Approve and execute: create positions and trade records
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Portfolio knowledge base: curated asset universe by asset class
# Encodes optimal allocation research (MPT, risk parity, core-satellite)
# ---------------------------------------------------------------------------

ASSET_UNIVERSE: dict[str, list[dict[str, Any]]] = {
    "equities": [
        {"ticker": "SPY", "name": "S&P 500 ETF", "sub_class": "us_large_cap", "instrument": "etf"},
        {"ticker": "QQQ", "name": "Nasdaq 100 ETF", "sub_class": "us_tech", "instrument": "etf"},
        {"ticker": "IWM", "name": "Russell 2000 ETF", "sub_class": "us_small_cap", "instrument": "etf"},
        {"ticker": "VGK", "name": "FTSE Europe ETF", "sub_class": "intl_developed", "instrument": "etf"},
        {"ticker": "EEM", "name": "Emerging Markets ETF", "sub_class": "emerging", "instrument": "etf"},
    ],
    "fixed_income": [
        {"ticker": "AGG", "name": "US Aggregate Bond ETF", "sub_class": "us_agg", "instrument": "etf"},
        {"ticker": "TLT", "name": "20+ Year Treasury ETF", "sub_class": "us_long_treasury", "instrument": "etf"},
        {"ticker": "LQD", "name": "Investment Grade Corp ETF", "sub_class": "us_ig_corp", "instrument": "etf"},
        {"ticker": "HYG", "name": "High Yield Corp ETF", "sub_class": "us_hy", "instrument": "etf"},
    ],
    "commodities": [
        {"ticker": "GLD", "name": "Gold ETF", "sub_class": "gold", "instrument": "etf"},
        {"ticker": "USO", "name": "Oil ETF", "sub_class": "oil", "instrument": "etf"},
        {"ticker": "DBC", "name": "Commodity Index ETF", "sub_class": "broad_commodity", "instrument": "etf"},
    ],
    "crypto": [
        {"ticker": "BTC-USD", "name": "Bitcoin", "sub_class": "bitcoin", "instrument": "crypto"},
        {"ticker": "ETH-USD", "name": "Ethereum", "sub_class": "ethereum", "instrument": "crypto"},
    ],
}

# Risk-appetite based allocation profiles (percentages)
RISK_PROFILES: dict[str, dict[str, float]] = {
    "conservative": {
        "equities": 30, "fixed_income": 45, "commodities": 10, "crypto": 0, "cash": 15,
    },
    "moderate": {
        "equities": 50, "fixed_income": 20, "commodities": 10, "crypto": 10, "cash": 10,
    },
    "aggressive": {
        "equities": 60, "fixed_income": 10, "commodities": 10, "crypto": 15, "cash": 5,
    },
}

# Within-class weights (core-satellite, risk-parity informed)
INTRA_CLASS_WEIGHTS: dict[str, dict[str, float]] = {
    # Equities: core = broad market, satellite = tech + small cap + intl
    "equities": {"SPY": 0.40, "QQQ": 0.25, "IWM": 0.10, "VGK": 0.15, "EEM": 0.10},
    # Fixed income: core = aggregate, satellite = long duration + credit
    "fixed_income": {"AGG": 0.45, "TLT": 0.25, "LQD": 0.20, "HYG": 0.10},
    # Commodities: gold-heavy for crisis hedge
    "commodities": {"GLD": 0.55, "USO": 0.20, "DBC": 0.25},
    # Crypto: BTC dominant
    "crypto": {"BTC-USD": 0.65, "ETH-USD": 0.35},
}

# Trading cost model parameters
TRADING_COSTS = {
    "commission_per_share": 0.005,   # $0.005 per share (typical institutional)
    "min_commission": 1.00,          # minimum per trade
    "etf_spread_bps": 2,             # 2 bps for liquid ETFs
    "equity_spread_bps": 5,          # 5 bps for single stocks
    "crypto_spread_bps": 15,         # 15 bps for crypto
    "market_impact_bps": 1,          # 1 bp market impact for small orders
    "sec_fee_per_million": 22.90,    # SEC fee per $1M of sells
}


def compute_trading_cost(
    ticker: str,
    quantity: float,
    price: float,
    instrument: str,
) -> dict[str, float]:
    """Simulate realistic trading costs for a single trade."""
    notional = quantity * price

    # Spread cost
    if instrument == "crypto":
        spread_bps = TRADING_COSTS["crypto_spread_bps"]
    elif instrument == "etf":
        spread_bps = TRADING_COSTS["etf_spread_bps"]
    else:
        spread_bps = TRADING_COSTS["equity_spread_bps"]

    spread_cost = notional * (spread_bps / 10_000)

    # Market impact (proportional to order size, simplified)
    impact_cost = notional * (TRADING_COSTS["market_impact_bps"] / 10_000)

    # Commission
    commission = max(
        quantity * TRADING_COSTS["commission_per_share"],
        TRADING_COSTS["min_commission"],
    )

    # SEC fee (only on sells, but for initialization all are buys, so 0)
    sec_fee = 0.0

    total_cost = spread_cost + impact_cost + commission + sec_fee
    slippage_pct = (total_cost / notional * 100) if notional > 0 else 0

    # Effective fill price (slightly worse than last close due to slippage)
    fill_price = price * (1 + spread_bps / 20_000 + TRADING_COSTS["market_impact_bps"] / 20_000)

    return {
        "spread_cost": round(spread_cost, 2),
        "impact_cost": round(impact_cost, 2),
        "commission": round(commission, 2),
        "sec_fee": round(sec_fee, 2),
        "total_cost": round(total_cost, 2),
        "slippage_pct": round(slippage_pct, 4),
        "fill_price": round(fill_price, 4),
    }


async def fetch_last_close_prices(tickers: list[str]) -> dict[str, float | None]:
    """Fetch last available close price for each ticker via yfinance."""
    import yfinance as yf

    def _fetch() -> dict[str, float | None]:
        prices: dict[str, float | None] = {}
        for ticker in tickers:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if hist.empty:
                    prices[ticker] = None
                else:
                    prices[ticker] = float(hist["Close"].iloc[-1])
            except Exception:
                logger.warning("Failed to fetch price for %s", ticker, exc_info=True)
                prices[ticker] = None
        return prices

    return await asyncio.to_thread(_fetch)


def generate_proposal(
    initial_amount: float,
    preferences: dict[str, Any],
    prices: dict[str, float | None],
) -> dict[str, Any]:
    """Generate an optimal portfolio proposal.

    Uses allocation targets from preferences (or risk-profile defaults),
    then applies intra-class weights to pick specific instruments.
    Calculates share quantities based on last close prices and trading costs.
    """

    risk_appetite = preferences.get("risk_appetite", "moderate")

    # Use user allocation targets if available, otherwise use risk profile
    alloc_targets_raw = preferences.get("allocation_targets")
    if alloc_targets_raw and isinstance(alloc_targets_raw, list):
        class_targets = {
            t["asset_class"]: t["target_weight"] / 100.0
            for t in alloc_targets_raw
        }
    else:
        profile = RISK_PROFILES.get(risk_appetite, RISK_PROFILES["moderate"])
        class_targets = {k: v / 100.0 for k, v in profile.items()}

    cash_target = class_targets.pop("cash", 0.10)
    cash_amount = initial_amount * cash_target

    holdings: list[dict[str, Any]] = []
    total_invested = 0.0
    total_trading_cost = 0.0
    trades: list[dict[str, Any]] = []

    for asset_class, class_weight in class_targets.items():
        class_amount = initial_amount * class_weight
        intra_weights = INTRA_CLASS_WEIGHTS.get(asset_class, {})
        universe = ASSET_UNIVERSE.get(asset_class, [])

        if not intra_weights or not universe:
            # No instruments for this class — add to cash
            cash_amount += class_amount
            continue

        for asset_info in universe:
            ticker = asset_info["ticker"]
            intra_w = intra_weights.get(ticker, 0)
            if intra_w <= 0:
                continue

            target_notional = class_amount * intra_w
            price = prices.get(ticker)

            if price is None or price <= 0:
                # Can't price this asset — allocate to cash
                cash_amount += target_notional
                continue

            # Calculate quantity (whole shares for equities/ETFs, fractional for crypto)
            if asset_info["instrument"] == "crypto":
                quantity = target_notional / price
                quantity = math.floor(quantity * 10000) / 10000  # 4 decimal places
            else:
                quantity = math.floor(target_notional / price)

            if quantity <= 0:
                cash_amount += target_notional
                continue

            # Compute trading costs
            cost_info = compute_trading_cost(
                ticker, quantity, price, asset_info["instrument"]
            )

            actual_notional = quantity * price
            fill_price = cost_info["fill_price"]
            actual_cost = quantity * fill_price

            holdings.append({
                "ticker": ticker,
                "name": asset_info["name"],
                "asset_class": asset_class,
                "sub_class": asset_info["sub_class"],
                "instrument": asset_info["instrument"],
                "direction": "long",
                "quantity": quantity,
                "price": round(price, 4),
                "fill_price": fill_price,
                "market_value": round(actual_notional, 2),
                "weight": 0,  # computed below
                "trading_cost": cost_info,
            })

            trades.append({
                "ticker": ticker,
                "name": asset_info["name"],
                "direction": "buy",
                "instrument": asset_info["instrument"],
                "quantity": quantity,
                "price": round(price, 4),
                "fill_price": fill_price,
                "notional": round(actual_notional, 2),
                **cost_info,
            })

            total_invested += actual_cost
            total_trading_cost += cost_info["total_cost"]

    # Adjust cash for actual investment + trading costs
    cash_amount = initial_amount - total_invested - total_trading_cost
    if cash_amount < 0:
        cash_amount = 0

    total_value = total_invested + cash_amount

    # Compute weights
    for h in holdings:
        h["weight"] = round(h["market_value"] / total_value * 100, 2) if total_value > 0 else 0

    # Aggregate by asset class for summary
    class_summary: dict[str, float] = {}
    for h in holdings:
        ac = h["asset_class"]
        class_summary[ac] = class_summary.get(ac, 0) + h["market_value"]
    class_summary["cash"] = cash_amount

    allocation_summary = {
        k: round(v / total_value * 100, 2) if total_value > 0 else 0
        for k, v in class_summary.items()
    }

    return {
        "initial_amount": initial_amount,
        "total_value": round(total_value, 2),
        "total_invested": round(total_invested, 2),
        "cash": round(cash_amount, 2),
        "total_trading_cost": round(total_trading_cost, 2),
        "num_positions": len(holdings),
        "holdings": holdings,
        "trades": trades,
        "allocation_summary": allocation_summary,
        "risk_appetite": risk_appetite,
        "strategy_notes": [
            "Core-satellite approach: 60-70% in broad market ETFs, 30-40% in tactical satellite positions",
            "Risk parity informed: balancing risk contribution across asset classes",
            "Diversification across equities, fixed income, commodities, and crypto",
            "Gold allocation provides crisis hedge and inflation protection",
            f"Cash buffer of {allocation_summary.get('cash', 0):.1f}% for rebalancing and opportunities",
        ],
    }
