'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  BookOpen,
  Database,
  Layers,
  Search,
  RefreshCw,
  ExternalLink,
  Star,
  TrendingUp,
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
  Upload,
  FileText,
  Lock,
  Unlock,
  Trash2,
  X,
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
};

const sentimentIcons: Record<string, typeof ArrowUp> = {
  bullish: ArrowUp,
  neutral: Minus,
  bearish: ArrowDown,
};

const categoryColors: Record<string, string> = {
  macro: 'text-info bg-info/10',
  fundamental: 'text-accent bg-accent/10',
  technical: 'text-warning bg-warning/10',
  research: 'text-profit bg-profit/10',
  event: 'text-loss bg-loss/10',
  education: 'text-info bg-info/10',
  sentiment: 'text-accent bg-accent/10',
  'Macro Thesis': 'text-info bg-info/10',
  'Sector Thesis': 'text-accent bg-accent/10',
  'Sector Analysis': 'text-accent bg-accent/10',
  'Risk Factor': 'text-loss bg-loss/10',
  'Monetary Policy': 'text-warning bg-warning/10',
  'Market Analysis': 'text-info bg-info/10',
  Earnings: 'text-profit bg-profit/10',
  Volatility: 'text-warning bg-warning/10',
  'Flow Analysis': 'text-accent bg-accent/10',
};

