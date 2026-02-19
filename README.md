# Overture

**AI-native multi-agent hedge fund system.** Instead of human-in-the-loop at every step, Overture puts the human as the architect and conductor -- AI agents sprint autonomously through the full investment lifecycle while you monitor from altitude.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [End-to-End Data Flow](#end-to-end-data-flow)
- [Database Schema](#database-schema)
- [API Keys & Configuration](#api-keys--configuration)
- [Data Sources & External APIs](#data-sources--external-apis)
- [Dashboard Pages](#dashboard-pages)
- [API Reference](#api-reference)
- [Quick Start](#quick-start)
- [Deploying to Production](#deploying-to-production)
- [Tech Stack](#tech-stack)

---

## How It Works

Two autonomous agent loops run continuously, coordinated by a master orchestrator:

```
┌─────────────────────────────────────────────────────────────────┐
│                        IDEA LOOP                                │
│                                                                 │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐│
│   │  Generate  │───>│  Validate  │───>│  Execute   │───>│Monitor ││
│   │           │    │           │    │           │    │        ││
│   │ News      │    │ Backtest  │    │ Sizing    │    │ P&L    ││
│   │ Screens   │    │ Reasoning │    │ Timing    │    │ Thesis ││
│   │ Social    │    │ Source    │    │ Stops     │    │ Alerts ││
│   │ Anomalies │    │ Risk      │    │ Instrument│    │ Exit   ││
│   └───────────┘    └───────────┘    └───────────┘    └────────┘│
│        ^                                                  │     │
│        └──────────────────────────────────────────────────┘     │
└────────────────────────────┬────────────────────────────────────┘
                             │ ^
                    trades ───┘ └─── risk limits, approvals
                             │ ^
┌────────────────────────────┴────────────────────────────────────┐
│                      PORTFOLIO LOOP                             │
│                                                                 │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐│
│   │  Assess   │───>│ Construct  │───>│   Risk    │───>│Rebal.  ││
│   │           │    │           │    │  Monitor  │    │        ││
│   │ Allocation│    │ Targets   │    │ VaR       │    │ Drift  ││
│   │ Drift     │    │ Views     │    │ Stress    │    │ Trades ││
│   │ Exposure  │    │ Optimize  │    │ Alerts    │    │ Timing ││
│   └───────────┘    └───────────┘    └───────────┘    └────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Human approval gates** are built in: trade execution plans and rebalancing proposals require your sign-off. You adjust, approve, or reject -- the agents handle everything else.

### Examples

**Silver flash crash:** Silver drops 10-sigma in a day -> Asset monitor triggers idea -> Validator backtests buy-the-dip at 5/10-sigma thresholds -> Historical win rate is 87% -> Executor builds trade plan (SLV ETF, sized for portfolio, stop at -3%) -> You approve in one click -> Monitor watches the position -> Alerts you when target hit.

**TSLA earnings risk:** Earnings approaching -> Generator flags deteriorating delivery numbers -> Validator models downside scenarios -> Executor proposes put spread sized to portfolio -> You review and approve -> Monitor tracks through earnings release.

**Tariff shock:** Breaking news on new tariffs -> Data pipeline ingests instantly -> Generator identifies exposed sectors -> Validator cross-references historical tariff responses -> Executor builds hedging trades -> You get an alert with a ready-to-go plan.

---

## Architecture

```
Overture/
├── backend/                      Python / FastAPI
│   ├── src/
│   │   ├── agents/
│   │   │   ├── llm/              Multi-provider LLM (OpenAI + Anthropic)
│   │   │   │   ├── router.py     Task-based routing: reasoning->Anthropic, extraction->OpenAI
│   │   │   │   ├── openai_provider.py    AsyncOpenAI client (GPT-4o)
│   │   │   │   └── anthropic_provider.py AsyncAnthropic client (Claude Sonnet)
│   │   │   ├── orchestrator/     LangGraph loops + coordinator
│   │   │   │   ├── coordinator.py  OvertureCoordinator (master orchestrator)
│   │   │   │   ├── idea_loop.py    StateGraph: generate->validate->execute->approve->monitor
│   │   │   │   └── portfolio_loop.py StateGraph: assess->construct->risk->rebalance
│   │   │   ├── idea/             Generator, Validator, Executor, Monitor agents
│   │   │   ├── portfolio/        Constructor, Risk Manager, Rebalancer, Monitor agents
│   │   │   ├── knowledge/        Data Curator, Educator, Librarian agents
│   │   │   └── context/          Investment best practices framework
│   │   ├── data/                 External data sources
│   │   │   ├── sources/
│   │   │   │   ├── yahoo_finance.py  Price, fundamentals, options, screening, anomaly detection
│   │   │   │   ├── news_rss.py       8 RSS feeds (Reuters, CNBC, Bloomberg, FT, etc.)
│   │   │   │   └── reddit.py         Reddit public API (5 subreddits)
│   │   │   └── market_data.py    Redis-cached data manager with TTLs
│   │   ├── models/               SQLAlchemy ORM (10 PostgreSQL tables)
│   │   │   ├── idea.py           Ideas with status pipeline
│   │   │   ├── trade.py          Trades with approval workflow
│   │   │   ├── portfolio.py      Portfolio + Positions
│   │   │   ├── knowledge.py      Knowledge entries + Market outlooks
│   │   │   ├── agent_state.py    Agent logs (with token tracking) + Task queue
│   │   │   └── rl.py             RL experiences + episodes
│   │   ├── services/             Backtest, valuation (DCF/comps), risk, screening
│   │   ├── rl/                   RL environment, state, actions, rewards, replay buffer
│   │   └── api/
│   │       ├── routes/           9 route modules + WebSocket
│   │       │   ├── ideas.py      CRUD + generate/validate/execute (DB-backed)
│   │       │   ├── portfolio.py  Overview, positions, risk, allocation, preferences (DB-backed)
│   │       │   ├── trades.py     CRUD + approve/reject/close (DB-backed)
│   │       │   ├── knowledge.py  CRUD + outlook + data pipeline (DB-backed)
│   │       │   ├── agents.py     Agent status, idea-loop start/stop, portfolio-loop start/stop
│   │       │   ├── market_data.py Price, OHLCV history, watchlists, asset info/news/social/summary
│   │       │   ├── alerts.py     Alert feed + dismiss
│   │       │   ├── rl.py         RL stats, episodes, replay buffer, training
│   │       │   └── seed.py       Database seeding ($1M paper portfolio)
│   │       └── websocket.py      Real-time: ideas, trades, alerts, agent status
│   └── tests/
├── frontend/                     Next.js 14 + Tailwind (dark theme)
│   └── src/
│       ├── app/                  12 pages (dashboard, ideas, portfolio, trades, agents, etc.)
│       │   ├── page.tsx          Dashboard with system controls toggles
│       │   ├── ideas/            Ideas pipeline + preferences sub-page
│       │   ├── portfolio/        Portfolio view + preferences sub-page
│       │   ├── trades/           Trade management
│       │   ├── agents/           Agent monitoring
│       │   ├── knowledge/        Knowledge base
│       │   ├── rl/               RL training
│       │   └── asset/[symbol]/   Single asset detail (info, news, social, AI summary)
│       ├── components/           Sidebar, StatCard, AlertFeed, PortfolioChart
│       ├── lib/                  API client (9 API modules), WebSocket client
│       └── types/                27+ TypeScript interfaces
├── docker-compose.yml            PostgreSQL 16 + Redis 7
└── .env.example                  Configuration template
```

---

## End-to-End Data Flow

This section explains how data moves through the system from external sources to what you see on the dashboard.

### 1. External Data Ingestion

```
External World                    Backend Data Layer                  Database
─────────────                    ──────────────────                  ────────
Yahoo Finance  ──yfinance──>  data/sources/yahoo_finance.py  ──>  Redis Cache (30s-1hr TTL)
  (prices, fundamentals,         - fetch_price()
   options, screening)           - fetch_info()
                                 - detect_unusual_moves()
                                 - screen()

RSS Feeds (8)  ──aiohttp──>  data/sources/news_rss.py       ──>  Redis Cache + Knowledge table
  (Reuters, CNBC, Bloomberg,     - fetch_all_feeds()
   FT, MarketWatch, Yahoo,       - ticker extraction via regex
   Seeking Alpha, Investing.com) - feedparser for XML parsing

Reddit (5 subs) ──aiohttp──>  data/sources/reddit.py        ──>  Redis Cache
  (wallstreetbets, investing,    - fetch_subreddit()
   stocks, options, economics)   - relevance scoring
                                 - ticker extraction + stopword filter
```

### 2. Agent Processing Pipeline

```
Data Layer ──> Idea Generator Agent ──> Raw Ideas (DB: ideas table, status=GENERATED)
                  │
                  │ Uses LLM (OpenAI or Anthropic via router.py)
                  │ Tools: search_news, run_screen, analyze_market_moves, search_social
                  v
           Idea Validator Agent ──> Validated/Rejected Ideas (status=VALIDATED or REJECTED)
                  │
                  │ Rule-based filters + LLM sanity check
                  │ Checks: confidence threshold, ticker blacklist, position capacity
                  v
           Trade Executor Agent ──> Execution Plans (DB: trades table, status=PENDING_APPROVAL)
                  │
                  │ Determines: order type, position sizing, stop-loss, take-profit
                  │ Auto-approve if notional <= threshold, else require human approval
                  v
           [HUMAN APPROVAL GATE] ──> Dashboard shows pending trades for review
                  │
                  v
           Trade Monitor Agent ──> Active Trades (status=OPEN)
                  │
                  │ Monitors: P&L, stop-loss, take-profit, holding period
                  │ Generates: alerts for significant events
                  v
           Portfolio Loop Agents ──> Rebalancing proposals, risk reports
```

### 3. LLM Routing

The system uses a multi-provider LLM strategy with task-based routing:

```
Task Type          Primary Provider     Fallback
─────────          ────────────────     ────────
reasoning          Anthropic (Claude)   OpenAI (GPT-4o)
analysis           Anthropic (Claude)   OpenAI (GPT-4o)
risk_assessment    Anthropic (Claude)   OpenAI (GPT-4o)
strategy           Anthropic (Claude)   OpenAI (GPT-4o)
extraction         OpenAI (GPT-4o)      Anthropic (Claude)
summarization      OpenAI (GPT-4o)      Anthropic (Claude)
classification     OpenAI (GPT-4o)      Anthropic (Claude)
data_formatting    OpenAI (GPT-4o)      Anthropic (Claude)
```

Every LLM call is logged to the `agent_logs` table with token usage (`{prompt_tokens, completion_tokens, total_tokens, cost}`).

### 4. Data Storage

```
PostgreSQL (persistent)          Redis (cache)                    In-Memory (ephemeral)
───────────────────────          ─────────────                    ─────────────────────
ideas table                      Market quotes (30s TTL)          Agent runtime status
trades table                     Price history (5min TTL)         Loop running state
portfolios table                 Fundamentals (1hr TTL)           Pending approvals queue
positions table                  Options chains (10min TTL)       Alert queue
knowledge_entries table          Screen results (15min TTL)       WebSocket connections
market_outlooks table
agent_logs table (with tokens)
agent_tasks table
rl_experiences table
rl_episodes table
```

### 5. Frontend Data Consumption

```
Frontend (Next.js)                        Backend (FastAPI)
──────────────────                        ────────────────
Dashboard page  ──GET /api/portfolio──>   Reads from PostgreSQL (portfolios, positions tables)
                ──GET /api/agents/status──> Reads from in-memory agent state
                ──GET /api/alerts──>       Reads from in-memory alert queue
                ──Toggle controls──>       POST /api/agents/idea-loop/start|stop
                                           POST /api/agents/portfolio-loop/start|stop

Asset Detail    ──GET /api/market-data/info/{sym}──>     yfinance (via asyncio.to_thread)
                ──GET /api/market-data/news/{sym}──>     RSS feeds (via aiohttp + feedparser)
                ──GET /api/market-data/social/{sym}──>   Reddit JSON API (via aiohttp)
                ──GET /api/market-data/summary/{sym}──>  Rule-based analysis on yfinance data

Ideas page      ──GET /api/ideas──>       PostgreSQL (ideas table)
Portfolio page  ──GET /api/portfolio──>   PostgreSQL (portfolios + positions tables)
Trades page     ──GET /api/trades──>      PostgreSQL (trades table)
Knowledge page  ──GET /api/knowledge──>   PostgreSQL (knowledge_entries + market_outlooks)

WebSocket       ──ws://host/ws/live──>    Real-time push: idea updates, trade alerts, agent status
```

### 6. Startup Sequence

When the backend starts:

1. **Database initialization**: SQLAlchemy creates all tables if they don't exist (`init_db()`)
2. **Auto-seed**: If no active portfolio found, seeds database with:
   - $1M paper portfolio with default preferences
   - 5 sample ideas (NVDA, BTC-USD, TLT, ETH-USD, SPY)
   - 3 sample trades
   - 3 knowledge entries
   - 3 market outlooks
3. **API server starts**: FastAPI with 9 route modules + WebSocket + CORS
4. **Ready for connections**: Frontend connects, fetches initial data via REST

---

## Database Schema

### 10 PostgreSQL Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| **ideas** | Investment ideas pipeline | title, thesis, tickers (JSON), status (GENERATED->VALIDATED->EXECUTING->MONITORING->CLOSED), confidence_score, timeframe, source |
| **trades** | Trade execution & tracking | idea_id (FK), direction (LONG/SHORT), instrument_type, entry_price, exit_price, quantity, stop_loss, take_profit, pnl, status (PLANNED->PENDING_APPROVAL->OPEN->CLOSED) |
| **portfolios** | Portfolio state | name, total_value, cash, invested, pnl, preferences (JSON), status (ACTIVE/PAUSED) |
| **positions** | Current holdings | portfolio_id (FK), ticker, direction, quantity, avg_entry_price, current_price, market_value, pnl, weight |
| **knowledge_entries** | Market intelligence | title, content, category (FUNDAMENTAL/TECHNICAL/MACRO/EVENT), layer (LONG_TERM/MID_TERM/SHORT_TERM), tickers (JSON), embedding (JSON for vector search) |
| **market_outlooks** | Directional views | layer, asset_class, outlook (BULLISH/NEUTRAL/BEARISH), confidence, rationale, key_drivers (JSON) |
| **agent_logs** | Agent execution logs | agent_name, action, status, duration_ms, llm_provider, llm_model, token_usage (JSON: prompt_tokens, completion_tokens, cost) |
| **agent_tasks** | Task queue | task_type, status, priority, payload (JSON), assigned_agent, parent_task_id (hierarchical) |
| **rl_experiences** | RL training data | episode_id, step, agent_name, state (JSON), action (JSON), reward, next_state (JSON), done |
| **rl_episodes** | RL episode summaries | agent_name, total_reward, total_steps, outcome (JSON) |

All tables have auto-generated UUID `id`, `created_at`, and `updated_at` timestamps.

---

## API Keys & Configuration

### Where to Add Keys

All configuration is in the `.env` file at the project root. Copy `.env.example` and fill in your keys:

```bash
cp .env.example .env
```

### Required Keys (for agent loops to function)

You need **at least one** LLM provider key for agents to work:

| Variable | Where to Get It | Cost | Purpose |
|----------|----------------|------|---------|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Pay-per-token (~$2.50/$10 per 1M input/output tokens for GPT-4o) | Extraction, summarization, classification tasks |
| `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | Pay-per-token (~$3/$15 per 1M input/output tokens for Claude Sonnet) | Reasoning, analysis, risk assessment tasks |

**Token cost estimate**: A single idea loop iteration (generate + validate + execute) uses roughly 5,000-15,000 tokens. At GPT-4o rates, that's ~$0.01-0.05 per iteration. The system controls toggles on the dashboard let you start/stop loops to manage costs.

### Optional Keys (enhance data quality)

| Variable | Where to Get It | Free Tier | Purpose |
|----------|----------------|-----------|---------|
| `ALPHA_VANTAGE_API_KEY` | [alphavantage.co/support/#api-key](https://www.alphavantage.co/support/#api-key) | 25 requests/day | Enhanced fundamentals, news sentiment |
| `REDDIT_CLIENT_ID` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (create "script" app) | 100 req/min | Authenticated Reddit API (higher limits) |
| `REDDIT_CLIENT_SECRET` | Same as above | -- | Required with REDDIT_CLIENT_ID |
| `NEWS_API_KEY` | [newsapi.org/register](https://newsapi.org/register) | 100 req/day (localhost only) | Additional news source |

### What Works Without Any Optional Keys

The system is designed to work without optional API keys:

- **Market data**: yfinance requires no API key (free, scrapes Yahoo Finance)
- **News**: RSS feeds are free, no authentication needed
- **Social**: Reddit public JSON API works without OAuth (rate-limited to ~10 req/min)
- **Asset detail page**: All 4 endpoints (info, news, social, summary) work without keys

### Configuration Reference

```bash
# === LLM Providers (need at least one) ===
OPENAI_API_KEY=sk-...                              # OpenAI API key
ANTHROPIC_API_KEY=sk-ant-...                        # Anthropic API key
DEFAULT_LLM_PROVIDER=openai                         # Primary provider: "openai" | "anthropic"
OPENAI_MODEL=gpt-4o                                 # OpenAI model
ANTHROPIC_MODEL=claude-sonnet-4-20250514             # Anthropic model

# === Database (auto-configured on Railway/Render) ===
DATABASE_URL=postgresql+asyncpg://overture:overture@localhost:5432/overture
REDIS_URL=redis://localhost:6379/0

# === Optional Data Source Keys ===
ALPHA_VANTAGE_API_KEY=                              # Optional
REDDIT_CLIENT_ID=                                   # Optional
REDDIT_CLIENT_SECRET=                               # Optional
NEWS_API_KEY=                                       # Optional

# === Application ===
APP_ENV=development                                 # development | production
APP_DEBUG=true                                      # Enable debug logging
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_URL=http://localhost:3000                  # For CORS

# === RL Training ===
RL_REPLAY_BUFFER_SIZE=10000
RL_BATCH_SIZE=64
RL_LEARNING_RATE=0.001
```

### Frontend Environment

Set these in Vercel (production) or in `frontend/.env.local` (development):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000            # Backend API URL
NEXT_PUBLIC_WS_URL=ws://localhost:8000               # WebSocket URL (auto-derived if not set)
```

---

## Data Sources & External APIs

### Current Data Sources (all free, no keys required)

| Source | Library | Data Provided | Limitations |
|--------|---------|---------------|-------------|
| **Yahoo Finance** | `yfinance` | Prices (equities, futures, crypto), fundamentals (P/E, market cap, EPS, beta, etc.), OHLCV history, options chains | Unofficial scraper; rate limits (~360 req/hr); can break without notice; IP blocking on cloud deployments |
| **RSS Feeds** (8 sources) | `aiohttp` + `feedparser` | Financial news from Reuters, CNBC, Bloomberg, FT, MarketWatch, Yahoo Finance, Seeking Alpha, Investing.com | Headlines + summaries only; no sentiment scoring; no ticker tagging (parsed via regex) |
| **Reddit** (5 subreddits) | `aiohttp` (JSON API) | Posts from r/wallstreetbets, r/investing, r/stocks, r/options, r/economics | ~10 req/min unauthenticated; aggressive bot detection; no historical search |

### Recommended Upgrades by Budget

#### Development / Prototyping ($0/month)

Current setup works. Use yfinance for prices, RSS for news, Reddit public API for social. Add free API keys for enhanced coverage:

| Action | Provider | Cost |
|--------|----------|------|
| Sign up for Alpha Vantage free key | [alphavantage.co](https://www.alphavantage.co/support/#api-key) | $0 (25 req/day) |
| Register Reddit OAuth app | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) | $0 (100 req/min) |
| Sign up for Finnhub free key | [finnhub.io](https://finnhub.io) | $0 (60 req/min -- generous free tier for news + fundamentals) |

#### Small Fund Value Stack ($100-130/month)

Replace yfinance with reliable paid APIs:

| Need | Provider | Cost | Why |
|------|----------|------|-----|
| Equities + Crypto (real-time) | [Twelve Data](https://twelvedata.com) Grow | $29/mo | 55 calls/min, unlimited daily, covers equities + crypto + futures |
| Historical + backup data | [Tiingo](https://tiingo.com) Power | $30/mo | 10,000 req/hr, 30yr history, clean EOD data |
| Fundamentals + News Sentiment | [Alpha Vantage](https://alphavantage.co) Premium | $49.99/mo | 75 req/min, AI-powered news sentiment scoring |
| Social Sentiment | [Quiver Quantitative](https://api.quiverquant.com) Hobbyist | $10/mo | Pre-processed Reddit/StockTwits sentiment, no NLP needed |
| Reddit (authenticated) | Reddit OAuth | $0 | 100 req/min with free app registration |

**Total: ~$119/month** -- reliable data for 40+ tickers.

#### Production Stack ($300-500/month)

For serious deployment with exchange-quality data:

| Need | Provider | Cost | Why |
|------|----------|------|-----|
| Equities + Crypto (real-time) | [Polygon.io](https://polygon.io) Advanced Stocks+Crypto | $249/mo | 20ms latency, WebSocket streaming, unlimited calls |
| Futures | [Twelve Data](https://twelvedata.com) Pro | $99/mo | Full WebSocket, 610+ calls/min |
| Fundamentals + News | [Alpha Vantage](https://alphavantage.co) Premium | $149.99/mo | 300 req/min, real-time, all features |
| Social Sentiment | [Quiver Quantitative](https://api.quiverquant.com) Trader | $75/mo | Full Tier 1 + Tier 2 data (Reddit, StockTwits, Twitter aggregated) |

**Total: ~$573/month** -- production-grade data.

### What NOT to Buy

| Provider | Reason |
|----------|--------|
| **Twitter/X API** | Basic tier ($100/mo) gives only 10,000 tweets/month with 7-day search -- too little for sentiment analysis. Pro tier is $5,000/mo. Use Quiver Quantitative instead for aggregated social sentiment. |
| **Bloomberg/Reuters** | $22,000-32,000/year per seat. Enterprise-grade, far beyond project needs. |
| **NewsAPI.org** | Free tier is localhost-only with 24hr delay. Paid starts at $449/mo. Use Finnhub or Alpha Vantage news instead. |
| **IEX Cloud** | Shut down August 2024. No longer available. |
| **StockTwits API** | Not accepting new registrations. Suspended indefinitely. |

---

## Dashboard Pages

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/` | Portfolio summary, alerts, agent status, system controls (loop toggles) |
| **Ideas** | `/ideas` | Idea pipeline (generated -> validated -> executing -> monitoring), filters |
| **Ideas Preferences** | `/ideas/preferences` | Alpha generation settings, information sources, manual idea input |
| **Portfolio** | `/portfolio` | Allocation chart, positions table, risk metrics, market outlook |
| **Portfolio Preferences** | `/portfolio/preferences` | Goals, allocation targets, risk parameters, constraints, rebalance schedule |
| **Asset Detail** | `/asset/[symbol]` | Single ticker view: fundamentals, news feed, Reddit social posts, AI summary |
| **Trades** | `/trades` | Pending approvals, active trades with P&L, trade history |
| **Agents** | `/agents` | Dual-loop visualization, agent status, activity log, start/stop controls |
| **Knowledge** | `/knowledge` | 3-layer knowledge view, source rankings, educational content |
| **RL Training** | `/rl` | Reward charts, experience buffer stats, training insights |

---

## API Reference

### Core Resources

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check (status, version, database) |

### Ideas

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/ideas` | List ideas (filterable by status, asset_class, source) |
| `GET` | `/api/ideas/{id}` | Get single idea |
| `POST` | `/api/ideas` | Create idea manually |
| `PUT` | `/api/ideas/{id}` | Update idea |
| `DELETE` | `/api/ideas/{id}` | Delete idea |
| `POST` | `/api/ideas/generate` | Trigger AI idea generation |
| `POST` | `/api/ideas/{id}/validate` | Validate an idea |
| `POST` | `/api/ideas/{id}/execute` | Create execution plan |
| `GET` | `/api/ideas/stats` | Idea statistics (by status, source, avg conviction) |

### Portfolio

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/portfolio` | Portfolio overview (value, cash, P&L) |
| `GET` | `/api/portfolio/positions` | All positions |
| `GET` | `/api/portfolio/risk` | Risk metrics (VaR, volatility, beta, Sharpe) |
| `GET` | `/api/portfolio/performance` | Performance metrics |
| `GET` | `/api/portfolio/allocation` | Allocation breakdown (by asset class, sector, geography) |
| `POST` | `/api/portfolio/rebalance` | Trigger rebalancing |
| `GET` | `/api/portfolio/preferences` | Get portfolio preferences |
| `PUT` | `/api/portfolio/preferences` | Update portfolio preferences |

### Trades

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/trades` | List trades (filterable) |
| `GET` | `/api/trades/{id}` | Get single trade |
| `GET` | `/api/trades/pending` | Pending trades summary |
| `GET` | `/api/trades/active` | Active trades summary |
| `POST` | `/api/trades/{id}/approve` | Approve a trade plan |
| `POST` | `/api/trades/{id}/reject` | Reject a trade plan |
| `POST` | `/api/trades/{id}/adjust` | Adjust trade parameters |
| `POST` | `/api/trades/{id}/close` | Close a trade |

### Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/agents/status` | All agent statuses + loop states |
| `GET` | `/api/agents/logs` | Agent activity logs |
| `POST` | `/api/agents/idea-loop/start` | Start idea generation loop |
| `POST` | `/api/agents/idea-loop/stop` | Stop idea generation loop |
| `POST` | `/api/agents/portfolio-loop/start` | Start portfolio management loop |
| `POST` | `/api/agents/portfolio-loop/stop` | Stop portfolio management loop |

### Knowledge

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/knowledge` | List knowledge entries (filterable by category, layer) |
| `GET` | `/api/knowledge/{id}` | Get single entry |
| `POST` | `/api/knowledge` | Create knowledge entry |
| `GET` | `/api/knowledge/outlook` | Market outlook (3 layers) |
| `PUT` | `/api/knowledge/outlook/{layer}` | Update outlook for a layer |
| `GET` | `/api/knowledge/sources` | Source credibility rankings |
| `GET` | `/api/knowledge/education` | Educational content |
| `POST` | `/api/knowledge/data-pipeline/trigger` | Trigger data pipeline refresh |

### Market Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/market-data/price/{symbol}` | Current price snapshot |
| `GET` | `/api/market-data/prices?symbols=X,Y` | Batch price snapshots |
| `GET` | `/api/market-data/history/{symbol}` | OHLCV history (period, interval params) |
| `GET` | `/api/market-data/watchlist/{class}` | Predefined watchlist prices (equities/futures/crypto) |
| `GET` | `/api/market-data/watchlists` | All watchlist tickers |
| `GET` | `/api/market-data/info/{symbol}` | Comprehensive asset info (25+ fields) |
| `GET` | `/api/market-data/news/{symbol}` | Latest news from RSS feeds |
| `GET` | `/api/market-data/social/{symbol}` | Reddit posts mentioning ticker |
| `GET` | `/api/market-data/summary/{symbol}` | AI-generated market analysis & outlook |

### Other

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/alerts` | Active alerts |
| `POST` | `/api/alerts/{id}/dismiss` | Dismiss alert |
| `POST` | `/api/alerts/dismiss-all` | Dismiss all alerts |
| `POST` | `/api/seed` | Seed database with sample data |
| `GET` | `/api/rl/stats` | RL training stats |
| `GET` | `/api/rl/episodes/{agent}` | RL episodes for an agent |
| `GET` | `/api/rl/replay-buffer/stats` | Replay buffer statistics |
| `POST` | `/api/rl/train/{agent}` | Start RL training |
| `WS` | `/ws/live` | Real-time updates (ideas, trades, alerts, agents) |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose (for PostgreSQL + Redis)

### Step 1: Clone and Configure

```bash
git clone https://github.com/clairex888/Overture.git
cd Overture
cp .env.example .env
```

Edit `.env` with your API keys. At minimum, add one LLM key:

```bash
# Pick one or both:
OPENAI_API_KEY=sk-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### Step 2: Start Database Infrastructure

```bash
docker compose up -d postgres redis
```

### Step 3: Run the Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn src.main:app --reload --port 8000
```

On first start, the database auto-seeds with a $1M paper portfolio and sample data.

### Step 4: Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Or Run Everything with Docker

```bash
docker compose up --build
```

---

## Deploying to Production

### Frontend -> Vercel

1. Import in [Vercel](https://vercel.com/new), set **Root Directory** to `frontend`
2. Set environment variables:
   ```
   NEXT_PUBLIC_API_URL=https://your-backend-url.com
   NEXT_PUBLIC_WS_URL=wss://your-backend-url.com
   ```
3. Deploy (auto-builds on push)

### Backend -> Railway (recommended)

1. Go to [railway.app](https://railway.app), create a new project
2. Add **PostgreSQL** and **Redis** services (one-click provisioning)
3. Add a **new service** from your GitHub repo:
   - Root Directory: `backend`
   - Start Command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
4. Add all environment variables from `.env.example`
   - Railway auto-provides `DATABASE_URL` and `REDIS_URL`
   - Set `FRONTEND_URL` to your Vercel URL for CORS
   - Add your LLM API keys

### Backend -> Render (alternative)

1. Create a new **Web Service** on [render.com](https://render.com)
2. Connect your repo, set root to `backend`
3. Build command: `pip install -e .`
4. Start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL and Redis managed services
6. Set environment variables

---

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), LangGraph, LangChain
- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts
- **Database:** PostgreSQL 16 (persistent), Redis 7 (cache with TTL)
- **LLM:** OpenAI GPT-4o + Anthropic Claude Sonnet (multi-provider with task-based routing + fallback)
- **Orchestration:** LangGraph StateGraphs for idea & portfolio loops
- **Market Data:** Yahoo Finance (yfinance), extensible to Polygon.io / Twelve Data / Alpha Vantage
- **News:** RSS feeds (8 sources), extensible to Finnhub / Alpha Vantage News Sentiment
- **Social:** Reddit public API, extensible to Quiver Quantitative / Reddit OAuth

## License

Private. All rights reserved.
