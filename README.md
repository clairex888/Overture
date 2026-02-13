# Overture

**AI-native multi-agent hedge fund system.** Instead of human-in-the-loop at every step, Overture puts the human as the architect and conductor — AI agents sprint autonomously through the full investment lifecycle while you monitor from altitude.

## How It Works

Two autonomous agent loops run continuously, coordinated by a master orchestrator:

```
┌─────────────────────────────────────────────────────────────────┐
│                        IDEA LOOP                                │
│                                                                 │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐│
│   │  Generate  │───▶│  Validate  │───▶│  Execute   │───▶│Monitor ││
│   │           │    │           │    │           │    │        ││
│   │ News      │    │ Backtest  │    │ Sizing    │    │ P&L    ││
│   │ Screens   │    │ Reasoning │    │ Timing    │    │ Thesis ││
│   │ Social    │    │ Source    │    │ Stops     │    │ Alerts ││
│   │ Anomalies │    │ Risk      │    │ Instrument│    │ Exit   ││
│   └───────────┘    └───────────┘    └───────────┘    └────────┘│
│        ▲                                                  │     │
│        └──────────────────────────────────────────────────┘     │
└────────────────────────────┬────────────────────────────────────┘
                             │ ▲
                    trades ───┘ └─── risk limits, approvals
                             │ ▲
┌────────────────────────────┴────────────────────────────────────┐
│                      PORTFOLIO LOOP                             │
│                                                                 │
│   ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌────────┐│
│   │  Assess   │───▶│ Construct  │───▶│   Risk    │───▶│Rebal.  ││
│   │           │    │           │    │  Monitor  │    │        ││
│   │ Allocation│    │ Targets   │    │ VaR       │    │ Drift  ││
│   │ Drift     │    │ Views     │    │ Stress    │    │ Trades ││
│   │ Exposure  │    │ Optimize  │    │ Alerts    │    │ Timing ││
│   └───────────┘    └───────────┘    └───────────┘    └────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Human approval gates** are built in: trade execution plans and rebalancing proposals require your sign-off. You adjust, approve, or reject — the agents handle everything else.

## Examples

**Silver flash crash:** Silver drops 10-sigma in a day → Asset monitor triggers idea → Validator backtests buy-the-dip at 5/10-sigma thresholds → Historical win rate is 87% → Executor builds trade plan (SLV ETF, sized for portfolio, stop at -3%) → You approve in one click → Monitor watches the position → Alerts you when target hit.

**TSLA earnings risk:** Earnings approaching → Generator flags deteriorating delivery numbers → Validator models downside scenarios → Executor proposes put spread sized to portfolio → You review and approve → Monitor tracks through earnings release.

**Tariff shock:** Breaking news on new tariffs → Data pipeline ingests instantly → Generator identifies exposed sectors → Validator cross-references historical tariff responses → Executor builds hedging trades → You get an alert with a ready-to-go plan.

## Architecture

```
├── backend/                      Python / FastAPI
│   ├── src/
│   │   ├── agents/
│   │   │   ├── llm/              Multi-provider LLM (OpenAI + Anthropic)
│   │   │   ├── orchestrator/     LangGraph loops + coordinator
│   │   │   ├── idea/             Generator, Validator, Executor, Monitor
│   │   │   ├── portfolio/        Constructor, Risk Manager, Rebalancer, Monitor
│   │   │   ├── knowledge/        Data Curator, Educator, Librarian
│   │   │   └── context/          Investment best practices framework
│   │   ├── data/                 Yahoo Finance, RSS, Reddit, social, pipeline
│   │   ├── models/               SQLAlchemy (Postgres): ideas, trades, portfolio, knowledge, RL
│   │   ├── services/             Backtest, valuation (DCF/comps), risk, screening, source ranking
│   │   ├── rl/                   RL environment, state, actions, rewards, replay buffer, trainer
│   │   └── api/                  REST routes + WebSocket real-time
│   └── tests/
├── frontend/                     Next.js 14 + Tailwind (dark theme)
│   └── src/
│       ├── app/                  7 dashboard pages
│       ├── components/           Sidebar, StatCard, AlertFeed, charts
│       ├── lib/                  API client, WebSocket client
│       └── types/                TypeScript types
├── docker-compose.yml            PostgreSQL 16 + Redis 7
└── .env.example                  Configuration template
```

### Knowledge Layer (3 tiers)

| Layer | Purpose | Update Frequency |
|-------|---------|-----------------|
| **Long-term** | Foundational: macro regimes, structural trends, sector dynamics | Weekly |
| **Mid-term** | Tactical: earnings cycles, policy shifts, sector rotation | Daily |
| **Short-term** | Immediate: breaking news, price anomalies, event catalysts | Continuous |

Each layer maintains its own market outlook (bullish/neutral/bearish per asset class), which guides portfolio construction and idea filtering.

### RL Training

Agents learn from their own investing experience:
- **Experience replay buffer** stores every decision and outcome
- **Reward functions** are calibrated per agent role (idea quality, execution quality, risk management)
- **Training loop** analyzes patterns, generates insights, and adjusts agent behavior
- Designed for future policy gradient / Q-learning upgrades

### Supported Asset Classes

Equities (US, China, global) · Bonds · Rates · Derivatives · Commodities · ETFs/Mutual Funds · Prediction Markets

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose (for PostgreSQL + Redis)

### 1. Clone and configure

```bash
git clone https://github.com/clairex888/Overture.git
cd Overture
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis
```

### 3. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn src.main:app --reload --port 8000
```

