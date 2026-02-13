'use client';

import { useState } from 'react';
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

// --- Mock Data ---

const agentTrainingStats = [
  {
    name: 'Idea Generator',
    totalEpisodes: 4520,
    avgReward: 0.72,
    bestReward: 1.84,
    worstReward: -0.93,
    status: 'training' as const,
    learningRate: 0.0003,
    epsilon: 0.15,
    lastUpdated: '2025-04-20T16:45:00Z',
  },
  {
    name: 'Trade Executor',
    totalEpisodes: 3890,
    avgReward: 0.58,
    bestReward: 2.12,
    worstReward: -1.45,
    status: 'paused' as const,
    learningRate: 0.0001,
    epsilon: 0.10,
    lastUpdated: '2025-04-20T15:30:00Z',
  },
  {
    name: 'Portfolio Manager',
    totalEpisodes: 6210,
    avgReward: 0.85,
    bestReward: 1.96,
    worstReward: -0.67,
    status: 'training' as const,
    learningRate: 0.0002,
    epsilon: 0.08,
    lastUpdated: '2025-04-20T17:00:00Z',
  },
  {
    name: 'Risk Monitor',
    totalEpisodes: 5100,
    avgReward: 0.91,
    bestReward: 1.52,
    worstReward: -0.32,
    status: 'converged' as const,
    learningRate: 0.00005,
    epsilon: 0.03,
    lastUpdated: '2025-04-20T12:00:00Z',
  },
];

// Reward history data for line chart
const rewardHistory = Array.from({ length: 50 }, (_, i) => {
  const episode = (i + 1) * 100;
  return {
    episode,
    'Idea Generator': parseFloat((0.1 + Math.log(i + 1) * 0.18 + (Math.random() - 0.5) * 0.15).toFixed(3)),
    'Trade Executor': parseFloat((-0.2 + Math.log(i + 1) * 0.15 + (Math.random() - 0.5) * 0.2).toFixed(3)),
    'Portfolio Manager': parseFloat((0.15 + Math.log(i + 1) * 0.2 + (Math.random() - 0.5) * 0.12).toFixed(3)),
  };
});

const replayBufferStats = {
  bufferSize: 128450,
  capacity: 256000,
  avgReward: 0.64,
  minReward: -2.31,
  maxReward: 2.85,
  oldestExperience: '2025-04-15T08:00:00Z',
  newestExperience: '2025-04-20T17:10:00Z',
  samplesPerSecond: 1240,
};

const trainingInsights = [
  {
    agent: 'Idea Generator',
    insight: 'Buy-the-dip strategies after >3 sigma moves show 78% win rate over 2,100 episodes. Increasing allocation to mean-reversion patterns.',
    type: 'pattern' as const,
    timestamp: '2025-04-20T17:05:00Z',
  },
  {
    agent: 'Portfolio Manager',
    insight: 'Sector concentration penalty (HHI > 0.15) consistently leads to -0.3 reward. Agent learned to cap individual sector at 30%.',
    type: 'learning' as const,
    timestamp: '2025-04-20T16:48:00Z',
  },
  {
    agent: 'Trade Executor',
    insight: 'Trailing stop at 2x ATR outperforms fixed stops by 23% in backtested episodes. Adapting stop-loss strategy.',
    type: 'optimization' as const,
    timestamp: '2025-04-20T16:30:00Z',
  },
  {
    agent: 'Risk Monitor',
    insight: 'Converged on optimal VaR threshold of 2.5% NAV. Further training shows diminishing returns. Recommending deployment.',
    type: 'convergence' as const,
    timestamp: '2025-04-20T15:15:00Z',
  },
  {
    agent: 'Idea Generator',
    insight: 'News sentiment combined with options flow data improved idea quality score by 15%. Adding flow data as permanent feature.',
    type: 'feature' as const,
    timestamp: '2025-04-20T14:40:00Z',
  },
  {
    agent: 'Portfolio Manager',
    insight: 'Risk parity weighting outperforms equal weight by 0.12 Sharpe points across 1,000 episode moving average.',
    type: 'learning' as const,
    timestamp: '2025-04-20T13:20:00Z',
  },
  {
    agent: 'Trade Executor',
    insight: 'Limit orders at bid/ask midpoint fill rate: 64%. Agent learning to adjust aggressiveness based on spread width.',
    type: 'optimization' as const,
    timestamp: '2025-04-20T12:50:00Z',
  },
  {
    agent: 'Idea Generator',
    insight: 'Earnings surprise > 10% creates 3-day momentum in 71% of cases. Developing post-earnings entry timing strategy.',
    type: 'pattern' as const,
    timestamp: '2025-04-20T11:30:00Z',
  },
  {
    agent: 'Risk Monitor',
    insight: 'Cross-asset correlation spikes during high-VIX regimes. Agent now dynamically adjusts hedging during volatility events.',
    type: 'learning' as const,
    timestamp: '2025-04-20T10:15:00Z',
  },
  {
    agent: 'Portfolio Manager',
    insight: 'Rebalancing frequency of weekly outperforms daily by 0.08 Sharpe after accounting for transaction costs.',
    type: 'optimization' as const,
    timestamp: '2025-04-20T09:00:00Z',
  },
];

