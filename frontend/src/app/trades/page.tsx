'use client';

import { useState } from 'react';
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
} from 'lucide-react';

// --- Mock Data ---

const pendingTrades = [
  {
    id: 'PT-001',
    ticker: 'NVDA',
    direction: 'Long',
    type: 'Market',
    qty: 500,
    price: 875.20,
    stopLoss: 840.00,
    takeProfit: 950.00,
    confidence: 0.87,
    reason: 'AI capex cycle thesis validated. Entry on pullback to 50-day SMA. Risk/reward 1:2.2.',
    requestedAt: '2025-04-20T16:45:00Z',
    agent: 'Trade Executor',
  },
  {
    id: 'PT-002',
    ticker: 'AMD',
    direction: 'Long',
    type: 'Limit',
    qty: 300,
    price: 162.50,
    stopLoss: 152.00,
    takeProfit: 190.00,
    confidence: 0.74,
    reason: 'MI300X shipment ramp thesis. Limit order at support level. Earnings catalyst in 2 weeks.',
    requestedAt: '2025-04-20T17:10:00Z',
    agent: 'Trade Executor',
  },
];

const activeTrades = [
  {
    id: 'AT-001',
    ticker: 'AAPL',
    direction: 'Long',
    type: 'Market',
    qty: 450,
    entry: 178.25,
    current: 192.53,
    stopLoss: 168.00,
    takeProfit: 210.00,
    status: 'Active',
    openedAt: '2025-03-15T10:30:00Z',
  },
  {
    id: 'AT-002',
    ticker: 'TSLA',
    direction: 'Short',
    type: 'Market',
    qty: 200,
    entry: 265.00,
    current: 258.40,
    stopLoss: 285.00,
    takeProfit: 230.00,
    status: 'Active',
    openedAt: '2025-04-02T14:15:00Z',
  },
  {
    id: 'AT-003',
    ticker: 'GLD',
    direction: 'Long',
    type: 'Market',
    qty: 350,
    entry: 198.75,
    current: 214.30,
    stopLoss: 190.00,
    takeProfit: 230.00,
    status: 'Active',
    openedAt: '2025-03-28T09:00:00Z',
  },
  {
    id: 'AT-004',
    ticker: 'KRE',
    direction: 'Short',
    type: 'Market',
    qty: 400,
    entry: 52.30,
    current: 48.75,
    stopLoss: 57.00,
    takeProfit: 42.00,
    status: 'Active',
    openedAt: '2025-04-10T11:45:00Z',
  },
  {
    id: 'AT-005',
    ticker: 'SPY',
    direction: 'Long',
    type: 'Market',
    qty: 500,
    entry: 502.30,
    current: 511.85,
    stopLoss: 490.00,
    takeProfit: 535.00,
    status: 'Trailing Stop',
    openedAt: '2025-02-20T10:00:00Z',
  },
];

const tradeHistory = [
  {
    id: 'HT-001',
    ticker: 'META',
    direction: 'Long',
    type: 'Market',
    qty: 200,
    entry: 485.20,
    exit: 522.80,
    stopLoss: 465.00,
    takeProfit: 530.00,
    status: 'Take Profit',
    openedAt: '2025-03-01T10:00:00Z',
    closedAt: '2025-03-22T14:30:00Z',
  },
  {
    id: 'HT-002',
    ticker: 'COIN',
    direction: 'Long',
    type: 'Market',
    qty: 150,
    entry: 235.60,
    exit: 218.40,
    stopLoss: 215.00,
    takeProfit: 280.00,
    status: 'Stop Loss',
    openedAt: '2025-03-10T09:30:00Z',
    closedAt: '2025-03-18T15:45:00Z',
  },
  {
    id: 'HT-003',
    ticker: 'XOM',
    direction: 'Short',
    type: 'Market',
    qty: 300,
    entry: 118.50,
    exit: 112.20,
    stopLoss: 125.00,
    takeProfit: 108.00,
    status: 'Manual Close',
    openedAt: '2025-02-15T11:00:00Z',
    closedAt: '2025-03-05T10:00:00Z',
  },
  {
    id: 'HT-004',
    ticker: 'GOOGL',
    direction: 'Long',
    type: 'Limit',
    qty: 250,
    entry: 155.30,
    exit: 172.90,
    stopLoss: 145.00,
    takeProfit: 175.00,
    status: 'Take Profit',
    openedAt: '2025-02-28T09:45:00Z',
    closedAt: '2025-04-01T13:20:00Z',
  },
  {
    id: 'HT-005',
    ticker: 'SLV',
    direction: 'Long',
    type: 'Market',
    qty: 500,
    entry: 21.80,
    exit: 23.45,
    stopLoss: 20.50,
    takeProfit: 24.00,
    status: 'Manual Close',
    openedAt: '2025-03-05T10:30:00Z',
    closedAt: '2025-04-08T11:00:00Z',
  },
  {
    id: 'HT-006',
    ticker: 'BA',
    direction: 'Short',
    type: 'Market',
    qty: 100,
    entry: 195.00,
    exit: 202.30,
    stopLoss: 205.00,
    takeProfit: 170.00,
    status: 'Stop Loss',
    openedAt: '2025-03-20T14:00:00Z',
    closedAt: '2025-04-02T09:30:00Z',
  },
  {
    id: 'HT-007',
    ticker: 'JPM',
    direction: 'Long',
    type: 'Market',
    qty: 180,
    entry: 198.40,
    exit: 215.60,
    stopLoss: 188.00,
    takeProfit: 220.00,
    status: 'Manual Close',
    openedAt: '2025-02-01T10:00:00Z',
    closedAt: '2025-03-15T15:00:00Z',
  },
  {
    id: 'HT-008',
    ticker: 'URA',
    direction: 'Long',
    type: 'Market',
    qty: 600,
    entry: 28.50,
    exit: 32.80,
    stopLoss: 26.00,
    takeProfit: 35.00,
    status: 'Manual Close',
    openedAt: '2025-01-15T09:00:00Z',
    closedAt: '2025-04-15T14:00:00Z',
  },
];