const difficultyColors: Record<string, string> = {
  beginner: 'text-profit bg-profit/10',
  intermediate: 'text-warning bg-warning/10',
  advanced: 'text-loss bg-loss/10',
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
  const [pipelineLoading, setPipelineLoading] = useState(false);

  // Upload state
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadLayer, setUploadLayer] = useState<string>('medium_term');
  const [uploadCategory, setUploadCategory] = useState<string>('research');
  const [uploadPublic, setUploadPublic] = useState(true);
  const [uploadTags, setUploadTags] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Document viewer state
  const [viewingEntry, setViewingEntry] = useState<KnowledgeEntry | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.allSettled([
        knowledgeAPI.list(),
        knowledgeAPI.sources(),
        knowledgeAPI.outlook(),
        knowledgeAPI.education(),
      ]);
      const [entriesR, sourcesR, outlookR, educationR] = results;
      if (entriesR.status === 'fulfilled') setKnowledgeEntries(entriesR.value);
      if (sourcesR.status === 'fulfilled') setSourceRankings(sourcesR.value);
      if (outlookR.status === 'fulfilled') setMarketOutlook(outlookR.value);
      if (educationR.status === 'fulfilled') setEducationContent(educationR.value);
      const allFailed = results.every((r) => r.status === 'rejected');
      if (allFailed) {
        const firstErr = results.find((r) => r.status === 'rejected') as PromiseRejectedResult;
        throw firstErr.reason;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load knowledge data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleTriggerPipeline = async () => {
    setPipelineLoading(true);
    try {
      await knowledgeAPI.triggerPipeline();
      await fetchData();
    } catch {
      // Pipeline trigger is non-critical
    } finally {
      setPipelineLoading(false);
    }
  };

  // File upload handlers
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setUploadFile(file);
      setUploadTitle(file.name.replace(/\.[^.]+$/, ''));
      setShowUpload(true);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
      setUploadTitle(file.name.replace(/\.[^.]+$/, ''));
      setShowUpload(true);
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;
    setUploading(true);
    setUploadError(null);
    try {
      await knowledgeAPI.upload(uploadFile, {
        title: uploadTitle,
        layer: uploadLayer,
        category: uploadCategory,
        is_public: uploadPublic,
        tags: uploadTags,
      });
      setShowUpload(false);
      setUploadFile(null);
      setUploadTitle('');
      setUploadTags('');
      await fetchData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('401') || msg.includes('unauthorized') || msg.includes('Unauthorized')) {
        setUploadError('Please log in first to upload documents.');
      } else if (msg.includes('413')) {
        setUploadError('File is too large (max 10 MB).');
      } else if (msg.includes('400')) {
        setUploadError('Could not extract text from file. Try a different format (PDF, TXT, MD, CSV).');
      } else {
        setUploadError(msg || 'Upload failed. Please try again.');
      }
    } finally {
      setUploading(false);
    }
  };

  const handleTogglePrivacy = async (entry: KnowledgeEntry) => {
    try {
      await knowledgeAPI.togglePrivacy(entry.id, !entry.is_public);
      await fetchData();
    } catch {
      // silent
    }
  };

  const handleDelete = async (entry: KnowledgeEntry) => {
    if (!window.confirm(`Delete "${entry.title}"?`)) return;
    try {
      await knowledgeAPI.delete(entry.id);
      await fetchData();
    } catch {
      // silent
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
            Multi-layer knowledge library with source credibility tracking
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            className="btn-secondary flex items-center gap-2"
            onClick={() => {
              setShowUpload(true);
              setUploadFile(null);
              setUploadTitle('');
            }}
          >
            <Upload className="w-4 h-4" />
            Upload
          </button>
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

      {/* Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors cursor-pointer ${
          dragOver
            ? 'border-info bg-info/5'
            : 'border-white/[0.1] hover:border-white/[0.2]'
        }`}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".txt,.md,.csv,.pdf"
          onChange={handleFileSelect}
        />
        <div className="flex items-center justify-center gap-3">
          <FileText className={`w-5 h-5 ${dragOver ? 'text-info' : 'text-text-muted'}`} />
          <span className={`text-sm ${dragOver ? 'text-info' : 'text-text-muted'}`}>
            Drop files here or click to upload (TXT, MD, CSV, PDF)
          </span>
        </div>
      </div>

      {/* Upload Modal */}
      {showUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-dark-800 rounded-xl border border-white/[0.1] p-6 w-full max-w-lg mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-text-primary">Upload to Knowledge Library</h3>
              <button onClick={() => setShowUpload(false)} className="text-text-muted hover:text-text-primary">
                <X className="w-5 h-5" />
              </button>
            </div>

            {uploadFile ? (
              <div className="flex items-center gap-2 mb-4 p-3 rounded-lg bg-dark-700 border border-white/[0.05]">
                <FileText className="w-4 h-4 text-info" />
                <span className="text-sm text-text-primary truncate">{uploadFile.name}</span>
                <span className="text-xs text-text-muted ml-auto">
                  {(uploadFile.size / 1024).toFixed(1)} KB
                </span>
              </div>
            ) : (
              <div
                className="mb-4 p-8 rounded-lg border-2 border-dashed border-white/[0.1] text-center cursor-pointer hover:border-white/[0.2]"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="w-8 h-8 mx-auto mb-2 text-text-muted" />
                <p className="text-sm text-text-muted">Click to select a file</p>
              </div>
            )}

            <div className="space-y-3">
              <div>
                <label className="text-xs text-text-muted mb-1 block">Title</label>
                <input
                  className="input-field w-full"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  placeholder="Entry title"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-text-muted mb-1 block">Time Horizon</label>
                  <select
                    className="input-field w-full"
                    value={uploadLayer}
                    onChange={(e) => setUploadLayer(e.target.value)}
                  >
                    <option value="long_term">Long-term (5-10yr)</option>
                    <option value="medium_term">Medium-term (1-3yr)</option>
                    <option value="short_term">Short-term (tactical)</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-text-muted mb-1 block">Category</label>
                  <select
                    className="input-field w-full"
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value)}
                  >
                    <option value="research">Research</option>
                    <option value="macro">Macro</option>
                    <option value="fundamental">Fundamental</option>
                    <option value="technical">Technical</option>
                    <option value="event">Event / News</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-text-muted mb-1 block">Tags (comma-separated)</label>
                <input
                  className="input-field w-full"
                  value={uploadTags}
                  onChange={(e) => setUploadTags(e.target.value)}
                  placeholder="e.g. AI, semiconductors, earnings"
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setUploadPublic(!uploadPublic)}
                  className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    uploadPublic
                      ? 'bg-profit/10 text-profit border border-profit/20'
                      : 'bg-warning/10 text-warning border border-warning/20'
                  }`}
                >
                  {uploadPublic ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                  {uploadPublic ? 'Public' : 'Private'}
                </button>
                <span className="text-[11px] text-text-muted">
                  {uploadPublic ? 'Visible to all users' : 'Only visible to you'}
                </span>
              </div>
            </div>

            {uploadError && (
              <p className="text-xs text-loss mt-3">{uploadError}</p>
            )}

            <div className="flex justify-end gap-3 mt-5">
              <button
                className="btn-secondary"
                onClick={() => setShowUpload(false)}
                disabled={uploading}
              >
                Cancel
              </button>
              <button
                className="btn-primary flex items-center gap-2"
                onClick={handleUpload}
                disabled={!uploadFile || uploading}
              >
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                Upload
              </button>
            </div>
          </div>
        </div>
      )}

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
            const isOwn = !!entry.uploaded_by;
            return (
              <div
                key={entry.id}
                className="p-4 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors cursor-pointer"
                onClick={() => setViewingEntry(entry)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                      <h4 className="text-sm font-medium text-text-primary">{entry.title}</h4>
                      <span
                        className={`status-badge text-[10px] ${
                          categoryColors[entry.category] || 'text-text-secondary bg-dark-500'
                        }`}
                      >
                        {entry.category}
                      </span>
                      {entry.file_name && (
                        <span className="status-badge text-[10px] text-info bg-info/10">
                          <FileText className="w-2.5 h-2.5 mr-0.5 inline" />
                          {entry.file_type?.split('/').pop() || 'file'}
                        </span>
                      )}
                      {!entry.is_public && (
                        <span className="status-badge text-[10px] text-warning bg-warning/10">
                          <Lock className="w-2.5 h-2.5 mr-0.5 inline" />
                          Private
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary leading-relaxed mb-2 whitespace-pre-line">
                      {entry.content.length > 500
                        ? entry.content.slice(0, 500) + '...'
                        : entry.content}
                    </p>
                    {entry.content.length > 500 && (
                      <button
                        onClick={(e) => { e.stopPropagation(); setViewingEntry(entry); }}
                        className="text-[11px] text-info hover:underline mb-2"
                      >
                        View full document
                      </button>
                    )}
                    <div className="flex items-center gap-4 text-[11px] text-text-muted flex-wrap">
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
                      {entry.tickers && entry.tickers.length > 0 && (
                        <span className="flex items-center gap-1 text-info">
                          {entry.tickers.join(', ')}
                        </span>
                      )}
                      {entry.tags.length > 0 && (
                        <span className="flex items-center gap-1">
                          <Tag className="w-3 h-3" />
                          {entry.tags.join(', ')}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 flex flex-col items-center gap-2">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold ${
                        confidencePct >= 90
                          ? 'bg-profit/10 text-profit'
                          : confidencePct >= 80
                          ? 'bg-info/10 text-info'
                          : 'bg-warning/10 text-warning'
                      }`}
                    >
                      {confidencePct}
                    </div>
                    {isOwn && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleTogglePrivacy(entry)}
                          className="p-1 rounded hover:bg-dark-600 text-text-muted hover:text-text-primary"
                          title={entry.is_public ? 'Make private' : 'Make public'}
                        >
                          {entry.is_public ? <Unlock className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                        </button>
                        <button
                          onClick={() => handleDelete(entry)}
                          className="p-1 rounded hover:bg-dark-600 text-text-muted hover:text-loss"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
          {filteredEntries.length === 0 && (
            <div className="text-center py-8 text-text-muted">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No entries for this layer yet</p>
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
              <span className="text-[10px] text-text-muted font-normal ml-1">Live from library</span>
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
                const sentiment = item.data.sentiment.toLowerCase();
                const sentimentLabel = sentiment.charAt(0).toUpperCase() + sentiment.slice(1);
                const SentimentIcon = sentimentIcons[sentiment] || Minus;
                const sentimentColor = sentimentColors[sentiment] || 'text-text-secondary';
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
                          {sentimentLabel}
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
                          sentiment === 'bullish'
                            ? 'bg-profit'
                            : sentiment === 'neutral'
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
          {educationContent.map((rec) => (
            <div
              key={rec.id}
              className="p-4 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors cursor-pointer"
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="text-sm font-medium text-text-primary flex-1">{rec.title}</h4>
                <span
                  className={`status-badge text-[10px] ml-2 shrink-0 ${
                    difficultyColors[rec.difficulty] || 'text-text-secondary bg-dark-500'
                  }`}
                >
                  {rec.difficulty.charAt(0).toUpperCase() + rec.difficulty.slice(1)}
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
          ))}
          {educationContent.length === 0 && (
            <div className="col-span-2 text-center py-8 text-text-muted">
              <GraduationCap className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No learning recommendations available</p>
            </div>
          )}
        </div>
      </div>

      {/* ── Document Viewer Modal ── */}
      {viewingEntry && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-6">
          <div className="bg-dark-800 rounded-xl border border-white/[0.1] w-full max-w-3xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-start justify-between p-5 border-b border-white/[0.06]">
              <div className="flex-1 min-w-0 mr-4">
                <h2 className="text-lg font-semibold text-text-primary mb-1">{viewingEntry.title}</h2>
                <div className="flex items-center gap-3 text-xs text-text-muted flex-wrap">
                  <span className={`status-badge text-[10px] ${categoryColors[viewingEntry.category] || 'text-text-secondary bg-dark-500'}`}>
                    {viewingEntry.category}
                  </span>
                  <span>Source: {viewingEntry.source}</span>
                  <span>Confidence: {Math.round(viewingEntry.confidence * 100)}%</span>
                  <span>{new Date(viewingEntry.created_at).toLocaleDateString()}</span>
                  {viewingEntry.file_name && (
                    <span className="flex items-center gap-1 text-info">
                      <FileText className="w-3 h-3" />
                      {viewingEntry.file_name}
                    </span>
                  )}
                </div>
                {viewingEntry.tickers && viewingEntry.tickers.length > 0 && (
                  <div className="flex gap-1 mt-2">
                    {viewingEntry.tickers.map((t) => (
                      <span key={t} className="px-1.5 py-0.5 rounded bg-dark-600 text-[10px] font-mono text-info">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => setViewingEntry(null)}
                className="p-1.5 rounded-lg hover:bg-dark-600 transition-colors text-text-muted"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5">
              <div className="prose prose-invert max-w-none">
                <pre className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap font-sans">
                  {viewingEntry.content}
                </pre>
              </div>
            </div>
            {/* Footer */}
            <div className="flex items-center justify-between p-4 border-t border-white/[0.06]">
              <span className="text-[10px] text-text-muted">
                {viewingEntry.content.length.toLocaleString()} characters
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(viewingEntry.content);
                  }}
                  className="btn-secondary text-xs px-3 py-1.5"
                >
                  Copy to Clipboard
                </button>
                <button
                  onClick={() => setViewingEntry(null)}
                  className="btn-primary text-xs px-3 py-1.5"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
