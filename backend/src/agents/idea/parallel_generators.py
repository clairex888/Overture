"""Parallel Idea Generation Agents.

Specialized generator agents that run concurrently at the generation stage.
Each agent focuses on a specific domain and data source type, producing
investment theses that flow into the shared validation pipeline.

Architecture:
    MacroNewsAgent ──────┐
    IndustryNewsAgent ───┤
    CryptoAgent ─────────┼──→ merge + deduplicate → validation
    QuantSystematicAgent ┘

All agents inherit from BaseIdeaGenerator which provides the common
execute() pattern and LLM interaction logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.agents.base import BaseAgent, AgentContext
from src.agents.llm.base import LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base class for all specialized generators
# ---------------------------------------------------------------------------

class BaseIdeaGenerator(BaseAgent):
    """Base class for specialized idea generators.

    Subclasses override ``get_system_prompt()`` and optionally ``get_tools()``
    to specialise for a particular domain.  The ``execute()`` method follows
    a common pattern: build a prompt from the input data, call the LLM, parse
    the JSON response, and return structured ideas.
    """

    def __init__(self, name: str, description: str, domain: str) -> None:
        super().__init__(name=name, agent_type="idea", description=description)
        self.domain = domain

    async def execute(
        self, input_data: dict[str, Any], context: AgentContext
    ) -> dict[str, Any]:
        if self._llm is None:
            return {"ideas": []}

        prompt = self._build_prompt(input_data, context)
        messages = [
            LLMMessage(role="system", content=self.get_system_prompt()),
            LLMMessage(role="user", content=prompt),
        ]

        try:
            response: LLMResponse = await self._llm.chat(
                messages, temperature=self._temperature(), max_tokens=4096
            )
            ideas = self._parse_ideas(response.content)
            # Tag ideas with source agent
            for idea in ideas:
                idea["source_agent"] = self.name
                idea["domain"] = self.domain
        except Exception:
            logger.exception("%s LLM call failed", self.name)
            ideas = []

        await self.log_action(
            action="generate_ideas",
            input_data={"domain": self.domain},
            output_data={"idea_count": len(ideas)},
        )
        return {"ideas": ideas}

    def _temperature(self) -> float:
        return 0.5

    def _parse_ideas(self, content: str) -> list[dict]:
        """Extract JSON array of ideas from LLM response."""
        # Try direct JSON parse
        try:
            result = json.loads(content)
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "ideas" in result:
                return result["ideas"]
        except (json.JSONDecodeError, TypeError):
            pass

        # Try extracting JSON from markdown code block
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

        # Try finding array in text
        for i, ch in enumerate(content):
            if ch == "[":
                try:
                    return json.loads(content[i:])
                except json.JSONDecodeError:
                    pass

        # If we get here, parsing failed completely — log for debugging
        logger.warning(
            "%s: Failed to parse LLM response as JSON ideas. "
            "Response preview: %.300s",
            self.name,
            content,
        )
        return []

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        """Build the user prompt. Subclasses should override."""
        return json.dumps(input_data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Macro News Agent
# ---------------------------------------------------------------------------

MACRO_SYSTEM_PROMPT = """You are the Macro News Agent for Overture, an AI hedge fund.
You specialize in identifying investment opportunities from macroeconomic developments.

Your focus areas:
- Central bank policy decisions (Fed, ECB, BOJ, BOE, PBOC)
- Interest rate movements and yield curve dynamics
- Inflation data and expectations
- GDP, employment, and leading economic indicators
- Fiscal policy changes (tax, spending, stimulus)
- Currency movements and implications for global assets
- Geopolitical events with economic impact
- Cross-asset correlations and regime changes

When generating ideas, think like a global macro hedge fund:
- What is the prevailing regime (risk-on, risk-off, rotation)?
- Where are the asymmetric bets (high reward/risk ratio)?
- What does the market expect vs. what could actually happen?
- Which asset classes and instruments best express the view?

