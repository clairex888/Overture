'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Plus,
  X,
  Sliders,
  Database,
  PenSquare,
} from 'lucide-react';
import { ideasAPI } from '@/lib/api';
import type { Ticker } from '@/types';

// --- Constants ---

const assetClasses = [
  { key: 'equities', label: 'Equities' },
  { key: 'fixed_income', label: 'Fixed Income' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'commodities', label: 'Commodities' },
  { key: 'fx', label: 'FX' },
] as const;

const timeframes = [
  { key: 'short_term', label: 'Short Term' },
  { key: 'medium_term', label: 'Medium Term' },
  { key: 'long_term', label: 'Long Term' },
] as const;

const riskLevels = [
  { key: 'conservative', label: 'Conservative', color: 'text-profit' },
  { key: 'moderate', label: 'Moderate', color: 'text-warning' },
  { key: 'aggressive', label: 'Aggressive', color: 'text-loss' },
] as const;

const informationSources = [
  { key: 'bloomberg', label: 'Bloomberg API', credibility: 0.95 },
  { key: 'reuters', label: 'Reuters News', credibility: 0.92 },
  { key: 'fred', label: 'Federal Reserve (FRED)', credibility: 0.98 },
  { key: 'coingecko', label: 'CoinGecko', credibility: 0.78 },
  { key: 'reddit', label: 'Reddit', credibility: 0.45 },
  { key: 'goldman_sachs', label: 'Goldman Sachs Research', credibility: 0.91 },
] as const;

const directionOptions = [
  { key: 'long', label: 'Long' },
  { key: 'short', label: 'Short' },
] as const;

// --- Component ---

