'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ArrowLeftRight,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
  TrendingDown,
  Award,
  BarChart3,
  AlertTriangle,
  Filter,
  Loader2,
} from 'lucide-react';
import { tradesAPI } from '@/lib/api';
import type { Trade, PendingSummary, ActiveSummary } from '@/types';

const CLOSED_STATUSES = ['closed', 'filled', 'rejected', 'cancelled'];

const statusBadgeColors: Record<string, string> = {
  open: 'text-profit bg-profit-muted',
  partially_filled: 'text-info bg-info-muted',
  filled: 'text-profit bg-profit-muted',
  closed: 'text-text-secondary bg-dark-500',
  cancelled: 'text-text-secondary bg-dark-500',
  rejected: 'text-loss bg-loss-muted',
  pending_approval: 'text-warning bg-warning-muted',
  approved: 'text-info bg-info-muted',
};

function formatDirection(direction: string): string {
  return direction === 'buy' ? 'Long' : direction === 'sell' ? 'Short' : direction;
}

function directionBadgeClass(direction: string): string {
  return direction === 'buy'
    ? 'text-profit bg-profit-muted'
    : 'text-loss bg-loss-muted';
}

function formatPrice(price: number | null): string {
  if (price == null) return '—';
  return `$${price.toFixed(2)}`;
}