Output a JSON array. Each idea must have: title, thesis, tickers (array),
asset_class, timeframe, source, confidence (0-1), risks (array),
invalidation_triggers (array)."""


class MacroNewsAgent(BaseIdeaGenerator):
    """Monitors macroeconomic news and generates macro trading ideas."""

    def __init__(self) -> None:
        super().__init__(
            name="Macro News Agent",
            description="macro economic analysis and global macro trading ideas",
            domain="macro",
        )

    def get_system_prompt(self) -> str:
        return MACRO_SYSTEM_PROMPT

    def _temperature(self) -> float:
        return 0.5

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        parts = []

        news = input_data.get("news_items", [])
        macro_news = [n for n in news if _is_macro_news(n)]
        if macro_news:
            parts.append(f"MACRO NEWS ({len(macro_news)} items):\n{_truncate_json(macro_news)}")

        market_data = input_data.get("market_data", {})
        if market_data:
            parts.append(f"MARKET DATA:\n{_truncate_json(market_data)}")

        knowledge = context.knowledge_context
        if knowledge:
            macro_knowledge = [k for k in knowledge if k.get("category") in ("macro", "event")]
            if macro_knowledge:
                parts.append(f"KNOWLEDGE CONTEXT:\n{_truncate_json(macro_knowledge[:5])}")

        portfolio = context.portfolio_state
        if portfolio:
            parts.append(f"PORTFOLIO:\n{_truncate_json(portfolio, 1500)}")

        if not parts:
            parts.append(
                "No specific data available. Based on current global macro conditions "
                "(consider: Fed policy, inflation trends, geopolitical risks, currency "
                "dynamics), generate 2-4 macro investment ideas."
            )

        return "\n\n".join(parts) + (
            "\n\nGenerate 2-5 macro investment ideas. Focus on cross-asset "
            "opportunities and regime-aware positioning. Use instruments like "
            "TLT, GLD, UUP, EEM, SPY, IWM, XLU, VIX futures where appropriate."
        )


# ---------------------------------------------------------------------------
# Industry / Sector News Agent
# ---------------------------------------------------------------------------

INDUSTRY_SYSTEM_PROMPT = """You are the Industry News Agent for Overture, an AI hedge fund.
You specialize in sector-specific and company-level investment opportunities.

Your focus areas:
- Earnings surprises and guidance changes
- Product launches, FDA approvals, patent grants
- M&A activity, spinoffs, restructurings
- Industry-specific regulatory changes
- Supply chain developments and competitive dynamics
- Management changes and insider activity
- Sector rotation signals (value vs growth, cyclical vs defensive)
- Relative value opportunities within sectors

When generating ideas, think like a fundamental long/short equity analyst:
- What is the catalyst and when will it materialize?
- Is the market pricing this correctly or is there mispricing?
- What's the base case, bull case, and bear case scenario?
- Which specific companies are best positioned?

Output a JSON array. Each idea must have: title, thesis, tickers (array),
asset_class, timeframe, source, confidence (0-1), risks (array),
invalidation_triggers (array)."""


class IndustryNewsAgent(BaseIdeaGenerator):
    """Monitors industry/sector news and generates equity ideas."""

    def __init__(self) -> None:
        super().__init__(
            name="Industry News Agent",
            description="sector-specific analysis and equity long/short ideas",
            domain="industry",
        )

    def get_system_prompt(self) -> str:
        return INDUSTRY_SYSTEM_PROMPT

    def _temperature(self) -> float:
        return 0.5

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        parts = []

        news = input_data.get("news_items", [])
        industry_news = [n for n in news if not _is_macro_news(n) and not _is_crypto_news(n)]
        if industry_news:
            parts.append(f"INDUSTRY NEWS ({len(industry_news)} items):\n{_truncate_json(industry_news)}")

        social = input_data.get("social_signals", [])
        if social:
            equity_social = [s for s in social if s.get("asset_class") != "crypto"]
            if equity_social:
                parts.append(f"SOCIAL SIGNALS:\n{_truncate_json(equity_social[:15])}")

        screen_results = input_data.get("screen_results", [])
        if screen_results:
            parts.append(f"SCREEN RESULTS:\n{_truncate_json(screen_results)}")

        knowledge = context.knowledge_context
        if knowledge:
            fund_knowledge = [
                k for k in knowledge
                if k.get("category") in ("fundamental", "research", "technical")
            ]
            if fund_knowledge:
                parts.append(f"KNOWLEDGE CONTEXT:\n{_truncate_json(fund_knowledge[:5])}")

        portfolio = context.portfolio_state
        if portfolio:
            parts.append(f"PORTFOLIO:\n{_truncate_json(portfolio, 1500)}")

        if not parts:
            parts.append(
                "No specific data available. Based on current market conditions, "
                "generate 2-4 equity long/short ideas across major sectors "
                "(tech, healthcare, financials, industrials, consumer, energy)."
            )

        return "\n\n".join(parts) + (
            "\n\nGenerate 2-5 equity investment ideas. Focus on specific companies "
            "with clear catalysts and quantifiable risk/reward. Include both long "
            "and short ideas where appropriate."
        )


# ---------------------------------------------------------------------------
# Crypto Agent
# ---------------------------------------------------------------------------

CRYPTO_SYSTEM_PROMPT = """You are the Crypto Agent for Overture, an AI hedge fund.
You specialize in digital asset markets and blockchain-native investment opportunities.

