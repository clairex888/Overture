'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Lightbulb,
  ArrowLeftRight,
  Bot,
  Loader2,
  Power,
  Database,
  Zap,
  ArrowUp,
  ArrowDown,
  Minus,
  Briefcase,
  Globe,
  Newspaper,
  ExternalLink,
  Target,
  BarChart3,
} from 'lucide-react';
import StatCard from '@/components/dashboard/StatCard';
import AlertFeed from '@/components/dashboard/AlertFeed';
import {
  alertsAPI,
  agentsAPI,
  ideasAPI,
  portfolioAPI,
  tradesAPI,
  knowledgeAPI,
  marketDataAPI,
} from '@/lib/api';
import PortfolioChart from '@/components/charts/PortfolioChart';
import type {
  Alert,
  Idea,
  AggregatePortfolio,
  AllAgentsStatus,
  AgentStatusEntry,
  PendingSummary,
  ActiveSummary,
  MarketOutlook,
  PortfolioListItem,
  DashboardNewsItem,
  PortfolioHistoryPoint,
} from '@/types';

// --- Helpers ---

function fmtCurrency(val: number): string {
  const abs = Math.abs(val);
  const prefix = val < 0 ? '-' : '';
  if (abs >= 1e9) return `${prefix}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${prefix}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${prefix}$${(abs / 1e3).toFixed(1)}K`;
  return `${prefix}$${abs.toFixed(0)}`;
}

