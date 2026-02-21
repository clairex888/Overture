# Overture Platform - Comprehensive Optimization Plan

## Architecture Review Summary

After a deep review of every file in both backend and frontend, here is the full
picture of what's real, what's broken, what's hardcoded, and the strategic plan
to fix it all — organized into 4 priority phases.

---

## PHASE 1: Dashboard Redesign + Market Outlook Migration
**Goal:** Make the dashboard a real strategic command center across all portfolios.

### 1A. Dashboard → Multi-Portfolio Strategic View
**Current state:** Dashboard shows single-portfolio stats, a hardcoded chart
(fake Jan–Apr growth data in `page.tsx:33-52`), and basic agent status cards.

**Changes:**
- **`frontend/src/app/page.tsx`** — Complete rewrite:
  - Replace hardcoded `portfolioHistory` array with real data from
    `portfolioAPI.list()` (already returns all portfolios with live PnL)
  - Add aggregate stats card row: Total AUM across all portfolios, aggregate
    PnL, aggregate day PnL, total positions count, overall risk score
  - Add portfolio cards grid: each portfolio shows name, value, PnL, position
    count, status badge — clicking navigates to `/portfolio?id=X`
  - Move the "Portfolio Value" chart section to show real aggregate value
    (requires new backend endpoint — see below)
  - Add "Key Risks & Exposure" section: pull from `portfolioAPI.risk()` for
    each portfolio, aggregate top concentration risks, sector exposure heatmap
  - Add "Opportunities" section: show top validated ideas not yet executed
    (filter ideas with status=validated)
  - Keep system controls (loop toggles, data pipeline) at bottom

- **`backend/src/api/routes/portfolio.py`** — Add new endpoints:
  - `GET /api/portfolio/aggregate` — returns combined AUM, PnL, risk across
    all user portfolios (iterates `list_portfolios` logic, sums values)
  - `GET /api/portfolio/history?days=90` — returns daily portfolio value
    snapshots. Implementation: create a new `PortfolioSnapshot` model that
    records daily values via a background task or on each price refresh

- **`backend/src/models/portfolio.py`** — Add `PortfolioSnapshot` model:
  - Fields: portfolio_id, date, total_value, invested, cash, pnl
  - Populated by the price cache refresh loop (already runs every 30 min)

### 1B. Move Market Outlook to Dashboard
**Current state:** Market outlook sits under the positions table in the portfolio
page (`portfolio/page.tsx:1242`). User correctly identified this is misplaced.

**Changes:**
- **`frontend/src/app/page.tsx`** — Add Market Outlook section between the
  portfolio cards and the agent status section. Fetch from
  `knowledgeAPI.outlook()`. Display 3-column layout (long/mid/short term) with
  sentiment icons, confidence bars, key factors, and summary text.
- **`frontend/src/app/portfolio/page.tsx`** — Remove the Market Outlook section
  (lines 1242–1290). The portfolio page should focus on positions, allocation,
  risk, and performance for that specific portfolio.

### 1C. Dashboard News Feed
- Add a "Market News" card to the dashboard that pulls from the data pipeline's
  `NewsCollector` results. Show the 5 most recent headlines with source badges.
- Backend: Add `GET /api/market-data/latest-news?limit=5` endpoint that returns
  cached news from the most recent `DataPipeline.collect()` call.

---

## PHASE 2: Agents Page — Real Status + Working Controls
**Goal:** Make agent status reflect actual work, connect start/stop to real loops.

### 2A. Agent Status Connection Audit
**Current state:** The agents page (`agents/page.tsx`) fetches from
`GET /api/agents/status` which calls `agent_engine.get_agent_statuses()`. This
returns 7 agents with status based on whether their parent loop is running. The
status IS connected to the real `AgentEngine` singleton. BUT:

- **Problem 1:** Agent names in the backend (`idea_generation`, `idea_validation`,
  etc.) don't match the `agentNames` in the frontend's stage definitions
  (`idea_generator`, `idea_validator`, etc.) → `resolveStageStatus()` always
  returns `idle` because the names never match.