function formatPnl(pnl: number | null): { display: string; sub: string; positive: boolean } | null {
  if (pnl == null) return null;
  const positive = pnl >= 0;
  return {
    display: `${positive ? '+' : ''}$${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    sub: '',
    positive,
  };
}

export default function TradesPage() {
  const [pendingData, setPendingData] = useState<PendingSummary | null>(null);
  const [activeData, setActiveData] = useState<ActiveSummary | null>(null);
  const [allTrades, setAllTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [historyFilter, setHistoryFilter] = useState<string>('all');

  const fetchData = useCallback(async () => {
    try {
      const [pending, active, all] = await Promise.all([
        tradesAPI.pending(),
        tradesAPI.active(),
        tradesAPI.list(),
      ]);
      setPendingData(pending);
      setActiveData(active);
      setAllTrades(all);
    } catch (err) {
      console.error('Failed to fetch trades:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleApprove = async (tradeId: string) => {
    setActionLoading(tradeId);
    try {
      await tradesAPI.approve(tradeId);
      await fetchData();
    } catch (err) {
      console.error('Failed to approve trade:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (tradeId: string) => {
    setActionLoading(tradeId);
    try {
      await tradesAPI.reject(tradeId, 'Rejected by user');
      await fetchData();
    } catch (err) {
      console.error('Failed to reject trade:', err);
    } finally {
      setActionLoading(null);
    }
  };

  // Derive closed/history trades from allTrades
  const closedTrades = allTrades.filter((t) =>
    CLOSED_STATUSES.includes(t.status)
  );

  // Compute summary stats from closed trades
  const totalClosedTrades = closedTrades.length;
  const tradesWithPnl = closedTrades.filter((t) => t.pnl != null);
  const wins = tradesWithPnl.filter((t) => (t.pnl as number) > 0).length;
  const winRate = tradesWithPnl.length > 0
    ? ((wins / tradesWithPnl.length) * 100).toFixed(1)
    : '0.0';
  const totalPnl = tradesWithPnl.reduce((sum, t) => sum + (t.pnl as number), 0);
  const avgPnl = tradesWithPnl.length > 0 ? totalPnl / tradesWithPnl.length : 0;
  const pnlValues = tradesWithPnl.map((t) => t.pnl as number);
  const bestTrade = pnlValues.length > 0 ? Math.max(...pnlValues) : 0;
  const worstTrade = pnlValues.length > 0 ? Math.min(...pnlValues) : 0;

  const filteredHistory =
    historyFilter === 'all'
      ? closedTrades
      : closedTrades.filter((t) => t.status === historyFilter);

  const pendingTrades = pendingData?.trades ?? [];
  const activeTrades = activeData?.trades ?? [];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 text-info animate-spin" />
        <span className="ml-3 text-text-muted">Loading trades...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Trades</h1>
          <p className="text-sm text-text-muted mt-1">
            Trade execution, management, and historical performance
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-secondary flex items-center gap-2">
            <Filter className="w-4 h-4" />
            Filters
          </button>
        </div>
      </div>

      {/* Pending Approval */}
      <div className="card border-warning/30 bg-dark-700">
        <div className="flex items-center gap-2 mb-4">
          <AlertTriangle className="w-4 h-4 text-warning" />
          <h3 className="text-sm font-semibold text-warning">Pending Approval</h3>
          <span className="ml-auto status-badge text-warning bg-warning-muted">
            {pendingData?.count ?? pendingTrades.length} pending
          </span>
        </div>
        {pendingTrades.length === 0 ? (
          <p className="text-sm text-text-muted py-4 text-center">
            No trades pending approval.
          </p>
        ) : (
          <div className="space-y-3">
            {pendingTrades.map((trade) => (
              <div
                key={trade.id}
                className="p-4 rounded-lg bg-dark-800 border border-warning/20"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="px-2 py-0.5 rounded bg-dark-500 text-sm font-mono font-medium text-text-primary">
                        {trade.symbol}
                      </span>
                      <span
                        className={`status-badge ${directionBadgeClass(trade.direction)}`}
                      >
                        {formatDirection(trade.direction)}
                      </span>
                      <span className="text-xs text-text-muted">{trade.instrument_type}</span>
                      <span className="text-xs text-text-muted">
                        {trade.quantity} shares @ {formatPrice(trade.limit_price)}
                      </span>
                    </div>
                    {trade.notes && (
                      <p className="text-xs text-text-secondary mb-2">{trade.notes}</p>
                    )}
                    <div className="flex items-center gap-4 text-[11px] text-text-muted">
                      {trade.stop_loss != null && (
                        <span>SL: {formatPrice(trade.stop_loss)}</span>
                      )}
                      {trade.take_profit != null && (
                        <span>TP: {formatPrice(trade.take_profit)}</span>
                      )}
                      <span>
                        Requested: {new Date(trade.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      className="btn-success flex items-center gap-1.5 text-xs"
                      onClick={() => handleApprove(trade.id)}
                      disabled={actionLoading === trade.id}
                    >
                      {actionLoading === trade.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      Approve
                    </button>
                    <button
                      className="btn-danger flex items-center gap-1.5 text-xs"
                      onClick={() => handleReject(trade.id)}
                      disabled={actionLoading === trade.id}
                    >
                      {actionLoading === trade.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5" />
                      )}
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="card">
          <div className="flex items-center gap-2 mb-1">
            <ArrowLeftRight className="w-4 h-4 text-info" />
            <span className="text-xs text-text-muted">Total Trades</span>
          </div>
          <p className="text-xl font-bold text-text-primary">{totalClosedTrades}</p>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-1">
            <Award className="w-4 h-4 text-profit" />
            <span className="text-xs text-text-muted">Win Rate</span>
          </div>
          <p className="text-xl font-bold text-profit">{winRate}%</p>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-1">
            <BarChart3 className="w-4 h-4 text-info" />
            <span className="text-xs text-text-muted">Avg P&L</span>
          </div>
          <p className={`text-xl font-bold ${avgPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {avgPnl >= 0 ? '+' : ''}${avgPnl.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="w-4 h-4 text-profit" />
            <span className="text-xs text-text-muted">Best Trade</span>
          </div>
          <p className="text-xl font-bold text-profit">
            +${bestTrade.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-1">
            <TrendingDown className="w-4 h-4 text-loss" />
            <span className="text-xs text-text-muted">Worst Trade</span>
          </div>
          <p className="text-xl font-bold text-loss">
            -${Math.abs(worstTrade).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
          </p>
        </div>
      </div>

      {/* Active Trades */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            Active Trades
          </h3>
          <span className="text-xs text-text-muted">
            {activeData?.count ?? activeTrades.length} open positions
            {activeData?.total_exposure != null && (
              <> &middot; ${activeData.total_exposure.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })} exposure</>
            )}
          </span>
        </div>
        {activeTrades.length === 0 ? (
          <p className="text-sm text-text-muted py-8 text-center">
            No active trades.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/[0.08]">
                  <th className="table-header text-left px-4 py-3">Symbol</th>
                  <th className="table-header text-left px-4 py-3">Direction</th>
                  <th className="table-header text-left px-4 py-3">Type</th>
                  <th className="table-header text-right px-4 py-3">Qty</th>
                  <th className="table-header text-right px-4 py-3">Entry</th>
                  <th className="table-header text-right px-4 py-3">P&L</th>
                  <th className="table-header text-right px-4 py-3">Stop Loss</th>
                  <th className="table-header text-right px-4 py-3">Take Profit</th>
                  <th className="table-header text-center px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {activeTrades.map((trade) => {
                  const pnlInfo = formatPnl(trade.pnl);
                  return (
                    <tr
                      key={trade.id}
                      className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                    >
                      <td className="table-cell">
                        <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                          {trade.symbol}
                        </span>
                      </td>
                      <td className="table-cell">
                        <span
                          className={`status-badge ${directionBadgeClass(trade.direction)}`}
                        >
                          {formatDirection(trade.direction)}
                        </span>
                      </td>
                      <td className="table-cell text-text-muted">{trade.instrument_type}</td>
                      <td className="table-cell text-right font-mono">
                        {trade.fill_quantity ?? trade.quantity}
                      </td>
                      <td className="table-cell text-right font-mono">
                        {formatPrice(trade.fill_price)}
                      </td>
                      <td
                        className={`table-cell text-right font-mono ${
                          pnlInfo
                            ? pnlInfo.positive
                              ? 'text-profit'
                              : 'text-loss'
                            : 'text-text-muted'
                        }`}
                      >
                        {pnlInfo ? (
                          <div>{pnlInfo.display}</div>
                        ) : (
                          <span>—</span>
                        )}
                      </td>
                      <td className="table-cell text-right font-mono text-text-muted">
                        {formatPrice(trade.stop_loss)}
                      </td>
                      <td className="table-cell text-right font-mono text-text-muted">
                        {formatPrice(trade.take_profit)}
                      </td>
                      <td className="table-cell text-center">
                        <span
                          className={`status-badge ${
                            statusBadgeColors[trade.status] || 'text-text-secondary bg-dark-500'
                          }`}
                        >
                          {trade.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Trade History */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Clock className="w-4 h-4 text-text-muted" />
            Trade History
          </h3>
          <div className="flex items-center gap-1">
            {['all', 'closed', 'filled', 'rejected', 'cancelled'].map((f) => (
              <button
                key={f}
                onClick={() => setHistoryFilter(f)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  historyFilter === f
                    ? 'bg-info/10 text-info border border-info/20'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
        {filteredHistory.length === 0 ? (
          <p className="text-sm text-text-muted py-8 text-center">
            No trade history found.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/[0.08]">
                  <th className="table-header text-left px-4 py-3">Symbol</th>
                  <th className="table-header text-left px-4 py-3">Direction</th>
                  <th className="table-header text-left px-4 py-3">Type</th>
                  <th className="table-header text-right px-4 py-3">Qty</th>
                  <th className="table-header text-right px-4 py-3">Entry</th>
                  <th className="table-header text-right px-4 py-3">Target</th>
                  <th className="table-header text-right px-4 py-3">P&L</th>
                  <th className="table-header text-center px-4 py-3">Status</th>
                  <th className="table-header text-left px-4 py-3">Closed At</th>
                </tr>
              </thead>
              <tbody>
                {filteredHistory.map((trade) => {
                  const pnlInfo = formatPnl(trade.pnl);
                  return (
                    <tr
                      key={trade.id}
                      className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                    >
                      <td className="table-cell">
                        <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                          {trade.symbol}
                        </span>
                      </td>
                      <td className="table-cell">
                        <span
                          className={`status-badge ${directionBadgeClass(trade.direction)}`}
                        >
                          {formatDirection(trade.direction)}
                        </span>
                      </td>
                      <td className="table-cell text-text-muted">{trade.instrument_type}</td>
                      <td className="table-cell text-right font-mono">
                        {trade.fill_quantity ?? trade.quantity}
                      </td>
                      <td className="table-cell text-right font-mono">
                        {formatPrice(trade.fill_price)}
                      </td>
                      <td className="table-cell text-right font-mono">
                        {formatPrice(trade.limit_price)}
                      </td>
                      <td
                        className={`table-cell text-right font-mono ${
                          pnlInfo
                            ? pnlInfo.positive
                              ? 'text-profit'
                              : 'text-loss'
                            : 'text-text-muted'
                        }`}
                      >
                        {pnlInfo ? (
                          <div>{pnlInfo.display}</div>
                        ) : (
                          <span>—</span>
                        )}
                      </td>
                      <td className="table-cell text-center">
                        <span
                          className={`status-badge ${
                            statusBadgeColors[trade.status] || 'text-text-secondary bg-dark-500'
                          }`}
                        >
                          {trade.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="table-cell text-text-muted text-xs">
                        {new Date(trade.updated_at).toLocaleDateString()}{' '}
                        {new Date(trade.updated_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
