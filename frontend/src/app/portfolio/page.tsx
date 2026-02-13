'use client';

import { useState } from 'react';
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

// --- Mock Data ---

const allocationData = [
  { name: 'Equities', value: 45, color: '#3b82f6' },
  { name: 'Bonds', value: 15, color: '#8b5cf6' },
  { name: 'Commodities', value: 12, color: '#f59e0b' },
  { name: 'ETFs', value: 18, color: '#00d084' },
  { name: 'Cash', value: 10, color: '#64748b' },
];

const positions = [
  {
    ticker: 'AAPL',
    name: 'Apple Inc.',
    direction: 'Long',
    qty: 450,
    entryPrice: 178.25,
    currentPrice: 192.53,
    weight: 6.9,
  },
  {
    ticker: 'TSLA',
    name: 'Tesla Inc.',
    direction: 'Short',
    qty: 200,
    entryPrice: 265.00,
    currentPrice: 258.40,
    weight: 4.1,
  },
  {
    ticker: 'NVDA',
    name: 'NVIDIA Corp.',
    direction: 'Long',
    qty: 300,
    entryPrice: 820.50,
    currentPrice: 875.20,
    weight: 21.0,
  },
  {
    ticker: 'SPY',
    name: 'SPDR S&P 500 ETF',
    direction: 'Long',
    qty: 500,
    entryPrice: 502.30,
    currentPrice: 511.85,
    weight: 20.5,
  },
  {
    ticker: 'GLD',
    name: 'SPDR Gold Shares',
    direction: 'Long',
    qty: 350,
    entryPrice: 198.75,
    currentPrice: 214.30,
    weight: 6.0,
  },
  {
    ticker: 'SLV',
    name: 'iShares Silver Trust',
    direction: 'Long',
    qty: 800,
    entryPrice: 22.10,
    currentPrice: 24.85,
    weight: 1.6,
  },
  {
    ticker: 'MSFT',
    name: 'Microsoft Corp.',
    direction: 'Long',
    qty: 250,
    entryPrice: 415.80,
    currentPrice: 428.60,
    weight: 8.6,
  },
  {
    ticker: 'TLT',
    name: 'iShares 20+ Yr Treasury',
    direction: 'Short',
    qty: 600,
    entryPrice: 98.50,
    currentPrice: 95.20,
    weight: 4.6,
  },
  {
    ticker: 'AMZN',
    name: 'Amazon.com Inc.',
    direction: 'Long',
    qty: 180,
    entryPrice: 178.90,
    currentPrice: 186.45,
    weight: 2.7,
  },
  {
    ticker: 'KRE',
    name: 'SPDR Regional Banking',
    direction: 'Short',
    qty: 400,
    entryPrice: 52.30,
    currentPrice: 48.75,
    weight: 1.6,
  },
];

const riskMetrics = [
  { label: 'Value at Risk (95%)', value: '$18,250', sublabel: '1-day VaR', icon: AlertTriangle, color: 'text-warning' },
  { label: 'Volatility', value: '14.2%', sublabel: 'Annualized', icon: Activity, color: 'text-info' },
  { label: 'Max Drawdown', value: '-8.3%', sublabel: 'Since inception', icon: TrendingDown, color: 'text-loss' },
  { label: 'Sharpe Ratio', value: '1.42', sublabel: 'Risk-adj. return', icon: Target, color: 'text-profit' },
  { label: 'Beta', value: '0.85', sublabel: 'vs S&P 500', icon: BarChart3, color: 'text-accent' },
  { label: 'HHI', value: '0.12', sublabel: 'Concentration', icon: PieChartIcon, color: 'text-info-light' },
];

const marketOutlook = {
  longTerm: [
    { asset: 'Equities', outlook: 'Bullish', confidence: 72 },
    { asset: 'Bonds', outlook: 'Neutral', confidence: 55 },
    { asset: 'Commodities', outlook: 'Bullish', confidence: 68 },
    { asset: 'Crypto', outlook: 'Bullish', confidence: 61 },
  ],
  midTerm: [
    { asset: 'Equities', outlook: 'Neutral', confidence: 52 },
    { asset: 'Bonds', outlook: 'Bearish', confidence: 64 },
    { asset: 'Commodities', outlook: 'Bullish', confidence: 71 },
    { asset: 'Crypto', outlook: 'Neutral', confidence: 48 },
  ],
  shortTerm: [
    { asset: 'Equities', outlook: 'Bearish', confidence: 58 },
    { asset: 'Bonds', outlook: 'Neutral', confidence: 50 },
    { asset: 'Commodities', outlook: 'Bullish', confidence: 75 },
    { asset: 'Crypto', outlook: 'Bearish', confidence: 62 },
  ],
};

