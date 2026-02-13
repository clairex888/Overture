'use client';

import { useState } from 'react';
import {
  Lightbulb,
  Search,
  Plus,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Zap,
  Clock,
  Filter,
} from 'lucide-react';
import type { Idea } from '@/types';

// --- Mock Data ---

const mockIdeas: Idea[] = [
  {
    id: '1',
    title: 'Long NVDA on AI Capex Cycle',
    description: 'NVIDIA positioned to benefit from accelerating AI infrastructure spending across hyperscalers.',
    source: 'agent',
    asset_class: 'equity',
    tickers: ['NVDA'],
    thesis: 'Hyperscaler capex guidance indicates 40%+ YoY growth in AI infrastructure. NVDA maintains 80%+ GPU market share with H100/B100 chips. Data center revenue expected to grow 100%+ YoY. Key risk: AMD MI300X adoption and custom silicon from Google/Amazon.',
    status: 'validated',
    confidence_score: 0.87,
    expected_return: 0.18,
    risk_level: 'medium',
    timeframe: 'medium_term',
    validation_results: {
      fundamental_score: 0.91,
      technical_score: 0.78,
      sentiment_score: 0.85,
      risk_adjusted_return: 0.14,
    },
    created_at: '2025-04-20T14:30:00Z',
    updated_at: '2025-04-20T16:45:00Z',
  },
  {
    id: '2',
    title: 'Short Regional Banks (KRE)',
    description: 'Commercial real estate exposure creating downside risk for regional banks.',
    source: 'news',
    asset_class: 'etf',
    tickers: ['KRE'],
    thesis: 'CRE loan maturity wall approaching with 30%+ of regional bank loans in commercial real estate. Office vacancy rates at record 19.6%. Potential for significant loan loss provisions in coming quarters.',
    status: 'validating',
    confidence_score: 0.72,
    expected_return: 0.12,
    risk_level: 'high',
    timeframe: 'short_term',
    created_at: '2025-04-20T10:00:00Z',
    updated_at: '2025-04-20T12:30:00Z',
  },
  {
    id: '3',
    title: 'Long Gold (GLD) on Rate Cut Cycle',
    description: 'Gold likely to benefit from expected Fed rate cuts and geopolitical uncertainty.',
    source: 'agent',
    asset_class: 'commodity',
    tickers: ['GLD', 'GDX'],
    thesis: 'Historical correlation between rate cuts and gold prices is strong. Central bank buying at record levels. Geopolitical risk premium likely to persist. Real yields declining as inflation expectations moderate.',
    status: 'executing',
    confidence_score: 0.81,
    expected_return: 0.15,
    risk_level: 'low',
    timeframe: 'long_term',
    validation_results: {
      fundamental_score: 0.85,
      technical_score: 0.82,
      sentiment_score: 0.76,
      risk_adjusted_return: 0.19,
    },
    created_at: '2025-04-19T08:00:00Z',
    updated_at: '2025-04-20T09:00:00Z',
  },
  {
    id: '4',
    title: 'Pairs Trade: MSFT Long / ORCL Short',
    description: 'Cloud market share divergence creating relative value opportunity.',
    source: 'screen',
    asset_class: 'equity',
    tickers: ['MSFT', 'ORCL'],
    thesis: 'Azure growing 29% vs OCI growing 12%. Valuation gap not reflecting growth differential. MSFT AI integration (Copilot) creating additional growth runway. ORCL overvalued on cloud transition narrative.',
    status: 'generated',
    confidence_score: 0.65,
    expected_return: 0.08,
    risk_level: 'medium',
    timeframe: 'medium_term',
    created_at: '2025-04-20T16:00:00Z',
    updated_at: '2025-04-20T16:00:00Z',
  },
  {
    id: '5',
    title: 'Long TSMC on Semiconductor Supercycle',
    description: 'Taiwan Semiconductor poised to benefit from AI chip demand surge.',
    source: 'agent',
    asset_class: 'equity',
    tickers: ['TSM'],
    thesis: 'Advanced node (3nm, 2nm) capacity fully booked through 2026. AI accelerator demand driving 20%+ revenue growth. CoWoS advanced packaging is key bottleneck giving TSMC pricing power.',
    status: 'monitoring',
    confidence_score: 0.79,
    expected_return: 0.22,
    risk_level: 'high',
    timeframe: 'long_term',
    validation_results: {
      fundamental_score: 0.88,
      technical_score: 0.71,
      sentiment_score: 0.80,
      risk_adjusted_return: 0.12,
    },
    created_at: '2025-04-15T10:00:00Z',
    updated_at: '2025-04-20T08:00:00Z',
  },
  {
    id: '6',
    title: 'Short Treasury Bonds (TLT)',
    description: 'Fiscal deficit and supply concerns to pressure long-duration Treasuries.',
    source: 'user',
    asset_class: 'etf',
    tickers: ['TLT'],
    thesis: 'US fiscal deficit projected at $1.9T. Treasury issuance increasing while Fed continues QT. Term premium should rise as market demands higher compensation for duration risk.',
    status: 'rejected',
    confidence_score: 0.45,
    expected_return: 0.06,
    risk_level: 'high',
    timeframe: 'medium_term',
    validation_results: {
      fundamental_score: 0.52,
      technical_score: 0.38,
      sentiment_score: 0.41,
      risk_adjusted_return: 0.03,
    },
    created_at: '2025-04-18T14:00:00Z',
    updated_at: '2025-04-19T10:00:00Z',
  },
  {
    id: '7',
    title: 'Long SPY Put Spread for Tail Risk',
    description: 'Hedging portfolio with SPY put spreads ahead of FOMC and earnings season.',
    source: 'agent',
    asset_class: 'equity',
    tickers: ['SPY'],
    thesis: 'VIX at historically low levels makes put protection cheap. Concentration risk in mag-7 stocks. Event calendar loaded with FOMC, major earnings, and geopolitical catalysts.',
    status: 'validated',
    confidence_score: 0.74,
    expected_return: -0.02,
    risk_level: 'low',
    timeframe: 'short_term',
    validation_results: {
      fundamental_score: 0.70,
      technical_score: 0.80,
      sentiment_score: 0.68,
      risk_adjusted_return: 0.08,
    },
    created_at: '2025-04-20T11:00:00Z',
    updated_at: '2025-04-20T14:00:00Z',
  },
  {
    id: '8',
    title: 'Long Uranium (URA) on Nuclear Renaissance',
    description: 'Nuclear energy demand surge driven by AI data center power needs.',
    source: 'news',
    asset_class: 'etf',
    tickers: ['URA', 'CCJ'],
    thesis: 'AI data centers projected to consume 8% of US electricity by 2030. Multiple tech companies signing nuclear PPAs. Uranium spot price trending higher with constrained supply.',
    status: 'closed',
    confidence_score: 0.83,
    expected_return: 0.25,
    risk_level: 'high',
    timeframe: 'long_term',
    created_at: '2025-03-01T10:00:00Z',
    updated_at: '2025-04-15T16:00:00Z',
  },
];

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

