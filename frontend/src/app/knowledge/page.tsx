'use client';

import { useState, useEffect } from 'react';
import {
  BookOpen,
  Database,
  Layers,
  Search,
  RefreshCw,
  ExternalLink,
  Star,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowUp,
  ArrowDown,
  GraduationCap,
  Zap,
  Clock,
  Tag,
  Shield,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { knowledgeAPI } from '@/lib/api';
import type {
  KnowledgeEntry,
  SourceCredibility,
  MarketOutlook,
  EducationalContent,
  OutlookLayer,
} from '@/types';

type LayerType = 'long_term' | 'medium_term' | 'short_term';

const sentimentColors: Record<string, string> = {
  bullish: 'text-profit',
  neutral: 'text-warning',
  bearish: 'text-loss',
  Bullish: 'text-profit',
  Neutral: 'text-warning',
  Bearish: 'text-loss',
};

const sentimentIcons: Record<string, typeof ArrowUp> = {
  bullish: ArrowUp,
  neutral: Minus,
  bearish: ArrowDown,
  Bullish: ArrowUp,
  Neutral: Minus,
  Bearish: ArrowDown,
};

const categoryColors: Record<string, string> = {
  'Macro Thesis': 'text-info bg-info-muted',
  'Sector Thesis': 'text-accent bg-accent-muted',
  'Sector Analysis': 'text-accent bg-accent-muted',
  'Risk Factor': 'text-loss bg-loss-muted',
  'Monetary Policy': 'text-warning bg-warning-muted',
  'Market Analysis': 'text-info bg-info-muted',
  Earnings: 'text-profit bg-profit-muted',
  Volatility: 'text-warning bg-warning-muted',
  'Flow Analysis': 'text-accent bg-accent-muted',
};

const difficultyColors: Record<string, string> = {
  Beginner: 'text-profit bg-profit-muted',
  beginner: 'text-profit bg-profit-muted',
  Intermediate: 'text-warning bg-warning-muted',
  intermediate: 'text-warning bg-warning-muted',
  Advanced: 'text-loss bg-loss-muted',
  advanced: 'text-loss bg-loss-muted',
};

const layerLabels: Record<string, string> = {
  long_term: 'Long-term',
  medium_term: 'Medium-term',
  short_term: 'Short-term',
};

export default function KnowledgePage() {
  const [activeLayer, setActiveLayer] = useState<LayerType>('short_term');
  const [searchQuery, setSearchQuery] = useState('');

  const [knowledgeEntries, setKnowledgeEntries] = useState<KnowledgeEntry[]>([]);
  const [sourceRankings, setSourceRankings] = useState<SourceCredibility[]>([]);
  const [marketOutlook, setMarketOutlook] = useState<MarketOutlook | null>(null);
  const [educationContent, setEducationContent] = useState<EducationalContent[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);
  const [pipelineLoading, setPipelineLoading] = useState(false);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      setError(null);
      try {
        const [entries, sources, outlook, education] = await Promise.all([
          knowledgeAPI.list(),
          knowledgeAPI.sources(),
          knowledgeAPI.outlook(),
          knowledgeAPI.education(),
        ]);
        setKnowledgeEntries(entries);
        setSourceRankings(sources);
        setMarketOutlook(outlook);
        setEducationContent(education);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load knowledge data');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const handleTriggerPipeline = async () => {
    setPipelineLoading(true);
    setPipelineStatus(null);
    try {
      const result = await knowledgeAPI.triggerPipeline();
      setPipelineStatus(result.message || 'Pipeline triggered successfully');
    } catch (err) {
      setPipelineStatus(err instanceof Error ? err.message : 'Failed to trigger pipeline');
    } finally {
      setPipelineLoading(false);
    }
  };

  const layers: { key: LayerType; label: string; icon: typeof Layers }[] = [
    { key: 'long_term', label: 'Long-term', icon: Layers },
    { key: 'medium_term', label: 'Medium-term', icon: Clock },
    { key: 'short_term', label: 'Short-term', icon: Zap },
  ];

  const filteredEntries = knowledgeEntries.filter((entry) => {
    if (entry.layer !== activeLayer) return false;
    if (
      searchQuery &&
      !entry.title.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !entry.content.toLowerCase().includes(searchQuery.toLowerCase())
    )
      return false;
    return true;
  });

  const outlookLayers: { key: LayerType; label: string; data: OutlookLayer | null }[] = marketOutlook
    ? [
        { key: 'long_term', label: 'Long-term', data: marketOutlook.long_term },
        { key: 'medium_term', label: 'Medium-term', data: marketOutlook.medium_term },
        { key: 'short_term', label: 'Short-term', data: marketOutlook.short_term },
      ]
    : [];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin text-info" />
          <p className="text-sm text-text-muted">Loading knowledge base...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <AlertCircle className="w-8 h-8 text-loss" />
          <p className="text-sm text-loss">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary flex items-center gap-2 text-sm"
          >
            <RefreshCw className="w-4 h-4" />
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
          <h1 className="text-2xl font-bold text-text-primary">Knowledge Base</h1>
          <p className="text-sm text-text-muted mt-1">
            Multi-layer knowledge graph with source credibility tracking
          </p>
        </div>
        <div className="flex items-center gap-3">
          {pipelineStatus && (
            <span className="text-xs text-text-secondary">{pipelineStatus}</span>
          )}
          <button
            className="btn-primary flex items-center gap-2"
            onClick={handleTriggerPipeline}
            disabled={pipelineLoading}
          >
            {pipelineLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Database className="w-4 h-4" />
            )}
            Trigger Data Pipeline
          </button>
        </div>
      </div>

      {/* Layer Tabs + Search */}
      <div className="flex items-center gap-4">
        <div className="flex gap-1 bg-dark-800 p-1 rounded-lg border border-white/[0.08]">
          {layers.map((layer) => {
            const Icon = layer.icon;
            const count = knowledgeEntries.filter((e) => e.layer === layer.key).length;
            return (
              <button
                key={layer.key}
                onClick={() => setActiveLayer(layer.key)}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-xs font-medium transition-colors ${
                  activeLayer === layer.key
                    ? 'bg-info/10 text-info border border-info/20'
                    : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {layer.label}
                <span
                  className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                    activeLayer === layer.key ? 'bg-info/20 text-info' : 'bg-dark-500 text-text-muted'
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search knowledge entries..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input-field w-full pl-9"
          />
        </div>
      </div>

      {/* Knowledge Entries */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-4">
          {layers.find((l) => l.key === activeLayer)?.label} Knowledge
        </h3>
        <div className="space-y-3">
          {filteredEntries.map((entry) => {
            const confidencePct = Math.round(entry.confidence * 100);
            return (
              <div
                key={entry.id}
                className="p-4 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1.5">
                      <h4 className="text-sm font-medium text-text-primary">{entry.title}</h4>
                      <span
                        className={`status-badge text-[10px] ${
                          categoryColors[entry.category] || 'text-text-secondary bg-dark-500'
                        }`}
                      >
                        {entry.category}
                      </span>
                    </div>
                    <p className="text-xs text-text-secondary leading-relaxed mb-2">
                      {entry.content}
                    </p>
                    <div className="flex items-center gap-4 text-[11px] text-text-muted">
                      <span className="flex items-center gap-1">
                        <ExternalLink className="w-3 h-3" />
                        {entry.source}
                      </span>
                      <span className="flex items-center gap-1">
                        <Star className="w-3 h-3" />
                        Confidence: {confidencePct}/100
                      </span>
                      <span>
                        {new Date(entry.created_at).toLocaleDateString()}{' '}
                        {new Date(entry.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                      {entry.tags.length > 0 && (
                        <span className="flex items-center gap-1">
                          <Tag className="w-3 h-3" />
                          {entry.tags.join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 flex flex-col items-center">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold ${
                        confidencePct >= 90
                          ? 'bg-profit-muted text-profit'
                          : confidencePct >= 80
                          ? 'bg-info-muted text-info'
                          : 'bg-warning-muted text-warning'
                      }`}
                    >
                      {confidencePct}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
          {filteredEntries.length === 0 && (
            <div className="text-center py-8 text-text-muted">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No entries match your search</p>
            </div>
          )}
        </div>
      </div>

      {/* Source Rankings + Market Outlook */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Source Credibility Rankings */}
        <div className="card overflow-hidden p-0">
          <div className="px-4 py-3 border-b border-white/[0.08]">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
              <Shield className="w-4 h-4 text-info" />
              Source Credibility Rankings
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/[0.08]">
                  <th className="table-header text-left px-4 py-3">Source</th>
                  <th className="table-header text-right px-4 py-3">Score</th>
                  <th className="table-header text-right px-4 py-3">Entries</th>
                  <th className="table-header text-right px-4 py-3">Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {sourceRankings.map((source) => {
                  const score = Math.round(source.credibility_score * 100);
                  const accuracy = Math.round(source.accuracy_history * 100);
                  return (
                    <tr
                      key={source.name}
                      className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                    >
                      <td className="table-cell">
                        <div>
                          <span className="text-text-primary text-xs font-medium">
                            {source.name}
                          </span>
                          <span className="text-[10px] text-text-muted ml-2">{source.type}</span>
                        </div>
                      </td>
                      <td className="table-cell text-right">
                        <span
                          className={`font-mono font-medium text-xs ${
                            score >= 90
                              ? 'text-profit'
                              : score >= 85
                              ? 'text-info'
                              : 'text-warning'
                          }`}
                        >
                          {score}
                        </span>
                      </td>
                      <td className="table-cell text-right font-mono text-xs">
                        {source.total_entries}
                      </td>
                      <td className="table-cell text-right font-mono text-xs">
                        <span className={accuracy >= 65 ? 'text-profit' : 'text-text-secondary'}>
                          {accuracy}%
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {sourceRankings.length === 0 && (
                  <tr>
                    <td colSpan={4} className="text-center py-6 text-text-muted text-xs">
                      No source data available
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Market Outlook */}
        <div className="space-y-6">
          <div className="card">
            <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-profit" />
              Market Outlook by Layer
            </h3>
            <div className="space-y-3">
              {outlookLayers.map((item) => {
                if (!item.data) return null;
                const sentiment = item.data.sentiment;
                const sentimentKey = sentiment.charAt(0).toUpperCase() + sentiment.slice(1).toLowerCase();
                const SentimentIcon = sentimentIcons[sentiment] || sentimentIcons[sentimentKey] || Minus;
                const sentimentColor = sentimentColors[sentiment] || sentimentColors[sentimentKey] || 'text-text-secondary';
                const confidencePct = Math.round(item.data.confidence * 100);
                return (
                  <div
                    key={item.key}
                    className="p-3 rounded-lg bg-dark-800 border border-white/[0.05]"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-medium text-text-primary">{item.label}</span>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-semibold ${sentimentColor}`}>
                          {sentimentKey}
                        </span>
                        <SentimentIcon className={`w-3.5 h-3.5 ${sentimentColor}`} />
                        <span className="text-[10px] text-text-muted">{confidencePct}%</span>
                      </div>
                    </div>
                    <p className="text-[11px] text-text-muted mb-2">{item.data.summary}</p>
                    {item.data.key_factors.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1">
                        {item.data.key_factors.map((factor, idx) => (
                          <span
                            key={idx}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-dark-600 text-text-secondary"
                          >
                            {factor}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 w-full bg-dark-600 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${
                          sentiment.toLowerCase() === 'bullish'
                            ? 'bg-profit'
                            : sentiment.toLowerCase() === 'neutral'
                            ? 'bg-warning'
                            : 'bg-loss'
                        }`}
                        style={{ width: `${confidencePct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
              {outlookLayers.length === 0 && (
                <div className="text-center py-6 text-text-muted">
                  <p className="text-xs">No market outlook data available</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Learning Recommendations */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
          <GraduationCap className="w-4 h-4 text-accent" />
          Learning Recommendations
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {educationContent.map((rec) => {
            const difficultyKey =
              rec.difficulty.charAt(0).toUpperCase() + rec.difficulty.slice(1).toLowerCase();
            return (
              <div
                key={rec.id}
                className="p-4 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors cursor-pointer"
              >
                <div className="flex items-start justify-between mb-2">
                  <h4 className="text-sm font-medium text-text-primary flex-1">{rec.title}</h4>
                  <span
                    className={`status-badge text-[10px] ml-2 shrink-0 ${
                      difficultyColors[rec.difficulty] ||
                      difficultyColors[difficultyKey] ||
                      'text-text-secondary bg-dark-500'
                    }`}
                  >
                    {difficultyKey}
                  </span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed mb-3">{rec.summary}</p>
                <div className="flex items-center gap-3 text-[11px] text-text-muted">
                  <span className="flex items-center gap-1">
                    <Tag className="w-3 h-3" />
                    {rec.category}
                  </span>
                  <span className="flex items-center gap-1">
                    <Star className="w-3 h-3" />
                    Relevance: {Math.round(rec.relevance_score * 100)}%
                  </span>
                  {rec.url && (
                    <a
                      href={rec.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-info hover:underline"
                    >
                      <ExternalLink className="w-3 h-3" />
                      Link
                    </a>
                  )}
                </div>
              </div>
            );
          })}
          {educationContent.length === 0 && (
            <div className="col-span-2 text-center py-8 text-text-muted">
              <GraduationCap className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No learning recommendations available</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
