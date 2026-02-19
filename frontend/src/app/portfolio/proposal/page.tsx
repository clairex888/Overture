'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  CheckCircle2,
  RefreshCw,
  Edit3,
  RotateCcw,
  Loader2,
  ArrowLeft,
  Rocket,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { portfolioAPI } from '@/lib/api';
import type {
  PortfolioProposal,
  ProposedHolding,
} from '@/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatCurrency(value: number): string {
  const absValue = Math.abs(value);
  const prefix = value < 0 ? '-' : '';
  return `${prefix}$${absValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

const CATEGORY_COLORS: Record<string, string> = {
  equities: '#3b82f6',
  Equities: '#3b82f6',
  Equity: '#3b82f6',
  Stocks: '#3b82f6',
  fixed_income: '#8b5cf6',
  Bonds: '#8b5cf6',
  'Fixed Income': '#8b5cf6',
  commodities: '#f59e0b',
  Commodities: '#f59e0b',
  ETFs: '#00d084',
  ETF: '#00d084',
  cash: '#64748b',
  Cash: '#64748b',
  crypto: '#e879f9',
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

function CustomPieTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-dark-600 border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted mb-1">{payload[0].name}</p>
      <p className="text-sm font-semibold text-text-primary">{payload[0].value}%</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner component that uses useSearchParams (must be inside Suspense)
// ---------------------------------------------------------------------------

function ProposalPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const portfolioId = searchParams.get('portfolio_id') || '';

  const [proposal, setProposal] = useState<PortfolioProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  // Editable holdings state
  const [editableHoldings, setEditableHoldings] = useState<ProposedHolding[]>([]);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);

  // ------------------------------------------------------------------
  // Fetch the proposal on mount
  // ------------------------------------------------------------------
  const fetchProposal = useCallback(async () => {
    if (!portfolioId) {
      setError('Missing portfolio_id in URL');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await portfolioAPI.generateProposal(portfolioId);
      setProposal(data);
      setEditableHoldings(data.holdings);
    } catch (err: any) {
      setError(err.message || 'Failed to generate proposal');
    } finally {
      setLoading(false);
    }
  }, [portfolioId]);

  useEffect(() => {
    fetchProposal();
  }, [fetchProposal]);

  // Sync editable holdings when proposal changes (e.g. after recalculate)
  useEffect(() => {
    if (proposal) {
      setEditableHoldings(proposal.holdings);
      setEditingIdx(null);
    }
  }, [proposal]);

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------

  const handleQuantityChange = (idx: number, newQty: string) => {
    const updated = [...editableHoldings];
    const qty = parseFloat(newQty);
    if (!isNaN(qty) && qty >= 0) {
      updated[idx] = { ...updated[idx], quantity: qty };
      setEditableHoldings(updated);
    }
  };

  const handleRecalculate = async () => {
    if (!proposal) return;
    setEditingIdx(null);
    setRecalculating(true);
    try {
      const recalced = await portfolioAPI.propose(
        portfolioId,
        proposal.initial_amount,
        editableHoldings.map((h) => ({
          ticker: h.ticker,
          name: h.name,
          asset_class: h.asset_class,
          sub_class: h.sub_class,
          instrument: h.instrument,
          quantity: h.quantity,
          price: h.price,
        })),
      );
      setProposal(recalced);
    } catch (err: any) {
      console.error('Failed to recalculate:', err);
    } finally {
      setRecalculating(false);
    }
  };

  const handleApprove = async () => {
    if (!proposal) return;
    setApproving(true);
    try {
      await portfolioAPI.approve(
        portfolioId,
        proposal.initial_amount,
        proposal.holdings,
      );
      router.push(`/portfolio?portfolio_id=${portfolioId}&approved=true`);
    } catch (err: any) {
      console.error('Failed to approve:', err);
    } finally {
      setApproving(false);
    }
  };

  const handleStartOver = () => {
    setProposal(null);
    setEditableHoldings([]);
    setEditingIdx(null);
    setError(null);
    fetchProposal();
  };

  // ------------------------------------------------------------------
  // Loading state
  // ------------------------------------------------------------------
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/portfolio" className="p-2 rounded-lg hover:bg-dark-700 transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-muted" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio Proposal</h1>
            <p className="text-sm text-text-muted mt-1">Generating your optimized allocation...</p>
          </div>
        </div>

        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="w-8 h-8 text-accent animate-spin" />
            <p className="text-sm text-text-muted">Analyzing market conditions and building proposal...</p>
          </div>
        </div>

        {/* Skeleton summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="card animate-fade-in">
              <div className="h-3 w-20 bg-dark-600 rounded animate-pulse mb-2" />
              <div className="h-7 w-28 bg-dark-600 rounded animate-pulse" />
            </div>
          ))}
        </div>

        {/* Skeleton content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="card lg:col-span-1">
            <div className="h-4 w-28 bg-dark-600 rounded animate-pulse mb-4" />
            <div className="h-[220px] bg-dark-600 rounded animate-pulse" />
          </div>
          <div className="card lg:col-span-2">
            <div className="h-4 w-28 bg-dark-600 rounded animate-pulse mb-4" />
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-5 bg-dark-600 rounded animate-pulse" />
              ))}
            </div>
          </div>
        </div>

        <div className="card overflow-hidden p-0">
          <div className="px-4 py-3 border-b border-white/[0.08]">
            <div className="h-4 w-32 bg-dark-600 rounded animate-pulse" />
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

  // ------------------------------------------------------------------
  // Error state
  // ------------------------------------------------------------------
  if (error || !proposal) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/portfolio" className="p-2 rounded-lg hover:bg-dark-700 transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-muted" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio Proposal</h1>
            <p className="text-sm text-text-muted mt-1">Something went wrong</p>
          </div>
        </div>

        <div className="card max-w-lg mx-auto text-center py-12">
          <div className="w-12 h-12 rounded-xl bg-loss/10 flex items-center justify-center mx-auto mb-4">
            <Rocket className="w-6 h-6 text-loss" />
          </div>
          <p className="text-sm text-text-primary font-medium mb-2">Failed to load proposal</p>
          <p className="text-xs text-text-muted mb-6">{error || 'No proposal data available'}</p>
          <div className="flex items-center justify-center gap-3">
            <Link
              href="/portfolio"
              className="btn-secondary flex items-center gap-2 text-xs px-4 py-2"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Back to Portfolio
            </Link>
            <button
              onClick={fetchProposal}
              className="px-4 py-2 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent/90 transition-colors flex items-center gap-2"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Build allocation pie data
  // ------------------------------------------------------------------
  const allocData = Object.entries(proposal.allocation_summary)
    .filter(([, v]) => v > 0)
    .map(([k, v], i) => ({
      name: k.charAt(0).toUpperCase() + k.slice(1).replace('_', ' '),
      value: v,
      color: getColorForCategory(k, i),
    }));

  // ------------------------------------------------------------------
  // Render proposal
  // ------------------------------------------------------------------
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/portfolio" className="p-2 rounded-lg hover:bg-dark-700 transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-muted" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio Proposal</h1>
            <p className="text-sm text-text-muted mt-1">
              Review the AI-optimized allocation, tweak as needed, then approve to execute
            </p>
          </div>
        </div>
        <button
          onClick={handleStartOver}
          className="btn-secondary flex items-center gap-2 text-xs"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Start Over
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="card">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Initial Capital</p>
          <p className="text-xl font-bold text-text-primary">{formatCurrency(proposal.initial_amount)}</p>
        </div>
        <div className="card">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">To Invest</p>
          <p className="text-xl font-bold text-info">{formatCurrency(proposal.total_invested)}</p>
        </div>
        <div className="card">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Cash Reserve</p>
          <p className="text-xl font-bold text-text-primary">{formatCurrency(proposal.cash)}</p>
          <span className="text-[11px] text-text-muted">
            {proposal.total_value > 0
              ? `${((proposal.cash / proposal.total_value) * 100).toFixed(1)}%`
              : '0%'}
          </span>
        </div>
        <div className="card">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Trading Costs</p>
          <p className="text-xl font-bold text-warning">{formatCurrency(proposal.total_trading_cost)}</p>
          <span className="text-[11px] text-text-muted">
            {proposal.total_invested > 0
              ? `${((proposal.total_trading_cost / proposal.total_invested) * 100).toFixed(3)}%`
              : '0%'}
          </span>
        </div>
        <div className="card">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Positions</p>
          <p className="text-xl font-bold text-accent">{proposal.num_positions}</p>
          <span className="text-[11px] text-text-muted">{proposal.risk_appetite} risk</span>
        </div>
      </div>

      {/* Allocation + Strategy + Cost Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pie Chart */}
        <div className="card lg:col-span-1">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Proposed Allocation</h3>
          {allocData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={allocData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={3}
                    dataKey="value"
                    animationDuration={800}
                  >
                    {allocData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomPieTooltip />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="mt-2 space-y-1.5">
                {allocData.map((item) => (
                  <div key={item.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
                      <span className="text-text-secondary">{item.name}</span>
                    </div>
                    <span className="text-text-primary font-medium">{item.value.toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-[220px] text-text-muted text-sm">
              No allocation data
            </div>
          )}
        </div>

        {/* Strategy Notes + Cost Breakdown */}
        <div className="card lg:col-span-2">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Strategy Notes</h3>
          <div className="space-y-2">
            {proposal.strategy_notes.map((note, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                <CheckCircle2 className="w-4 h-4 text-profit shrink-0 mt-0.5" />
                <span>{note}</span>
              </div>
            ))}
          </div>

          {/* Cost Breakdown */}
          <div className="mt-6 pt-4 border-t border-white/[0.08]">
            <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
              Trading Cost Breakdown
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {(() => {
                const totals = proposal.trades.reduce(
                  (acc, t) => ({
                    spread: acc.spread + t.spread_cost,
                    impact: acc.impact + t.impact_cost,
                    commission: acc.commission + t.commission,
                    total: acc.total + t.total_cost,
                  }),
                  { spread: 0, impact: 0, commission: 0, total: 0 },
                );
                return [
                  { label: 'Spread', value: totals.spread },
                  { label: 'Market Impact', value: totals.impact },
                  { label: 'Commission', value: totals.commission },
                  { label: 'Total', value: totals.total },
                ].map((item) => (
                  <div key={item.label} className="p-3 rounded-lg bg-dark-800">
                    <p className="text-[11px] text-text-muted mb-1">{item.label}</p>
                    <p className="text-sm font-semibold text-text-primary">
                      ${item.value.toFixed(2)}
                    </p>
                  </div>
                ));
              })()}
            </div>
          </div>
        </div>
      </div>

      {/* Holdings Table -- Editable */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            Proposed Holdings
            <span className="text-xs text-text-muted font-normal">Click quantity to edit</span>
          </h3>
          <button
            onClick={handleRecalculate}
            disabled={recalculating}
            className="btn-secondary flex items-center gap-1.5 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {recalculating ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            Recalculate
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="table-header text-left px-4 py-3">Asset</th>
                <th className="table-header text-left px-4 py-3">Class</th>
                <th className="table-header text-right px-4 py-3">Qty</th>
                <th className="table-header text-right px-4 py-3">Price</th>
                <th className="table-header text-right px-4 py-3">Fill Price</th>
                <th className="table-header text-right px-4 py-3">Notional</th>
                <th className="table-header text-right px-4 py-3">Weight</th>
                <th className="table-header text-right px-4 py-3">Cost</th>
                <th className="table-header text-right px-4 py-3">Slippage</th>
              </tr>
            </thead>
            <tbody>
              {editableHoldings.map((h, idx) => (
                <tr
                  key={h.ticker}
                  className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                >
                  <td className="table-cell">
                    <div className="flex items-center gap-2">
                      <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                        {h.ticker}
                      </span>
                      <span className="text-[11px] text-text-muted hidden lg:inline">{h.name}</span>
                    </div>
                  </td>
                  <td className="table-cell">
                    <span
                      className="status-badge"
                      style={{
                        color: getColorForCategory(h.asset_class, idx),
                        backgroundColor: getColorForCategory(h.asset_class, idx) + '20',
                      }}
                    >
                      {h.asset_class.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="table-cell text-right">
                    {editingIdx === idx ? (
                      <input
                        type="number"
                        value={h.quantity}
                        onChange={(e) => handleQuantityChange(idx, e.target.value)}
                        onBlur={() => setEditingIdx(null)}
                        onKeyDown={(e) => e.key === 'Enter' && setEditingIdx(null)}
                        autoFocus
                        className="w-24 px-2 py-1 bg-dark-800 border border-accent/50 rounded text-right text-xs font-mono text-text-primary focus:outline-none"
                      />
                    ) : (
                      <button
                        onClick={() => setEditingIdx(idx)}
                        className="font-mono text-text-primary hover:text-accent transition-colors flex items-center gap-1 ml-auto"
                      >
                        {h.instrument === 'crypto'
                          ? h.quantity.toFixed(4)
                          : h.quantity.toLocaleString()}
                        <Edit3 className="w-3 h-3 text-text-muted" />
                      </button>
                    )}
                  </td>
                  <td className="table-cell text-right font-mono">${h.price.toFixed(2)}</td>
                  <td className="table-cell text-right font-mono text-text-muted">${h.fill_price.toFixed(2)}</td>
                  <td className="table-cell text-right font-mono">
                    ${h.market_value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </td>
                  <td className="table-cell text-right font-mono text-text-primary">{h.weight.toFixed(1)}%</td>
                  <td className="table-cell text-right font-mono text-warning">
                    ${h.trading_cost.total_cost.toFixed(2)}
                  </td>
                  <td className="table-cell text-right font-mono text-text-muted">
                    {h.trading_cost.slippage_pct.toFixed(3)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Approve Bar */}
      <div className="flex items-center justify-between p-4 rounded-xl bg-dark-700 border border-accent/20">
        <div>
          <p className="text-sm font-semibold text-text-primary">Ready to execute?</p>
          <p className="text-xs text-text-muted mt-0.5">
            Positions will be opened at the fill prices shown above. You can always rebalance later.
          </p>
        </div>
        <button
          onClick={handleApprove}
          disabled={approving}
          className="px-6 py-3 rounded-lg bg-profit text-white font-medium text-sm hover:bg-profit/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {approving ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Executing Trades...
            </>
          ) : (
            <>
              <CheckCircle2 className="w-4 h-4" />
              Approve &amp; Trade
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Default export wraps the inner component in Suspense (required by Next.js
// when using useSearchParams in a client component)
// ---------------------------------------------------------------------------

export default function ProposalPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 text-accent animate-spin" />
        </div>
      }
    >
      <ProposalPageInner />
    </Suspense>
  );
}