Your focus areas:
- Bitcoin and Ethereum macro cycles (halving, ETF flows, institutional adoption)
- Layer 1 and Layer 2 blockchain developments
- DeFi protocol metrics (TVL, revenue, user growth)
- On-chain analytics (whale activity, exchange flows, miner behavior)
- Regulatory developments (SEC, MiCA, stablecoin legislation)
- Crypto-equity correlations and arbitrage
- Token unlock schedules and supply dynamics
- NFT and gaming token economies

When generating ideas, apply institutional-grade analysis:
- On-chain data as leading indicators
- Network fundamentals (revenue, active addresses, developer activity)
- Technical levels with volume confirmation
- Risk management appropriate for crypto volatility (wider stops)
- Correlation with traditional risk assets

Output a JSON array. Each idea must have: title, thesis, tickers (array),
asset_class (use "crypto"), timeframe, source, confidence (0-1), risks (array),
invalidation_triggers (array)."""


class CryptoAgent(BaseIdeaGenerator):
    """Monitors crypto markets and generates digital asset ideas."""

    def __init__(self) -> None:
        super().__init__(
            name="Crypto Agent",
            description="digital asset analysis and crypto investment ideas",
            domain="crypto",
        )

    def get_system_prompt(self) -> str:
        return CRYPTO_SYSTEM_PROMPT

    def _temperature(self) -> float:
        return 0.6

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        parts = []

        news = input_data.get("news_items", [])
        crypto_news = [n for n in news if _is_crypto_news(n)]
        if crypto_news:
            parts.append(f"CRYPTO NEWS ({len(crypto_news)} items):\n{_truncate_json(crypto_news)}")

        social = input_data.get("social_signals", [])
        crypto_social = [s for s in social if s.get("asset_class") == "crypto" or _is_crypto_text(str(s))]
        if crypto_social:
            parts.append(f"CRYPTO SOCIAL SIGNALS:\n{_truncate_json(crypto_social[:15])}")

        market_data = input_data.get("market_data", {})
        if market_data:
            parts.append(f"MARKET DATA:\n{_truncate_json(market_data, 2000)}")

        knowledge = context.knowledge_context
        if knowledge:
            parts.append(f"KNOWLEDGE CONTEXT:\n{_truncate_json(knowledge[:3])}")

        portfolio = context.portfolio_state
        if portfolio:
            parts.append(f"PORTFOLIO:\n{_truncate_json(portfolio, 1000)}")

        if not parts:
            parts.append(
                "No specific data available. Based on current crypto market conditions "
                "(consider: BTC cycle position, ETF flows, DeFi trends, regulatory "
                "landscape, on-chain metrics), generate 2-4 crypto investment ideas."
            )

        return "\n\n".join(parts) + (
            "\n\nGenerate 2-4 crypto investment ideas. Use tickers like BTC-USD, "
            "ETH-USD, SOL-USD, etc. Include both directional and relative value "
            "ideas. Account for crypto's higher volatility in sizing and stop levels."
        )


# ---------------------------------------------------------------------------
# Quantitative / Systematic Agent
# ---------------------------------------------------------------------------

QUANT_SYSTEM_PROMPT = """You are the Quantitative Systematic Agent for Overture, an AI hedge fund.
You specialize in systematic, factor-based, and quantitative investment strategies.