const riskColors: Record<string, string> = {
  low: 'text-profit',
  medium: 'text-warning',
  high: 'text-loss',
  extreme: 'text-loss-light',
};

const sourceIcons: Record<string, string> = {
  news: '📰',
  screen: '📊',
  agent: '🤖',
  user: '👤',
  aggregated: '🔗',
};

export default function IdeasPage() {
  const [filter, setFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredIdeas = mockIdeas.filter((idea) => {
    if (filter !== 'all' && idea.status !== filter) return false;
    if (
      searchQuery &&
      !idea.title.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !idea.tickers.some((t) =>
        t.toLowerCase().includes(searchQuery.toLowerCase())
      )
    )
      return false;
    return true;
  });

  const stageCounts = pipelineStages.map((stage) => ({
    ...stage,
    count: mockIdeas.filter((i) => i.status === stage.key).length,
  }));

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
          <button className="btn-primary flex items-center gap-2">
            <Zap className="w-4 h-4" />
            Generate Ideas
          </button>
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
              <th className="table-header text-right px-4 py-3">Confidence</th>
              <th className="table-header text-right px-4 py-3">Exp. Return</th>
              <th className="table-header text-center px-4 py-3">Risk</th>
              <th className="table-header text-left px-4 py-3">Timeframe</th>
              <th className="table-header text-left px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {filteredIdeas.map((idea) => (
              <>
                <tr
                  key={idea.id}
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
                      {sourceIcons[idea.source]} {idea.source}
                    </span>
                  </td>
                  <td className="table-cell">
                    <div className="flex gap-1">
                      {idea.tickers.map((t) => (
                        <span
                          key={t}
                          className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-secondary"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="table-cell">
                    <span
                      className={`status-badge ${statusColors[idea.status]}`}
                    >
                      {idea.status}
                    </span>
                  </td>
                  <td className="table-cell text-right font-mono">
                    <span
                      className={
                        idea.confidence_score >= 0.7
                          ? 'text-profit'
                          : idea.confidence_score >= 0.5
                          ? 'text-warning'
                          : 'text-loss'
                      }
                    >
                      {(idea.confidence_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="table-cell text-right font-mono">
                    {idea.expected_return !== undefined && (
                      <span
                        className={
                          idea.expected_return >= 0 ? 'text-profit' : 'text-loss'
                        }
                      >
                        {idea.expected_return >= 0 ? '+' : ''}
                        {(idea.expected_return * 100).toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td className="table-cell text-center">
                    <span className={`text-xs font-medium ${riskColors[idea.risk_level]}`}>
                      {idea.risk_level}
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
                    <td colSpan={10} className="px-4 py-4 bg-dark-800">
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {/* Thesis */}
                        <div>
                          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                            Investment Thesis
                          </h4>
                          <p className="text-sm text-text-secondary leading-relaxed">
                            {idea.thesis}
                          </p>
                          {idea.source_url && (
                            <a
                              href={idea.source_url}
                              className="inline-flex items-center gap-1 text-xs text-info mt-2 hover:text-info-light"
                            >
                              Source <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>

                        {/* Validation Results */}
                        <div>
                          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                            Validation Results
                          </h4>
                          {idea.validation_results ? (
                            <div className="grid grid-cols-2 gap-2">
                              {Object.entries(idea.validation_results).map(
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
                              <button className="btn-primary text-xs">
                                Validate
                              </button>
                            )}
                            {idea.status === 'validated' && (
                              <button className="btn-success text-xs">
                                Create Trade
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
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
