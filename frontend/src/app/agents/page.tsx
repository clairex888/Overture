'use client';

import { useState } from 'react';
import {
  Bot,
  Play,
  Square,
  RefreshCw,
  Zap,
  Shield,
  ArrowRight,
  Activity,
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Search,
} from 'lucide-react';

// --- Mock Data ---

const ideaLoopStages = [
  { id: 'generate', label: 'Generate', description: 'Scanning sources for ideas', status: 'running' as const, agent: 'Idea Generator' },
  { id: 'validate', label: 'Validate', description: 'Multi-factor validation', status: 'running' as const, agent: 'Idea Validator' },
  { id: 'execute', label: 'Execute', description: 'Awaiting trade approval', status: 'idle' as const, agent: 'Trade Executor' },
  { id: 'monitor', label: 'Monitor', description: 'Tracking open positions', status: 'running' as const, agent: 'Position Monitor' },
];

const portfolioLoopStages = [
  { id: 'assess', label: 'Assess', description: 'Evaluating portfolio state', status: 'running' as const, agent: 'Portfolio Manager' },
  { id: 'construct', label: 'Construct', description: 'Optimizing allocations', status: 'idle' as const, agent: 'Portfolio Constructor' },
  { id: 'risk_monitor', label: 'Risk Monitor', description: 'Computing VaR & exposures', status: 'running' as const, agent: 'Risk Monitor' },
  { id: 'rebalance', label: 'Rebalance', description: 'Last rebalance 2h ago', status: 'idle' as const, agent: 'Rebalancer' },
];

const agentCards = [
  {
    name: 'Idea Generator',
    type: 'Idea Loop',
    status: 'running' as const,
    lastAction: 'Scanning news sources for AI infrastructure investment signals',
    lastActionAt: '2 min ago',
    tasksCompleted: 847,
    tasksFailed: 12,
    uptime: '99.2%',
  },
  {
    name: 'Idea Validator',
    type: 'Idea Loop',
    status: 'running' as const,
    lastAction: 'Running multi-factor validation on NVDA long thesis',
    lastActionAt: '45 sec ago',
    tasksCompleted: 623,
    tasksFailed: 8,
    uptime: '99.7%',
  },
  {
    name: 'Knowledge Curator',
    type: 'Idea Loop',
    status: 'running' as const,
    lastAction: 'Processing Fed FOMC minutes and updating macro outlook',
    lastActionAt: '3 min ago',
    tasksCompleted: 2150,
    tasksFailed: 21,
    uptime: '98.9%',
  },
  {
    name: 'Trade Executor',
    type: 'Idea Loop',
    status: 'idle' as const,
    lastAction: 'Awaiting trade approval for NVDA order (PT-001)',
    lastActionAt: '10 min ago',
    tasksCompleted: 312,
    tasksFailed: 5,
    uptime: '99.5%',
  },
  {
    name: 'Portfolio Manager',
    type: 'Portfolio Loop',
    status: 'running' as const,
    lastAction: 'Rebalancing sector weights after GOOG earnings beat',
    lastActionAt: '5 min ago',
    tasksCompleted: 1204,
    tasksFailed: 3,
    uptime: '99.9%',
  },
  {
    name: 'Risk Monitor',
    type: 'Portfolio Loop',
    status: 'running' as const,
    lastAction: 'Computing Value-at-Risk with updated correlation matrix',
    lastActionAt: '1 min ago',
    tasksCompleted: 5621,
    tasksFailed: 0,
    uptime: '100%',
  },
  {
    name: 'Rebalancer',
    type: 'Portfolio Loop',
    status: 'idle' as const,
    lastAction: 'Completed sector rebalance: reduced Tech by 3%, added Energy 2%',
    lastActionAt: '2 hr ago',
    tasksCompleted: 89,
    tasksFailed: 1,
    uptime: '99.8%',
  },
  {
    name: 'RL Trainer',
    type: 'Training',
    status: 'error' as const,
    lastAction: 'Training interrupted: GPU memory exceeded during batch 4,521',
    lastActionAt: '15 min ago',
    tasksCompleted: 4520,
    tasksFailed: 42,
    uptime: '94.1%',
  },
];

