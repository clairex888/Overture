'use client';

import { useEffect, useState } from 'react';
import {
  DollarSign,
  TrendingUp,
  Lightbulb,
  ArrowLeftRight,
  Shield,
  Bot,
  Loader2,
} from 'lucide-react';
import StatCard from '@/components/dashboard/StatCard';
import AlertFeed from '@/components/dashboard/AlertFeed';
import PortfolioChart from '@/components/charts/PortfolioChart';
import { alertsAPI, agentsAPI, ideasAPI, portfolioAPI, tradesAPI } from '@/lib/api';
import type {
  Alert,
  Idea,
  PortfolioOverview,
  AllAgentsStatus,
  AgentStatusEntry,
  PendingSummary,
  ActiveSummary,
  RiskMetrics,
} from '@/types';

// --- Mock portfolio history (no history endpoint yet) ---

const portfolioHistory = [
  { date: 'Jan 1', value: 10000000 },
  { date: 'Jan 8', value: 10120000 },
  { date: 'Jan 15', value: 10085000 },
  { date: 'Jan 22', value: 10250000 },
  { date: 'Jan 29', value: 10310000 },
  { date: 'Feb 5', value: 10195000 },
  { date: 'Feb 12', value: 10480000 },
  { date: 'Feb 19', value: 10520000 },
  { date: 'Feb 26', value: 10690000 },
  { date: 'Mar 5', value: 10750000 },
  { date: 'Mar 12', value: 10620000 },
  { date: 'Mar 19', value: 10880000 },
  { date: 'Mar 26', value: 10950000 },
  { date: 'Apr 2', value: 11100000 },
  { date: 'Apr 9', value: 11250000 },
  { date: 'Apr 16', value: 11180000 },
  { date: 'Apr 23', value: 11420000 },
  { date: 'Apr 30', value: 11580000 },
];

const statusColors: Record<string, string> = {
  running: 'bg-profit',
  idle: 'bg-warning',
  error: 'bg-loss',
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

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [agentsStatus, setAgentsStatus] = useState<AllAgentsStatus | null>(null);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [overview, setOverview] = useState<PortfolioOverview | null>(null);
  const [pendingTrades, setPendingTrades] = useState<PendingSummary | null>(null);
  const [activeTrades, setActiveTrades] = useState<ActiveSummary | null>(null);
  const [riskMetrics, setRiskMetrics] = useState<RiskMetrics | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const [
          alertsData,
          agentsData,
          ideasData,
          overviewData,
          pendingData,
          activeData,
          riskData,
        ] = await Promise.all([
          alertsAPI.list().catch(() => [] as Alert[]),
          agentsAPI.status().catch(() => null),
          ideasAPI.list().catch(() => [] as Idea[]),
          portfolioAPI.overview().catch(() => null),
          tradesAPI.pending().catch(() => null),
          tradesAPI.active().catch(() => null),
          portfolioAPI.risk().catch(() => null),
        ]);

        setAlerts(alertsData);
        setAgentsStatus(agentsData);
        setIdeas(ideasData);
        setOverview(overviewData);
        setPendingTrades(pendingData);
        setActiveTrades(activeData);
        setRiskMetrics(riskData);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  const agents: AgentStatusEntry[] = agentsStatus?.agents ?? [];
  const activeAgentCount = agents.filter((a) => a.status === 'running').length;
  const totalAgentCount = agents.length;

  const portfolioValue = overview
    ? `$${(overview.total_value / 1e6).toFixed(2)}M`
    : '--';
  const totalPnl = overview
    ? `+$${(overview.total_pnl / 1e3).toFixed(1)}K`
    : '--';
  const totalPnlPct = overview ? overview.total_pnl_pct : undefined;
  const dayPnlPct = overview ? overview.day_pnl_pct : undefined;

  const ideasCount = ideas.length;
  const validatingCount = ideas.filter((i) => i.status === 'validating').length;

  const activeTradesCount = activeTrades?.count ?? 0;
  const pendingTradesCount = pendingTrades?.count ?? 0;

  const riskScore = riskMetrics
    ? `${((riskMetrics.portfolio_volatility * 10) / 0.25).toFixed(1)}/10`
    : '--';
  const riskLabel = riskMetrics
    ? riskMetrics.portfolio_volatility < 0.15
      ? 'low'
      : riskMetrics.portfolio_volatility < 0.25
        ? 'moderate'
        : 'high'
    : '';

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
            <p className="text-sm text-text-muted mt-1">
              Real-time overview of your AI hedge fund operations
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
              <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
              <span className="text-xs text-text-secondary">Live</span>
            </div>
          </div>
        </div>

        {/* Loading indicator */}
        <div className="flex items-center justify-center py-32">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-info animate-spin" />
            <span className="text-sm text-text-muted">Loading dashboard data...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted mt-1">
            Real-time overview of your AI hedge fund operations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Live</span>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          title="Portfolio Value"
          value={portfolioValue}
          change={totalPnlPct}
          subtitle="since inception"
          icon={DollarSign}
          variant="info"
        />
        <StatCard
          title="Total P&L"
          value={totalPnl}
          change={dayPnlPct}
          subtitle="this month"
          icon={TrendingUp}
          variant="profit"
        />
        <StatCard
          title="Active Ideas"
          value={String(ideasCount)}
          subtitle={`${validatingCount} validating`}
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
          title="Risk Score"
          value={riskScore}
          subtitle={riskLabel}
          icon={Shield}
          variant="warning"
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Portfolio Chart - spans 2 cols */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary">
              Portfolio Value
            </h3>
            <div className="flex items-center gap-1">
              {['1W', '1M', '3M', 'YTD', '1Y'].map((period) => (
                <button
                  key={period}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    period === '3M'
                      ? 'bg-info/10 text-info'
                      : 'text-text-muted hover:text-text-secondary'
                  }`}
                >
                  {period}
                </button>
              ))}
            </div>
          </div>
          <PortfolioChart data={portfolioHistory} height={280} />
        </div>

        {/* Alerts */}
        <div className="lg:col-span-1">
          <AlertFeed alerts={alerts} maxItems={5} />
        </div>
      </div>

      {/* Agent Status & Recent Ideas */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Agent Status */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Bot className="w-4 h-4 text-accent" />
              Agent Status
            </h3>
            <span className="text-xs text-profit font-medium">
              {activeAgentCount}/{totalAgentCount} Active
            </span>
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

        {/* Recent Ideas */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-warning" />
              Latest Ideas
            </h3>
            <a
              href="/ideas"
              className="text-xs text-info hover:text-info-light transition-colors"
            >
              View All
            </a>
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
    </div>
  );
}