function fmtPct(val: number): string {
  return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`;
}

function timeAgo(ts: string | null): string {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    const sec = Math.floor((Date.now() - d.getTime()) / 1000);
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  } catch {
    return '';
  }
}

const statusColors: Record<string, string> = {
  running: 'bg-profit',
  idle: 'bg-text-muted',
  error: 'bg-loss',
};

const outlookColors: Record<string, string> = {
  bullish: 'text-profit',
  neutral: 'text-warning',
  bearish: 'text-loss',
};

const outlookIcons: Record<string, typeof ArrowUp> = {
  bullish: ArrowUp,
  neutral: Minus,
  bearish: ArrowDown,
};

const ideaStatusColors: Record<string, string> = {
  generated: 'text-text-secondary bg-dark-500',
  validating: 'text-info bg-info-muted',
  validated: 'text-profit bg-profit-muted',
  rejected: 'text-loss bg-loss-muted',
  executing: 'text-warning bg-warning-muted',
  monitoring: 'text-accent bg-accent-muted',
  closed: 'text-text-muted bg-dark-400',
};

// ============================================================
// Dashboard Page
// ============================================================

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [agentsStatus, setAgentsStatus] = useState<AllAgentsStatus | null>(null);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [aggregate, setAggregate] = useState<AggregatePortfolio | null>(null);
  const [portfolios, setPortfolios] = useState<PortfolioListItem[]>([]);
  const [pendingTrades, setPendingTrades] = useState<PendingSummary | null>(null);
  const [activeTrades, setActiveTrades] = useState<ActiveSummary | null>(null);
  const [outlook, setOutlook] = useState<MarketOutlook | null>(null);
  const [news, setNews] = useState<DashboardNewsItem[]>([]);
  const [history, setHistory] = useState<PortfolioHistoryPoint[]>([]);
  const [ideaLoopRunning, setIdeaLoopRunning] = useState(false);
  const [portfolioLoopRunning, setPortfolioLoopRunning] = useState(false);
  const [togglingIdeaLoop, setTogglingIdeaLoop] = useState(false);
  const [togglingPortfolioLoop, setTogglingPortfolioLoop] = useState(false);
  const [togglingPipeline, setTogglingPipeline] = useState(false);

  const toggleIdeaLoop = async () => {
    setTogglingIdeaLoop(true);
    try {
      if (ideaLoopRunning) {
        await agentsAPI.stopIdeaLoop();
        setIdeaLoopRunning(false);
      } else {
        await agentsAPI.startIdeaLoop();
        setIdeaLoopRunning(true);
      }
    } catch {
      // revert on error
    } finally {
      setTogglingIdeaLoop(false);
    }
  };

  const togglePortfolioLoop = async () => {
    setTogglingPortfolioLoop(true);
    try {
      if (portfolioLoopRunning) {
        await agentsAPI.stopPortfolioLoop();
        setPortfolioLoopRunning(false);
      } else {
        await agentsAPI.startPortfolioLoop();
        setPortfolioLoopRunning(true);
      }
    } catch {
      // revert on error
    } finally {
      setTogglingPortfolioLoop(false);
    }
  };

  const triggerDataPipeline = async () => {
    setTogglingPipeline(true);
    try {
      await knowledgeAPI.triggerPipeline();
    } catch {
      // ignore
    } finally {
      setTogglingPipeline(false);
    }
  };

  useEffect(() => {
    async function fetchData() {
      try {
        const [
          alertsData,
          agentsData,
          ideasData,
          aggData,
          portfolioList,
          pendingData,
          activeData,
          outlookData,
          newsData,
          historyData,
        ] = await Promise.all([
          alertsAPI.list().catch(() => [] as Alert[]),
          agentsAPI.status().catch(() => null),
          ideasAPI.list().catch(() => [] as Idea[]),
          portfolioAPI.aggregate().catch(() => null),
          portfolioAPI.list().catch(() => [] as PortfolioListItem[]),
          tradesAPI.pending().catch(() => null),
          tradesAPI.active().catch(() => null),
          knowledgeAPI.outlook().catch(() => null),
          marketDataAPI.latestNews(8).catch(() => [] as DashboardNewsItem[]),
          portfolioAPI.history(90).catch(() => [] as PortfolioHistoryPoint[]),
        ]);

        setAlerts(alertsData);
        setAgentsStatus(agentsData);
        setIdeas(ideasData);
        setAggregate(aggData);
        setPortfolios(portfolioList);
        setPendingTrades(pendingData);
        setActiveTrades(activeData);
        setOutlook(outlookData);
        setNews(newsData);
        setHistory(historyData);
        if (agentsData) {
          setIdeaLoopRunning(agentsData.idea_loop_running);
          setPortfolioLoopRunning(agentsData.portfolio_loop_running);
        }
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  const agents: AgentStatusEntry[] = agentsStatus?.agents ?? [];
  const activeAgentCount = agents.filter((a) => a.status === 'running').length;
  const totalAgentCount = agents.length;

  // Aggregate stats
  const totalAum = aggregate?.total_aum ?? 0;
  const totalPnl = aggregate?.total_pnl ?? 0;
  const totalPnlPct = aggregate?.total_pnl_pct ?? 0;
  const totalPositions = aggregate?.total_positions ?? 0;
  const portfolioCount = aggregate?.portfolio_count ?? 0;

  const activeTradesCount = activeTrades?.count ?? 0;
  const pendingTradesCount = pendingTrades?.count ?? 0;

  // Validated ideas ready for execution
  const validatedIdeas = ideas.filter((i) => i.status === 'validated');
  const validatingCount = ideas.filter((i) => i.status === 'validating').length;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
            <p className="text-sm text-text-muted mt-1">Strategic overview of your AI hedge fund</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Live</span>
          </div>
        </div>
        <div className="flex items-center justify-center py-32">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-info animate-spin" />
            <span className="text-sm text-text-muted">Loading dashboard data...</span>
          </div>
        </div>
      </div>
    );
  }

  // Outlook sections
  const outlookSections = outlook
    ? [
        { title: 'Long-term (6–12 mo)', data: outlook.long_term },
        { title: 'Mid-term (1–6 mo)', data: outlook.medium_term },
        { title: 'Short-term (1–4 wk)', data: outlook.short_term },
      ]
    : [];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted mt-1">
            Strategic overview across {portfolioCount} portfolio{portfolioCount !== 1 ? 's' : ''}
            {' '}&middot; {totalPositions} positions
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Live</span>
          </div>
        </div>
      </div>

      {/* ── Row 1: Aggregate Stats ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          title="Total AUM"
          value={fmtCurrency(totalAum)}
          change={totalPnlPct}
          subtitle="all portfolios"
          icon={DollarSign}
          variant="info"
        />
        <StatCard
          title="Total P&L"
          value={fmtCurrency(totalPnl)}
          change={totalPnlPct}
          subtitle="since inception"
          icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
          variant={totalPnl >= 0 ? 'profit' : 'loss'}
        />
        <StatCard
          title="Active Ideas"
          value={String(ideas.length)}
          subtitle={`${validatingCount} validating · ${validatedIdeas.length} ready`}
          icon={Lightbulb}
          variant="warning"
        />
        <StatCard
          title="Open Trades"
          value={String(activeTradesCount)}
          subtitle={`${pendingTradesCount} pending approval`}
          icon={ArrowLeftRight}
          variant="info"
        />
        <StatCard
          title="Agents"
          value={`${activeAgentCount}/${totalAgentCount}`}
          subtitle={activeAgentCount > 0 ? 'active' : 'all idle'}
          icon={Bot}
          variant={activeAgentCount > 0 ? 'profit' : 'warning'}
        />
      </div>

      {/* ── Row 2: Portfolios + Market Outlook ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Portfolio Cards */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-accent" />
              Portfolios
            </h3>
            <Link href="/portfolio" className="text-xs text-info hover:text-info-light transition-colors">
              Manage
            </Link>
          </div>
          {portfolios.length === 0 ? (
            <div className="text-center py-8">
              <Briefcase className="w-8 h-8 text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-muted mb-3">No portfolios yet</p>
              <Link href="/portfolio" className="text-xs text-info hover:underline">
                Create your first portfolio
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {portfolios.map((p) => (
                <Link
                  key={p.id}
                  href={`/portfolio?id=${p.id}`}
                  className="flex items-center justify-between p-3 rounded-lg bg-dark-800 hover:bg-dark-750 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2 h-2 rounded-full ${p.pnl >= 0 ? 'bg-profit' : 'bg-loss'}`} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">{p.name}</p>
                      <p className="text-[11px] text-text-muted">
                        {p.positions_count} position{p.positions_count !== 1 ? 's' : ''}
                        {' '}&middot; {p.status}
                      </p>
                    </div>
                  </div>
                  <div className="text-right shrink-0 ml-4">
                    <p className="text-sm font-mono font-semibold text-text-primary">
                      {fmtCurrency(p.total_value)}
                    </p>
                    <p className={`text-xs font-mono ${p.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {fmtPct(p.pnl_pct)} ({fmtCurrency(p.pnl)})
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {/* Top Holdings & Exposure */}
          {aggregate && aggregate.top_holdings?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-white/[0.06]">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Top Holdings */}
                <div>
                  <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Top Holdings</h4>
                  <div className="space-y-1">
                    {aggregate.top_holdings.slice(0, 5).map((h) => (
                      <div key={`${h.portfolio}-${h.symbol}`} className="flex items-center justify-between py-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-semibold text-text-primary">{h.symbol}</span>
                          <span className="text-[10px] text-text-muted">{h.weight}%</span>
                        </div>
                        <span className={`text-xs font-mono ${h.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                          {fmtCurrency(h.pnl)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
                {/* Sector Exposure */}
                <div>
                  <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Sector Exposure</h4>
                  <div className="space-y-1.5">
                    {Object.entries(aggregate.sector_exposure)
                      .sort(([, a], [, b]) => b - a)
                      .map(([sector, pct]) => (
                        <div key={sector}>
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-xs text-text-secondary capitalize">{sector}</span>
                            <span className="text-xs font-mono text-text-muted">{pct}%</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-dark-600 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-accent/70"
                              style={{ width: `${Math.min(pct, 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Market Outlook */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Globe className="w-4 h-4 text-info" />
              Market Outlook
            </h3>
          </div>
          {outlookSections.length === 0 ? (
            <p className="text-xs text-text-muted py-4 text-center">No outlook data available</p>
          ) : (
            <div className="space-y-4">
              {outlookSections.map((section) => {
                const layer = section.data;
                const sentiment = layer.sentiment.toLowerCase();
                const sentimentLabel = sentiment.charAt(0).toUpperCase() + sentiment.slice(1);
                const OutlookIcon = outlookIcons[sentiment] || Minus;
                const colorClass = outlookColors[sentiment] || 'text-text-muted';

                return (
                  <div key={section.title}>
                    <h4 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">
                      {section.title}
                    </h4>
                    <div className="flex items-center justify-between p-2 rounded-lg bg-dark-800 mb-1.5">
                      <div className="flex items-center gap-2">
                        <OutlookIcon className={`w-3.5 h-3.5 ${colorClass}`} />
                        <span className={`text-xs font-medium ${colorClass}`}>{sentimentLabel}</span>
                      </div>
                      <span className="text-[10px] text-text-muted">{Math.round(layer.confidence * 100)}% conf.</span>
                    </div>
                    {layer.summary && (
                      <p className="text-[11px] text-text-secondary leading-relaxed mb-1">{layer.summary}</p>
                    )}
                    {layer.key_factors.length > 0 && (
                      <div className="space-y-0.5">
                        {layer.key_factors.slice(0, 3).map((factor: string, idx: number) => (
                          <p key={idx} className="text-[10px] text-text-muted pl-2 border-l border-white/10">
                            {factor}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Portfolio Value Chart (only shown when history exists) ── */}
      {history.length > 1 && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-info" />
              Portfolio Value Over Time
            </h3>
            <span className="text-[10px] text-text-muted">{history.length} days</span>
          </div>
          <PortfolioChart
            data={history.map((h) => ({ date: h.date, value: h.total_value }))}
            height={250}
          />
        </div>
      )}

      {/* ── Row 3: News + Alerts + Opportunities ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Market News */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-warning" />
              Market News
            </h3>
          </div>
          {news.length === 0 ? (
            <p className="text-xs text-text-muted py-4 text-center">
              No recent news. Trigger the data pipeline to fetch.
            </p>
          ) : (
            <div className="space-y-2">
              {news.slice(0, 6).map((item, idx) => (
                <div key={idx} className="p-2 rounded-lg bg-dark-800 hover:bg-dark-750 transition-colors">
                  <div className="flex items-start gap-2">
                    <div className="flex-1 min-w-0">
                      {item.url ? (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs font-medium text-text-primary hover:text-info line-clamp-2 transition-colors"
                        >
                          {item.title}
                        </a>
                      ) : (
                        <p className="text-xs font-medium text-text-primary line-clamp-2">{item.title}</p>
                      )}
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-text-muted">{item.source}</span>
                        {item.published && (
                          <span className="text-[10px] text-text-muted">{timeAgo(item.published)}</span>
                        )}
                      </div>
                    </div>
                    {item.url && (
                      <ExternalLink className="w-3 h-3 text-text-muted shrink-0 mt-0.5" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alerts */}
        <div>
          <AlertFeed alerts={alerts} maxItems={5} />
        </div>

        {/* Opportunities — validated ideas ready for execution */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Target className="w-4 h-4 text-profit" />
              Opportunities
            </h3>
            <Link href="/ideas" className="text-xs text-info hover:text-info-light transition-colors">
              View All Ideas
            </Link>
          </div>
          {validatedIdeas.length === 0 ? (
            <div className="text-center py-6">
              <Lightbulb className="w-6 h-6 text-text-muted mx-auto mb-2" />
              <p className="text-xs text-text-muted">No validated ideas ready yet</p>
              <p className="text-[10px] text-text-muted mt-1">Generate and validate ideas to see opportunities</p>
            </div>
          ) : (
            <div className="space-y-2">
              {validatedIdeas.slice(0, 4).map((idea) => (
                <div
                  key={idea.id}
                  className="p-2.5 rounded-lg bg-dark-800 hover:bg-dark-750 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-xs font-medium text-text-primary truncate">{idea.title}</h4>
                      <p className="text-[11px] text-text-muted mt-0.5 line-clamp-1">{idea.thesis}</p>
                    </div>
                    <span className="text-[10px] font-mono text-profit shrink-0">
                      {(idea.conviction * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex gap-1 mt-1.5">
                    {idea.tickers.map((t) => (
                      <span
                        key={t.symbol}
                        className="px-1.5 py-0.5 rounded bg-dark-500 text-[10px] font-mono text-text-secondary"
                      >
                        {t.symbol}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Row 4: Agent Status + Latest Ideas ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Status */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Bot className="w-4 h-4 text-accent" />
              Agent Status
            </h3>
            <Link href="/agents" className="text-xs text-info hover:text-info-light transition-colors">
              {activeAgentCount}/{totalAgentCount} Active
            </Link>
          </div>
          <div className="space-y-2">
            {agents.map((agent) => (
              <div
                key={agent.name}
                className="flex items-center gap-3 p-2.5 rounded-lg bg-dark-800 hover:bg-dark-750 transition-colors"
              >
                <div
                  className={`w-2 h-2 rounded-full ${
                    statusColors[agent.status] || 'bg-warning'
                  } ${agent.status === 'running' ? 'animate-pulse-slow' : ''}`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-text-primary">
                      {agent.display_name}
                    </span>
                    <span className="text-[10px] text-text-muted capitalize">
                      {agent.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted truncate mt-0.5">
                    {agent.current_task || 'No active task'}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-[10px] text-text-muted">
                    {agent.run_count} done
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Latest Ideas */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-warning" />
              Latest Ideas
            </h3>
            <Link href="/ideas" className="text-xs text-info hover:text-info-light transition-colors">
              View All
            </Link>
          </div>
          <div className="space-y-2">
            {ideas.slice(0, 4).map((idea) => (
              <div
                key={idea.id}
                className="p-3 rounded-lg bg-dark-800 hover:bg-dark-750 transition-colors cursor-pointer"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-xs font-medium text-text-primary truncate">
                      {idea.title}
                    </h4>
                    <p className="text-[11px] text-text-muted mt-0.5 line-clamp-1">
                      {idea.thesis}
                    </p>
                  </div>
                  <span
                    className={`status-badge ${
                      ideaStatusColors[idea.status] || 'text-text-secondary bg-dark-500'
                    } shrink-0`}
                  >
                    {idea.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <div className="flex gap-1">
                    {idea.tickers.map((t) => (
                      <span
                        key={t.symbol}
                        className="px-1.5 py-0.5 rounded bg-dark-500 text-[10px] font-mono text-text-secondary"
                      >
                        {t.symbol}
                      </span>
                    ))}
                  </div>
                  <span className="text-[10px] text-text-muted">
                    Conviction: {(idea.conviction * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 5: System Controls ── */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Power className="w-4 h-4 text-info" />
            System Controls
          </h3>
          <span className="text-[10px] text-text-muted">Manage loops & token costs</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Idea Generation Loop */}
          <div className="p-4 rounded-lg bg-dark-800 border border-white/[0.06]">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Lightbulb className="w-4 h-4 text-warning" />
                <span className="text-xs font-semibold text-text-primary">Idea Loop</span>
              </div>
              <button
                onClick={toggleIdeaLoop}
                disabled={togglingIdeaLoop}
                className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${
                  ideaLoopRunning ? 'bg-profit' : 'bg-dark-500'
                } ${togglingIdeaLoop ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                    ideaLoopRunning ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
            <p className="text-[11px] text-text-muted">
              Auto-generates and validates investment ideas using AI agents.
            </p>
            <div className="mt-2 flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${ideaLoopRunning ? 'bg-profit animate-pulse-slow' : 'bg-dark-400'}`} />
              <span className="text-[10px] text-text-muted">{ideaLoopRunning ? 'Running' : 'Stopped'}</span>
            </div>
          </div>

          {/* Portfolio Management Loop */}
          <div className="p-4 rounded-lg bg-dark-800 border border-white/[0.06]">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-accent" />
                <span className="text-xs font-semibold text-text-primary">Portfolio Loop</span>
              </div>
              <button
                onClick={togglePortfolioLoop}
                disabled={togglingPortfolioLoop}
                className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${
                  portfolioLoopRunning ? 'bg-profit' : 'bg-dark-500'
                } ${togglingPortfolioLoop ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                    portfolioLoopRunning ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
            <p className="text-[11px] text-text-muted">
              Monitors positions, triggers rebalancing, and manages risk.
            </p>
            <div className="mt-2 flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${portfolioLoopRunning ? 'bg-profit animate-pulse-slow' : 'bg-dark-400'}`} />
              <span className="text-[10px] text-text-muted">{portfolioLoopRunning ? 'Running' : 'Stopped'}</span>
            </div>
          </div>

          {/* Data Pipeline */}
          <div className="p-4 rounded-lg bg-dark-800 border border-white/[0.06]">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-info" />
                <span className="text-xs font-semibold text-text-primary">Data Pipeline</span>
              </div>
              <button
                onClick={triggerDataPipeline}
                disabled={togglingPipeline}
                className={`px-3 py-1 rounded-md text-[10px] font-medium transition-colors ${
                  togglingPipeline
                    ? 'bg-dark-500 text-text-muted cursor-not-allowed'
                    : 'bg-info/10 text-info hover:bg-info/20 cursor-pointer'
                }`}
              >
                {togglingPipeline ? 'Running...' : 'Run Now'}
              </button>
            </div>
            <p className="text-[11px] text-text-muted">
              Fetches market data, news, and builds knowledge base.
            </p>
            <div className="mt-2 flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-dark-400" />
              <span className="text-[10px] text-text-muted">Manual trigger</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
