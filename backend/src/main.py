import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import ideas, portfolio, agents, knowledge, trades, alerts, rl, seed, market_data, auth
from src.api.websocket import router as ws_router
from src.config import settings
from src.models import base as db_base
from src.models.base import async_session_factory
import src.models.user  # noqa: F401 — ensure User table is created

logger = logging.getLogger(__name__)

# Lazy-import agent engine so auth/portfolio/etc. still work if agent deps fail
try:
    from src.agents.engine import agent_engine
    _agent_engine_ok = True
except Exception as _agent_err:
    _agent_engine_ok = False
    agent_engine = None  # type: ignore[assignment]
    logger.warning("Agent engine unavailable: %s — agent loops disabled", _agent_err)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_base.init_db()

    # Auto-seed if database is empty (idempotent)
    if db_base.db_ready:
        try:
            async with async_session_factory() as session:
                result = await seed.run_seed(session)
                await session.commit()
                logger.info("Auto-seed: %s", result.message)
        except Exception as exc:
            logger.warning("Auto-seed skipped: %s", exc)

        # Seed master admin account (idempotent)
        try:
            await _seed_master_user()
        except Exception as exc:
            logger.error("Master user seed FAILED: %s", exc, exc_info=True)

        # Add user_id column to portfolios if missing (schema migration)
        try:
            await _migrate_portfolio_user_id()
        except Exception as exc:
            logger.error("Portfolio user_id migration FAILED: %s", exc, exc_info=True)

        # Migrate orphan portfolios (no user_id) to the admin user
        try:
            await _assign_orphan_portfolios()
        except Exception as exc:
            logger.error("Orphan portfolio migration FAILED: %s", exc, exc_info=True)

        # Add upload/privacy columns to knowledge_entries if missing
        try:
            await _migrate_knowledge_upload_cols()
        except Exception as exc:
            logger.error("Knowledge upload columns migration FAILED: %s", exc, exc_info=True)

        # Seed sample knowledge articles (idempotent)
        try:
            await _seed_knowledge_articles()
        except Exception as exc:
            logger.error("Knowledge seed FAILED: %s", exc, exc_info=True)

    if _agent_engine_ok:
        logger.info("Agent engine ready (use /api/agents/idea-loop/start to begin)")
    else:
        logger.warning("Agent engine NOT available — agent features disabled")
    yield

    # Shutdown: stop any running agent loops
    if _agent_engine_ok and agent_engine is not None:
        await agent_engine.shutdown()


async def _seed_master_user() -> None:
    """Create or reset the master admin account.

    Resets the password on every startup so the master account always works
    even if the JWT secret or bcrypt rounds changed between deploys.
    """
    from sqlalchemy import select
    from src.models.user import User, UserRole
    from src.auth import hash_password
    from uuid import uuid4

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == "admin@overture.ai")
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Reset password on every startup so the master account always works
            existing.hashed_password = hash_password("admin123")
            existing.is_active = True
            await session.commit()
            logger.info("Master admin password reset: admin@overture.ai")
            return

        admin = User(
            id=str(uuid4()),
            email="admin@overture.ai",
            hashed_password=hash_password("admin123"),
            display_name="Master Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        logger.info("Master admin account created: admin@overture.ai")


async def _migrate_portfolio_user_id() -> None:
    """Add user_id column to portfolios table if it doesn't exist.

    create_all() only creates new tables — it never adds columns to existing
    ones. This handles the schema migration without Alembic.

    The column must be UUID type (not VARCHAR) to match users.id which is
    also UUID. PostgreSQL rejects FK constraints between mismatched types.
    """
    from sqlalchemy import text

    async with async_session_factory() as session:
        # Check if the column already exists
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'portfolios' AND column_name = 'user_id'"
        ))
        if result.scalar_one_or_none():
            return  # Column already exists

        # Add the column — must be UUID to match users.id type
        await session.execute(text(
            "ALTER TABLE portfolios "
            "ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE"
        ))
        await session.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_portfolios_user_id ON portfolios (user_id)"
        ))
        await session.commit()
        logger.info("Added user_id column to portfolios table.")