export default function IdeasPreferencesPage() {
  // Alpha Generation Preferences state
  const [preferredAssets, setPreferredAssets] = useState<string[]>(['equities']);
  const [timeframePref, setTimeframePref] = useState<string>('medium_term');
  const [riskTolerance, setRiskTolerance] = useState<string>('moderate');
  const [minConviction, setMinConviction] = useState<number>(50);
  const [autoGenerate, setAutoGenerate] = useState<boolean>(false);

  // Information Sources state
  const [enabledSources, setEnabledSources] = useState<string[]>([
    'bloomberg',
    'reuters',
    'fred',
    'goldman_sachs',
  ]);

  // Manual Idea Form state
  const [ideaTitle, setIdeaTitle] = useState('');
  const [ideaThesis, setIdeaThesis] = useState('');
  const [ideaAssetClass, setIdeaAssetClass] = useState('equities');
  const [ideaTimeframe, setIdeaTimeframe] = useState('medium_term');
  const [ideaTickers, setIdeaTickers] = useState<Ticker[]>([]);
  const [ideaConviction, setIdeaConviction] = useState<number>(50);
  const [ideaTags, setIdeaTags] = useState('');
  const [ideaNotes, setIdeaNotes] = useState('');

  // Ticker input staging
  const [tickerSymbol, setTickerSymbol] = useState('');
  const [tickerDirection, setTickerDirection] = useState('long');
  const [tickerWeight, setTickerWeight] = useState<number>(100);

  // UI state
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // --- Handlers ---

  const toggleAssetClass = (key: string) => {
    setPreferredAssets((prev) =>
      prev.includes(key) ? prev.filter((a) => a !== key) : [...prev, key]
    );
  };

  const toggleSource = (key: string) => {
    setEnabledSources((prev) =>
      prev.includes(key) ? prev.filter((s) => s !== key) : [...prev, key]
    );
  };

  const addTicker = () => {
    const symbol = tickerSymbol.trim().toUpperCase();
    if (!symbol) return;
    if (ideaTickers.some((t) => t.symbol === symbol)) return;
    setIdeaTickers((prev) => [
      ...prev,
      { symbol, direction: tickerDirection, weight: tickerWeight / 100 },
    ]);
    setTickerSymbol('');
    setTickerWeight(100);
  };

  const removeTicker = (symbol: string) => {
    setIdeaTickers((prev) => prev.filter((t) => t.symbol !== symbol));
  };

  const handleSubmitIdea = useCallback(async () => {
    // Validation
    if (!ideaTitle.trim()) {
      setError('Title is required.');
      return;
    }
    if (!ideaThesis.trim()) {
      setError('Thesis is required.');
      return;
    }
    if (ideaTickers.length === 0) {
      setError('At least one ticker is required.');
      return;
    }

    try {
      setSubmitting(true);
      setError(null);
      setSuccess(null);

      const payload = {
        title: ideaTitle.trim(),
        thesis: ideaThesis.trim(),
        asset_class: ideaAssetClass,
        timeframe: ideaTimeframe,
        tickers: ideaTickers,
        conviction: ideaConviction / 100,
        source: 'human',
        tags: ideaTags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        notes: ideaNotes.trim() || null,
      };

      await ideasAPI.create(payload);
      setSuccess('Idea submitted successfully!');

      // Reset form
      setIdeaTitle('');
      setIdeaThesis('');
      setIdeaAssetClass('equities');
      setIdeaTimeframe('medium_term');
      setIdeaTickers([]);
      setIdeaConviction(50);
      setIdeaTags('');
      setIdeaNotes('');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Failed to submit idea'
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    ideaTitle,
    ideaThesis,
    ideaAssetClass,
    ideaTimeframe,
    ideaTickers,
    ideaConviction,
    ideaTags,
    ideaNotes,
  ]);

  const riskIndex = riskLevels.findIndex((r) => r.key === riskTolerance);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/ideas"
            className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Ideas
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">
              Ideas Preferences
            </h1>
            <p className="text-sm text-text-muted mt-1">
              Configure idea generation, information sources, and submit manual ideas
            </p>
          </div>
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

      {/* Success Banner */}
      {success && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-profit/10 border border-profit/20">
          <CheckCircle2 className="w-5 h-5 text-profit shrink-0" />
          <p className="text-sm text-profit">{success}</p>
          <button
            onClick={() => setSuccess(null)}
            className="ml-auto text-xs text-profit hover:text-profit/80"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* =====================================================
          SECTION 1: Alpha Generation Preferences
          ===================================================== */}
      <div className="card">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-info/10 flex items-center justify-center">
            <Sliders className="w-4 h-4 text-info" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Alpha Generation Preferences
            </h2>
            <p className="text-xs text-text-muted">
              Control how AI-generated ideas are produced
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Preferred Asset Classes */}
          <div>
            <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
              Preferred Asset Classes
            </label>
            <div className="space-y-2">
              {assetClasses.map((ac) => (
                <label
                  key={ac.key}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    preferredAssets.includes(ac.key)
                      ? 'bg-info/5 border-info/30 text-text-primary'
                      : 'bg-dark-800 border-white/[0.05] text-text-muted hover:border-white/[0.1]'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={preferredAssets.includes(ac.key)}
                    onChange={() => toggleAssetClass(ac.key)}
                    className="w-4 h-4 rounded border-dark-400 bg-dark-700 text-info focus:ring-info/50 focus:ring-offset-0"
                  />
                  <span className="text-sm font-medium">{ac.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-6">
            {/* Timeframe Preference */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                Timeframe Preference
              </label>
              <div className="flex gap-2">
                {timeframes.map((tf) => (
                  <button
                    key={tf.key}
                    onClick={() => setTimeframePref(tf.key)}
                    className={`flex-1 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors border ${
                      timeframePref === tf.key
                        ? 'bg-info/10 text-info border-info/20'
                        : 'bg-dark-800 text-text-muted border-white/[0.05] hover:border-white/[0.1] hover:text-text-secondary'
                    }`}
                  >
                    {tf.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Risk Tolerance */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                Risk Tolerance
              </label>
              <div className="px-1">
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={1}
                  value={riskIndex}
                  onChange={(e) =>
                    setRiskTolerance(riskLevels[Number(e.target.value)].key)
                  }
                  className="w-full h-2 bg-dark-700 rounded-lg appearance-none cursor-pointer accent-info"
                />
                <div className="flex justify-between mt-2">
                  {riskLevels.map((rl) => (
                    <span
                      key={rl.key}
                      className={`text-xs font-medium ${
                        riskTolerance === rl.key
                          ? rl.color
                          : 'text-text-muted'
                      }`}
                    >
                      {rl.label}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Minimum Conviction Threshold */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                Minimum Conviction Threshold
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={minConviction}
                  onChange={(e) => setMinConviction(Number(e.target.value))}
                  className="flex-1 h-2 bg-dark-700 rounded-lg appearance-none cursor-pointer accent-info"
                />
                <span
                  className={`text-sm font-mono font-semibold min-w-[3rem] text-right ${
                    minConviction >= 70
                      ? 'text-profit'
                      : minConviction >= 40
                      ? 'text-warning'
                      : 'text-loss'
                  }`}
                >
                  {minConviction}%
                </span>
              </div>
            </div>

            {/* Auto-Generate Toggle */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                Auto-Generate Ideas
              </label>
              <button
                onClick={() => setAutoGenerate(!autoGenerate)}
                className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                  autoGenerate ? 'bg-info' : 'bg-dark-500'
                }`}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
                    autoGenerate ? 'translate-x-6' : 'translate-x-1'
                  }`}
                />
              </button>
              <p className="text-xs text-text-muted mt-2">
                {autoGenerate
                  ? 'AI will automatically generate ideas based on your preferences'
                  : 'Ideas will only be generated when manually triggered'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* =====================================================
          SECTION 2: Information Sources
          ===================================================== */}
      <div className="card">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
            <Database className="w-4 h-4 text-accent" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Information Sources
            </h2>
            <p className="text-xs text-text-muted">
              Enable or disable data sources used for idea generation and validation
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {informationSources.map((source) => {
            const isEnabled = enabledSources.includes(source.key);
            const credPct = Math.round(source.credibility * 100);
            return (
              <label
                key={source.key}
                className={`flex items-center justify-between p-4 rounded-lg border cursor-pointer transition-colors ${
                  isEnabled
                    ? 'bg-dark-700 border-info/20'
                    : 'bg-dark-800 border-white/[0.05] hover:border-white/[0.1]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={() => toggleSource(source.key)}
                    className="w-4 h-4 rounded border-dark-400 bg-dark-700 text-info focus:ring-info/50 focus:ring-offset-0"
                  />
                  <span
                    className={`text-sm font-medium ${
                      isEnabled ? 'text-text-primary' : 'text-text-muted'
                    }`}
                  >
                    {source.label}
                  </span>
                </div>
                <span
                  className={`text-xs font-mono px-2 py-0.5 rounded ${
                    credPct >= 90
                      ? 'text-profit bg-profit/10'
                      : credPct >= 70
                      ? 'text-warning bg-warning/10'
                      : 'text-loss bg-loss/10'
                  }`}
                >
                  {credPct}%
                </span>
              </label>
            );
          })}
        </div>
      </div>

      {/* =====================================================
          SECTION 3: Manual Idea Input Form
          ===================================================== */}
      <div className="card">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-8 h-8 rounded-lg bg-warning/10 flex items-center justify-center">
            <PenSquare className="w-4 h-4 text-warning" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-text-primary">
              Manual Idea Input
            </h2>
            <p className="text-xs text-text-muted">
              Submit a new investment idea directly
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Column */}
          <div className="space-y-4">
            {/* Title */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Title
              </label>
              <input
                type="text"
                value={ideaTitle}
                onChange={(e) => setIdeaTitle(e.target.value)}
                placeholder="e.g. Long NVDA on AI Capex Cycle"
                className="input-field w-full"
              />
            </div>

            {/* Thesis */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Thesis
              </label>
              <textarea
                value={ideaThesis}
                onChange={(e) => setIdeaThesis(e.target.value)}
                placeholder="Describe the investment thesis..."
                rows={4}
                className="input-field w-full resize-none"
              />
            </div>

            {/* Asset Class + Timeframe */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                  Asset Class
                </label>
                <select
                  value={ideaAssetClass}
                  onChange={(e) => setIdeaAssetClass(e.target.value)}
                  className="input-field w-full"
                >
                  {assetClasses.map((ac) => (
                    <option key={ac.key} value={ac.key}>
                      {ac.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                  Timeframe
                </label>
                <select
                  value={ideaTimeframe}
                  onChange={(e) => setIdeaTimeframe(e.target.value)}
                  className="input-field w-full"
                >
                  {timeframes.map((tf) => (
                    <option key={tf.key} value={tf.key}>
                      {tf.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Conviction */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Conviction
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={ideaConviction}
                  onChange={(e) => setIdeaConviction(Number(e.target.value))}
                  className="flex-1 h-2 bg-dark-700 rounded-lg appearance-none cursor-pointer accent-info"
                />
                <span
                  className={`text-sm font-mono font-semibold min-w-[3rem] text-right ${
                    ideaConviction >= 70
                      ? 'text-profit'
                      : ideaConviction >= 40
                      ? 'text-warning'
                      : 'text-loss'
                  }`}
                >
                  {ideaConviction}%
                </span>
              </div>
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-4">
            {/* Tickers */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Tickers
              </label>

              {/* Existing tickers */}
              {ideaTickers.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-3">
                  {ideaTickers.map((t) => (
                    <div
                      key={t.symbol}
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.05]"
                    >
                      <span className="font-mono text-sm text-text-primary font-medium">
                        {t.symbol}
                      </span>
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          t.direction === 'long'
                            ? 'text-profit bg-profit/10'
                            : 'text-loss bg-loss/10'
                        }`}
                      >
                        {t.direction}
                      </span>
                      <span className="text-xs text-text-muted font-mono">
                        {((t.weight || 0) * 100).toFixed(0)}%
                      </span>
                      <button
                        onClick={() => removeTicker(t.symbol)}
                        className="text-text-muted hover:text-loss transition-colors"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add ticker controls */}
              <div className="flex items-end gap-2">
                <div className="flex-1">
                  <input
                    type="text"
                    value={tickerSymbol}
                    onChange={(e) => setTickerSymbol(e.target.value)}
                    placeholder="Symbol (e.g. AAPL)"
                    className="input-field w-full"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addTicker();
                      }
                    }}
                  />
                </div>
                <div className="w-24">
                  <select
                    value={tickerDirection}
                    onChange={(e) => setTickerDirection(e.target.value)}
                    className="input-field w-full"
                  >
                    {directionOptions.map((d) => (
                      <option key={d.key} value={d.key}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="w-20">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={tickerWeight}
                    onChange={(e) => setTickerWeight(Number(e.target.value))}
                    placeholder="Wt%"
                    className="input-field w-full text-center"
                  />
                </div>
                <button
                  onClick={addTicker}
                  className="btn-secondary flex items-center gap-1 shrink-0"
                >
                  <Plus className="w-4 h-4" />
                  Add
                </button>
              </div>
            </div>

            {/* Tags */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Tags
              </label>
              <input
                type="text"
                value={ideaTags}
                onChange={(e) => setIdeaTags(e.target.value)}
                placeholder="momentum, earnings, macro (comma-separated)"
                className="input-field w-full"
              />
            </div>

            {/* Notes */}
            <div>
              <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Notes
              </label>
              <textarea
                value={ideaNotes}
                onChange={(e) => setIdeaNotes(e.target.value)}
                placeholder="Additional notes or context..."
                rows={4}
                className="input-field w-full resize-none"
              />
            </div>
          </div>
        </div>

        {/* Submit Button */}
        <div className="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-white/[0.05]">
          <button
            onClick={handleSubmitIdea}
            disabled={submitting}
            className="btn-primary flex items-center gap-2"
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                Submit Idea
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
