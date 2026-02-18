'use client';

import { useState, useEffect } from 'react';
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Wallet,
  PieChart as PieChartIcon,
  Shield,
  Activity,
  BarChart3,
  Target,
  AlertTriangle,
  ArrowUp,
  ArrowDown,
  Minus,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import { portfolioAPI, knowledgeAPI } from '@/lib/api';
import type {
  PortfolioOverview,
  Position,
  RiskMetrics,
  AllocationBreakdown,
  MarketOutlook,
} from '@/types';

// Color mapping for asset class categories in the pie chart
const CATEGORY_COLORS: Record<string, string> = {
  Equities: '#3b82f6',
  Equity: '#3b82f6',
  Stocks: '#3b82f6',
  Bonds: '#8b5cf6',
  'Fixed Income': '#8b5cf6',
  Commodities: '#f59e0b',
  ETFs: '#00d084',
  ETF: '#00d084',
  Cash: '#64748b',
  Crypto: '#e879f9',
  Alternatives: '#f97316',
  'Real Estate': '#14b8a6',
  FX: '#6366f1',
  Options: '#ec4899',
  Futures: '#a855f7',
};

const DEFAULT_COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b', '#00d084', '#64748b', '#e879f9', '#f97316', '#14b8a6'];

function getColorForCategory(category: string, index: number): string {
  return CATEGORY_COLORS[category] || DEFAULT_COLORS[index % DEFAULT_COLORS.length];
}

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

function formatCurrency(value: number): string {
  const absValue = Math.abs(value);
  const prefix = value < 0 ? '-' : '';
  return `${prefix}$${absValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatCurrencyDetailed(value: number): string {
  const absValue = Math.abs(value);
  const prefix = value >= 0 ? '+' : '-';
  return `${prefix}$${absValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function deriveRiskScore(risk: RiskMetrics): { score: string; label: string; colorClass: string } {
  // Derive a 0-10 risk score from portfolio_beta and portfolio_volatility
  const betaScore = Math.min(risk.portfolio_beta * 5, 5);
  const volScore = Math.min(risk.portfolio_volatility * 20, 5);
  const raw = betaScore + volScore;
  const score = Math.min(Math.max(raw, 0), 10);
  const rounded = Math.round(score * 10) / 10;

  let label: string;
  let colorClass: string;
  if (rounded <= 3) {
    label = 'Low';
    colorClass = 'text-profit';
  } else if (rounded <= 6) {
    label = 'Moderate';
    colorClass = 'text-warning';
  } else {
    label = 'High';
    colorClass = 'text-loss';
  }

  return { score: `${rounded.toFixed(1)}/10`, label, colorClass };
}

function CustomPieTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-dark-600 border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted mb-1">{payload[0].name}</p>
      <p className="text-sm font-semibold text-text-primary">{payload[0].value}%</p>
    </div>
  );
}

