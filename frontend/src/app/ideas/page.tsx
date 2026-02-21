'use client';

import { useState, useEffect, useCallback, Fragment } from 'react';
import {
  Lightbulb,
  Search,
  ChevronDown,
  ChevronRight,
  Zap,
  Play,
  Pause,
  Loader2,
  AlertCircle,
  Trash2,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  Brain,
  BarChart3,
  TrendingUp,
  Shield,
  Database,
  ChevronDownIcon,
} from 'lucide-react';
import type { Idea } from '@/types';
import { ideasAPI } from '@/lib/api';

// --- Constants ---

const pipelineStages = [
  { key: 'generated', label: 'Generated', color: 'bg-dark-400' },
  { key: 'validating', label: 'Validating', color: 'bg-info' },
  { key: 'validated', label: 'Validated', color: 'bg-profit' },
  { key: 'executing', label: 'Executing', color: 'bg-warning' },
  { key: 'monitoring', label: 'Monitoring', color: 'bg-accent' },
  { key: 'closed', label: 'Closed', color: 'bg-text-muted' },
];

const statusFilters = [
  'all', 'generated', 'validating', 'validated', 'rejected',
  'executing', 'monitoring', 'closed',
] as const;

const statusColors: Record<string, string> = {
  generated: 'text-text-secondary bg-dark-500',
  validating: 'text-info bg-info-muted',
  validated: 'text-profit bg-profit-muted',
  rejected: 'text-loss bg-loss-muted',
  executing: 'text-warning bg-warning-muted',
  monitoring: 'text-accent bg-accent-muted',
  closed: 'text-text-muted bg-dark-400',
};

const agentColors: Record<string, string> = {
  'Macro News Agent': 'text-blue-400',
  'Industry News Agent': 'text-emerald-400',
  'Crypto Agent': 'text-purple-400',
  'Quant Systematic Agent': 'text-cyan-400',
  'Commodities Agent': 'text-amber-400',
  'Social Media Agent': 'text-pink-400',
};

const agentShortNames: Record<string, string> = {
  'Macro News Agent': 'Macro',
  'Industry News Agent': 'Industry',
  'Crypto Agent': 'Crypto',
  'Quant Systematic Agent': 'Quant',
  'Commodities Agent': 'Commodities',
  'Social Media Agent': 'Social',
};

const verdictColors: Record<string, string> = {
  PASS: 'text-profit bg-profit/10 border-profit/20',
  FAIL: 'text-loss bg-loss/10 border-loss/20',
  NEEDS_MORE_DATA: 'text-warning bg-warning/10 border-warning/20',
};

const AGENT_DOMAINS = [
  { key: 'macro', label: 'Macro', description: 'Fed, rates, inflation, geopolitics' },
  { key: 'industry', label: 'Industry', description: 'Earnings, M&A, sector rotation' },
  { key: 'crypto', label: 'Crypto', description: 'BTC, ETH, DeFi, on-chain' },
  { key: 'quant', label: 'Quant', description: 'Factor, momentum, mean reversion' },
  { key: 'commodities', label: 'Commodities', description: 'Oil, metals, agriculture' },
  { key: 'social', label: 'Social', description: 'Reddit, X sentiment, retail flow' },
] as const;

const lensIcons: Record<string, any> = {
  backtest: TrendingUp,
  fundamental: BarChart3,
  reasoning: Brain,
  data_analysis: Database,
};

// --- Helpers ---

function highlightThesis(text: string): JSX.Element[] {
  // Highlight important data points in the thesis text
  const parts: JSX.Element[] = [];
  // Split by patterns: $TICKER, percentages, dollar amounts, key terms
  const regex = /(\$[A-Z]{1,5}|\d+\.?\d*%|\$\d+[\d,.]*[BMKbmk]?|(?:bullish|bearish|long|short|buy|sell|overweight|underweight|outperform|underperform))/gi;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  const copy = text;
  while ((match = regex.exec(copy)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={key++}>{copy.slice(lastIndex, match.index)}</span>);
    }
    const word = match[0];
    const lower = word.toLowerCase();
    let cls = 'text-info font-semibold'; // default highlight
    if (lower.includes('%') || word.startsWith('$')) {
      cls = 'text-accent font-semibold';
    }
    if (['bullish', 'long', 'buy', 'overweight', 'outperform'].includes(lower)) {
      cls = 'text-profit font-semibold';
    }
    if (['bearish', 'short', 'sell', 'underweight', 'underperform'].includes(lower)) {
      cls = 'text-loss font-semibold';
    }
    if (word.startsWith('$') && /^[A-Z]/.test(word.slice(1))) {
      cls = 'text-cyan-400 font-mono font-semibold';
    }
    parts.push(<span key={key++} className={cls}>{word}</span>);
    lastIndex = match.index + word.length;
  }
  if (lastIndex < copy.length) {
    parts.push(<span key={key++}>{copy.slice(lastIndex)}</span>);
  }
  return parts;
}