const outlookColors: Record<string, string> = {
  Bullish: 'text-profit',
  Neutral: 'text-warning',
  Bearish: 'text-loss',
};

const outlookIcons: Record<string, typeof ArrowUp> = {
  Bullish: ArrowUp,
  Neutral: Minus,
  Bearish: ArrowDown,
};

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

  const computedPositions = positions.map((p) => {
    const pnlDollar =
      p.direction === 'Long'
        ? (p.currentPrice - p.entryPrice) * p.qty
        : (p.entryPrice - p.currentPrice) * p.qty;
    const pnlPct =
      p.direction === 'Long'
        ? ((p.currentPrice - p.entryPrice) / p.entryPrice) * 100
        : ((p.entryPrice - p.currentPrice) / p.entryPrice) * 100;
    return { ...p, pnlDollar, pnlPct };
  });

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
              <p className="text-2xl font-bold text-text-primary tracking-tight">$1,247,832</p>
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
              <p className="text-2xl font-bold text-text-primary tracking-tight">$312,450</p>
              <span className="text-xs text-text-muted">25.0% of portfolio</span>
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
              <p className="text-2xl font-bold text-text-primary tracking-tight">$935,382</p>
              <span className="text-xs text-text-muted">10 active positions</span>
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
              <p className="text-2xl font-bold text-profit tracking-tight">+$47,832</p>
              <span className="text-xs text-profit font-medium">+3.98%</span>
              <span className="text-xs text-text-muted ml-1">all time</span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-profit-muted flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-profit" />
            </div>
          </div>
        </div>

        <div className="card animate-fade-in">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Risk Score</p>
              <p className="text-2xl font-bold text-warning tracking-tight">6.2/10</p>
              <span className="text-xs text-warning">Moderate</span>
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
          <span className="text-xs text-text-muted">{positions.length} active positions</span>
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
              {sortedPositions.map((pos) => (
                <tr
                  key={pos.ticker}
                  className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                >
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                        {pos.ticker}
                      </span>
                      <span className="text-[11px] text-text-muted hidden lg:inline">{pos.name}</span>
                    </div>
                  </td>
                  <td className="table-cell">
                    <span
                      className={`status-badge ${
                        pos.direction === 'Long'
                          ? 'text-profit bg-profit-muted'
                          : 'text-loss bg-loss-muted'
                      }`}
                    >
                      {pos.direction}
                    </span>
                  </td>
                  <td className="table-cell text-right font-mono">{pos.qty.toLocaleString()}</td>
                  <td className="table-cell text-right font-mono">${pos.entryPrice.toFixed(2)}</td>
                  <td className="table-cell text-right font-mono">${pos.currentPrice.toFixed(2)}</td>
                  <td className={`table-cell text-right font-mono ${pos.pnlDollar >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {pos.pnlDollar >= 0 ? '+' : ''}${pos.pnlDollar.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className={`table-cell text-right font-mono ${pos.pnlPct >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%
                  </td>
                  <td className="table-cell text-right font-mono text-text-primary">{pos.weight.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Market Outlook */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Market Outlook by Timeframe</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            { title: 'Long-term (6-12 mo)', data: marketOutlook.longTerm },
            { title: 'Mid-term (1-6 mo)', data: marketOutlook.midTerm },
            { title: 'Short-term (1-4 wk)', data: marketOutlook.shortTerm },
          ].map((section) => (
            <div key={section.title}>
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                {section.title}
              </h4>
              <div className="space-y-2">
                {section.data.map((item) => {
                  const OutlookIcon = outlookIcons[item.outlook];
                  return (
                    <div
                      key={item.asset}
                      className="flex items-center justify-between p-2.5 rounded-lg bg-dark-800"
                    >
                      <span className="text-sm text-text-secondary">{item.asset}</span>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-medium ${outlookColors[item.outlook]}`}>
                          {item.outlook}
                        </span>
                        <OutlookIcon className={`w-3.5 h-3.5 ${outlookColors[item.outlook]}`} />
                        <span className="text-[10px] text-text-muted">{item.confidence}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