- **Problem 2:** `run_count` and `error_count` are derived from loop iteration
  count, not per-agent task counts. All agents in the same loop show the same
  number.
- **Problem 3:** `uptime_seconds` is always 0 (hardcoded in `agents.py:109`).
- **Problem 4:** `current_task` is always `None`.

**Changes:**
- **`backend/src/agents/engine.py`** — Fix `get_agent_statuses()`:
  - Track per-agent task counts (separate counters for generators, validators,
    executor, monitor, portfolio, risk, knowledge)
  - Track per-agent last run time and current task description
  - Compute real uptime from `_started_at` timestamps
  - Record error counts per agent when exceptions occur in loops

- **`backend/src/api/routes/agents.py`** — Fix name mapping:
  - Change agent keys to match frontend expectations OR update frontend stage
    definitions to match backend keys. I'll align both to a canonical set.

- **`frontend/src/app/agents/page.tsx`** — Fix stage definitions:
  - Update `ideaLoopStageDefinitions[].agentNames` to match backend keys
  - Update `getAgentType()` mapping to match

### 2B. Start/Stop Buttons — Already Working
The start/stop buttons DO work. They call `agentsAPI.startIdeaLoop()` /
`agentsAPI.stopIdeaLoop()` which hit `POST /api/agents/idea-loop/start` /
`stop`. These call `agent_engine.start_idea_loop()` / `stop_idea_loop()` which
create/cancel real `asyncio.Task` objects. **No fix needed** — the buttons work,
the issue is that the STATUS display is broken (fixed in 2A).

### 2C. Activity Log — Connect to Real Agent Messages
**Current state:** `GET /api/agents/logs` returns `agent_engine.get_logs()` which
is `self._agent_messages[-50:]`. These messages ARE populated when the loops run
(each node appends to `agent_messages`). BUT they're empty when loops haven't run.

**Changes:**
- **`backend/src/agents/engine.py`** — Also log messages during single-shot
  operations (`generate_ideas_once`, `validate_ideas_once`) so the activity log
  shows data even without the autonomous loop running.
- Persist agent messages to DB (new `AgentLog` model) so they survive restarts.

---

## PHASE 3: Knowledge Page — Fix Upload + Dynamic Sources
**Goal:** Working upload, viewable documents, dynamic source credibility.

### 3A. Fix Knowledge Upload
**Current state:** The upload endpoint (`POST /api/knowledge/upload`) requires
authentication (`user: User = Depends(get_current_user)`). The frontend's
`knowledgeAPI.upload()` correctly sends the auth token via FormData. The backend
extracts text from PDF/TXT/MD/CSV files. **The code looks correct.**

**Likely issue:** The upload may fail silently if:
1. User is not authenticated (no token → 401, but frontend may swallow error)
2. The `get_current_user` dependency fails

**Changes:**
- **`frontend/src/app/knowledge/page.tsx`** — Improve error display:
  - Show the actual error message from the API (currently `setUploadError` is
    set but may not surface auth errors clearly)
  - Add auth check: if user is not logged in, show "Please log in to upload"
  - After successful upload, scroll to the new entry

- **`backend/src/api/routes/knowledge.py`** — Make upload work without auth for
  testing (add `get_optional_user` fallback), or ensure the auth flow is solid.

### 3B. Document Viewing / Download
**Current state:** Knowledge entries show content preview (first 500 chars) but
no way to view the full document or download the original file. Files are stored
as extracted text in `KnowledgeEntry.content`, not as raw files.

**Changes:**
- **`frontend/src/app/knowledge/page.tsx`** — Add document viewer:
  - Click on an entry to expand and show FULL content in a modal/side panel
  - Add a "View Full" button that opens a clean reading view
  - For entries with `file_name`, show a badge with the file type
  - Add copy-to-clipboard button for the content

- **`backend/src/api/routes/knowledge.py`** — The `GET /{entry_id}` endpoint
  already returns the full content. No backend change needed for viewing.
  For download of original files, we'd need to store raw bytes (future — not
  in this phase since files are already text-extracted).

