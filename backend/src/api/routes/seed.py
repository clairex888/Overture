"""
Seed API route.

Initializes the database with a paper portfolio and sample data.
Called automatically on startup if the database is empty.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from src.models.base import get_session
from src.models.portfolio import Portfolio, PortfolioStatus
from src.models.idea import Idea, IdeaSource, IdeaStatus, Timeframe
from src.models.trade import Trade, TradeStatus, TradeDirection, InstrumentType
from src.models.knowledge import (
    KnowledgeEntry, KnowledgeCategory, KnowledgeLayer,
    MarketOutlook, OutlookSentiment,
)

router = APIRouter()


class SeedResult(BaseModel):
    success: bool
    message: str
    portfolio_id: str | None = None
    ideas_created: int = 0
    trades_created: int = 0
    knowledge_entries_created: int = 0
    outlooks_created: int = 0


async def run_seed(session: AsyncSession) -> SeedResult:
    """Core seed logic, reusable from both API and startup."""
    # Check if a portfolio already exists
    result = await session.execute(select(Portfolio).limit(1))
    existing = result.scalar_one_or_none()

    if existing:
        return SeedResult(
            success=True,
            message=f"Portfolio already exists: {existing.name}",
            portfolio_id=existing.id,
        )

    # --- Paper Portfolio ($1M) ---
    portfolio = Portfolio(
        id=str(uuid4()),
        name="Paper Portfolio",
        description="AI Hedge Fund Paper Trading Portfolio - $1M Initial Capital",
        total_value=1_000_000.0,
        cash=1_000_000.0,
        invested=0.0,
        pnl=0.0,
        pnl_pct=0.0,
        risk_score=0.0,
        preferences={
            "target_annual_return": 15,
            "max_drawdown_tolerance": 15,
            "investment_horizon": "medium_term",
            "benchmark": "SPY",
            "allocation_targets": [
                {"asset_class": "equities", "target_weight": 45},
                {"asset_class": "fixed_income", "target_weight": 20},
                {"asset_class": "crypto", "target_weight": 15},
                {"asset_class": "commodities", "target_weight": 5},
                {"asset_class": "cash", "target_weight": 15},
            ],
            "risk_appetite": "moderate",
            "max_position_size": 10,
            "concentration_limit": 30,
            "stop_loss_pct": 5,
            "excluded_sectors": [],
            "excluded_tickers": [],
            "hard_rules": "",
            "rebalance_frequency": "weekly",
            "drift_tolerance": 5,
            "auto_rebalance": False,
        },
        status=PortfolioStatus.ACTIVE,
    )
    session.add(portfolio)
    await session.flush()

    # --- Sample Ideas ---
    ideas_data = [
        {
            "title": "AI Infrastructure Long - NVDA Momentum",
            "description": "NVIDIA continues to dominate AI chip market with strong data center revenue growth.",
            "thesis": "NVIDIA's data center revenue grew 85% YoY with strong forward guidance. AI capex cycle has years of runway. Technical breakout above $850 confirmed.",
            "source": IdeaSource.AGENT,
            "asset_class": "equities",
            "tickers": [{"symbol": "NVDA", "direction": "long", "weight": 1.0}],
            "status": IdeaStatus.VALIDATED,
            "confidence_score": 0.82,
            "timeframe": Timeframe.MEDIUM_TERM,
            "validation_results": {
                "score": 0.82,
                "risk_assessment": "moderate",
                "market_alignment": "aligned",
                "agent": "validation_agent",
                "validated_at": "2026-02-10T10:00:00Z",
            },
            "metadata_": {
                "tags": ["ai", "semiconductors", "momentum"],
                "notes": "Strong earnings catalyst",
            },
        },
        {
            "title": "Bitcoin Institutional Adoption Wave",
            "description": "Spot Bitcoin ETF inflows accelerating with institutional adoption metrics climbing.",
            "thesis": "Record $2.1B weekly ETF inflows signal sustained institutional demand. On-chain metrics confirm accumulation phase. Target $85K by Q2 2026.",
            "source": IdeaSource.AGENT,
            "asset_class": "crypto",
            "tickers": [{"symbol": "BTC-USD", "direction": "long", "weight": 1.0}],
            "status": IdeaStatus.EXECUTING,
            "confidence_score": 0.75,
            "timeframe": Timeframe.MEDIUM_TERM,
            "validation_results": {
                "score": 0.75,
                "risk_assessment": "high",
                "market_alignment": "aligned",
                "agent": "validation_agent",
                "validated_at": "2026-02-08T14:00:00Z",
            },
            "metadata_": {
                "tags": ["bitcoin", "etf", "institutional"],
                "notes": "Position sized for crypto volatility",
                "execution_plan": {
                    "trades": [],
                    "entry_strategy": "limit_order",
                    "position_size_pct": 0.05,
                    "stop_loss_pct": 0.10,
                    "take_profit_pct": 0.25,
                    "planned_at": "2026-02-09T09:00:00Z",
                    "agent": "execution_agent",
                },
            },
        },
        {
            "title": "Treasury Duration Extension Play",
            "description": "Long-duration Treasuries offer attractive yields with potential rate cut tailwind.",
            "thesis": "Fed easing cycle expected to resume. 20+ year treasury yields at 4.5% offer carry plus potential capital gains on rate cuts. Recession hedge value.",
            "source": IdeaSource.USER,
            "asset_class": "fixed_income",
            "tickers": [{"symbol": "TLT", "direction": "long", "weight": 1.0}],
            "status": IdeaStatus.VALIDATED,
            "confidence_score": 0.68,
            "timeframe": Timeframe.LONG_TERM,
            "validation_results": {
                "score": 0.68,
                "risk_assessment": "low",
                "market_alignment": "neutral",
                "agent": "validation_agent",
                "validated_at": "2026-02-11T12:00:00Z",
            },
            "metadata_": {
                "tags": ["bonds", "rates", "duration"],
                "notes": "Fed policy dependent",
            },
        },
        {
            "title": "Ethereum L2 Ecosystem Growth",
            "description": "Ethereum Layer 2 scaling solutions driving network growth and fee revenue.",
            "thesis": "ETH L2 TVL growing 40% QoQ. EIP-4844 reducing L2 costs by 90%. Staking yield + fee burn creating deflationary dynamics.",
            "source": IdeaSource.AGENT,
            "asset_class": "crypto",
            "tickers": [{"symbol": "ETH-USD", "direction": "long", "weight": 1.0}],
            "status": IdeaStatus.GENERATED,
            "confidence_score": 0.60,
            "timeframe": Timeframe.MEDIUM_TERM,
            "metadata_": {
                "tags": ["ethereum", "l2", "defi"],
                "notes": "Needs validation",
            },
        },
        {
            "title": "SPY Downside Hedge - Near-term Caution",
            "description": "Technical overbought signals and upcoming CPI data warrant hedging exposure.",
            "thesis": "SPX at resistance with VIX at extreme lows. CPI release and large options expiration could trigger 3-5% correction. Put spread hedge recommended.",
            "source": IdeaSource.AGENT,
            "asset_class": "equities",
            "tickers": [{"symbol": "SPY", "direction": "short", "weight": 1.0}],
            "status": IdeaStatus.GENERATED,
            "confidence_score": 0.55,
            "timeframe": Timeframe.SHORT_TERM,
            "metadata_": {
                "tags": ["hedge", "puts", "volatility"],
                "notes": "Tactical hedge only",
            },
        },
    ]

    ideas_created = 0
    for data in ideas_data:
        idea = Idea(id=str(uuid4()), **data)
        session.add(idea)
        ideas_created += 1
    await session.flush()

    # --- Sample Trades ---
    trades_data = [
        {
            "tickers": ["NVDA"],
            "direction": TradeDirection.LONG,
            "instrument_type": InstrumentType.EQUITY,
            "status": TradeStatus.PENDING_APPROVAL,
            "quantity": 50.0,
            "entry_price": 890.0,
            "stop_loss": 850.0,
            "take_profit": 950.0,
            "metadata_": {
                "symbol": "NVDA",
                "notes": "AI chip momentum play",
                "direction_label": "buy",
                "limit_price": 890.0,
            },
        },
        {
            "tickers": ["ETH-USD"],
            "direction": TradeDirection.LONG,
            "instrument_type": InstrumentType.CRYPTO,
            "status": TradeStatus.OPEN,
            "quantity": 5.0,
            "entry_price": 3180.0,
            "current_price": 3530.0,
            "stop_loss": 2900.0,
            "take_profit": 3800.0,
            "pnl": 1750.0,
            "pnl_pct": 0.11,
            "metadata_": {
                "symbol": "ETH-USD",
                "notes": "ETH breakout trade",
                "direction_label": "buy",
                "fill_price": 3180.0,
                "fill_quantity": 5.0,
                "limit_price": 3200.0,
            },
        },
        {
            "tickers": ["SPY"],
            "direction": TradeDirection.SHORT,
            "instrument_type": InstrumentType.EQUITY,
            "status": TradeStatus.PENDING_APPROVAL,
            "quantity": 100.0,
            "stop_loss": 510.0,
            "take_profit": 470.0,
            "metadata_": {
                "symbol": "SPY",
                "notes": "Hedging position against drawdown",
                "direction_label": "sell",
            },
        },
    ]

    trades_created = 0
    for data in trades_data:
        trade = Trade(id=str(uuid4()), **data)
        session.add(trade)
        trades_created += 1
    await session.flush()

    # --- Knowledge Entries ---
    ke_data = [
        {
            "title": "Fed signals patience on rate cuts amid persistent services inflation",
            "content": "Federal Reserve minutes from January meeting reveal committee members prefer to wait for more data before cutting rates further. Services inflation remains sticky at 3.8% annualized.",
            "category": KnowledgeCategory.MACRO,
            "layer": KnowledgeLayer.MID_TERM,
            "source": "reuters",
            "source_credibility_score": 0.90,
            "tags": ["fed", "rates", "inflation"],
            "asset_classes": [],
            "tickers": [],
        },
        {
            "title": "NVIDIA earnings beat expectations, guidance strong on AI demand",
            "content": "NVIDIA reported Q4 earnings of $5.16 per share vs $4.80 expected. Revenue guidance for Q1 2026 at $28B, above consensus of $26.5B. Data center revenue grew 85% YoY.",
            "category": KnowledgeCategory.FUNDAMENTAL,
            "layer": KnowledgeLayer.SHORT_TERM,
            "source": "bloomberg",
            "source_credibility_score": 0.95,
            "tags": ["earnings", "ai", "semiconductors"],
            "asset_classes": ["equities"],
            "tickers": ["NVDA"],
        },
        {
            "title": "Bitcoin ETF inflows accelerate to record levels",
            "content": "Spot Bitcoin ETFs saw $2.1B in net inflows last week, the highest since launch. BlackRock's IBIT leads with $890M. Institutional adoption metrics continue to climb.",
            "category": KnowledgeCategory.FUNDAMENTAL,
            "layer": KnowledgeLayer.MID_TERM,
            "source": "coingecko",
            "source_credibility_score": 0.85,
            "tags": ["bitcoin", "etf", "institutional"],
            "asset_classes": ["crypto"],
            "tickers": ["BTC-USD"],
        },
    ]

    ke_created = 0
    for data in ke_data:
        entry = KnowledgeEntry(id=str(uuid4()), **data)
        session.add(entry)
        ke_created += 1

    # --- Market Outlooks ---
    outlooks_data = [
        {
            "layer": KnowledgeLayer.LONG_TERM,
            "asset_class": "general",
            "outlook": OutlookSentiment.BULLISH,
            "confidence": 0.65,
            "rationale": "Structural AI/tech adoption and easing cycle support multi-year equity growth. Fixed income attractive at current yields.",
            "key_drivers": [
                "AI productivity revolution",
                "Global easing cycle underway",
                "Strong US corporate earnings trajectory",
                "Demographics shifting in emerging markets",
            ],
        },
        {
            "layer": KnowledgeLayer.MID_TERM,
            "asset_class": "general",
            "outlook": OutlookSentiment.NEUTRAL,
            "confidence": 0.55,
            "rationale": "Mixed signals: earnings growth solid but valuations stretched. Watching Fed trajectory and geopolitical developments.",
            "key_drivers": [
                "Fed rate path uncertainty",
                "Q4 earnings season results",
                "Geopolitical tensions in multiple regions",
                "Credit spreads tightening",
            ],
        },
        {
            "layer": KnowledgeLayer.SHORT_TERM,
            "asset_class": "general",
            "outlook": OutlookSentiment.BEARISH,
            "confidence": 0.60,
            "rationale": "Near-term caution warranted. Technical overbought signals, upcoming CPI data, and options expiration could trigger volatility.",
            "key_drivers": [
                "SPX at technical resistance",
                "VIX suppressed to extreme lows",
                "CPI release this week",
                "Large options expiration Friday",
            ],
        },
    ]

    outlooks_created = 0
    for data in outlooks_data:
        outlook = MarketOutlook(id=str(uuid4()), **data)
        session.add(outlook)
        outlooks_created += 1

    return SeedResult(
        success=True,
        message="Database seeded successfully with $1M paper portfolio",
        portfolio_id=portfolio.id,
        ideas_created=ideas_created,
        trades_created=trades_created,
        knowledge_entries_created=ke_created,
        outlooks_created=outlooks_created,
    )


@router.post("/", response_model=SeedResult)
async def seed_database(session: AsyncSession = Depends(get_session)):
    """Initialize the database with a paper portfolio and sample data.

    Idempotent: if a portfolio already exists, returns the existing one.
    """
    return await run_seed(session)
