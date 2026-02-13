'use client';

import {
  DollarSign,
  TrendingUp,
  Lightbulb,
  ArrowLeftRight,
  Shield,
  Bot,
} from 'lucide-react';
import StatCard from '@/components/dashboard/StatCard';
import AlertFeed from '@/components/dashboard/AlertFeed';
import PortfolioChart from '@/components/charts/PortfolioChart';
import type { Alert, AgentStatus, Idea } from '@/types';

// --- Mock Data ---

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

const mockAlerts: Alert[] = [
  {
    id: '1',
    type: 'trade',
    level: 'critical',
    title: 'Trade Pending Approval',
    message: 'Long NVDA 500 shares @ $875.20 requires manual approval before execution.',
    action_required: true,
    action_url: '/trades',
    created_at: new Date(Date.now() - 5 * 60000).toISOString(),
  },
  {
    id: '2',
    type: 'risk',
    level: 'warning',
    title: 'Concentration Risk',
    message: 'Technology sector exposure at 42%, exceeding 35% threshold.',
    action_required: true,
    action_url: '/portfolio',
    created_at: new Date(Date.now() - 32 * 60000).toISOString(),
  },
  {
    id: '3',
    type: 'idea',
    level: 'info',
    title: 'New Idea Validated',
    message: 'Short thesis on regional banks validated with 0.82 confidence score.',
    action_required: false,
    created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
  },
  {
    id: '4',
    type: 'system',
    level: 'info',
    title: 'Knowledge Base Updated',
    message: 'Ingested 47 new data points from Fed minutes and earnings reports.',
    action_required: false,
    created_at: new Date(Date.now() - 4 * 3600000).toISOString(),
  },
  {
    id: '5',
    type: 'trade',
    level: 'warning',
    title: 'Stop Loss Approaching',
    message: 'TSLA short position approaching stop loss at $265.00 (current: $258.40).',
    action_required: false,
    created_at: new Date(Date.now() - 6 * 3600000).toISOString(),
  },
];

const mockAgents: AgentStatus[] = [
  {
    name: 'Idea Generator',
    type: 'idea_loop',
    status: 'running',
    last_action: 'Scanning news sources for investment opportunities',
    last_action_at: new Date(Date.now() - 120000).toISOString(),
    tasks_completed: 847,
    tasks_failed: 12,
  },
  {
    name: 'Idea Validator',
    type: 'idea_loop',
    status: 'running',
    last_action: 'Running multi-factor validation on NVDA long thesis',
    last_action_at: new Date(Date.now() - 45000).toISOString(),
    tasks_completed: 623,
    tasks_failed: 8,
  },
  {
    name: 'Portfolio Manager',
    type: 'portfolio_loop',
    status: 'running',
    last_action: 'Rebalancing sector weights after GOOG earnings',
    last_action_at: new Date(Date.now() - 300000).toISOString(),
    tasks_completed: 1204,
    tasks_failed: 3,
  },
  {
    name: 'Risk Monitor',
    type: 'portfolio_loop',
    status: 'running',
    last_action: 'Computing Value-at-Risk with updated correlations',
    last_action_at: new Date(Date.now() - 60000).toISOString(),
    tasks_completed: 5621,
    tasks_failed: 0,
  },
  {
    name: 'Trade Executor',
    type: 'portfolio_loop',
    status: 'idle',
    last_action: 'Awaiting trade approval for NVDA order',
    last_action_at: new Date(Date.now() - 600000).toISOString(),
    tasks_completed: 312,
    tasks_failed: 5,
  },
  {
    name: 'Knowledge Curator',
    type: 'idea_loop',
    status: 'running',
    last_action: 'Processing Fed FOMC minutes from latest meeting',
    last_action_at: new Date(Date.now() - 180000).toISOString(),
    tasks_completed: 2150,
    tasks_failed: 21,
  },
];