### 3C. Confirm Knowledge Is Used by Agents
**Current state:** The RAG pipeline (`services/knowledge_rag.py`) IS connected.
`agent_engine._get_knowledge_context()` queries the DB for relevant entries and
passes them to agents via `AgentContext.knowledge_context`. This works.

**Changes:**
- **`frontend/src/app/knowledge/page.tsx`** — Add "Used by agents" indicator:
  - Show which entries were recently retrieved by agents (requires tracking)
  - Add a small "Agent Usage" badge showing retrieval count

- **`backend/src/services/knowledge_rag.py`** — Add retrieval tracking:
  - When `get_context()` returns entries, increment a usage counter in metadata
  - Add `GET /api/knowledge/{id}/usage` endpoint to check retrieval stats

### 3D. Dynamic Source Credibility
**Current state:** Source credibility rankings are 100% hardcoded in
`_sources_store` (knowledge.py:214-221). The `SourceRankingService` exists in
`services/source_ranking.py` with a full Bayesian update system, but it's
**never called** from anywhere.

**Changes:**
- **`backend/src/api/routes/knowledge.py`** — Replace hardcoded `_sources_store`
  with dynamic data:
  - `GET /api/knowledge/sources` should aggregate actual sources from
    `KnowledgeEntry` records: count entries per source, compute average
    credibility score, track last fetch time
  - Also incorporate data from `SourceRankingService` if available

- **`backend/src/agents/engine.py`** — Wire source ranking into the validation
  feedback loop:
  - After an idea's trade closes (P&L known), call
    `source_ranking_service.update_score(source, idea_id, outcome)`
  - This creates the feedback loop: source → idea → trade → P&L → credibility

- **`frontend/src/app/knowledge/page.tsx`** — Add dynamic indicators:
  - Show "Dynamic" vs "Default" badge next to credibility scores
  - Show trend arrow (improving/declining) based on recent score changes
  - Add "Add Source" button to register new data sources

---

## PHASE 4: Cross-Cutting Fixes
**Goal:** Fix remaining broken flows and improve overall reliability.

### 4A. Portfolio History Tracking (for Dashboard Chart)
- Add `PortfolioSnapshot` model and daily recording
- Price cache refresh loop records snapshots after each refresh
- Dashboard chart uses real historical data instead of hardcoded array

### 4B. Agent Log Persistence
- New `AgentLog` model (timestamp, agent_name, action, status, details, duration)
- Persist logs to DB during loop iterations and single-shot operations
- Agents page shows real historical activity instead of in-memory buffer

### 4C. Risk Metrics Improvement
- Replace placeholder VaR (1.5% * invested) with historical simulation using
  cached price data from yfinance
- Compute real Sharpe ratio from position returns
- Compute portfolio beta against SPY using price correlations
- Add sector exposure breakdown using position metadata

### 4D. Alert System Persistence
- New `Alert` model (type, severity, message, trade_id, dismissed, created_at)
- Trade monitor creates real alerts in DB when stop-loss/take-profit hit
- Dashboard alert feed shows real alerts instead of in-memory buffer

---

## Implementation Order

| Step | Phase | Description | Files Changed |
|------|-------|-------------|---------------|
| 1 | 2A | Fix agent name mapping + status | engine.py, agents.py, agents/page.tsx |
| 2 | 1B | Move market outlook to dashboard | page.tsx, portfolio/page.tsx |
| 3 | 1A | Dashboard multi-portfolio view | page.tsx, portfolio.py |
| 4 | 3A | Fix knowledge upload error handling | knowledge/page.tsx |
| 5 | 3B | Add document viewer | knowledge/page.tsx |
| 6 | 3D | Dynamic source credibility | knowledge.py, engine.py |
| 7 | 1A | Portfolio history + real chart | portfolio.py, models, page.tsx |
| 8 | 4B | Agent log persistence | models, engine.py, agents.py |
| 9 | 1C | Dashboard news feed | page.tsx, market_data.py |
| 10 | 4C | Real risk metrics | portfolio.py, services/risk.py |
