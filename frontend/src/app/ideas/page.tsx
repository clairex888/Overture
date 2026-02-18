'use client';

import { useState, useEffect, useCallback, Fragment } from 'react';
import {
  Lightbulb,
  Search,
  ChevronDown,
  ChevronRight,
  Zap,
  Filter,
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
  human: '👤',
  agent: '🤖',
};

export default function IdeasPage() {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [generating, setGenerating] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

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

  useEffect(() => {
    fetchIdeas();
  }, [fetchIdeas]);

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      setError(null);
      await ideasAPI.generate();
      await fetchIdeas();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate ideas');
    } finally {
      setGenerating(false);
    }
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
          <button className="btn-secondary flex items-center gap-2">
            <Filter className="w-4 h-4" />
            Advanced Filters
          </button>
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
            {generating ? 'Generating...' : 'Generate Ideas'}
          </button>
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
                      {sourceIcons[idea.source] || '📄'} {idea.source}
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