### 4. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — the dashboard connects to the backend at port 8000.

### Or run everything with Docker

```bash
docker compose up --build
```

## Deploying to Production

### Frontend → Vercel

1. **Import in Vercel:**
   - Go to [vercel.com/new](https://vercel.com/new)
   - Import the `Overture` repository
   - Set **Root Directory** to `frontend`
   - Framework preset will auto-detect **Next.js**

2. **Set environment variables** in Vercel project settings:
   ```
   NEXT_PUBLIC_API_URL=https://your-backend-url.com
   NEXT_PUBLIC_WS_URL=wss://your-backend-url.com
   ```

3. **Deploy.** Vercel builds and deploys automatically on every push.

### Backend → Railway (recommended)

1. Go to [railway.app](https://railway.app), create a new project
2. Add **PostgreSQL** and **Redis** services (one-click)
3. Add a **new service** from your GitHub repo:
   - Set **Root Directory** to `backend`
   - Set **Start Command** to `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables from `.env.example` (Railway provides `DATABASE_URL` and `REDIS_URL` automatically)
5. Set `FRONTEND_URL` to your Vercel deployment URL for CORS

### Backend → Render (alternative)

1. Create a new **Web Service** on [render.com](https://render.com)
2. Connect your repo, set root to `backend`
3. Build command: `pip install -e .`
4. Start command: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL and Redis as managed services
6. Set environment variables accordingly

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Dashboard** | Portfolio summary, alerts, agent status, recent ideas |
| **Ideas** | Idea pipeline (generated → validated → executing → monitoring), filters |
| **Portfolio** | Allocation chart, positions table, risk metrics, market outlook |
| **Trades** | Pending approvals, active trades with P&L, trade history |
| **Agents** | Dual-loop visualization, agent status, activity log, start/stop controls |
| **Knowledge** | 3-layer knowledge view, source rankings, educational content |
| **RL Training** | Reward charts, experience buffer stats, training insights |

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/ideas` | List ideas (filterable) |
| `POST` | `/api/ideas/generate` | Trigger idea generation |
| `POST` | `/api/ideas/{id}/validate` | Validate an idea |
| `GET` | `/api/portfolio` | Portfolio overview |
| `GET` | `/api/portfolio/risk` | Risk metrics |
| `GET` | `/api/trades` | List trades |
| `POST` | `/api/trades/{id}/approve` | Approve a trade plan |
| `GET` | `/api/agents/status` | All agent statuses |
| `POST` | `/api/agents/idea-loop/start` | Start idea loop |
| `POST` | `/api/agents/portfolio-loop/start` | Start portfolio loop |
| `GET` | `/api/knowledge` | Knowledge entries |
| `GET` | `/api/knowledge/outlook` | Market outlook |
| `WS` | `/ws/live` | Real-time updates (ideas, trades, alerts, agents) |

## Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 (async), LangGraph, LangChain
- **Frontend:** Next.js 14, React 18, TypeScript, Tailwind CSS, Recharts
- **Database:** PostgreSQL 16, Redis 7
- **LLM:** OpenAI GPT-4o + Anthropic Claude (multi-provider with smart routing)
- **Data:** Yahoo Finance, RSS feeds, Reddit API, extensible connector system

## License

Private. All rights reserved.