const episodeHistory = [
  { id: 'EP-4520', agent: 'Idea Generator', steps: 342, totalReward: 1.24, outcome: 'Profitable', duration: '4m 12s' },
  { id: 'EP-4519', agent: 'Idea Generator', steps: 289, totalReward: -0.31, outcome: 'Loss', duration: '3m 45s' },
  { id: 'EP-6210', agent: 'Portfolio Manager', steps: 518, totalReward: 1.67, outcome: 'Profitable', duration: '6m 22s' },
  { id: 'EP-6209', agent: 'Portfolio Manager', steps: 445, totalReward: 0.92, outcome: 'Profitable', duration: '5m 38s' },
  { id: 'EP-3890', agent: 'Trade Executor', steps: 156, totalReward: -0.85, outcome: 'Loss', duration: '2m 03s' },
  { id: 'EP-3889', agent: 'Trade Executor', steps: 234, totalReward: 1.45, outcome: 'Profitable', duration: '3m 11s' },
  { id: 'EP-5100', agent: 'Risk Monitor', steps: 612, totalReward: 1.12, outcome: 'Profitable', duration: '7m 45s' },
  { id: 'EP-5099', agent: 'Risk Monitor', steps: 580, totalReward: 0.88, outcome: 'Profitable', duration: '7m 12s' },
  { id: 'EP-4518', agent: 'Idea Generator', steps: 310, totalReward: 0.56, outcome: 'Profitable', duration: '3m 58s' },
  { id: 'EP-6208', agent: 'Portfolio Manager', steps: 490, totalReward: -0.22, outcome: 'Loss', duration: '5m 55s' },
  { id: 'EP-3888', agent: 'Trade Executor', steps: 198, totalReward: 0.73, outcome: 'Profitable', duration: '2m 41s' },
  { id: 'EP-5098', agent: 'Risk Monitor', steps: 595, totalReward: 1.05, outcome: 'Profitable', duration: '7m 30s' },
];

const statusColors: Record<string, { dot: string; text: string; bg: string; label: string }> = {
  training: { dot: 'bg-profit', text: 'text-profit', bg: 'bg-profit-muted', label: 'Training' },
  paused: { dot: 'bg-warning', text: 'text-warning', bg: 'bg-warning-muted', label: 'Paused' },
  converged: { dot: 'bg-info', text: 'text-info', bg: 'bg-info-muted', label: 'Converged' },
  error: { dot: 'bg-loss', text: 'text-loss', bg: 'bg-loss-muted', label: 'Error' },
};

const insightTypeColors: Record<string, string> = {
  pattern: 'text-info bg-info-muted',
  learning: 'text-profit bg-profit-muted',
  optimization: 'text-warning bg-warning-muted',
  convergence: 'text-accent bg-accent-muted',
  feature: 'text-info bg-info-muted',
};

const insightTypeIcons: Record<string, typeof Lightbulb> = {
  pattern: BarChart3,
  learning: Brain,
  optimization: Zap,
  convergence: CheckCircle2,
  feature: Cpu,
};

