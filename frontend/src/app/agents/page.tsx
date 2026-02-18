'use client';

import { useState, useEffect, useCallback } from 'react';
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
  Loader2,
} from 'lucide-react';
import { agentsAPI } from '@/lib/api';
import type { AgentStatusEntry, AgentLogEntry } from '@/types';

// --- Static config ---

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

// --- Loop stage definitions ---

const ideaLoopStageDefinitions = [
  { id: 'generate', label: 'Generate', description: 'Scanning sources for ideas', agentNames: ['idea_generator'] },
  { id: 'validate', label: 'Validate', description: 'Multi-factor validation', agentNames: ['idea_validator'] },
  { id: 'execute', label: 'Execute', description: 'Awaiting trade approval', agentNames: ['trade_executor'] },
  { id: 'monitor', label: 'Monitor', description: 'Tracking open positions', agentNames: ['position_monitor'] },
];

const portfolioLoopStageDefinitions = [
  { id: 'assess', label: 'Assess', description: 'Evaluating portfolio state', agentNames: ['portfolio_manager'] },
  { id: 'construct', label: 'Construct', description: 'Optimizing allocations', agentNames: ['portfolio_constructor'] },
  { id: 'risk_monitor', label: 'Risk Monitor', description: 'Computing VaR & exposures', agentNames: ['risk_monitor'] },
  { id: 'rebalance', label: 'Rebalance', description: 'Rebalancing portfolio', agentNames: ['rebalancer'] },
];

// --- Helpers ---

function mapLogStatus(status: string): string {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'started':
      return 'info';
    case 'skipped':
      return 'warning';
    default:
      return 'info';
  }
}

function formatUptime(uptimeSeconds: number): string {
  if (uptimeSeconds <= 0) return '0%';
  // Approximate uptime percentage assuming the agent has been expected to run
  // for the total elapsed time since deployment. For display we compute as
  // a ratio: if uptime > 24h treat it as near-100%.
  const hours = uptimeSeconds / 3600;
  if (hours >= 24) return '99.9%';
  if (hours >= 12) return '99.5%';
  if (hours >= 1) return '98%';
  return `${Math.min(100, (uptimeSeconds / 3600) * 100).toFixed(1)}%`;
}

function formatTimestamp(timestamp: string): string {
  try {
    const d = new Date(timestamp);
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return timestamp;
  }
}

function getAgentType(agentName: string): string {
  const ideaAgents = ['idea_generator', 'idea_validator', 'trade_executor', 'position_monitor', 'knowledge_curator'];
  const portfolioAgents = ['portfolio_manager', 'portfolio_constructor', 'risk_monitor', 'rebalancer'];
  if (ideaAgents.includes(agentName)) return 'Idea Loop';
  if (portfolioAgents.includes(agentName)) return 'Portfolio Loop';
  return 'Training';
}