async def _assign_orphan_portfolios() -> None:
    """One-time migration: assign any portfolios without a user_id to the admin."""
    from sqlalchemy import select, update
    from src.models.portfolio import Portfolio
    from src.models.user import User

    async with async_session_factory() as session:
        # Find admin user
        result = await session.execute(
            select(User).where(User.email == "admin@overture.ai")
        )
        admin = result.scalar_one_or_none()
        if not admin:
            return

        # Assign orphan portfolios to admin
        result = await session.execute(
            update(Portfolio)
            .where(Portfolio.user_id.is_(None))
            .values(user_id=admin.id)
        )
        if result.rowcount > 0:
            await session.commit()
            logger.info("Assigned %d orphan portfolios to admin user.", result.rowcount)


async def _migrate_knowledge_upload_cols() -> None:
    """Add upload/privacy columns to knowledge_entries if they don't exist."""
    from sqlalchemy import text

    cols = [
        ("uploaded_by_user_id", "UUID REFERENCES users(id) ON DELETE SET NULL"),
        ("is_public", "BOOLEAN DEFAULT TRUE NOT NULL"),
        ("file_name", "VARCHAR(500)"),
        ("file_type", "VARCHAR(50)"),
    ]
    async with async_session_factory() as session:
        for col_name, col_sql in cols:
            result = await session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'knowledge_entries' AND column_name = :col"
            ), {"col": col_name})
            if result.scalar_one_or_none():
                continue
            await session.execute(text(
                f"ALTER TABLE knowledge_entries ADD COLUMN {col_name} {col_sql}"
            ))
            logger.info("Added column %s to knowledge_entries.", col_name)
        await session.commit()