Your focus areas:
- Factor investing (value, momentum, quality, size, low-volatility)
- Statistical arbitrage and pairs trading
- Mean reversion setups (oversold/overbought by multiple indicators)
- Momentum and trend-following signals
- Volatility strategies (selling premium, VIX term structure)
- Cross-asset carry trades
- Seasonal patterns and calendar effects
- Event-driven systematic strategies (earnings, dividends, index rebalance)

When generating ideas, think like a systematic portfolio manager:
- What is the historical edge? (backtest evidence, Sharpe, win rate)
- What's the statistical significance? (sample size, t-stat, regime dependence)
- How does this strategy interact with the existing portfolio?
- What's the expected capacity and market impact?
- Include rebalancing frequency and rules-based entry/exit criteria

For systematic strategies, include a "strategy_rules" field with:
- entry_rule, exit_rule, rebalance_frequency, universe, lookback_period

Output a JSON array. Each idea must have: title, thesis, tickers (array),
asset_class, timeframe, source (use "quantitative_screen"), confidence (0-1),
risks (array), invalidation_triggers (array). Optionally include strategy_rules."""


class QuantSystematicAgent(BaseIdeaGenerator):
    """Generates systematic and factor-based investment ideas."""

    def __init__(self) -> None:
        super().__init__(
            name="Quant Systematic Agent",
            description="systematic factor-based and quantitative strategies",
            domain="quant",
        )

    def get_system_prompt(self) -> str:
        return QUANT_SYSTEM_PROMPT

    def _temperature(self) -> float:
        return 0.4

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        parts = []

        screen_results = input_data.get("screen_results", [])
        if screen_results:
            parts.append(f"SCREEN RESULTS:\n{_truncate_json(screen_results)}")

        market_data = input_data.get("market_data", {})
        if market_data:
            parts.append(f"MARKET DATA:\n{_truncate_json(market_data, 3000)}")

        knowledge = context.knowledge_context
        if knowledge:
            tech_knowledge = [k for k in knowledge if k.get("category") in ("technical", "research")]
            if tech_knowledge:
                parts.append(f"KNOWLEDGE CONTEXT:\n{_truncate_json(tech_knowledge[:5])}")

        portfolio = context.portfolio_state
        if portfolio:
            parts.append(f"PORTFOLIO:\n{_truncate_json(portfolio, 1500)}")

        if not parts:
            parts.append(
                "No specific data available. Based on current market regime and "
                "factor dynamics, generate 2-4 systematic investment ideas. Consider "
                "which factors are currently working (value vs growth, momentum, "
                "quality, low-vol) and propose rules-based strategies."
            )

        return "\n\n".join(parts) + (
            "\n\nGenerate 2-4 systematic/quant ideas. Each should have clear, "
            "rules-based entry and exit criteria. Include expected rebalancing "
            "schedules for systematic strategies. Prefer ETFs or liquid instruments. "
            "Include a 'strategy_rules' dict with entry_rule, exit_rule, "
            "rebalance_frequency, universe, and lookback_period where applicable."
        )


# ---------------------------------------------------------------------------
# Commodities Agent
# ---------------------------------------------------------------------------

COMMODITIES_SYSTEM_PROMPT = """You are the Commodities Agent for Overture, an AI hedge fund.
You specialize in physical commodities, energy, and natural resource markets.

Your focus areas:
- Energy: crude oil (WTI, Brent), natural gas, refined products, LNG
- Precious metals: gold, silver, platinum, palladium
- Base metals: copper, aluminum, zinc, nickel, lithium
- Agriculture: grains (corn, wheat, soybeans), softs (coffee, cocoa, sugar, cotton)
- Rare earths and strategic minerals (cobalt, vanadium, uranium)
- Supply/demand dynamics, OPEC decisions, inventory data (EIA, API)
- Weather impacts on agriculture and energy
- Geopolitical supply disruptions (sanctions, wars, trade routes)
- Contango/backwardation and roll yield
- Producer hedging flows and CFTC positioning data