const activityLog = [
  { time: '17:12:45', agent: 'Risk Monitor', action: 'VaR updated: $18,250 (95% 1-day). Portfolio within risk limits.', level: 'info' as const },
  { time: '17:12:30', agent: 'Idea Generator', action: 'New idea generated: Long AMD on MI300X shipment ramp. Confidence: 0.74.', level: 'info' as const },
  { time: '17:11:58', agent: 'Idea Validator', action: 'Validation complete for NVDA long thesis. Score: 0.87. Recommended for execution.', level: 'success' as const },
  { time: '17:11:15', agent: 'Trade Executor', action: 'Trade PT-001 (Long NVDA 500 shares) submitted for manual approval.', level: 'warning' as const },
  { time: '17:10:42', agent: 'Knowledge Curator', action: 'Ingested 12 new data points from FOMC meeting minutes.', level: 'info' as const },
  { time: '17:09:30', agent: 'Portfolio Manager', action: 'Sector exposure check: Technology at 42%, exceeding 35% threshold.', level: 'warning' as const },
  { time: '17:08:55', agent: 'Risk Monitor', action: 'Correlation matrix updated with latest 30-day rolling window.', level: 'info' as const },
  { time: '17:07:20', agent: 'Idea Generator', action: 'Scanning Reuters, Bloomberg, SEC filings for new investment signals.', level: 'info' as const },
  { time: '17:06:45', agent: 'RL Trainer', action: 'Error: CUDA out of memory during episode 4,521. Batch size too large.', level: 'error' as const },
  { time: '17:05:30', agent: 'Rebalancer', action: 'Rebalance skipped: no drift exceeds threshold (current max drift: 1.2%).', level: 'info' as const },
  { time: '17:04:15', agent: 'Idea Validator', action: 'Started multi-factor validation on KRE short thesis.', level: 'info' as const },
  { time: '17:03:00', agent: 'Risk Monitor', action: 'Stress test complete: portfolio survives 2008-style scenario with -12.4% drawdown.', level: 'success' as const },
  { time: '17:02:30', agent: 'Knowledge Curator', action: 'Updated credibility scores for 8 news sources based on recent accuracy.', level: 'info' as const },
  { time: '17:01:45', agent: 'Trade Executor', action: 'Trailing stop updated for SPY position: new stop at $505.20.', level: 'info' as const },
  { time: '17:00:30', agent: 'Portfolio Manager', action: 'Daily portfolio assessment started. NAV: $1,247,832.', level: 'info' as const },
  { time: '16:58:15', agent: 'Idea Generator', action: 'Completed scan of 847 news articles. 3 potential signals identified.', level: 'success' as const },
  { time: '16:55:00', agent: 'Risk Monitor', action: 'Greeks update: portfolio delta 0.72, gamma 0.03, vega exposure $4,200.', level: 'info' as const },
  { time: '16:52:30', agent: 'Rebalancer', action: 'Completed sector rebalance: reduced Tech by 3%, added Energy 2%, Commodities 1%.', level: 'success' as const },
  { time: '16:50:00', agent: 'Knowledge Curator', action: 'Long-term outlook updated: Equities bullish (72% confidence).', level: 'info' as const },
  { time: '16:48:20', agent: 'Idea Validator', action: 'Rejected thesis: Short TLT. Fundamental score too low (0.52).', level: 'warning' as const },
];

const statusColors: Record<string, { dot: string; text: string; bg: string }> = {
  running: { dot: 'bg-profit', text: 'text-profit', bg: 'bg-profit-muted' },
  idle: { dot: 'bg-text-muted', text: 'text-text-muted', bg: 'bg-dark-500' },
  error: { dot: 'bg-loss', text: 'text-loss', bg: 'bg-loss-muted' },
};

const logLevelColors: Record<string, string> = {
  info: 'text-info',
  success: 'text-profit',
  warning: 'text-warning',
  error: 'text-loss',
};

const logLevelIcons: Record<string, typeof Activity> = {
  info: Activity,
  success: CheckCircle2,
  warning: AlertCircle,
  error: XCircle,
};