const agentLineColors: Record<string, string> = {
  'Idea Generator': '#3b82f6',
  'Trade Executor': '#f59e0b',
  'Portfolio Manager': '#00d084',
};

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

  const filteredEpisodes =
    selectedAgent === 'all'
      ? episodeHistory
      : episodeHistory.filter((e) => e.agent === selectedAgent);

  const capacityPct = ((replayBufferStats.bufferSize / replayBufferStats.capacity) * 100).toFixed(1);

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
          <button className="btn-primary flex items-center gap-2">
            <Play className="w-4 h-4" />
            Start All Training
          </button>
        </div>
      </div>

      {/* Agent Training Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {agentTrainingStats.map((agent) => {
          const colors = statusColors[agent.status];
          return (
            <div key={agent.name} className="card hover:border-white/[0.15] transition-colors">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Brain className="w-4 h-4 text-accent" />
                  <span className="text-xs font-semibold text-text-primary">{agent.name}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${colors.dot} ${agent.status === 'training' ? 'animate-pulse-slow' : ''}`} />
                  <span className={`text-[10px] font-medium ${colors.text}`}>{colors.label}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <span className="text-[10px] text-text-muted block">Total Episodes</span>
                  <span className="text-sm font-bold text-text-primary font-mono">{agent.totalEpisodes.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted block">Avg Reward</span>
                  <span className={`text-sm font-bold font-mono ${agent.avgReward >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {agent.avgReward >= 0 ? '+' : ''}{agent.avgReward.toFixed(2)}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted block">Best Reward</span>
                  <span className="text-sm font-bold font-mono text-profit">+{agent.bestReward.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-[10px] text-text-muted block">Worst Reward</span>
                  <span className="text-sm font-bold font-mono text-loss">{agent.worstReward.toFixed(2)}</span>
                </div>
              </div>

              <div className="pt-2 border-t border-white/[0.05] flex items-center justify-between text-[10px] text-text-muted">
                <span>LR: {agent.learningRate}</span>
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
            {Object.entries(agentLineColors).map(([name, color]) => (
              <div key={name} className="flex items-center gap-1.5">
                <div className="w-3 h-0.5 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-text-muted">{name}</span>
              </div>
            ))}
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
            <Line
              type="monotone"
              dataKey="Idea Generator"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              animationDuration={1000}
            />
            <Line
              type="monotone"
              dataKey="Trade Executor"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              animationDuration={1000}
            />
            <Line
              type="monotone"
              dataKey="Portfolio Manager"
              stroke="#00d084"
              strokeWidth={2}
              dot={false}
              animationDuration={1000}
            />
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
                  {replayBufferStats.bufferSize.toLocaleString()} experiences
                </span>
                <span className="text-[10px] text-text-muted">
                  {replayBufferStats.capacity.toLocaleString()} max
                </span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="p-2.5 rounded-lg bg-dark-800">
                <span className="text-[10px] text-text-muted block">Avg Reward</span>
                <span className="text-sm font-bold text-profit font-mono">+{replayBufferStats.avgReward.toFixed(2)}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-dark-800">
                <span className="text-[10px] text-text-muted block">Samples/sec</span>
                <span className="text-sm font-bold text-text-primary font-mono">{replayBufferStats.samplesPerSecond.toLocaleString()}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-dark-800">
                <span className="text-[10px] text-text-muted block">Min Reward</span>
                <span className="text-sm font-bold text-loss font-mono">{replayBufferStats.minReward.toFixed(2)}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-dark-800">
                <span className="text-[10px] text-text-muted block">Max Reward</span>
                <span className="text-sm font-bold text-profit font-mono">+{replayBufferStats.maxReward.toFixed(2)}</span>
              </div>
            </div>

            <div className="pt-3 border-t border-white/[0.05] text-[11px] text-text-muted space-y-1">
              <div className="flex justify-between">
                <span>Oldest Experience</span>
                <span>{new Date(replayBufferStats.oldestExperience).toLocaleDateString()}</span>
              </div>
              <div className="flex justify-between">
                <span>Newest Experience</span>
                <span>{new Date(replayBufferStats.newestExperience).toLocaleDateString()}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Training Insights */}
        <div className="lg:col-span-2 card">
          <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Lightbulb className="w-4 h-4 text-warning" />
            Training Insights
          </h3>
          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {trainingInsights.map((insight, idx) => {
              const InsightIcon = insightTypeIcons[insight.type];
              return (
                <div
                  key={idx}
                  className="p-3 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <InsightIcon className={`w-4 h-4 mt-0.5 shrink-0 ${insightTypeColors[insight.type].split(' ')[0]}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-accent">{insight.agent}</span>
                        <span className={`status-badge text-[10px] ${insightTypeColors[insight.type]}`}>
                          {insight.type}
                        </span>
                        <span className="text-[10px] text-text-muted ml-auto shrink-0">
                          {new Date(insight.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <p className="text-xs text-text-secondary leading-relaxed">{insight.insight}</p>
                    </div>
                  </div>
                </div>
              );
            })}
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
            {['all', ...agentTrainingStats.map((a) => a.name)].map((f) => (
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
                    <span className="text-xs text-text-secondary">{ep.agent}</span>
                  </td>
                  <td className="table-cell text-right font-mono">{ep.steps}</td>
                  <td className={`table-cell text-right font-mono font-medium ${ep.totalReward >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {ep.totalReward >= 0 ? '+' : ''}{ep.totalReward.toFixed(2)}
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
                  <td className="table-cell text-right text-text-muted font-mono text-xs">{ep.duration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