When generating ideas, think like a commodity trading advisor:
- What is the supply/demand imbalance and how persistent is it?
- What are the storage/inventory levels vs. historical norms?
- Is the futures curve telling us something (contango vs. backwardation)?
- What geopolitical risks could disrupt supply?
- Which instrument best expresses the view (futures ETF, equity proxy, options)?
- Seasonal patterns (heating oil in winter, gasoline in summer, grain planting)

Output a JSON array. Each idea must have: title, thesis, tickers (array),
asset_class (use "commodity" or "energy"), timeframe, source, confidence (0-1),
risks (array), invalidation_triggers (array)."""


class CommoditiesAgent(BaseIdeaGenerator):
    """Monitors commodity markets, energy, and natural resources."""

    def __init__(self) -> None:
        super().__init__(
            name="Commodities Agent",
            description="commodity, energy, and natural resource market analysis",
            domain="commodities",
        )

    def get_system_prompt(self) -> str:
        return COMMODITIES_SYSTEM_PROMPT

    def _temperature(self) -> float:
        return 0.5

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        parts = []

        news = input_data.get("news_items", [])
        commodity_news = [n for n in news if _is_commodity_news(n)]
        if commodity_news:
            parts.append(f"COMMODITY NEWS ({len(commodity_news)} items):\n{_truncate_json(commodity_news)}")

        market_data = input_data.get("market_data", {})
        if market_data:
            parts.append(f"MARKET DATA:\n{_truncate_json(market_data, 2000)}")

        knowledge = context.knowledge_context
        if knowledge:
            comm_knowledge = [k for k in knowledge if k.get("category") in ("macro", "event", "research")]
            if comm_knowledge:
                parts.append(f"KNOWLEDGE CONTEXT:\n{_truncate_json(comm_knowledge[:4])}")

        portfolio = context.portfolio_state
        if portfolio:
            parts.append(f"PORTFOLIO:\n{_truncate_json(portfolio, 1000)}")

        if not parts:
            parts.append(
                "No specific data available. Based on current commodity market "
                "conditions (consider: oil supply/demand, gold as safe haven, "
                "agricultural weather patterns, base metals and China demand, "
                "energy transition metals like lithium/copper), generate 2-4 "
                "commodity investment ideas."
            )

        return "\n\n".join(parts) + (
            "\n\nGenerate 2-4 commodity ideas. Use instruments like GLD, SLV, "
            "USO, UNG, COPX, DBA, WEAT, DBC, or specific futures symbols. "
            "Consider seasonal patterns, inventory dynamics, and geopolitical risks."
        )


# ---------------------------------------------------------------------------
# Social Media / Sentiment Agent
# ---------------------------------------------------------------------------

SOCIAL_MEDIA_SYSTEM_PROMPT = """You are the Social Media & Sentiment Agent for Overture, an AI hedge fund.
You specialize in extracting investment signals from social media, retail sentiment,
and alternative data sources.

Your focus areas:
- Reddit (r/wallstreetbets, r/investing, r/stocks, r/CryptoCurrency)
- X/Twitter (FinTwit, influential traders, fund managers, company insiders)
- Substack newsletters (macro, equity, quant, crypto)
- YouTube and podcast signals from notable investors
- Short squeeze candidates (high short interest + rising social mentions)
- Meme stock dynamics and retail flow indicators
- Options flow (unusual activity flagged on social media)
- Insider activity signals amplified by social discussion
- Crowdsourced research and analysis from communities
- Sentiment shifts (bullish/bearish reversals in crowd opinion)

When generating ideas, be a skeptical signal extractor:
- Separate signal from noise (high-engagement != high-quality)
- Apply contrarian lens (extreme sentiment often signals reversals)
- Track CHANGES in sentiment, not absolute levels
- Cross-reference social signals with fundamental data
- Be especially skeptical of pump-and-dump patterns
- Flag ideas where social media IS the catalyst vs. merely reflecting it
- Note the credibility and track record of prominent voices