async def _seed_knowledge_articles() -> None:
    """Seed the knowledge library with real investment research articles (idempotent)."""
    from sqlalchemy import select, func
    from src.models.knowledge import (
        KnowledgeEntry, KnowledgeCategory, KnowledgeLayer,
        MarketOutlook, OutlookSentiment,
    )
    from uuid import uuid4

    async with async_session_factory() as session:
        count = (await session.execute(
            select(func.count()).select_from(KnowledgeEntry)
        )).scalar() or 0
        if count > 0:
            return  # Already seeded

        articles = [
            # ── Long-term (Secular Trends, 5-10 years) ─────────────────
            KnowledgeEntry(
                id=str(uuid4()),
                title="The AI Investment Revolution: A Multi-Decade Opportunity",
                content=(
                    "Artificial intelligence represents the most significant technological shift "
                    "since the internet. Enterprise AI spending is projected to grow at a 35% CAGR "
                    "through 2030, driven by three pillars: infrastructure (semiconductors, cloud), "
                    "platform (foundation models, MLOps), and application (vertical SaaS, automation).\n\n"
                    "The semiconductor supply chain is experiencing a structural demand shift. NVIDIA "
                    "controls ~80% of the AI accelerator market, while AMD and custom silicon from "
                    "hyperscalers are gaining share. Memory makers (HBM3e) like SK Hynix and Micron "
                    "are critical bottlenecks.\n\n"
                    "Productivity gains from AI adoption could add $4.4 trillion annually to the "
                    "global economy per McKinsey. Key beneficiaries: software companies integrating "
                    "AI copilots (Microsoft, Salesforce), cloud infrastructure providers (AWS, Azure, "
                    "GCP), and companies with proprietary data moats."
                ),
                category=KnowledgeCategory.MACRO,
                layer=KnowledgeLayer.LONG_TERM,
                source="Overture Research",
                source_credibility_score=0.92,
                tags=["AI", "semiconductors", "cloud", "productivity"],
                asset_classes=["equities"],
                tickers=["NVDA", "MSFT", "GOOGL", "AMD", "MU"],
                metadata_={"original_category": "macro"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Global Demographics & The Great Wealth Transfer",
                content=(
                    "Two mega-trends are reshaping global capital flows. In developed markets, "
                    "populations are aging rapidly — by 2030, all baby boomers will be 65+, "
                    "triggering the largest intergenerational wealth transfer in history ($84 "
                    "trillion in the US alone).\n\n"
                    "This creates structural demand for healthcare (GLP-1 drugs, medtech, elder "
                    "care), wealth management, and income-generating assets. Meanwhile, emerging "
                    "markets (India, Southeast Asia, Africa) are adding 1+ billion middle-class "
                    "consumers by 2035, driving demand for consumer staples, financial inclusion "
                    "(digital payments, microfinance), and infrastructure.\n\n"
                    "Portfolio positioning: Overweight healthcare/pharma (LLY, UNH, ISRG) for "
                    "developed market aging; consider EM consumer ETFs and fintech exposure for "
                    "the emerging middle class growth story."
                ),
                category=KnowledgeCategory.MACRO,
                layer=KnowledgeLayer.LONG_TERM,
                source="Overture Research",
                source_credibility_score=0.88,
                tags=["demographics", "aging", "wealth-transfer", "emerging-markets"],
                asset_classes=["equities", "etf"],
                tickers=["LLY", "UNH", "ISRG", "NU", "SE"],
                metadata_={"original_category": "macro"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Energy Transition: Investment Roadmap to Net Zero",
                content=(
                    "The global energy transition from fossil fuels to renewables represents "
                    "a $150+ trillion investment opportunity through 2050. Solar is now the "
                    "cheapest source of electricity in history, and battery storage costs have "
                    "fallen 90% since 2010.\n\n"
                    "Key investment themes: (1) Utility-scale solar and wind developers, (2) "
                    "Grid infrastructure and energy storage (battery supply chain from lithium "
                    "mining to cell manufacturing), (3) Electric vehicles and charging "
                    "infrastructure, (4) Green hydrogen for industrial decarbonization, "
                    "(5) Carbon capture technology.\n\n"
                    "Risk factors: Permitting bottlenecks, grid interconnection queues (2,000+ "
                    "GW backlog in the US), raw material supply constraints (lithium, copper, "
                    "rare earths), and policy uncertainty. Traditional energy companies (XOM, "
                    "CVX) remain cash-flow generative during the transition and offer hedging value."
                ),
                category=KnowledgeCategory.RESEARCH,
                layer=KnowledgeLayer.LONG_TERM,
                source="Overture Research",
                source_credibility_score=0.90,
                tags=["energy", "renewables", "EVs", "net-zero", "batteries"],
                asset_classes=["equities", "commodities"],
                tickers=["TSLA", "ENPH", "NEE", "XOM", "ALB"],
                metadata_={"original_category": "research"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="De-Globalization and Supply Chain Reshoring",
                content=(
                    "The post-2020 era has accelerated a structural shift from hyper-globalization "
                    "toward regionalized supply chains. US-China technology decoupling (CHIPS Act, "
                    "export controls), nearshoring to Mexico and Vietnam, and friend-shoring among "
                    "allied nations are reshaping global trade patterns.\n\n"
                    "Semiconductor reshoring is the most capital-intensive effort — TSMC, Samsung, "
                    "and Intel are investing $200B+ in US and European fabs. This benefits "
                    "semiconductor equipment makers (ASML, AMAT, LRCX) and construction/engineering "
                    "firms.\n\n"
                    "Mexico is the primary nearshoring beneficiary, with FDI doubling since 2020. "
                    "The peso has strengthened as manufacturing shifts south. Key sectors: "
                    "automotive, electronics assembly, and industrial real estate. Infrastructure "
                    "spending (roads, ports, power) in reshoring destinations creates additional "
                    "investment opportunities."
                ),
                category=KnowledgeCategory.MACRO,
                layer=KnowledgeLayer.LONG_TERM,
                source="Overture Research",
                source_credibility_score=0.87,
                tags=["reshoring", "geopolitics", "supply-chain", "semiconductors"],
                asset_classes=["equities"],
                tickers=["ASML", "AMAT", "LRCX", "INTC", "TSM"],
                metadata_={"original_category": "macro"},
            ),
            # ── Medium-term (Cyclical, 1-3 years) ─────────────────────
            KnowledgeEntry(
                id=str(uuid4()),
                title="Fed Rate Cycle Analysis: Navigating the Policy Pivot",
                content=(
                    "The Federal Reserve's rate cycle is at a critical inflection point. After "
                    "the most aggressive tightening cycle in 40 years (525bps in 16 months), the "
                    "Fed has begun easing. Historical analysis shows equities rally 15-20% in the "
                    "12 months following the first rate cut, with small-caps and rate-sensitive "
                    "sectors outperforming.\n\n"
                    "Key indicators to monitor: (1) Core PCE trajectory — needs sustained move "
                    "below 2.5%, (2) Labor market — initial claims trend and JOLTS quits rate, "
                    "(3) Financial conditions index — tightening vs easing impulse, (4) Term "
                    "premium on 10Y Treasuries.\n\n"
                    "Duration positioning: The yield curve un-inversion trade is underway. "
                    "Intermediate-duration bonds (5-7Y) offer the best risk-adjusted carry. "
                    "Floating-rate loans and short-duration credit lose their advantage as the "
                    "Fed cuts. REITs and utilities historically outperform by 8-12% in the first "
                    "year of rate cuts."
                ),
                category=KnowledgeCategory.MACRO,
                layer=KnowledgeLayer.MID_TERM,
                source="Federal Reserve Analysis",
                source_credibility_score=0.93,
                tags=["fed", "rates", "monetary-policy", "bonds", "duration"],
                asset_classes=["fixed_income", "equities"],
                tickers=["TLT", "IEF", "VNQ", "XLU", "IWM"],
                metadata_={"original_category": "macro"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Corporate Earnings Cycle: Margin Trends and Recovery Signals",
                content=(
                    "S&P 500 earnings are in a recovery phase after the 2023-2024 earnings "
                    "recession in non-tech sectors. Net margins have rebounded from 11.2% to "
                    "12.8%, driven by cost restructuring, AI-enabled productivity gains, and "
                    "moderating input costs.\n\n"
                    "The earnings breadth is improving — only 35% of sectors drove earnings growth "
                    "in 2024 (Mag-7 dominated), expanding to ~60% in 2026 estimates. This supports "
                    "an equal-weight vs cap-weight rotation. Sectors with the strongest earnings "
                    "revision momentum: industrials (reshoring capex), healthcare (GLP-1 ramp), "
                    "and financials (net interest margin normalization).\n\n"
                    "Watch for: Capex cycle maturation — companies have front-loaded AI/cloud "
                    "spending; a deceleration in capex growth could signal the next margin pressure "
                    "point. Operating leverage cuts both ways."
                ),
                category=KnowledgeCategory.FUNDAMENTAL,
                layer=KnowledgeLayer.MID_TERM,
                source="Bloomberg Intelligence",
                source_credibility_score=0.91,
                tags=["earnings", "margins", "capex", "breadth"],
                asset_classes=["equities"],
                tickers=["SPY", "RSP", "XLI", "XLF", "XLV"],
                metadata_={"original_category": "fundamental"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="US Housing Market: Structural Shortage Meets Rate Sensitivity",
                content=(
                    "The US housing market faces a unique structural setup: a 4-5 million unit "
                    "supply deficit built over a decade of underbuilding, combined with the "
                    "'golden handcuffs' effect where 80% of existing mortgages are below 5%, "
                    "locking homeowners in place.\n\n"
                    "This creates a floor under home prices even as affordability deteriorates. "
                    "New home builders (DHI, LEN, NVR) are benefiting disproportionately as "
                    "existing home inventory remains frozen. Every 100bps decline in mortgage "
                    "rates unlocks ~5 million additional homebuyers.\n\n"
                    "Building materials (VMC, MLM aggregates; BLDR distribution) and residential "
                    "REITs focused on sunbelt markets offer leveraged exposure. Risk: A recession "
                    "scenario where job losses overwhelm the rate-cut benefit."
                ),
                category=KnowledgeCategory.RESEARCH,
                layer=KnowledgeLayer.MID_TERM,
                source="Overture Research",
                source_credibility_score=0.86,
                tags=["housing", "real-estate", "builders", "mortgages"],
                asset_classes=["equities", "real_estate"],
                tickers=["DHI", "LEN", "NVR", "VMC", "BLDR"],
                metadata_={"original_category": "research"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Sector Rotation Playbook: Late-Cycle Positioning",
                content=(
                    "Historical business cycle analysis suggests the US economy is in a "
                    "late-expansion phase characterized by: still-positive but decelerating GDP "
                    "growth, tight labor market with early softening signals, peak corporate "
                    "margins beginning to plateau, and a Fed shifting to easing.\n\n"
                    "Traditional late-cycle winners: Healthcare (+4.2% avg alpha), consumer "
                    "staples (+2.8%), and utilities (+3.1%). Late-cycle underperformers: "
                    "materials (-2.5%), industrials (-1.8%), and consumer discretionary (-2.1%).\n\n"
                    "However, the AI capex cycle may override traditional sector rotation — "
                    "technology and communication services have maintained relative strength "
                    "despite late-cycle indicators. Quality factor (high ROE, low debt, stable "
                    "earnings) consistently outperforms in late-cycle environments. Consider "
                    "barbell: defensive quality + secular growth."
                ),
                category=KnowledgeCategory.TECHNICAL,
                layer=KnowledgeLayer.MID_TERM,
                source="Overture Research",
                source_credibility_score=0.84,
                tags=["sector-rotation", "business-cycle", "quality", "defensive"],
                asset_classes=["equities"],
                tickers=["XLV", "XLP", "XLU", "QUAL", "MTUM"],
                metadata_={"original_category": "technical"},
            ),
            # ── Short-term (Tactical, days-months) ────────────────────
            KnowledgeEntry(
                id=str(uuid4()),
                title="Q1 2026 Earnings Season Preview: Key Themes to Watch",
                content=(
                    "Q1 2026 earnings season kicks off mid-April with major bank results. "
                    "Consensus expects 8.2% YoY EPS growth for the S&P 500, with particular "
                    "strength in technology (+15%), healthcare (+12%), and financials (+10%).\n\n"
                    "Key themes: (1) AI monetization — expect management commentary on AI "
                    "revenue contribution becoming material (>5% of revenue) for cloud providers, "
                    "(2) Tariff impact — companies with significant China/Mexico exposure will "
                    "need to address supply chain adjustments and margin headwinds, (3) Consumer "
                    "health — watch for credit delinquency commentary from banks and discretionary "
                    "spending trends from retailers.\n\n"
                    "Tactical positioning: Pre-earnings volatility typically peaks 1-2 weeks before "
                    "reporting. Historical data shows buying quality mega-caps after >5% pullbacks "
                    "during earnings season generates 70% win rate over the following 30 days."
                ),
                category=KnowledgeCategory.EVENT,
                layer=KnowledgeLayer.SHORT_TERM,
                source="Reuters",
                source_credibility_score=0.89,
                tags=["earnings", "Q1-2026", "banks", "AI-monetization"],
                asset_classes=["equities"],
                tickers=["JPM", "AAPL", "AMZN", "MSFT", "META"],
                metadata_={"original_category": "event"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Technical Analysis: S&P 500 Market Structure — February 2026",
                content=(
                    "The S&P 500 is trading near all-time highs with constructive market "
                    "structure. Key levels: Support at 5,850 (50-DMA) and 5,680 (200-DMA); "
                    "resistance at 6,100 (upper Bollinger Band). The index has held above its "
                    "rising 50-DMA for 45 consecutive trading days.\n\n"
                    "Breadth analysis: The advance-decline line is confirming new highs — a "
                    "bullish signal. However, the percentage of stocks above their 200-DMA has "
                    "declined from 75% to 62% over the past month, suggesting narrowing "
                    "participation that bears monitoring.\n\n"
                    "Momentum: RSI(14) at 58 — neutral, not overbought. MACD histogram positive "
                    "and expanding. VIX at 14.2, below its 6-month average of 16.5, suggesting "
                    "complacency. Options market: Put/call ratio at 0.72, below average (0.85), "
                    "indicating bullish positioning. Risk: A VIX spike above 20 would trigger "
                    "systematic selling from vol-targeting strategies."
                ),
                category=KnowledgeCategory.TECHNICAL,
                layer=KnowledgeLayer.SHORT_TERM,
                source="Overture Technical",
                source_credibility_score=0.82,
                tags=["technical", "S&P500", "breadth", "VIX", "momentum"],
                asset_classes=["equities"],
                tickers=["SPY", "QQQ", "VIX"],
                metadata_={"original_category": "technical"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Geopolitical Risk Monitor: February 2026",
                content=(
                    "Current geopolitical risk factors ranked by potential market impact:\n\n"
                    "1. US-China Trade Tensions (HIGH): New tariff announcements targeting "
                    "semiconductors and EVs could disrupt supply chains. The semiconductor "
                    "equipment export control list is expected to expand in Q2. Watch for "
                    "retaliatory rare earth export restrictions from China.\n\n"
                    "2. Middle East Energy Disruption (MEDIUM): Ongoing tensions in the "
                    "Strait of Hormuz region. Oil supply disruption risk is elevated but "
                    "priced in at ~$5/barrel risk premium. Key metric: tanker insurance rates "
                    "as a leading indicator.\n\n"
                    "3. European Fiscal Stress (LOW-MEDIUM): Several EU nations approaching "
                    "debt sustainability thresholds. ECB bond-buying backstop limits tail risk "
                    "but political fragmentation could flare. Monitor France-Germany spread.\n\n"
                    "Portfolio hedges: Consider 1-3% allocation to gold (GLD), tail-risk put "
                    "spreads on EEM, and energy sector calls as geopolitical optionality."
                ),
                category=KnowledgeCategory.EVENT,
                layer=KnowledgeLayer.SHORT_TERM,
                source="Reuters",
                source_credibility_score=0.88,
                tags=["geopolitics", "trade-war", "oil", "risk", "hedging"],
                asset_classes=["equities", "commodities"],
                tickers=["GLD", "EEM", "XLE", "USO"],
                metadata_={"original_category": "event"},
            ),
            KnowledgeEntry(
                id=str(uuid4()),
                title="Market Sentiment & Positioning Report: Weekly Update",
                content=(
                    "Fund flow and positioning data for the week ending Feb 14, 2026:\n\n"
                    "Equity flows: +$12.3B into US equity funds (4th consecutive week of inflows). "
                    "Technology sector ETFs saw +$4.1B, the largest weekly inflow since November. "
                    "Emerging market equity funds saw -$1.8B in outflows on dollar strength.\n\n"
                    "Options market: S&P 500 skew (25-delta put vs call IV) at -3.2%, below "
                    "the 6-month average of -5.1%, indicating reduced demand for downside "
                    "protection. Gamma exposure (GEX) is positive at the 6,000 strike, "
                    "suggesting dealer hedging will dampen volatility near current levels.\n\n"
                    "Sentiment indicators: AAII Bull-Bear spread at +18% (moderately bullish). "
                    "CNN Fear & Greed Index at 62 (Greed). Insider selling: Elevated in "
                    "technology sector — CEO/CFO sales at 1.8x the 12-month average. "
                    "Contrarian signal: Extreme insider selling historically precedes "
                    "3-5% pullbacks within 60 days."
                ),
                category=KnowledgeCategory.MACRO,
                layer=KnowledgeLayer.SHORT_TERM,
                source="Bloomberg",
                source_credibility_score=0.90,
                tags=["sentiment", "flows", "positioning", "options", "insider-trading"],
                asset_classes=["equities"],
                tickers=["SPY", "QQQ", "EEM"],
                metadata_={"original_category": "sentiment"},
            ),
        ]

        for article in articles:
            session.add(article)

        # Seed market outlooks for each layer
        for layer_enum, sentiment, confidence, rationale, drivers in [
            (
                KnowledgeLayer.LONG_TERM,
                OutlookSentiment.BULLISH,
                0.75,
                "Secular tailwinds from AI adoption, demographics, and energy transition "
                "support a constructive long-term outlook. Productivity gains from AI could "
                "drive above-trend earnings growth for the next decade.",
                ["AI productivity revolution", "Emerging market consumer growth",
                 "Energy transition investment", "Healthcare innovation"],
            ),
            (
                KnowledgeLayer.MID_TERM,
                OutlookSentiment.NEUTRAL,
                0.60,
                "Mixed signals: Fed easing supports risk assets, but late-cycle dynamics "
                "and elevated valuations limit upside. Earnings breadth improvement is "
                "encouraging but needs confirmation over the next two quarters.",
                ["Fed rate-cut cycle", "Earnings breadth improving",
                 "Valuations above historical average", "Margin pressure emerging"],
            ),
            (
                KnowledgeLayer.SHORT_TERM,
                OutlookSentiment.BULLISH,
                0.65,
                "Constructive near-term setup: positive momentum, supportive flows, and "
                "benign volatility. Earnings season is a potential catalyst. Risk of "
                "complacency given low VIX and bullish positioning.",
                ["Positive price momentum", "Strong fund inflows",
                 "Low volatility environment", "Earnings season catalyst"],
            ),
        ]:
            existing = (await session.execute(
                select(MarketOutlook)
                .where(MarketOutlook.layer == layer_enum)
                .where(MarketOutlook.asset_class == "general")
            )).scalar_one_or_none()
            if not existing:
                session.add(MarketOutlook(
                    id=str(uuid4()),
                    layer=layer_enum,
                    asset_class="general",
                    outlook=sentiment,
                    confidence=confidence,
                    rationale=rationale,
                    key_drivers=drivers,
                ))

        await session.commit()
        logger.info("Seeded %d knowledge articles and market outlooks.", len(articles))


app = FastAPI(
    title="Overture - AI Hedge Fund",
    description="Multi-agent AI-native hedge fund system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API routes
app.include_router(ideas.router, prefix="/api/ideas", tags=["ideas"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
app.include_router(rl.router, prefix="/api/rl", tags=["rl"])
app.include_router(seed.router, prefix="/api/seed", tags=["seed"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["market-data"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

# WebSocket
app.include_router(ws_router, prefix="/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "database": "connected" if db_base.db_ready else "unavailable",
    }