function computePnl(entry: number, exit: number, qty: number, direction: string) {
  const pnlDollar = direction === 'Long' ? (exit - entry) * qty : (entry - exit) * qty;
  const pnlPct = direction === 'Long' ? ((exit - entry) / entry) * 100 : ((entry - exit) / entry) * 100;
  return { pnlDollar, pnlPct };
}

const statusBadgeColors: Record<string, string> = {
  Active: 'text-profit bg-profit-muted',
  'Trailing Stop': 'text-info bg-info-muted',
  'Take Profit': 'text-profit bg-profit-muted',
  'Stop Loss': 'text-loss bg-loss-muted',
  'Manual Close': 'text-text-secondary bg-dark-500',
};

export default function TradesPage() {
  const [historyFilter, setHistoryFilter] = useState<string>('all');

  // Calculate summary stats from history
  const historyPnls = tradeHistory.map((t) => computePnl(t.entry, t.exit, t.qty, t.direction));
  const totalTrades = tradeHistory.length;
  const wins = historyPnls.filter((p) => p.pnlDollar > 0).length;
  const winRate = ((wins / totalTrades) * 100).toFixed(1);
  const avgPnl = historyPnls.reduce((sum, p) => sum + p.pnlDollar, 0) / totalTrades;
  const bestTrade = Math.max(...historyPnls.map((p) => p.pnlDollar));
  const worstTrade = Math.min(...historyPnls.map((p) => p.pnlDollar));

  const filteredHistory =
    historyFilter === 'all'
      ? tradeHistory
      : tradeHistory.filter((t) => t.status === historyFilter);

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
            {pendingTrades.length} pending
          </span>
        </div>
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
                      {trade.ticker}
                    </span>
                    <span
                      className={`status-badge ${
                        trade.direction === 'Long'
                          ? 'text-profit bg-profit-muted'
                          : 'text-loss bg-loss-muted'
                      }`}
                    >
                      {trade.direction}
                    </span>
                    <span className="text-xs text-text-muted">{trade.type}</span>
                    <span className="text-xs text-text-muted">
                      {trade.qty} shares @ ${trade.price.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary mb-2">{trade.reason}</p>
                  <div className="flex items-center gap-4 text-[11px] text-text-muted">
                    <span>SL: ${trade.stopLoss.toFixed(2)}</span>
                    <span>TP: ${trade.takeProfit.toFixed(2)}</span>
                    <span>Confidence: {(trade.confidence * 100).toFixed(0)}%</span>
                    <span>Agent: {trade.agent}</span>
                    <span>
                      Requested: {new Date(trade.requestedAt).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button className="btn-success flex items-center gap-1.5 text-xs">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Approve
                  </button>
                  <button className="btn-danger flex items-center gap-1.5 text-xs">
                    <XCircle className="w-3.5 h-3.5" />
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="card">
          <div className="flex items-center gap-2 mb-1">
            <ArrowLeftRight className="w-4 h-4 text-info" />
            <span className="text-xs text-text-muted">Total Trades</span>
          </div>
          <p className="text-xl font-bold text-text-primary">{totalTrades}</p>
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
          <span className="text-xs text-text-muted">{activeTrades.length} open positions</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="table-header text-left px-4 py-3">Ticker</th>
                <th className="table-header text-left px-4 py-3">Direction</th>
                <th className="table-header text-left px-4 py-3">Type</th>
                <th className="table-header text-right px-4 py-3">Qty</th>
                <th className="table-header text-right px-4 py-3">Entry</th>
                <th className="table-header text-right px-4 py-3">Current</th>
                <th className="table-header text-right px-4 py-3">P&L</th>
                <th className="table-header text-right px-4 py-3">Stop Loss</th>
                <th className="table-header text-right px-4 py-3">Take Profit</th>
                <th className="table-header text-center px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {activeTrades.map((trade) => {
                const { pnlDollar, pnlPct } = computePnl(
                  trade.entry,
                  trade.current,
                  trade.qty,
                  trade.direction
                );
                return (
                  <tr
                    key={trade.id}
                    className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                  >
                    <td className="table-cell">
                      <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                        {trade.ticker}
                      </span>
                    </td>
                    <td className="table-cell">
                      <span
                        className={`status-badge ${
                          trade.direction === 'Long'
                            ? 'text-profit bg-profit-muted'
                            : 'text-loss bg-loss-muted'
                        }`}
                      >
                        {trade.direction}
                      </span>
                    </td>
                    <td className="table-cell text-text-muted">{trade.type}</td>
                    <td className="table-cell text-right font-mono">{trade.qty}</td>
                    <td className="table-cell text-right font-mono">${trade.entry.toFixed(2)}</td>
                    <td className="table-cell text-right font-mono">${trade.current.toFixed(2)}</td>
                    <td className={`table-cell text-right font-mono ${pnlDollar >= 0 ? 'text-profit' : 'text-loss'}`}>
                      <div>
                        {pnlDollar >= 0 ? '+' : ''}${pnlDollar.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                      <div className="text-[10px]">
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </div>
                    </td>
                    <td className="table-cell text-right font-mono text-text-muted">
                      ${trade.stopLoss.toFixed(2)}
                    </td>
                    <td className="table-cell text-right font-mono text-text-muted">
                      ${trade.takeProfit.toFixed(2)}
                    </td>
                    <td className="table-cell text-center">
                      <span className={`status-badge ${statusBadgeColors[trade.status] || 'text-text-secondary bg-dark-500'}`}>
                        {trade.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Trade History */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Clock className="w-4 h-4 text-text-muted" />
            Trade History
          </h3>
          <div className="flex items-center gap-1">
            {['all', 'Take Profit', 'Stop Loss', 'Manual Close'].map((f) => (
              <button
                key={f}
                onClick={() => setHistoryFilter(f)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  historyFilter === f
                    ? 'bg-info/10 text-info border border-info/20'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {f === 'all' ? 'All' : f}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="table-header text-left px-4 py-3">Ticker</th>
                <th className="table-header text-left px-4 py-3">Direction</th>
                <th className="table-header text-left px-4 py-3">Type</th>
                <th className="table-header text-right px-4 py-3">Qty</th>
                <th className="table-header text-right px-4 py-3">Entry</th>
                <th className="table-header text-right px-4 py-3">Exit</th>
                <th className="table-header text-right px-4 py-3">P&L</th>
                <th className="table-header text-center px-4 py-3">Outcome</th>
                <th className="table-header text-left px-4 py-3">Closed At</th>
              </tr>
            </thead>
            <tbody>
              {filteredHistory.map((trade) => {
                const { pnlDollar, pnlPct } = computePnl(
                  trade.entry,
                  trade.exit,
                  trade.qty,
                  trade.direction
                );
                return (
                  <tr
                    key={trade.id}
                    className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                  >
                    <td className="table-cell">
                      <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                        {trade.ticker}
                      </span>
                    </td>
                    <td className="table-cell">
                      <span
                        className={`status-badge ${
                          trade.direction === 'Long'
                            ? 'text-profit bg-profit-muted'
                            : 'text-loss bg-loss-muted'
                        }`}
                      >
                        {trade.direction}
                      </span>
                    </td>
                    <td className="table-cell text-text-muted">{trade.type}</td>
                    <td className="table-cell text-right font-mono">{trade.qty}</td>
                    <td className="table-cell text-right font-mono">${trade.entry.toFixed(2)}</td>
                    <td className="table-cell text-right font-mono">${trade.exit.toFixed(2)}</td>
                    <td className={`table-cell text-right font-mono ${pnlDollar >= 0 ? 'text-profit' : 'text-loss'}`}>
                      <div>
                        {pnlDollar >= 0 ? '+' : ''}${pnlDollar.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                      <div className="text-[10px]">
                        {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                      </div>
                    </td>
                    <td className="table-cell text-center">
                      <span className={`status-badge ${statusBadgeColors[trade.status] || 'text-text-secondary bg-dark-500'}`}>
                        {trade.status}
                      </span>
                    </td>
                    <td className="table-cell text-text-muted text-xs">
                      {new Date(trade.closedAt).toLocaleDateString()}{' '}
                      {new Date(trade.closedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