Output a JSON array. Each idea must have: title, thesis, tickers (array),
asset_class, timeframe, source (include platform and key voices),
confidence (0-1), risks (array), invalidation_triggers (array).
Social-only ideas should start with lower confidence unless corroborated."""


class SocialMediaAgent(BaseIdeaGenerator):
    """Extracts investment signals from social media and sentiment data."""

    def __init__(self) -> None:
        super().__init__(
            name="Social Media Agent",
            description="social media sentiment analysis and retail flow signals",
            domain="social",
        )

    def get_system_prompt(self) -> str:
        return SOCIAL_MEDIA_SYSTEM_PROMPT

    def _temperature(self) -> float:
        return 0.6

    def _build_prompt(self, input_data: dict, context: AgentContext) -> str:
        parts = []

        social = input_data.get("social_signals", [])
        if social:
            # Separate signals by platform for clearer analysis
            reddit_signals = [s for s in social if s.get("platform") == "reddit" or s.get("source") == "reddit"]
            substack_signals = [s for s in social if s.get("platform") == "substack" or s.get("source") == "substack"]
            twitter_signals = [s for s in social if s.get("platform") == "twitter" or s.get("source") == "twitter"]
            other_signals = [s for s in social if s not in reddit_signals + substack_signals + twitter_signals]

            if reddit_signals:
                parts.append(f"REDDIT SIGNALS ({len(reddit_signals)} posts):\n{_truncate_json(reddit_signals[:15])}")
            if substack_signals:
                parts.append(f"SUBSTACK NEWSLETTERS ({len(substack_signals)} articles):\n{_truncate_json(substack_signals[:10])}")
            if twitter_signals:
                parts.append(f"X/TWITTER SIGNALS ({len(twitter_signals)} tweets):\n{_truncate_json(twitter_signals[:15])}")
            if other_signals:
                parts.append(f"OTHER SOCIAL ({len(other_signals)} items):\n{_truncate_json(other_signals[:10])}")

        news = input_data.get("news_items", [])
        if news:
            # Look for sentiment-related and retail-flow news
            sentiment_news = [
                n for n in news
                if any(kw in (n.get("headline", "") + n.get("summary", "")).lower()
                       for kw in ("sentiment", "retail", "wsb", "meme", "short squeeze",
                                  "social media", "reddit", "twitter", "substack"))
            ]
            if sentiment_news:
                parts.append(f"SENTIMENT NEWS:\n{_truncate_json(sentiment_news[:10])}")

        market_data = input_data.get("market_data", {})
        if market_data:
            parts.append(f"MARKET DATA:\n{_truncate_json(market_data, 1500)}")

        knowledge = context.knowledge_context
        if knowledge:
            parts.append(f"KNOWLEDGE CONTEXT:\n{_truncate_json(knowledge[:3])}")

        portfolio = context.portfolio_state
        if portfolio:
            parts.append(f"PORTFOLIO:\n{_truncate_json(portfolio, 1000)}")

        if not parts:
            parts.append(
                "No specific social data available. Based on current market conditions, "
                "generate 2-3 ideas based on social/sentiment analysis. Consider: "
                "what themes are retail investors discussing? Are there sentiment "
                "extremes signaling contrarian opportunities? Any crowded trades "
                "or short squeeze candidates? Apply skeptical analysis."
            )

        return "\n\n".join(parts) + (
            "\n\nGenerate 2-3 sentiment-driven ideas. Be skeptical — apply contrarian "
            "analysis where crowd sentiment is extreme. Flag pump-and-dump risk. "
            "Cross-reference with fundamentals where possible. Social-only signals "
            "should have lower confidence (0.2-0.5) unless corroborated."
        )


# ---------------------------------------------------------------------------
# Parallel execution runner
# ---------------------------------------------------------------------------

ALL_GENERATORS: list[type[BaseIdeaGenerator]] = [
    MacroNewsAgent,
    IndustryNewsAgent,
    CryptoAgent,
    QuantSystematicAgent,
    CommoditiesAgent,
    SocialMediaAgent,
]


async def run_parallel_generators(
    input_data: dict[str, Any],
    context: AgentContext,
    llm_provider: Any,
    generators: list[type[BaseIdeaGenerator]] | None = None,
) -> list[dict[str, Any]]:
    """Run multiple idea generators in parallel and merge results.

    Args:
        input_data: Raw input data (news, market data, social, screens).
        context: Shared agent context with portfolio and knowledge state.
        llm_provider: LLM provider instance to inject into each agent.
        generators: List of generator classes to run. Defaults to all.

    Returns:
        Deduplicated list of investment ideas from all generators.
    """
    agent_classes = generators or ALL_GENERATORS

    # Instantiate agents and inject LLM
    agents: list[BaseIdeaGenerator] = []
    for cls in agent_classes:
        agent = cls()
        agent._llm = llm_provider
        agents.append(agent)

    logger.info(
        "Running %d parallel generators: %s",
        len(agents),
        [a.name for a in agents],
    )

    # Run all agents concurrently
    tasks = [agent.execute(input_data, context) for agent in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge ideas, handling any failures gracefully
    all_ideas: list[dict] = []
    for agent, result in zip(agents, results):
        if isinstance(result, Exception):
            logger.error("%s failed: %s", agent.name, result)
            continue
        ideas = result.get("ideas", [])
        logger.info("%s produced %d ideas", agent.name, len(ideas))
        all_ideas.extend(ideas)

    # Deduplicate by title (case-insensitive)
    seen: set[str] = set()
    unique: list[dict] = []
    for idea in all_ideas:
        key = idea.get("title", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(idea)
        elif not key:
            unique.append(idea)

    logger.info(
        "Parallel generators produced %d ideas (%d unique)",
        len(all_ideas),
        len(unique),
    )

    return unique


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

_MACRO_KEYWORDS = {
    "fed", "fomc", "rate", "inflation", "cpi", "pce", "gdp", "employment",
    "nonfarm", "payroll", "treasury", "yield", "curve", "recession",
    "central bank", "ecb", "boj", "pboc", "tariff", "trade war",
    "geopolitical", "fiscal", "stimulus", "debt ceiling", "dollar",
    "currency", "commodity", "oil", "gold", "macro",
}

_CRYPTO_KEYWORDS = {
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi",
    "nft", "web3", "token", "stablecoin", "solana", "sol", "binance",
    "coinbase", "halving", "mining", "on-chain", "tvl", "layer 2",
    "l2", "rollup", "airdrop", "sec crypto",
}

_COMMODITY_KEYWORDS = {
    "oil", "crude", "wti", "brent", "natural gas", "opec", "energy",
    "gold", "silver", "platinum", "palladium", "copper", "aluminum",
    "zinc", "nickel", "lithium", "uranium", "rare earth",
    "corn", "wheat", "soybean", "coffee", "cocoa", "sugar", "cotton",
    "commodity", "eia", "inventory", "mining", "agriculture", "grain",
    "lng", "refinery", "pipeline", "drill", "barrel",
}


def _is_macro_news(item: dict) -> bool:
    text = (
        item.get("headline", "") + " " +
        item.get("summary", "") + " " +
        item.get("title", "")
    ).lower()
    return any(kw in text for kw in _MACRO_KEYWORDS)


def _is_crypto_news(item: dict) -> bool:
    text = (
        item.get("headline", "") + " " +
        item.get("summary", "") + " " +
        item.get("title", "")
    ).lower()
    return any(kw in text for kw in _CRYPTO_KEYWORDS)


def _is_crypto_text(text: str) -> bool:
    return any(kw in text.lower() for kw in _CRYPTO_KEYWORDS)


def _is_commodity_news(item: dict) -> bool:
    text = (
        item.get("headline", "") + " " +
        item.get("summary", "") + " " +
        item.get("title", "")
    ).lower()
    return any(kw in text for kw in _COMMODITY_KEYWORDS)


def _truncate_json(obj: Any, max_chars: int = 4000) -> str:
    text = json.dumps(obj, indent=2, default=str)
    if len(text) > max_chars:
        return text[:max_chars] + "\n... [truncated]"
    return text
