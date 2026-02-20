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
  'all',
  'generated',
  'validating',
  'validated',
  'rejected',
  'executing',
  'monitoring',
  'closed',
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

const sourceIcons: Record<string, string> = {
  human: '\u{1F464}',
  agent: '\u{1F916}',
};

const AGENT_DOMAINS = [
  { key: 'macro', label: 'Macro', description: 'Fed, rates, inflation, geopolitics' },
  { key: 'industry', label: 'Industry', description: 'Earnings, M&A, sector rotation' },
  { key: 'crypto', label: 'Crypto', description: 'BTC, ETH, DeFi, on-chain' },
  { key: 'quant', label: 'Quant', description: 'Factor, momentum, mean reversion' },
  { key: 'commodities', label: 'Commodities', description: 'Oil, metals, agriculture' },
  { key: 'social', label: 'Social', description: 'Reddit, X sentiment, retail flow' },
] as const;

export default function IdeasPage() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [generating, setGenerating] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Agent domain selection
  const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());

  // Auto-generation state
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
      // Silently ignore — status endpoint may not be available yet
    }
  }, []);

  useEffect(() => {
    fetchIdeas();
    fetchAutoStatus();
  }, [fetchIdeas, fetchAutoStatus]);

  // Poll for new ideas while auto-generation is running
  useEffect(() => {
    if (!autoRunning) return;
    const interval = setInterval(() => {
      fetchIdeas();
      fetchAutoStatus();
    }, 15000);
    return () => clearInterval(interval);
  }, [autoRunning, fetchIdeas, fetchAutoStatus]);

  const getDomainsPayload = (): string[] | undefined => {
    if (selectedDomains.size === 0 || selectedDomains.size === AGENT_DOMAINS.length) {
      return undefined; // all agents
    }
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
      const result = await ideasAPI.autoGenerateStart({
        interval_seconds: 60,
        ...(domains ? { domains } : {}),
      });
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
      if (next.has(domain)) {
        next.delete(domain);
      } else {
        next.add(domain);
      }
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

  const filteredIdeas = ideas.filter((idea) => {
    if (filter !== 'all' && idea.status !== filter) return false;
    if (
      searchQuery &&
      !idea.title.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !idea.tickers.some((t) =>
        t.symbol.toLowerCase().includes(searchQuery.toLowerCase())
      )
    )
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
          {/* Generate Once */}
          <button
            className="btn-primary flex items-center gap-2"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {generating ? 'Generating...' : 'Generate Once'}
          </button>

          {/* Auto-Generate Start / Pause */}
          {autoRunning ? (
            <button
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-warning/10 text-warning border border-warning/20 hover:bg-warning/20 transition-colors"
              onClick={handleAutoStop}
              disabled={autoLoading}
            >
              {autoLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Pause className="w-4 h-4" />
              )}
              Pause Auto
              {autoIterations > 0 && (
                <span className="ml-1 text-xs opacity-70">({autoIterations})</span>
              )}
            </button>
          ) : (
            <button
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-profit/10 text-profit border border-profit/20 hover:bg-profit/20 transition-colors"
              onClick={handleAutoStart}
              disabled={autoLoading}
            >
              {autoLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
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
          <button
            onClick={() => setError(null)}
            className="ml-auto text-xs text-loss hover:text-loss-light"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Agent Domain Selector */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-primary">
            Agent Focus
          </h3>
          <span className="text-xs text-text-muted">
            {selectedDomains.size === 0
              ? 'All agents active'
              : `${selectedDomains.size} of ${AGENT_DOMAINS.length} selected`}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {AGENT_DOMAINS.map((agent) => {
            return (
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
                <div className="text-[10px] mt-0.5 opacity-70">
                  {agent.description}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Pipeline Visualization */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-4">
          Pipeline Overview
        </h3>
        <div className="flex items-center gap-2">
          {stageCounts.map((stage, idx) => (
            <div key={stage.key} className="flex items-center gap-2 flex-1">
              <div
                className={`flex-1 rounded-lg p-3 border border-white/[0.05] ${
                  stage.count > 0 ? 'bg-dark-700' : 'bg-dark-800'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-2 h-2 rounded-full ${stage.color}`} />
                  <span className="text-xs text-text-muted">{stage.label}</span>
                </div>
                <span className="text-xl font-bold text-text-primary">
                  {stage.count}
                </span>
              </div>
              {idx < stageCounts.length - 1 && (
                <ChevronRight className="w-4 h-4 text-dark-400 shrink-0" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Search & Filter */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search ideas by title or ticker..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input-field w-full pl-9"
          />
        </div>
        <div className="flex gap-1">
          {statusFilters.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === s
                  ? 'bg-info/10 text-info border border-info/20'
                  : 'text-text-muted hover:text-text-secondary hover:bg-dark-700'
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
              <th className="table-header text-left px-4 py-3">Source</th>
              <th className="table-header text-left px-4 py-3">Tickers</th>
              <th className="table-header text-left px-4 py-3">Status</th>
              <th className="table-header text-right px-4 py-3">Conviction</th>
              <th className="table-header text-left px-4 py-3">Timeframe</th>
              <th className="table-header text-left px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {filteredIdeas.map((idea) => (
              <Fragment key={idea.id}>
                <tr
                  onClick={() =>
                    setExpandedId(expandedId === idea.id ? null : idea.id)
                  }
                  className="border-b border-white/[0.05] hover:bg-dark-750 cursor-pointer transition-colors"
                >
                  <td className="table-cell">
                    {expandedId === idea.id ? (
                      <ChevronDown className="w-4 h-4 text-text-muted" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-text-muted" />
                    )}
                  </td>
                  <td className="table-cell">
                    <span className="text-text-primary font-medium">
                      {idea.title}
                    </span>
                  </td>
                  <td className="table-cell">
                    <span className="text-sm">
                      {sourceIcons[idea.source] || '\u{1F4C4}'} {idea.source}
                    </span>
                  </td>
                  <td className="table-cell">
                    <div className="flex gap-1">
                      {idea.tickers.map((t) => (
                        <span
                          key={t.symbol}
                          className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-secondary"
                        >
                          {t.symbol}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="table-cell">
                    <span
                      className={`status-badge ${statusColors[idea.status] || ''}`}
                    >
                      {idea.status}
                    </span>
                  </td>
                  <td className="table-cell text-right font-mono">
                    <span
                      className={
                        idea.conviction >= 0.7
                          ? 'text-profit'
                          : idea.conviction >= 0.5
                          ? 'text-warning'
                          : 'text-loss'
                      }
                    >
                      {(idea.conviction * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="table-cell">
                    <span className="text-xs text-text-muted capitalize">
                      {idea.timeframe.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="table-cell">
                    <span className="text-xs text-text-muted">
                      {new Date(idea.created_at).toLocaleDateString()}
                    </span>
                  </td>
                </tr>
                {expandedId === idea.id && (
                  <tr key={`${idea.id}-detail`} className="border-b border-white/[0.05]">
                    <td colSpan={8} className="px-4 py-4 bg-dark-800">
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {/* Thesis */}
                        <div>
                          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                            Investment Thesis
                          </h4>
                          <p className="text-sm text-text-secondary leading-relaxed">
                            {idea.thesis}
                          </p>
                          {idea.tags && idea.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-3">
                              {idea.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="px-2 py-0.5 rounded-full bg-dark-500 text-[10px] text-text-muted"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                          {idea.notes && (
                            <div className="mt-3">
                              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1">
                                Notes
                              </h4>
                              <p className="text-xs text-text-muted leading-relaxed">
                                {idea.notes}
                              </p>
                            </div>
                          )}
                        </div>

                        {/* Validation Results */}
                        <div>
                          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                            Validation Results
                          </h4>
                          {idea.validation_result ? (
                            <div className="grid grid-cols-2 gap-2">
                              {Object.entries(idea.validation_result).map(
                                ([key, value]) => (
                                  <div
                                    key={key}
                                    className="p-2 rounded-lg bg-dark-700"
                                  >
                                    <span className="text-[10px] text-text-muted uppercase">
                                      {key.replace(/_/g, ' ')}
                                    </span>
                                    <p className="text-sm font-semibold text-text-primary mt-0.5">
                                      {typeof value === 'number'
                                        ? (value * 100).toFixed(0) + '%'
                                        : String(value)}
                                    </p>
                                  </div>
                                )
                              )}
                            </div>
                          ) : (
                            <p className="text-xs text-text-muted">
                              Validation pending...
                            </p>
                          )}
                          <div className="flex gap-2 mt-3">
                            {idea.status === 'generated' && (
                              <button
                                className="btn-primary text-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleValidate(idea.id);
                                }}
                                disabled={actionLoading === idea.id}
                              >
                                {actionLoading === idea.id ? (
                                  <span className="flex items-center gap-1">
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                    Validating...
                                  </span>
                                ) : (
                                  'Validate'
                                )}
                              </button>
                            )}
                            {idea.status === 'validated' && (
                              <button
                                className="btn-success text-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleExecute(idea.id);
                                }}
                                disabled={actionLoading === idea.id}
                              >
                                {actionLoading === idea.id ? (
                                  <span className="flex items-center gap-1">
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                    Creating...
                                  </span>
                                ) : (
                                  'Create Trade'
                                )}
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