export default function AgentsPage() {
  const [ideaLoopRunning, setIdeaLoopRunning] = useState(true);
  const [portfolioLoopRunning, setPortfolioLoopRunning] = useState(true);
  const [logFilter, setLogFilter] = useState('all');

  const filteredLog =
    logFilter === 'all'
      ? activityLog
      : activityLog.filter((l) => l.level === logFilter);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Agents</h1>
          <p className="text-sm text-text-muted mt-1">
            Autonomous agent orchestration, monitoring, and activity log
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className="w-2 h-2 rounded-full bg-profit animate-pulse-slow" />
            <span className="text-xs text-text-secondary">
              {agentCards.filter((a) => a.status === 'running').length}/{agentCards.length} Active
            </span>
          </div>
        </div>
      </div>

      {/* Loop Visualizations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Idea Loop */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Zap className="w-4 h-4 text-warning" />
              Idea Loop
            </h3>
            <button
              onClick={() => setIdeaLoopRunning(!ideaLoopRunning)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                ideaLoopRunning
                  ? 'bg-loss/20 text-loss-light border border-loss/30 hover:bg-loss/30'
                  : 'bg-profit/20 text-profit-light border border-profit/30 hover:bg-profit/30'
              }`}
            >
              {ideaLoopRunning ? (
                <>
                  <Square className="w-3 h-3" /> Stop
                </>
              ) : (
                <>
                  <Play className="w-3 h-3" /> Start
                </>
              )}
            </button>
          </div>
          <div className="flex items-center gap-1">
            {ideaLoopStages.map((stage, idx) => (
              <div key={stage.id} className="flex items-center gap-1 flex-1">
                <div className="flex-1 p-3 rounded-lg bg-dark-800 border border-white/[0.05]">
                  <div className="flex items-center gap-2 mb-1.5">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        statusColors[stage.status].dot
                      } ${stage.status === 'running' ? 'animate-pulse-slow' : ''}`}
                    />
                    <span className="text-xs font-medium text-text-primary">{stage.label}</span>
                  </div>
                  <p className="text-[10px] text-text-muted leading-tight">{stage.description}</p>
                  <p className="text-[10px] text-text-muted mt-1 opacity-60">{stage.agent}</p>
                </div>
                {idx < ideaLoopStages.length - 1 && (
                  <ArrowRight className="w-3.5 h-3.5 text-dark-400 shrink-0" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Portfolio Loop */}
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Shield className="w-4 h-4 text-info" />
              Portfolio Loop
            </h3>
            <button
              onClick={() => setPortfolioLoopRunning(!portfolioLoopRunning)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                portfolioLoopRunning
                  ? 'bg-loss/20 text-loss-light border border-loss/30 hover:bg-loss/30'
                  : 'bg-profit/20 text-profit-light border border-profit/30 hover:bg-profit/30'
              }`}
            >
              {portfolioLoopRunning ? (
                <>
                  <Square className="w-3 h-3" /> Stop
                </>
              ) : (
                <>
                  <Play className="w-3 h-3" /> Start
                </>
              )}
            </button>
          </div>
          <div className="flex items-center gap-1">
            {portfolioLoopStages.map((stage, idx) => (
              <div key={stage.id} className="flex items-center gap-1 flex-1">
                <div className="flex-1 p-3 rounded-lg bg-dark-800 border border-white/[0.05]">
                  <div className="flex items-center gap-2 mb-1.5">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        statusColors[stage.status].dot
                      } ${stage.status === 'running' ? 'animate-pulse-slow' : ''}`}
                    />
                    <span className="text-xs font-medium text-text-primary">{stage.label}</span>
                  </div>
                  <p className="text-[10px] text-text-muted leading-tight">{stage.description}</p>
                  <p className="text-[10px] text-text-muted mt-1 opacity-60">{stage.agent}</p>
                </div>
                {idx < portfolioLoopStages.length - 1 && (
                  <ArrowRight className="w-3.5 h-3.5 text-dark-400 shrink-0" />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Agent Status Cards */}
      <div>
        <h3 className="text-sm font-semibold text-text-primary mb-3">Agent Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {agentCards.map((agent) => {
            const colors = statusColors[agent.status];
            return (
              <div key={agent.name} className="card hover:border-white/[0.15] transition-colors">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Bot className="w-4 h-4 text-accent" />
                    <span className="text-xs font-semibold text-text-primary">{agent.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className={`w-2 h-2 rounded-full ${colors.dot} ${agent.status === 'running' ? 'animate-pulse-slow' : ''}`} />
                    <span className={`text-[10px] font-medium ${colors.text} capitalize`}>
                      {agent.status}
                    </span>
                  </div>
                </div>
                <p className="text-[11px] text-text-muted mb-3 line-clamp-2">{agent.lastAction}</p>
                <div className="flex items-center gap-1 mb-2">
                  <span className={`status-badge text-[10px] ${colors.bg} ${colors.text}`}>{agent.type}</span>
                  <span className="text-[10px] text-text-muted ml-auto">{agent.lastActionAt}</span>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-white/[0.05]">
                  <div className="text-center flex-1">
                    <p className="text-xs font-semibold text-text-primary">{agent.tasksCompleted.toLocaleString()}</p>
                    <p className="text-[9px] text-text-muted">Completed</p>
                  </div>
                  <div className="text-center flex-1 border-x border-white/[0.05]">
                    <p className="text-xs font-semibold text-loss">{agent.tasksFailed}</p>
                    <p className="text-[9px] text-text-muted">Failed</p>
                  </div>
                  <div className="text-center flex-1">
                    <p className="text-xs font-semibold text-text-primary">{agent.uptime}</p>
                    <p className="text-[9px] text-text-muted">Uptime</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Activity Log */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Activity className="w-4 h-4 text-info" />
            Activity Log
          </h3>
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              {['all', 'info', 'success', 'warning', 'error'].map((f) => (
                <button
                  key={f}
                  onClick={() => setLogFilter(f)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                    logFilter === f
                      ? 'bg-info/10 text-info border border-info/20'
                      : 'text-text-muted hover:text-text-secondary'
                  }`}
                >
                  {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
            <button className="p-1.5 rounded-lg bg-dark-500 hover:bg-dark-400 transition-colors">
              <RefreshCw className="w-3.5 h-3.5 text-text-muted" />
            </button>
          </div>
        </div>
        <div className="space-y-1 max-h-[500px] overflow-y-auto">
          {filteredLog.map((entry, idx) => {
            const LogIcon = logLevelIcons[entry.level];
            return (
              <div
                key={idx}
                className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-dark-800 transition-colors"
              >
                <LogIcon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${logLevelColors[entry.level]}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-text-muted">{entry.time}</span>
                    <span className="text-xs font-medium text-accent">{entry.agent}</span>
                  </div>
                  <p className="text-xs text-text-secondary mt-0.5">{entry.action}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