export default function PortfolioPage() {
  const [sortField, setSortField] = useState<string>('weight');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [loading, setLoading] = useState(true);

  const [overview, setOverview] = useState<PortfolioOverview>({
    total_value: 0,
    cash: 0,
    invested: 0,
    total_pnl: 0,
    total_pnl_pct: 0,
    day_pnl: 0,
    day_pnl_pct: 0,
    positions_count: 0,
    last_updated: '',
  });

  const [positions, setPositions] = useState<Position[]>([]);

  const [risk, setRisk] = useState<RiskMetrics>({
    var_95: 0,
    var_99: 0,
    portfolio_volatility: 0,
    portfolio_beta: 0,
    sharpe_ratio: 0,
    max_drawdown: 0,
    concentration_top5: 0,
    sector_concentration: {},
    correlation_risk: '',
    last_calculated: '',
  });

  const [allocation, setAllocation] = useState<AllocationBreakdown>({
    by_asset_class: [],
    by_sector: [],
    by_geography: [],
    last_updated: '',
  });

  const [outlook, setOutlook] = useState<MarketOutlook>({
    long_term: { layer: 'long_term', sentiment: 'neutral', confidence: 0, summary: '', key_factors: [], risks: [], opportunities: [], last_updated: '' },
    medium_term: { layer: 'medium_term', sentiment: 'neutral', confidence: 0, summary: '', key_factors: [], risks: [], opportunities: [], last_updated: '' },
    short_term: { layer: 'short_term', sentiment: 'neutral', confidence: 0, summary: '', key_factors: [], risks: [], opportunities: [], last_updated: '' },
    consensus_sentiment: 'neutral',
    last_updated: '',
  });

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const [overviewData, positionsData, riskData, allocationData, outlookData] = await Promise.all([
          portfolioAPI.overview(),
          portfolioAPI.positions(),
          portfolioAPI.risk(),
          portfolioAPI.allocation(),
          knowledgeAPI.outlook(),
        ]);
        setOverview(overviewData);
        setPositions(positionsData);
        setRisk(riskData);
        setAllocation(allocationData);
        setOutlook(outlookData);
      } catch (err) {
        console.error('Failed to fetch portfolio data:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // Map allocation by_asset_class to pie chart data
  const allocationData = allocation.by_asset_class.map((entry, index) => ({
    name: entry.category,
    value: Math.round(entry.current_weight * 100) / 100,
    color: getColorForCategory(entry.category, index),
  }));

  // Compute P&L for each position and apply sorting
  const computedPositions = positions.map((p) => ({
    ...p,
    pnlDollar: p.unrealized_pnl,
    pnlPct: p.unrealized_pnl_pct,
  }));

  const sortedPositions = [...computedPositions].sort((a, b) => {
    const aVal = sortField === 'pnl' ? a.pnlDollar : sortField === 'pnlPct' ? a.pnlPct : a.weight;
    const bVal = sortField === 'pnl' ? b.pnlDollar : sortField === 'pnlPct' ? b.pnlPct : b.weight;
    return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
  });

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  // Build risk metrics display cards from real data
  const riskMetrics = [
    { label: 'Value at Risk (95%)', value: formatCurrency(risk.var_95), sublabel: '1-day VaR', icon: AlertTriangle, color: 'text-warning' },
    { label: 'Volatility', value: `${(risk.portfolio_volatility * 100).toFixed(1)}%`, sublabel: 'Annualized', icon: Activity, color: 'text-info' },
    { label: 'Max Drawdown', value: `${(risk.max_drawdown * 100).toFixed(1)}%`, sublabel: 'Since inception', icon: TrendingDown, color: 'text-loss' },
    { label: 'Sharpe Ratio', value: risk.sharpe_ratio.toFixed(2), sublabel: 'Risk-adj. return', icon: Target, color: 'text-profit' },
    { label: 'Beta', value: risk.portfolio_beta.toFixed(2), sublabel: 'vs S&P 500', icon: BarChart3, color: 'text-accent' },
    { label: 'Top-5 Conc.', value: `${(risk.concentration_top5 * 100).toFixed(0)}%`, sublabel: 'Concentration', icon: PieChartIcon, color: 'text-info-light' },
  ];

  const riskScore = deriveRiskScore(risk);

  const pnlIsPositive = overview.total_pnl >= 0;
  const pnlColorClass = pnlIsPositive ? 'text-profit' : 'text-loss';

  // Outlook sections with layer data
  const outlookSections = [
    { title: 'Long-term (6-12 mo)', data: outlook.long_term },
    { title: 'Mid-term (1-6 mo)', data: outlook.medium_term },
    { title: 'Short-term (1-4 wk)', data: outlook.short_term },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio</h1>
            <p className="text-sm text-text-muted mt-1">
              Real-time portfolio positions, allocation, and risk analytics
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
              <div className="w-2 h-2 rounded-full bg-warning animate-pulse-slow" />
              <span className="text-xs text-text-secondary">Loading</span>
            </div>
          </div>
        </div>

        {/* Loading skeleton for summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card animate-fade-in">
              <div className="flex items-start justify-between">
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-20 bg-dark-600 rounded animate-pulse" />
                  <div className="h-7 w-32 bg-dark-600 rounded animate-pulse" />
                  <div className="h-3 w-24 bg-dark-600 rounded animate-pulse" />
                </div>
                <div className="w-10 h-10 rounded-lg bg-dark-600 animate-pulse" />
              </div>
            </div>
          ))}
        </div>

        {/* Loading skeleton for charts area */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="card lg:col-span-1">
            <div className="h-4 w-28 bg-dark-600 rounded animate-pulse mb-4" />
            <div className="h-[260px] bg-dark-600 rounded animate-pulse" />
          </div>
          <div className="lg:col-span-2">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="card">
                  <div className="h-3 w-20 bg-dark-600 rounded animate-pulse mb-2" />
                  <div className="h-6 w-16 bg-dark-600 rounded animate-pulse mb-1" />
                  <div className="h-3 w-12 bg-dark-600 rounded animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Loading skeleton for positions */}
        <div className="card overflow-hidden p-0">
          <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
            <div className="h-4 w-20 bg-dark-600 rounded animate-pulse" />
            <div className="h-3 w-28 bg-dark-600 rounded animate-pulse" />
          </div>
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 bg-dark-600 rounded animate-pulse" />
            ))}
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
          <h1 className="text-2xl font-bold text-text-primary">Portfolio</h1>
          <p className="text-sm text-text-muted mt-1">
            Real-time portfolio positions, allocation, and risk analytics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Live</span>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="card animate-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Total Value</p>
              <p className="text-2xl font-bold text-text-primary tracking-tight">{formatCurrency(overview.total_value)}</p>
              <span className="text-xs text-text-muted">All positions + cash</span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-info-muted flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-info" />
            </div>
          </div>
        </div>

        <div className="card animate-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Cash</p>
              <p className="text-2xl font-bold text-text-primary tracking-tight">{formatCurrency(overview.cash)}</p>
              <span className="text-xs text-text-muted">
                {overview.total_value > 0
                  ? `${((overview.cash / overview.total_value) * 100).toFixed(1)}% of portfolio`
                  : '0% of portfolio'}
              </span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-warning-muted flex items-center justify-center">
              <Wallet className="w-5 h-5 text-warning" />
            </div>
          </div>
        </div>

        <div className="card animate-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Invested</p>
              <p className="text-2xl font-bold text-text-primary tracking-tight">{formatCurrency(overview.invested)}</p>
              <span className="text-xs text-text-muted">{overview.positions_count} active position{overview.positions_count !== 1 ? 's' : ''}</span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-accent-muted flex items-center justify-center">
              <PieChartIcon className="w-5 h-5 text-accent" />
            </div>
          </div>
        </div>

        <div className="card animate-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Total P&L</p>
              <p className={`text-2xl font-bold ${pnlColorClass} tracking-tight`}>{formatCurrencyDetailed(overview.total_pnl)}</p>
              <span className={`text-xs ${pnlColorClass} font-medium`}>
                {overview.total_pnl_pct >= 0 ? '+' : ''}{overview.total_pnl_pct.toFixed(2)}%
              </span>
              <span className="text-xs text-text-muted ml-1">all time</span>
            </div>
            <div className={`w-10 h-10 rounded-lg ${pnlIsPositive ? 'bg-profit-muted' : 'bg-loss-muted'} flex items-center justify-center`}>
              {pnlIsPositive
                ? <TrendingUp className="w-5 h-5 text-profit" />
                : <TrendingDown className="w-5 h-5 text-loss" />
              }
            </div>
          </div>
        </div>

        <div className="card animate-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Risk Score</p>
              <p className={`text-2xl font-bold ${riskScore.colorClass} tracking-tight`}>{riskScore.score}</p>
              <span className={`text-xs ${riskScore.colorClass}`}>{riskScore.label}</span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-warning-muted flex items-center justify-center">
              <Shield className="w-5 h-5 text-warning" />
            </div>
          </div>
        </div>
      </div>

      {/* Allocation Chart + Risk Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pie Chart */}
        <div className="card lg:col-span-1">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Asset Allocation</h3>
          {allocationData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={allocationData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={95}
                    paddingAngle={3}
                    dataKey="value"
                    animationDuration={800}
                  >
                    {allocationData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomPieTooltip />} />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value: string) => (
                      <span className="text-xs text-text-secondary">{value}</span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 space-y-1.5">
                {allocationData.map((item) => (
                  <div key={item.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
                      <span className="text-text-secondary">{item.name}</span>
                    </div>
                    <span className="text-text-primary font-medium">{item.value}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-[260px] text-text-muted text-sm">
              No allocation data available
            </div>
          )}
        </div>

        {/* Risk Metrics */}
        <div className="lg:col-span-2">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {riskMetrics.map((metric) => {
              const Icon = metric.icon;
              return (
                <div key={metric.label} className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className={`w-4 h-4 ${metric.color}`} />
                    <span className="text-xs text-text-muted">{metric.label}</span>
                  </div>
                  <p className="text-xl font-bold text-text-primary">{metric.value}</p>
                  <span className="text-[11px] text-text-muted">{metric.sublabel}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Positions Table */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">Positions</h3>
          <span className="text-xs text-text-muted">{positions.length} active position{positions.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="table-header text-left px-4 py-3">Ticker</th>
                <th className="table-header text-left px-4 py-3">Direction</th>
                <th className="table-header text-right px-4 py-3">Qty</th>
                <th className="table-header text-right px-4 py-3">Entry Price</th>
                <th className="table-header text-right px-4 py-3">Current Price</th>
                <th
                  className="table-header text-right px-4 py-3 cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('pnl')}
                >
                  P&L ($) {sortField === 'pnl' && (sortDir === 'desc' ? '\u25BC' : '\u25B2')}
                </th>
                <th
                  className="table-header text-right px-4 py-3 cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('pnlPct')}
                >
                  P&L (%) {sortField === 'pnlPct' && (sortDir === 'desc' ? '\u25BC' : '\u25B2')}
                </th>
                <th
                  className="table-header text-right px-4 py-3 cursor-pointer hover:text-text-secondary"
                  onClick={() => handleSort('weight')}
                >
                  Weight {sortField === 'weight' && (sortDir === 'desc' ? '\u25BC' : '\u25B2')}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedPositions.map((pos) => {
                const directionLabel = pos.direction.charAt(0).toUpperCase() + pos.direction.slice(1);
                const isLong = pos.direction.toLowerCase() === 'long';
                return (
                  <tr
                    key={pos.id}
                    className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                  >
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                          {pos.symbol}
                        </span>
                        <span className="text-[11px] text-text-muted hidden lg:inline">{pos.asset_class}</span>
                      </div>
                    </td>
                    <td className="table-cell">
                      <span
                        className={`status-badge ${
                          isLong
                            ? 'text-profit bg-profit-muted'
                            : 'text-loss bg-loss-muted'
                        }`}
                      >
                        {directionLabel}
                      </span>
                    </td>
                    <td className="table-cell text-right font-mono">{pos.quantity.toLocaleString()}</td>
                    <td className="table-cell text-right font-mono">${pos.avg_entry_price.toFixed(2)}</td>
                    <td className="table-cell text-right font-mono">${pos.current_price.toFixed(2)}</td>
                    <td className={`table-cell text-right font-mono ${pos.pnlDollar >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {pos.pnlDollar >= 0 ? '+' : ''}${pos.pnlDollar.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className={`table-cell text-right font-mono ${pos.pnlPct >= 0 ? 'text-profit' : 'text-loss'}`}>
                      {pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%
                    </td>
                    <td className="table-cell text-right font-mono text-text-primary">{pos.weight.toFixed(1)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Market Outlook */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Market Outlook by Timeframe</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {outlookSections.map((section) => {
            const layer = section.data;
            const sentiment = layer.sentiment.toLowerCase();
            const sentimentLabel = sentiment.charAt(0).toUpperCase() + sentiment.slice(1);
            const OutlookIcon = outlookIcons[sentiment] || Minus;
            const colorClass = outlookColors[sentiment] || 'text-text-muted';

            return (
              <div key={section.title}>
                <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                  {section.title}
                </h4>

                {/* Sentiment summary */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-dark-800 mb-2">
                  <span className="text-sm text-text-secondary">Sentiment</span>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium ${colorClass}`}>
                      {sentimentLabel}
                    </span>
                    <OutlookIcon className={`w-3.5 h-3.5 ${colorClass}`} />
                    <span className="text-[10px] text-text-muted">{Math.round(layer.confidence * 100)}%</span>
                  </div>
                </div>

                {/* Summary text */}
                {layer.summary && (
                  <p className="text-xs text-text-secondary mb-2 px-1 leading-relaxed">{layer.summary}</p>
                )}

                {/* Key factors */}
                {layer.key_factors.length > 0 && (
                  <div className="space-y-1">
                    {layer.key_factors.map((factor, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2.5 rounded-lg bg-dark-800"
                      >
                        <span className="text-sm text-text-secondary">{factor}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
