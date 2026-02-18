'use client';

import { useState, useEffect } from 'react';
import {
  Brain,
  Play,
  Pause,
  RefreshCw,
  Database,
  Cpu,
  TrendingUp,
  Award,
  Zap,
  Clock,
  BarChart3,
  Activity,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Lightbulb,
  Loader2,
} from 'lucide-react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { rlAPI } from '@/lib/api';
import type { AgentRLStats, RLEpisode, ReplayBufferStats } from '@/types';

const statusColors: Record<string, { dot: string; text: string; bg: string; label: string }> = {
  training: { dot: 'bg-profit', text: 'text-profit', bg: 'bg-profit-muted', label: 'Training' },
  paused: { dot: 'bg-warning', text: 'text-warning', bg: 'bg-warning-muted', label: 'Paused' },
  converged: { dot: 'bg-info', text: 'text-info', bg: 'bg-info-muted', label: 'Converged' },
  error: { dot: 'bg-loss', text: 'text-loss', bg: 'bg-loss-muted', label: 'Error' },
};

const agentLineColors: Record<string, string> = {
  'Idea Generator': '#3b82f6',
  'Trade Executor': '#f59e0b',
  'Portfolio Manager': '#00d084',
  'Risk Monitor': '#a855f7',
};

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

function CustomChartTooltip({ active, payload, label }: any) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-dark-600 border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted mb-1.5">Episode {label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 text-xs">
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-text-secondary">{p.name}:</span>
          <span className={`font-mono font-medium ${p.value >= 0 ? 'text-profit' : 'text-loss'}`}>
            {p.value.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function RLTrainingPage() {
  const [selectedAgent, setSelectedAgent] = useState<string>('all');
  const [agentStats, setAgentStats] = useState<AgentRLStats[]>([]);
  const [episodes, setEpisodes] = useState<RLEpisode[]>([]);
  const [replayBuffer, setReplayBuffer] = useState<ReplayBufferStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startingTraining, setStartingTraining] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        const [stats, bufferStats] = await Promise.all([
          rlAPI.stats(),
          rlAPI.replayBufferStats(),
        ]);

        setAgentStats(stats);
        setReplayBuffer(bufferStats);

        // Fetch episodes for each agent and combine
        const episodeResults = await Promise.all(
          stats.map((s) => rlAPI.episodes(s.agent_name))
        );
        const allEpisodes = episodeResults
          .flat()
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        setEpisodes(allEpisodes);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch RL data');
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  const handleStartAllTraining = async () => {
    try {
      setStartingTraining(true);
      await Promise.all(agentStats.map((s) => rlAPI.startTraining(s.agent_name)));
      // Refresh stats after starting training
      const stats = await rlAPI.stats();
      setAgentStats(stats);
    } catch (err) {
      console.error('Failed to start training:', err);
    } finally {
      setStartingTraining(false);
    }
  };

  // Build reward history chart data from agent reward_trend arrays
  const rewardHistory =
    agentStats.length > 0 && agentStats[0].reward_trend.length > 0
      ? agentStats[0].reward_trend.map((_, i) => ({
          episode: (i + 1) * 100,
          ...Object.fromEntries(
            agentStats.map((s) => [s.agent_name, s.reward_trend[i]])
          ),
        }))
      : [];

  // Build training insights from all agents' insights arrays
  const trainingInsights = agentStats.flatMap((s) =>
    s.insights.map((insight) => ({
      agent: s.agent_name,
      insight,
    }))
  );

  const filteredEpisodes =
    selectedAgent === 'all'
      ? episodes
      : episodes.filter((e) => e.agent_name === selectedAgent);

  const capacityPct =
    replayBuffer ? ((replayBuffer.size / replayBuffer.capacity) * 100).toFixed(1) : '0';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="flex items-center gap-3 text-text-muted">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="text-sm">Loading RL training data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="flex flex-col items-center gap-3 text-text-muted">
          <AlertCircle className="w-8 h-8 text-loss" />
          <span className="text-sm">{error}</span>
          <button
            onClick={() => window.location.reload()}
            className="btn-secondary text-xs"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">RL Training</h1>
          <p className="text-sm text-text-muted mt-1">
            Reinforcement learning agent training, rewards, and experience replay
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-secondary flex items-center gap-2">
            <RefreshCw className="w-4 h-4" />
            Reset Buffers
          </button>
          <button
            className="btn-primary flex items-center gap-2"
            onClick={handleStartAllTraining}
            disabled={startingTraining}
          >
            {startingTraining ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            Start All Training
          </button>
        </div>
      </div>

      {/* Agent Training Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {agentStats.map((agent) => {
          const colors = statusColors[agent.status] || statusColors.error;
          return (
            <div key={agent.agent_name} className="card hover:border-white/[0.15] transition-colors">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Brain className="w-4 h-4 text-accent" />
                  <span className="text-xs font-semibold text-text-primary">{agent.agent_name}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${colors.dot} ${agent.status === 'training' ? 'animate-pulse-slow' : ''}`} />
                  <span className={`text-[10px] font-medium ${colors.text}`}>{colors.label}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <span className="text-[10px] text-text-muted block">Total Episodes</span>
                  <span className="text-sm font-bold text-text-primary font-mono">{agent.total_episodes.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted block">Avg Reward</span>
                  <span className={`text-sm font-bold font-mono ${agent.avg_reward >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {agent.avg_reward >= 0 ? '+' : ''}{agent.avg_reward.toFixed(2)}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted block">Best Reward</span>
                  <span className="text-sm font-bold font-mono text-profit">+{agent.best_episode_reward.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted block">Worst Reward</span>
                  <span className="text-sm font-bold font-mono text-loss">{agent.worst_episode_reward.toFixed(2)}</span>
                </div>
              </div>

              <div className="pt-2 border-t border-white/[0.05] flex items-center justify-between text-[10px] text-text-muted">
                <span>LR: {agent.learning_rate}</span>
                <span>Eps: {agent.epsilon}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Reward History Chart */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-profit" />
            Reward History
          </h3>
          <div className="flex items-center gap-3 text-[11px]">
            {agentStats.map((s) => {
              const color = agentLineColors[s.agent_name] || '#888';
              return (
                <div key={s.agent_name} className="flex items-center gap-1.5">
                  <div className="w-3 h-0.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-text-muted">{s.agent_name}</span>
                </div>
              );
            })}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={rewardHistory} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="episode"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#64748b', fontSize: 11 }}
              dy={10}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#64748b', fontSize: 11 }}
              dx={-10}
              width={50}
            />
            <Tooltip content={<CustomChartTooltip />} />
            {agentStats.map((s) => (
              <Line
                key={s.agent_name}
                type="monotone"
                dataKey={s.agent_name}
                stroke={agentLineColors[s.agent_name] || '#888'}
                strokeWidth={2}
                dot={false}
                animationDuration={1000}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Replay Buffer + Training Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Replay Buffer Stats */}
        <div className="card">
          <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Database className="w-4 h-4 text-info" />
            Experience Replay Buffer
          </h3>
          {replayBuffer && (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-text-muted">Buffer Capacity</span>
                  <span className="text-xs font-mono text-text-primary">{capacityPct}%</span>
                </div>
                <div className="w-full bg-dark-600 rounded-full h-2">
                  <div
                    className="h-2 rounded-full bg-info"
                    style={{ width: `${capacityPct}%` }}
                  />
                </div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-[10px] text-text-muted">
                    {replayBuffer.size.toLocaleString()} experiences
                  </span>
                  <span className="text-[10px] text-text-muted">
                    {replayBuffer.capacity.toLocaleString()} max
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-2.5 rounded-lg bg-dark-800">
                  <span className="text-[10px] text-text-muted block">Avg Reward</span>
                  <span className="text-sm font-bold text-profit font-mono">+{replayBuffer.avg_reward.toFixed(2)}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-dark-800">
                  <span className="text-[10px] text-text-muted block">Samples/sec</span>
                  <span className="text-sm font-bold text-text-primary font-mono">{replayBuffer.samples_per_second.toLocaleString()}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-dark-800">
                  <span className="text-[10px] text-text-muted block">Min Reward</span>
                  <span className="text-sm font-bold text-loss font-mono">{replayBuffer.min_reward.toFixed(2)}</span>
                </div>
                <div className="p-2.5 rounded-lg bg-dark-800">
                  <span className="text-[10px] text-text-muted block">Max Reward</span>
                  <span className="text-sm font-bold text-profit font-mono">+{replayBuffer.max_reward.toFixed(2)}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Training Insights */}
        <div className="lg:col-span-2 card">
          <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-warning" />
            Training Insights
          </h3>
          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {trainingInsights.length === 0 ? (
              <p className="text-xs text-text-muted py-4 text-center">No insights available yet.</p>
            ) : (
              trainingInsights.map((insight, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <Lightbulb className="w-4 h-4 mt-0.5 shrink-0 text-warning" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-accent">{insight.agent}</span>
                      </div>
                      <p className="text-xs text-text-secondary leading-relaxed">{insight.insight}</p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Episode History Table */}
      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Activity className="w-4 h-4 text-info" />
            Episode History
          </h3>
          <div className="flex items-center gap-1">
            {['all', ...agentStats.map((a) => a.agent_name)].map((f) => (
              <button
                key={f}
                onClick={() => setSelectedAgent(f)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  selectedAgent === f
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
                <th className="table-header text-left px-4 py-3">Episode ID</th>
                <th className="table-header text-left px-4 py-3">Agent</th>
                <th className="table-header text-right px-4 py-3">Steps</th>
                <th className="table-header text-right px-4 py-3">Total Reward</th>
                <th className="table-header text-center px-4 py-3">Outcome</th>
                <th className="table-header text-right px-4 py-3">Duration</th>
              </tr>
            </thead>
            <tbody>
              {filteredEpisodes.map((ep) => (
                <tr
                  key={ep.id}
                  className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                >
                  <td className="table-cell">
                    <span className="text-xs font-mono text-text-primary">{ep.id}</span>
                  </td>
                  <td className="table-cell">
                    <span className="text-xs text-text-secondary">{ep.agent_name}</span>
                  </td>
                  <td className="table-cell text-right font-mono">{ep.steps}</td>
                  <td className={`table-cell text-right font-mono font-medium ${ep.total_reward >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {ep.total_reward >= 0 ? '+' : ''}{ep.total_reward.toFixed(2)}
                  </td>
                  <td className="table-cell text-center">
                    <span
                      className={`status-badge ${
                        ep.outcome === 'Profitable'
                          ? 'text-profit bg-profit-muted'
                          : 'text-loss bg-loss-muted'
                      }`}
                    >
                      {ep.outcome}
                    </span>
                  </td>
                  <td className="table-cell text-right text-text-muted font-mono text-xs">
                    {formatDuration(ep.duration_seconds)}
                  </td>
                </tr>
              ))}
              {filteredEpisodes.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-xs text-text-muted">
                    No episodes found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