function formatLastRun(lastRun: string | null): string {
  if (!lastRun) return 'Never';
  try {
    const d = new Date(lastRun);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 60) return `${diffSec} sec ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffHr = Math.floor(diffMin / 60);
    return `${diffHr} hr ago`;
  } catch {
    return lastRun;
  }
}

function resolveStageStatus(
  stageAgentNames: string[],
  agents: AgentStatusEntry[]
): 'running' | 'idle' | 'error' {
  const matched = agents.filter((a) => stageAgentNames.includes(a.name));
  if (matched.length === 0) return 'idle';
  if (matched.some((a) => a.status === 'error')) return 'error';
  if (matched.some((a) => a.status === 'running')) return 'running';
  return 'idle';
}

function resolveStageAgent(
  stageAgentNames: string[],
  agents: AgentStatusEntry[]
): string {
  const matched = agents.find((a) => stageAgentNames.includes(a.name));
  return matched?.display_name ?? stageAgentNames[0];
}

// --- Component ---

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentStatusEntry[]>([]);
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [ideaLoopRunning, setIdeaLoopRunning] = useState(false);
  const [portfolioLoopRunning, setPortfolioLoopRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loopActionLoading, setLoopActionLoading] = useState<string | null>(null);
  const [logFilter, setLogFilter] = useState('all');

  const fetchStatus = useCallback(async () => {
    try {
      const status = await agentsAPI.status();
      setAgents(status.agents);
      setIdeaLoopRunning(status.idea_loop_running);
      setPortfolioLoopRunning(status.portfolio_loop_running);
    } catch (err) {
      console.error('Failed to fetch agent status:', err);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const logEntries = await agentsAPI.logs();
      setLogs(logEntries);
    } catch (err) {
      console.error('Failed to fetch agent logs:', err);
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchLogs()]);
    setLoading(false);
  }, [fetchStatus, fetchLogs]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleIdeaLoopToggle = async () => {
    setLoopActionLoading('idea');
    try {
      if (ideaLoopRunning) {
        await agentsAPI.stopIdeaLoop();
      } else {
        await agentsAPI.startIdeaLoop();
      }
      await fetchStatus();
    } catch (err) {
      console.error('Failed to toggle idea loop:', err);
    } finally {
      setLoopActionLoading(null);
    }
  };

  const handlePortfolioLoopToggle = async () => {
    setLoopActionLoading('portfolio');
    try {
      if (portfolioLoopRunning) {
        await agentsAPI.stopPortfolioLoop();
      } else {
        await agentsAPI.startPortfolioLoop();
      }
      await fetchStatus();
    } catch (err) {
      console.error('Failed to toggle portfolio loop:', err);
    } finally {
      setLoopActionLoading(null);
    }
  };

  // Build loop stages from live agent statuses
  const ideaLoopStages = ideaLoopStageDefinitions.map((def) => ({
    ...def,
    status: resolveStageStatus(def.agentNames, agents),
    agent: resolveStageAgent(def.agentNames, agents),
  }));

  const portfolioLoopStages = portfolioLoopStageDefinitions.map((def) => ({
    ...def,
    status: resolveStageStatus(def.agentNames, agents),
    agent: resolveStageAgent(def.agentNames, agents),
  }));

  // Map agent entries to card data
  const agentCards = agents.map((agent) => ({
    name: agent.display_name,
    agentName: agent.name,
    type: getAgentType(agent.name),
    status: (agent.status === 'running' || agent.status === 'idle' || agent.status === 'error'
      ? agent.status
      : 'idle') as 'running' | 'idle' | 'error',
    lastAction: agent.current_task || 'No current task',
    lastActionAt: formatLastRun(agent.last_run),
    tasksCompleted: agent.run_count,
    tasksFailed: agent.error_count,
    uptime: formatUptime(agent.uptime_seconds),
  }));

  // Map log entries to display format
  const activityLog = logs.map((entry) => ({
    time: formatTimestamp(entry.timestamp),
    agent: entry.agent_name,
    action: entry.action,
    level: mapLogStatus(entry.status) as 'info' | 'success' | 'warning' | 'error',
  }));

  const filteredLog =
    logFilter === 'all'
      ? activityLog
      : activityLog.filter((l) => l.level === logFilter);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 text-accent animate-spin" />
        <span className="ml-3 text-text-muted">Loading agent data...</span>
      </div>
    );
  }

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
          <button
            onClick={fetchAll}
            className="p-2 rounded-lg bg-dark-700 border border-white/[0.08] hover:bg-dark-600 transition-colors"
            title="Refresh all data"
          >
            <RefreshCw className="w-4 h-4 text-text-muted" />
          </button>
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
              onClick={handleIdeaLoopToggle}
              disabled={loopActionLoading === 'idea'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                ideaLoopRunning
                  ? 'bg-loss/20 text-loss-light border border-loss/30 hover:bg-loss/30'
                  : 'bg-profit/20 text-profit-light border border-profit/30 hover:bg-profit/30'
              } ${loopActionLoading === 'idea' ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {loopActionLoading === 'idea' ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin" /> ...
                </>
              ) : ideaLoopRunning ? (
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
                        statusColors[stage.status]?.dot ?? statusColors.idle.dot
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
              onClick={handlePortfolioLoopToggle}
              disabled={loopActionLoading === 'portfolio'}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                portfolioLoopRunning
                  ? 'bg-loss/20 text-loss-light border border-loss/30 hover:bg-loss/30'
                  : 'bg-profit/20 text-profit-light border border-profit/30 hover:bg-profit/30'
              } ${loopActionLoading === 'portfolio' ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {loopActionLoading === 'portfolio' ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin" /> ...
                </>
              ) : portfolioLoopRunning ? (
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
                        statusColors[stage.status]?.dot ?? statusColors.idle.dot
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
            const colors = statusColors[agent.status] ?? statusColors.idle;
            return (
              <div key={agent.agentName} className="card hover:border-white/[0.15] transition-colors">
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
            <button
              onClick={fetchLogs}
              className="p-1.5 rounded-lg bg-dark-500 hover:bg-dark-400 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5 text-text-muted" />
            </button>
          </div>
        </div>
        <div className="space-y-1 max-h-[500px] overflow-y-auto">
          {filteredLog.length === 0 ? (
            <div className="text-center py-8 text-text-muted text-sm">
              No log entries found.
            </div>
          ) : (
            filteredLog.map((entry, idx) => {
              const LogIcon = logLevelIcons[entry.level] ?? Activity;
              return (
                <div
                  key={idx}
                  className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-dark-800 transition-colors"
                >
                  <LogIcon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${logLevelColors[entry.level] ?? logLevelColors.info}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-text-muted">{entry.time}</span>
                      <span className="text-xs font-medium text-accent">{entry.agent}</span>
                    </div>
                    <p className="text-xs text-text-secondary mt-0.5">{entry.action}</p>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