const mockIdeas: Idea[] = [
  {
    id: '1',
    title: 'Long NVDA on AI Capex Cycle',
    description: 'NVIDIA positioned to benefit from accelerating AI infrastructure spending',
    source: 'agent',
    asset_class: 'equity',
    tickers: ['NVDA'],
    thesis: 'Hyperscaler capex guidance indicates 40%+ YoY growth in AI infrastructure. NVDA maintains 80%+ GPU market share.',
    status: 'validated',
    confidence_score: 0.87,
    expected_return: 0.18,
    risk_level: 'medium',
    timeframe: 'medium_term',
    created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 1 * 3600000).toISOString(),
  },
  {
    id: '2',
    title: 'Short Regional Banks (KRE)',
    description: 'Commercial real estate exposure creating downside risk for regional banks',
    source: 'news',
    asset_class: 'etf',
    tickers: ['KRE'],
    thesis: 'CRE loan maturity wall approaching with 30%+ of regional bank loans in commercial real estate.',
    status: 'validating',
    confidence_score: 0.72,
    expected_return: 0.12,
    risk_level: 'high',
    timeframe: 'short_term',
    created_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 3 * 3600000).toISOString(),
  },
  {
    id: '3',
    title: 'Long Gold (GLD) on Rate Cut Cycle',
    description: 'Gold likely to benefit from expected Fed rate cuts and geopolitical uncertainty',
    source: 'agent',
    asset_class: 'commodity',
    tickers: ['GLD', 'GDX'],
    thesis: 'Historical correlation between rate cuts and gold prices. Central bank buying at record levels.',
    status: 'executing',
    confidence_score: 0.81,
    expected_return: 0.15,
    risk_level: 'low',
    timeframe: 'long_term',
    created_at: new Date(Date.now() - 24 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 12 * 3600000).toISOString(),
  },
  {
    id: '4',
    title: 'Pairs Trade: MSFT Long / ORCL Short',
    description: 'Cloud market share divergence creating relative value opportunity',
    source: 'screen',
    asset_class: 'equity',
    tickers: ['MSFT', 'ORCL'],
    thesis: 'Azure growing 29% vs OCI growing 12%. Valuation gap not reflecting growth differential.',
    status: 'generated',
    confidence_score: 0.65,
    expected_return: 0.08,
    risk_level: 'medium',
    timeframe: 'medium_term',
    created_at: new Date(Date.now() - 1 * 3600000).toISOString(),
    updated_at: new Date(Date.now() - 1 * 3600000).toISOString(),
  },
];

const statusColors: Record<string, string> = {
  running: 'bg-profit',
  idle: 'bg-warning',
  error: 'bg-loss',
};

const riskLevelColors: Record<string, string> = {
  low: 'text-profit bg-profit-muted',
  medium: 'text-warning bg-warning-muted',
  high: 'text-loss bg-loss-muted',
  extreme: 'text-loss-light bg-loss-muted',
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
          value="$11.58M"
          change={15.8}
          subtitle="since inception"
          icon={DollarSign}
          variant="info"
        />
        <StatCard
          title="Total P&L"
          value="+$1.58M"
          change={2.34}
          subtitle="this month"
          icon={TrendingUp}
          variant="profit"
        />
        <StatCard
          title="Active Ideas"
          value="12"
          subtitle="4 validating"
          icon={Lightbulb}
          variant="warning"
        />
        <StatCard
          title="Open Trades"
          value="8"
          subtitle="1 pending approval"
          icon={ArrowLeftRight}
          variant="info"
        />
        <StatCard
          title="Risk Score"
          value="6.2/10"
          subtitle="moderate"
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
          <AlertFeed alerts={mockAlerts} maxItems={5} />
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
              5/6 Active
            </span>
          </div>
          <div className="space-y-2">
            {mockAgents.map((agent) => (
              <div
                key={agent.name}
                className="flex items-center gap-3 p-2.5 rounded-lg bg-dark-800 hover:bg-dark-750 transition-colors"
              >
                <div
                  className={`w-2 h-2 rounded-full ${
                    statusColors[agent.status]
                  } ${agent.status === 'running' ? 'animate-pulse-slow' : ''}`}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-text-primary">
                      {agent.name}
                    </span>
                    <span className="text-[10px] text-text-muted capitalize">
                      {agent.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted truncate mt-0.5">
                    {agent.last_action}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-[10px] text-text-muted">
                    {agent.tasks_completed} done
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
            {mockIdeas.map((idea) => (
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
                      ideaStatusColors[idea.status]
                    } shrink-0`}
                  >
                    {idea.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-2">
                  <div className="flex gap-1">
                    {idea.tickers.map((t) => (
                      <span
                        key={t}
                        className="px-1.5 py-0.5 rounded bg-dark-500 text-[10px] font-mono text-text-secondary"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                  <span className="text-[10px] text-text-muted">
                    Confidence: {(idea.confidence_score * 100).toFixed(0)}%
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded ${
                      riskLevelColors[idea.risk_level]
                    }`}
                  >
                    {idea.risk_level}
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