// --- Chain of Thought Component ---
function ChainOfThought({ steps }: { steps: any[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set([steps.length - 1])); // last step open

  const stepIcons: Record<string, string> = {
    planning: '1',
    tool_execution: '2',
    scoring: '3',
    synthesis: '4',
  };

  const stepColors: Record<string, string> = {
    planning: 'border-blue-500/30 bg-blue-500/5',
    tool_execution: 'border-amber-500/30 bg-amber-500/5',
    scoring: 'border-purple-500/30 bg-purple-500/5',
    synthesis: 'border-profit/30 bg-profit/5',
  };

  const toggle = (idx: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      {steps.map((step: any, idx: number) => (
        <div key={idx} className={`rounded-lg border ${stepColors[step.step] || 'border-white/10 bg-dark-700'}`}>
          <button
            onClick={() => toggle(idx)}
            className="w-full flex items-center gap-3 px-3 py-2 text-left"
          >
            <div className="w-5 h-5 rounded-full bg-dark-600 flex items-center justify-center text-[10px] font-bold text-text-secondary shrink-0">
              {stepIcons[step.step] || idx + 1}
            </div>
            <span className="text-xs font-semibold text-text-primary flex-1">{step.title}</span>
            <ChevronDown className={`w-3.5 h-3.5 text-text-muted transition-transform ${expanded.has(idx) ? '' : '-rotate-90'}`} />
          </button>
          {expanded.has(idx) && (
            <div className="px-3 pb-3 pl-11">
              <div className="text-xs text-text-secondary whitespace-pre-wrap leading-relaxed">
                {step.content}
              </div>
              {/* Show tool result data inline */}
              {step.data?.backtest_results?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {step.data.backtest_results.map((tr: any, i: number) => {
                    const results = tr.data?.results || {};
                    return Object.entries(results).map(([ticker, stats]: [string, any]) => (
                      stats && typeof stats === 'object' && stats.win_rate !== undefined && (
                        <div key={`${i}-${ticker}`} className="flex items-center gap-3 p-2 rounded bg-dark-700/50 text-[10px]">
                          <span className="font-mono font-bold text-cyan-400">{ticker}</span>
                          <span className="text-text-muted">{stats.trade_count} trades</span>
                          <span className={stats.win_rate >= 0.55 ? 'text-profit font-semibold' : stats.win_rate < 0.45 ? 'text-loss' : 'text-text-secondary'}>
                            {(stats.win_rate * 100).toFixed(0)}% win
                          </span>
                          <span className={stats.sharpe_ratio >= 1 ? 'text-profit' : stats.sharpe_ratio < 0 ? 'text-loss' : 'text-text-muted'}>
                            Sharpe {stats.sharpe_ratio?.toFixed(2)}
                          </span>
                          <span className="text-text-muted">
                            avg {stats.avg_return_pct?.toFixed(1)}%
                          </span>
                        </div>
                      )
                    ));
                  })}
                </div>
              )}
              {step.data?.fundamental_results?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {step.data.fundamental_results.map((tr: any, i: number) => {
                    if (tr.tool === 'get_fundamentals') {
                      const funds = tr.data?.fundamentals || {};
                      return Object.entries(funds).map(([ticker, info]: [string, any]) => (
                        info && typeof info === 'object' && !info.error && (
                          <div key={`${i}-${ticker}`} className="flex flex-wrap items-center gap-2 p-2 rounded bg-dark-700/50 text-[10px]">
                            <span className="font-mono font-bold text-cyan-400">{ticker}</span>
                            {info.pe_ratio != null && <span className="text-text-secondary">P/E: <span className="text-text-primary font-semibold">{info.pe_ratio?.toFixed(1)}</span></span>}
                            {info.revenue_growth != null && <span className={`${info.revenue_growth > 0 ? 'text-profit' : 'text-loss'}`}>Rev: {(info.revenue_growth * 100)?.toFixed(0)}%</span>}
                            {info.profit_margin != null && <span className="text-text-muted">Margin: {(info.profit_margin * 100)?.toFixed(1)}%</span>}
                            {info.roe != null && <span className="text-text-muted">ROE: {(info.roe * 100)?.toFixed(1)}%</span>}
                          </div>
                        )
                      ));
                    }
                    return null;
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}


export default function IdeasPage() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [generating, setGenerating] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());
  const [autoRunning, setAutoRunning] = useState(false);
  const [autoIterations, setAutoIterations] = useState(0);
  const [autoLoading, setAutoLoading] = useState(false);

  const fetchIdeas = useCallback(async () => {
    try {
      setError(null);
      const data = await ideasAPI.list();
      setIdeas(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch ideas');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAutoStatus = useCallback(async () => {
    try {
      const status = await ideasAPI.autoGenerateStatus();
      setAutoRunning(status.running);
      setAutoIterations(status.iterations);
    } catch {
      // Silently ignore
    }
  }, []);

  useEffect(() => {
    fetchIdeas();
    fetchAutoStatus();
  }, [fetchIdeas, fetchAutoStatus]);

  useEffect(() => {
    if (!autoRunning) return;
    const interval = setInterval(() => {
      fetchIdeas();
      fetchAutoStatus();
    }, 15000);
    return () => clearInterval(interval);
  }, [autoRunning, fetchIdeas, fetchAutoStatus]);

  const getDomainsPayload = (): string[] | undefined => {
    if (selectedDomains.size === 0 || selectedDomains.size === AGENT_DOMAINS.length) return undefined;
    return Array.from(selectedDomains);
  };

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      setError(null);
      const domains = getDomainsPayload();
      await ideasAPI.generate(domains ? { domains } : undefined);
      await fetchIdeas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate ideas');
    } finally {
      setGenerating(false);
    }
  };

  const handleAutoStart = async () => {
    try {
      setAutoLoading(true);
      setError(null);
      const domains = getDomainsPayload();
      const result = await ideasAPI.autoGenerateStart({ interval_seconds: 60, ...(domains ? { domains } : {}) });
      setAutoRunning(result.running);
      setAutoIterations(result.iterations);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start auto-generation');
    } finally {
      setAutoLoading(false);
    }
  };

  const handleAutoStop = async () => {
    try {
      setAutoLoading(true);
      setError(null);
      const result = await ideasAPI.autoGenerateStop();
      setAutoRunning(result.running);
      setAutoIterations(result.iterations);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop auto-generation');
    } finally {
      setAutoLoading(false);
    }
  };

  const toggleDomain = (domain: string) => {
    setSelectedDomains((prev) => {
      const next = new Set(prev);
      if (next.has(domain)) next.delete(domain);
      else next.add(domain);
      return next;
    });
  };

  const handleValidate = async (id: string) => {
    try {
      setActionLoading(id);
      setError(null);
      await ideasAPI.validate(id);
      await fetchIdeas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to validate idea');
    } finally {
      setActionLoading(null);
    }
  };

  const handleExecute = async (id: string) => {
    try {
      setActionLoading(id);
      setError(null);
      await ideasAPI.execute(id);
      await fetchIdeas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute idea');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      setActionLoading(id);
      setError(null);
      await ideasAPI.delete(id);
      if (expandedId === id) setExpandedId(null);
      await fetchIdeas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete idea');
    } finally {
      setActionLoading(null);
    }
  };

  const handleFeedback = async (id: string, vote: 'up' | 'down') => {
    try {
      const result = await ideasAPI.feedback(id, vote);
      // Update idea in local state
      setIdeas(prev => prev.map(idea =>
        idea.id === id
          ? { ...idea, feedback_up: result.total_up, feedback_down: result.total_down }
          : idea
      ));
    } catch (err) {
      console.error('Feedback failed:', err);
    }
  };

  const filteredIdeas = ideas.filter((idea) => {
    if (filter !== 'all' && idea.status !== filter) return false;
    if (searchQuery && !idea.title.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !idea.tickers.some((t) => t.symbol.toLowerCase().includes(searchQuery.toLowerCase())))
      return false;
    return true;
  });

  const stageCounts = pipelineStages.map((stage) => ({
    ...stage,
    count: ideas.filter((i) => i.status === stage.key).length,
  }));

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-info animate-spin" />
          <p className="text-sm text-text-muted">Loading ideas...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Ideas Pipeline</h1>
          <p className="text-sm text-text-muted mt-1">
            AI-generated investment ideas with multi-factor validation
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-primary flex items-center gap-2" onClick={handleGenerate} disabled={generating}>
            {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
            {generating ? 'Generating...' : 'Generate Once'}
          </button>
          {autoRunning ? (
            <button
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-warning/10 text-warning border border-warning/20 hover:bg-warning/20 transition-colors"
              onClick={handleAutoStop} disabled={autoLoading}
            >
              {autoLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Pause className="w-4 h-4" />}
              Pause Auto
              {autoIterations > 0 && <span className="ml-1 text-xs opacity-70">({autoIterations})</span>}
            </button>
          ) : (
            <button
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-profit/10 text-profit border border-profit/20 hover:bg-profit/20 transition-colors"
              onClick={handleAutoStart} disabled={autoLoading}
            >
              {autoLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Auto-Generate
            </button>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-loss/10 border border-loss/20">
          <AlertCircle className="w-5 h-5 text-loss shrink-0" />
          <p className="text-sm text-loss">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-xs text-loss hover:text-loss-light">Dismiss</button>
        </div>
      )}

      {/* Agent Domain Selector */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-primary">Agent Focus</h3>
          <span className="text-xs text-text-muted">
            {selectedDomains.size === 0 ? 'All agents active' : `${selectedDomains.size} of ${AGENT_DOMAINS.length} selected`}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {AGENT_DOMAINS.map((agent) => (
            <button
              key={agent.key}
              onClick={() => toggleDomain(agent.key)}
              className={`rounded-lg p-3 border text-left transition-all ${
                selectedDomains.has(agent.key)
                  ? 'bg-accent/10 border-accent/30 text-accent'
                  : selectedDomains.size === 0
                  ? 'bg-dark-700 border-white/[0.08] text-text-secondary hover:border-white/[0.15]'
                  : 'bg-dark-800 border-white/[0.05] text-text-muted hover:border-white/[0.1]'
              }`}
            >
              <div className="text-xs font-semibold">{agent.label}</div>
              <div className="text-[10px] mt-0.5 opacity-70">{agent.description}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Pipeline Visualization */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Pipeline Overview</h3>
        <div className="flex items-center gap-2">
          {stageCounts.map((stage, idx) => (
            <div key={stage.key} className="flex items-center gap-2 flex-1">
              <div className={`flex-1 rounded-lg p-3 border border-white/[0.05] ${stage.count > 0 ? 'bg-dark-700' : 'bg-dark-800'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2 h-2 rounded-full ${stage.color}`} />
                  <span className="text-xs text-text-muted">{stage.label}</span>
                </div>
                <span className="text-xl font-bold text-text-primary">{stage.count}</span>
              </div>
              {idx < stageCounts.length - 1 && <ChevronRight className="w-4 h-4 text-dark-400 shrink-0" />}
            </div>
          ))}
        </div>
      </div>

      {/* Search & Filter */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text" placeholder="Search ideas by title or ticker..."
            value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
            className="input-field w-full pl-9"
          />
        </div>
        <div className="flex gap-1">
          {statusFilters.map((s) => (
            <button key={s} onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === s ? 'bg-info/10 text-info border border-info/20' : 'text-text-muted hover:text-text-secondary hover:bg-dark-700'
              }`}
            >
              {s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Ideas Table */}
      <div className="card overflow-hidden p-0">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/[0.08]">
              <th className="table-header text-left px-4 py-3 w-8" />
              <th className="table-header text-left px-4 py-3">Title</th>
              <th className="table-header text-left px-4 py-3">Agent</th>
              <th className="table-header text-left px-4 py-3">Tickers</th>
              <th className="table-header text-left px-4 py-3">Status</th>
              <th className="table-header text-right px-4 py-3">Conviction</th>
              <th className="table-header text-left px-4 py-3">Timeframe</th>
              <th className="table-header text-center px-4 py-3">Feedback</th>
              <th className="table-header text-center px-4 py-3 w-12" />
            </tr>
          </thead>
          <tbody>
            {filteredIdeas.map((idea) => (
              <Fragment key={idea.id}>
                <tr
                  onClick={() => setExpandedId(expandedId === idea.id ? null : idea.id)}
                  className="border-b border-white/[0.05] hover:bg-dark-750 cursor-pointer transition-colors"
                >
                  <td className="table-cell">
                    {expandedId === idea.id ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
                  </td>
                  <td className="table-cell">
                    <span className="text-text-primary font-medium">{idea.title}</span>
                  </td>
                  <td className="table-cell">
                    {idea.source_agent ? (
                      <span className={`text-xs font-medium ${agentColors[idea.source_agent] || 'text-text-secondary'}`}>
                        {agentShortNames[idea.source_agent] || idea.source_agent}
                      </span>
                    ) : (
                      <span className="text-xs text-text-muted">{idea.source}</span>
                    )}
                  </td>
                  <td className="table-cell">
                    <div className="flex gap-1">
                      {idea.tickers.map((t) => (
                        <span key={t.symbol} className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-secondary">
                          {t.symbol}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="table-cell">
                    <span className={`status-badge ${statusColors[idea.status] || ''}`}>{idea.status}</span>
                  </td>
                  <td className="table-cell text-right font-mono">
                    <span className={idea.conviction >= 0.7 ? 'text-profit' : idea.conviction >= 0.5 ? 'text-warning' : 'text-loss'}>
                      {(idea.conviction * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="table-cell">
                    <span className="text-xs text-text-muted capitalize">{idea.timeframe.replace('_', ' ')}</span>
                  </td>
                  <td className="table-cell text-center">
                    <div className="flex items-center justify-center gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleFeedback(idea.id, 'up')}
                        className="flex items-center gap-0.5 text-[10px] text-text-muted hover:text-profit transition-colors"
                        title="Thumbs up"
                      >
                        <ThumbsUp className="w-3 h-3" />
                        {idea.feedback_up > 0 && <span className="text-profit font-medium">{idea.feedback_up}</span>}
                      </button>
                      <button
                        onClick={() => handleFeedback(idea.id, 'down')}
                        className="flex items-center gap-0.5 text-[10px] text-text-muted hover:text-loss transition-colors"
                        title="Thumbs down"
                      >
                        <ThumbsDown className="w-3 h-3" />
                        {idea.feedback_down > 0 && <span className="text-loss font-medium">{idea.feedback_down}</span>}
                      </button>
                    </div>
                  </td>
                  <td className="table-cell text-center">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(idea.id); }}
                      disabled={actionLoading === idea.id}
                      className="p-1 rounded hover:bg-loss/10 text-text-muted hover:text-loss transition-colors"
                      title="Delete idea"
                    >
                      {actionLoading === idea.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                  </td>
                </tr>

                {/* Expanded Detail Row */}
                {expandedId === idea.id && (
                  <tr key={`${idea.id}-detail`} className="border-b border-white/[0.05]">
                    <td colSpan={9} className="px-4 py-4 bg-dark-800">
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* LEFT: Thesis + Source Info + Feedback */}
                        <div className="space-y-4">
                          {/* Structured Thesis Section */}
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                                Investment Thesis
                              </h4>
                              {/* Thumbs up/down in thesis section */}
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => handleFeedback(idea.id, 'up')}
                                  className={`flex items-center gap-1 px-2 py-1 rounded-lg border text-xs transition-colors ${
                                    idea.feedback_up > 0
                                      ? 'border-profit/30 bg-profit/10 text-profit'
                                      : 'border-white/10 text-text-muted hover:border-profit/30 hover:text-profit'
                                  }`}
                                >
                                  <ThumbsUp className="w-3.5 h-3.5" />
                                  <span className="font-medium">{idea.feedback_up || 0}</span>
                                </button>
                                <button
                                  onClick={() => handleFeedback(idea.id, 'down')}
                                  className={`flex items-center gap-1 px-2 py-1 rounded-lg border text-xs transition-colors ${
                                    idea.feedback_down > 0
                                      ? 'border-loss/30 bg-loss/10 text-loss'
                                      : 'border-white/10 text-text-muted hover:border-loss/30 hover:text-loss'
                                  }`}
                                >
                                  <ThumbsDown className="w-3.5 h-3.5" />
                                  <span className="font-medium">{idea.feedback_down || 0}</span>
                                </button>
                              </div>
                            </div>

                            {/* One-line summary (first sentence) */}
                            {idea.thesis && (
                              <div className="mb-2 p-2 rounded-lg bg-dark-700 border border-white/[0.06]">
                                <p className="text-sm text-text-primary font-medium leading-relaxed">
                                  {highlightThesis(idea.thesis.split('. ')[0] + '.')}
                                </p>
                              </div>
                            )}

                            {/* Full thesis with highlights */}
                            {idea.thesis && idea.thesis.split('. ').length > 1 && (
                              <p className="text-xs text-text-secondary leading-relaxed">
                                {highlightThesis(idea.thesis.split('. ').slice(1).join('. '))}
                              </p>
                            )}
                          </div>

                          {/* Source Agent Badge */}
                          {idea.source_agent && (
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-text-muted uppercase">Generated by</span>
                              <span className={`text-xs font-semibold ${agentColors[idea.source_agent] || 'text-text-secondary'}`}>
                                {idea.source_agent}
                              </span>
                            </div>
                          )}

                          {/* Source URLs */}
                          {idea.source_urls && idea.source_urls.length > 0 && (
                            <div>
                              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                                Source Inspirations
                              </h4>
                              <div className="space-y-1">
                                {idea.source_urls.slice(0, 5).map((url, idx) => (
                                  <a key={idx} href={url} target="_blank" rel="noopener noreferrer"
                                    className="flex items-center gap-1.5 text-xs text-info hover:text-info-light transition-colors truncate"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <ExternalLink className="w-3 h-3 shrink-0" />
                                    <span className="truncate">{url.replace(/^https?:\/\//, '').split('/').slice(0, 2).join('/')}</span>
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Tags */}
                          {idea.tags && idea.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                              {idea.tags.map((tag) => (
                                <span key={tag} className="px-2 py-0.5 rounded-full bg-dark-500 text-[10px] text-text-muted">{tag}</span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* RIGHT: Validation Results */}
                        <div>
                          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                            Validation Results
                          </h4>
                          {idea.validation_result ? (
                            <div className="space-y-3">
                              {/* Verdict Badge */}
                              {idea.validation_result.verdict && (
                                <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-bold ${verdictColors[idea.validation_result.verdict] || 'text-text-secondary bg-dark-700'}`}>
                                  {idea.validation_result.verdict === 'PASS' ? 'PASS' :
                                   idea.validation_result.verdict === 'FAIL' ? 'FAIL' : 'NEEDS MORE DATA'}
                                  {typeof idea.validation_result.weighted_score === 'number' && (
                                    <span className="font-mono">{(idea.validation_result.weighted_score * 100).toFixed(0)}%</span>
                                  )}
                                </div>
                              )}

                              {/* Key Findings */}
                              {idea.validation_result.key_findings?.length > 0 && (
                                <div className="p-2 rounded-lg bg-dark-700 border border-white/[0.06]">
                                  <h5 className="text-[10px] font-semibold text-text-muted uppercase mb-1">Key Findings</h5>
                                  <ul className="space-y-0.5">
                                    {(idea.validation_result.key_findings as string[]).slice(0, 4).map((finding, idx) => (
                                      <li key={idx} className="text-[11px] text-text-secondary flex items-start gap-1.5">
                                        <span className="text-accent mt-0.5">-</span>
                                        <span>{finding}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Individual Validator Scores */}
                              {idea.validation_result.scores && typeof idea.validation_result.scores === 'object' && (
                                <div className="grid grid-cols-2 gap-2">
                                  {Object.entries(idea.validation_result.scores as Record<string, any>).map(([lens, scoreData]) => {
                                    const score = typeof scoreData === 'object' ? scoreData?.score : scoreData;
                                    const analysis = typeof scoreData === 'object' ? scoreData?.analysis : '';
                                    const scoreNum = typeof score === 'number' ? score : 0.5;
                                    const Icon = lensIcons[lens] || Shield;
                                    return (
                                      <div key={lens} className="p-2.5 rounded-lg bg-dark-700 border border-white/[0.06]">
                                        <div className="flex items-center justify-between mb-1.5">
                                          <div className="flex items-center gap-1.5">
                                            <Icon className="w-3 h-3 text-text-muted" />
                                            <span className="text-[10px] text-text-muted uppercase font-semibold">
                                              {lens.replace(/_/g, ' ')}
                                            </span>
                                          </div>
                                          <span className={`text-xs font-mono font-bold ${
                                            scoreNum >= 0.7 ? 'text-profit' : scoreNum >= 0.5 ? 'text-warning' : 'text-loss'
                                          }`}>
                                            {(scoreNum * 100).toFixed(0)}%
                                          </span>
                                        </div>
                                        <div className="h-1.5 rounded-full bg-dark-500 overflow-hidden">
                                          <div
                                            className={`h-full rounded-full transition-all ${
                                              scoreNum >= 0.7 ? 'bg-profit' : scoreNum >= 0.5 ? 'bg-warning' : 'bg-loss'
                                            }`}
                                            style={{ width: `${scoreNum * 100}%` }}
                                          />
                                        </div>
                                        {analysis && (
                                          <p className="text-[10px] text-text-muted mt-1.5 line-clamp-3 leading-relaxed">
                                            {analysis.split('\n')[0]}
                                          </p>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}

                              {/* Chain of Thought */}
                              {idea.validation_result.chain_of_thought?.length > 0 && (
                                <div>
                                  <h5 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">
                                    Chain of Thought
                                  </h5>
                                  <ChainOfThought steps={idea.validation_result.chain_of_thought} />
                                </div>
                              )}

                              {/* Flags */}
                              {idea.validation_result.flags?.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {(idea.validation_result.flags as string[]).slice(0, 8).map((flag, idx) => (
                                    <span key={idx} className="px-1.5 py-0.5 rounded bg-loss/10 text-[10px] text-loss">
                                      {flag}
                                    </span>
                                  ))}
                                </div>
                              )}

                              {/* Suggested Actions */}
                              {idea.validation_result.suggested_actions?.length > 0 && (
                                <div className="space-y-1">
                                  <h5 className="text-[10px] font-semibold text-text-muted uppercase">Suggested Actions</h5>
                                  {(idea.validation_result.suggested_actions as any[]).map((action, idx) => (
                                    <div key={idx} className="flex items-center gap-2 p-2 rounded-lg bg-dark-700 border border-white/[0.06]">
                                      <span className="text-[10px] text-accent font-medium">{action.label}</span>
                                      <span className="text-[10px] text-text-muted">{action.description}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : (
                            <p className="text-xs text-text-muted">Validation pending...</p>
                          )}

                          {/* Action Buttons */}
                          <div className="flex gap-2 mt-3">
                            {(idea.status === 'generated' || idea.status === 'validated' || idea.status === 'rejected') && (
                              <button
                                className="btn-primary text-xs"
                                onClick={(e) => { e.stopPropagation(); handleValidate(idea.id); }}
                                disabled={actionLoading === idea.id}
                              >
                                {actionLoading === idea.id ? (
                                  <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />Validating...</span>
                                ) : idea.status === 'generated' ? 'Validate' : 'Re-validate'}
                              </button>
                            )}
                            {idea.status === 'validated' && (
                              <button
                                className="btn-success text-xs"
                                onClick={(e) => { e.stopPropagation(); handleExecute(idea.id); }}
                                disabled={actionLoading === idea.id}
                              >
                                {actionLoading === idea.id ? (
                                  <span className="flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />Creating...</span>
                                ) : 'Create Trade'}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>

        {filteredIdeas.length === 0 && (
          <div className="text-center py-12 text-text-muted">
            <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No ideas match your filters</p>
          </div>
        )}
      </div>
    </div>
  );
}
