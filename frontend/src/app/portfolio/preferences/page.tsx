'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Target,
  PieChart,
  Shield,
  Ban,
  CalendarClock,
  Save,
  Plus,
  X,
  Check,
  AlertTriangle,
} from 'lucide-react';
import { portfolioAPI } from '@/lib/api';
import type { PortfolioPreferences, AssetAllocationTarget } from '@/types';

const SECTOR_OPTIONS = [
  'Technology',
  'Healthcare',
  'Financials',
  'Energy',
  'Consumer Discretionary',
  'Consumer Staples',
  'Industrials',
  'Materials',
  'Real Estate',
  'Utilities',
  'Communication Services',
];

const DEFAULT_ALLOCATION_TARGETS: AssetAllocationTarget[] = [
  { asset_class: 'equities', target_weight: 50 },
  { asset_class: 'fixed_income', target_weight: 20 },
  { asset_class: 'crypto', target_weight: 10 },
  { asset_class: 'commodities', target_weight: 10 },
  { asset_class: 'cash', target_weight: 10 },
];

const DEFAULT_PREFERENCES: PortfolioPreferences = {
  target_annual_return: 12,
  max_drawdown_tolerance: 15,
  investment_horizon: 'medium_term',
  benchmark: 'SPY',
  allocation_targets: DEFAULT_ALLOCATION_TARGETS,
  risk_appetite: 'moderate',
  max_position_size: 10,
  concentration_limit: 30,
  stop_loss_pct: 5,
  excluded_sectors: [],
  excluded_tickers: [],
  hard_rules: '',
  rebalance_frequency: 'monthly',
  drift_tolerance: 5,
  auto_rebalance: false,
};

const ASSET_CLASS_LABELS: Record<string, string> = {
  equities: 'Equities',
  fixed_income: 'Fixed Income',
  crypto: 'Crypto',
  commodities: 'Commodities',
  cash: 'Cash',
};

const ASSET_CLASS_COLORS: Record<string, string> = {
  equities: 'bg-blue-500',
  fixed_income: 'bg-violet-500',
  crypto: 'bg-fuchsia-400',
  commodities: 'bg-amber-500',
  cash: 'bg-slate-500',
};

export default function PortfolioPreferencesPage() {
  const [preferences, setPreferences] = useState<PortfolioPreferences>(DEFAULT_PREFERENCES);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [tickerInput, setTickerInput] = useState('');

  useEffect(() => {
    async function loadPreferences() {
      setLoading(true);
      try {
        const data = await portfolioAPI.getPreferences();
        setPreferences(data);
      } catch (err) {
        console.error('Failed to load preferences, using defaults:', err);
        // Keep defaults if endpoint not available yet
      } finally {
        setLoading(false);
      }
    }
    loadPreferences();
  }, []);

  const allocationTotal = preferences.allocation_targets.reduce(
    (sum, t) => sum + t.target_weight,
    0
  );

  const updateField = useCallback(
    <K extends keyof PortfolioPreferences>(field: K, value: PortfolioPreferences[K]) => {
      setPreferences((prev) => ({ ...prev, [field]: value }));
      setSaveSuccess(false);
      setSaveError(null);
    },
    []
  );

  const updateAllocationTarget = useCallback((assetClass: string, weight: number) => {
    setPreferences((prev) => ({
      ...prev,
      allocation_targets: prev.allocation_targets.map((t) =>
        t.asset_class === assetClass ? { ...t, target_weight: weight } : t
      ),
    }));
    setSaveSuccess(false);
    setSaveError(null);
  }, []);

  const addExcludedTicker = useCallback(() => {
    const ticker = tickerInput.trim().toUpperCase();
    if (ticker && !preferences.excluded_tickers.includes(ticker)) {
      setPreferences((prev) => ({
        ...prev,
        excluded_tickers: [...prev.excluded_tickers, ticker],
      }));
      setTickerInput('');
      setSaveSuccess(false);
      setSaveError(null);
    }
  }, [tickerInput, preferences.excluded_tickers]);

  const removeExcludedTicker = useCallback((ticker: string) => {
    setPreferences((prev) => ({
      ...prev,
      excluded_tickers: prev.excluded_tickers.filter((t) => t !== ticker),
    }));
    setSaveSuccess(false);
    setSaveError(null);
  }, []);

  const toggleExcludedSector = useCallback((sector: string) => {
    setPreferences((prev) => {
      const isExcluded = prev.excluded_sectors.includes(sector);
      return {
        ...prev,
        excluded_sectors: isExcluded
          ? prev.excluded_sectors.filter((s) => s !== sector)
          : [...prev.excluded_sectors, sector],
      };
    });
    setSaveSuccess(false);
    setSaveError(null);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError(null);
    try {
      await portfolioAPI.updatePreferences(preferences);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      console.error('Failed to save preferences:', err);
      setSaveError(err instanceof Error ? err.message : 'Failed to save preferences');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Link href="/portfolio" className="p-2 rounded-lg hover:bg-dark-700 transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-muted" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio Preferences</h1>
            <p className="text-sm text-text-muted mt-1">Loading preferences...</p>
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card animate-fade-in">
              <div className="h-4 w-32 bg-dark-600 rounded animate-pulse mb-4" />
              <div className="space-y-3">
                <div className="h-8 bg-dark-600 rounded animate-pulse" />
                <div className="h-8 bg-dark-600 rounded animate-pulse" />
                <div className="h-8 bg-dark-600 rounded animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/portfolio" className="p-2 rounded-lg hover:bg-dark-700 transition-colors">
            <ArrowLeft className="w-5 h-5 text-text-muted" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio Preferences</h1>
            <p className="text-sm text-text-muted mt-1">
              Configure portfolio goals, risk parameters, and rebalancing rules
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Section 1: Portfolio Goals */}
        <div className="card">
          <div className="flex items-center gap-2 mb-5">
            <Target className="w-4 h-4 text-info" />
            <h3 className="text-sm font-semibold text-text-primary">Portfolio Goals</h3>
          </div>

          {/* Target Annual Return */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider">
                Target Annual Return
              </label>
              <span className="text-sm font-semibold text-text-primary">
                {preferences.target_annual_return}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={50}
              step={1}
              value={preferences.target_annual_return}
              onChange={(e) => updateField('target_annual_return', Number(e.target.value))}
              className="w-full h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-info"
            />
            <div className="flex justify-between text-[10px] text-text-muted mt-1">
              <span>0%</span>
              <span>25%</span>
              <span>50%</span>
            </div>
          </div>

          {/* Max Drawdown Tolerance */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider">
                Maximum Drawdown Tolerance
              </label>
              <span className="text-sm font-semibold text-text-primary">
                {preferences.max_drawdown_tolerance}%
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={50}
              step={1}
              value={preferences.max_drawdown_tolerance}
              onChange={(e) => updateField('max_drawdown_tolerance', Number(e.target.value))}
              className="w-full h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-warning"
            />
            <div className="flex justify-between text-[10px] text-text-muted mt-1">
              <span>0%</span>
              <span>25%</span>
              <span>50%</span>
            </div>
          </div>

          {/* Investment Horizon */}
          <div className="mb-4">
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-2">
              Investment Horizon
            </label>
            <select
              value={preferences.investment_horizon}
              onChange={(e) =>
                updateField(
                  'investment_horizon',
                  e.target.value as PortfolioPreferences['investment_horizon']
                )
              }
              className="w-full bg-dark-700 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-info/50 transition-colors"
            >
              <option value="short_term">Short Term (0-1 year)</option>
              <option value="medium_term">Medium Term (1-5 years)</option>
              <option value="long_term">Long Term (5+ years)</option>
            </select>
          </div>

          {/* Benchmark Selection */}
          <div>
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-2">
              Benchmark
            </label>
            <div className="flex gap-2">
              {['SPY', 'QQQ'].map((bench) => (
                <button
                  key={bench}
                  onClick={() => updateField('benchmark', bench)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    preferences.benchmark === bench
                      ? 'bg-info/20 text-info border border-info/30'
                      : 'bg-dark-700 text-text-secondary border border-white/[0.08] hover:bg-dark-600'
                  }`}
                >
                  {bench}
                </button>
              ))}
              <input
                type="text"
                placeholder="Custom..."
                value={
                  preferences.benchmark !== 'SPY' && preferences.benchmark !== 'QQQ'
                    ? preferences.benchmark
                    : ''
                }
                onChange={(e) => updateField('benchmark', e.target.value.toUpperCase())}
                onFocus={() => {
                  if (preferences.benchmark === 'SPY' || preferences.benchmark === 'QQQ') {
                    updateField('benchmark', '');
                  }
                }}
                className="flex-1 bg-dark-700 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50 transition-colors"
              />
            </div>
          </div>
        </div>

        {/* Section 2: Asset Allocation Targets */}
        <div className="card">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <PieChart className="w-4 h-4 text-accent" />
              <h3 className="text-sm font-semibold text-text-primary">Asset Allocation Targets</h3>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`text-sm font-bold ${
                  allocationTotal === 100
                    ? 'text-profit'
                    : allocationTotal > 100
                    ? 'text-loss'
                    : 'text-warning'
                }`}
              >
                {allocationTotal}%
              </span>
              <span className="text-xs text-text-muted">/ 100%</span>
              {allocationTotal === 100 && <Check className="w-4 h-4 text-profit" />}
              {allocationTotal !== 100 && <AlertTriangle className="w-4 h-4 text-warning" />}
            </div>
          </div>

          {/* Total progress bar */}
          <div className="mb-5">
            <div className="h-3 bg-dark-700 rounded-full overflow-hidden flex">
              {preferences.allocation_targets.map((target) => (
                <div
                  key={target.asset_class}
                  className={`${ASSET_CLASS_COLORS[target.asset_class] || 'bg-slate-400'} transition-all duration-300`}
                  style={{ width: `${Math.min(target.target_weight, 100)}%` }}
                  title={`${ASSET_CLASS_LABELS[target.asset_class] || target.asset_class}: ${target.target_weight}%`}
                />
              ))}
            </div>
          </div>

          {/* Individual sliders */}
          <div className="space-y-4">
            {preferences.allocation_targets.map((target) => (
              <div key={target.asset_class}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-2.5 h-2.5 rounded-sm ${
                        ASSET_CLASS_COLORS[target.asset_class] || 'bg-slate-400'
                      }`}
                    />
                    <span className="text-xs text-text-secondary">
                      {ASSET_CLASS_LABELS[target.asset_class] || target.asset_class}
                    </span>
                  </div>
                  <span className="text-sm font-semibold text-text-primary">
                    {target.target_weight}%
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={target.target_weight}
                  onChange={(e) =>
                    updateAllocationTarget(target.asset_class, Number(e.target.value))
                  }
                  className="w-full h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-info"
                />
              </div>
            ))}
          </div>

          {allocationTotal !== 100 && (
            <div className="mt-4 flex items-center gap-2 px-3 py-2 rounded-lg bg-warning/10 border border-warning/20">
              <AlertTriangle className="w-3.5 h-3.5 text-warning flex-shrink-0" />
              <span className="text-xs text-warning">
                Allocation targets must sum to 100%. Currently at {allocationTotal}%.
              </span>
            </div>
          )}
        </div>

        {/* Section 3: Risk Parameters */}
        <div className="card">
          <div className="flex items-center gap-2 mb-5">
            <Shield className="w-4 h-4 text-warning" />
            <h3 className="text-sm font-semibold text-text-primary">Risk Parameters</h3>
          </div>

          {/* Risk Appetite */}
          <div className="mb-4">
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-3">
              Risk Appetite
            </label>
            <div className="flex gap-2">
              {(['conservative', 'moderate', 'aggressive'] as const).map((level) => (
                <label
                  key={level}
                  className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium cursor-pointer transition-colors ${
                    preferences.risk_appetite === level
                      ? level === 'conservative'
                        ? 'bg-profit/15 text-profit border border-profit/30'
                        : level === 'moderate'
                        ? 'bg-warning/15 text-warning border border-warning/30'
                        : 'bg-loss/15 text-loss border border-loss/30'
                      : 'bg-dark-700 text-text-secondary border border-white/[0.08] hover:bg-dark-600'
                  }`}
                >
                  <input
                    type="radio"
                    name="risk_appetite"
                    value={level}
                    checked={preferences.risk_appetite === level}
                    onChange={() => updateField('risk_appetite', level)}
                    className="sr-only"
                  />
                  {level.charAt(0).toUpperCase() + level.slice(1)}
                </label>
              ))}
            </div>
          </div>

          {/* Max Single Position Size */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider">
                Max Single Position Size
              </label>
              <span className="text-sm font-semibold text-text-primary">
                {preferences.max_position_size}%
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={50}
              step={1}
              value={preferences.max_position_size}
              onChange={(e) => updateField('max_position_size', Number(e.target.value))}
              className="w-full h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-warning"
            />
            <div className="flex justify-between text-[10px] text-text-muted mt-1">
              <span>1%</span>
              <span>25%</span>
              <span>50%</span>
            </div>
          </div>

          {/* Concentration Limit */}
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider">
                Concentration Limit (Top 5)
              </label>
              <span className="text-sm font-semibold text-text-primary">
                {preferences.concentration_limit}%
              </span>
            </div>
            <input
              type="range"
              min={10}
              max={100}
              step={5}
              value={preferences.concentration_limit}
              onChange={(e) => updateField('concentration_limit', Number(e.target.value))}
              className="w-full h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-warning"
            />
            <div className="flex justify-between text-[10px] text-text-muted mt-1">
              <span>10%</span>
              <span>55%</span>
              <span>100%</span>
            </div>
          </div>

          {/* Stop Loss Policy */}
          <div>
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-2">
              Stop Loss Policy
            </label>
            <div className="flex items-center gap-3">
              <input
                type="number"
                min={0}
                max={50}
                step={0.5}
                value={preferences.stop_loss_pct}
                onChange={(e) => updateField('stop_loss_pct', Number(e.target.value))}
                className="w-24 bg-dark-700 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-info/50 transition-colors text-center"
              />
              <span className="text-sm text-text-muted">% loss triggers stop</span>
            </div>
          </div>
        </div>

        {/* Section 4: Constraints & Rules */}
        <div className="card">
          <div className="flex items-center gap-2 mb-5">
            <Ban className="w-4 h-4 text-loss" />
            <h3 className="text-sm font-semibold text-text-primary">Constraints & Rules</h3>
          </div>

          {/* Excluded Sectors */}
          <div className="mb-4">
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-3">
              Excluded Sectors
            </label>
            <div className="flex flex-wrap gap-2">
              {SECTOR_OPTIONS.map((sector) => {
                const isExcluded = preferences.excluded_sectors.includes(sector);
                return (
                  <button
                    key={sector}
                    onClick={() => toggleExcludedSector(sector)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      isExcluded
                        ? 'bg-loss/15 text-loss border border-loss/30'
                        : 'bg-dark-700 text-text-secondary border border-white/[0.08] hover:bg-dark-600'
                    }`}
                  >
                    {isExcluded && <span className="mr-1">x</span>}
                    {sector}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Excluded Tickers */}
          <div className="mb-4">
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-3">
              Excluded Tickers
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                placeholder="Enter ticker symbol..."
                value={tickerInput}
                onChange={(e) => setTickerInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') addExcludedTicker();
                }}
                className="flex-1 bg-dark-700 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50 transition-colors"
              />
              <button
                onClick={addExcludedTicker}
                className="px-3 py-2 bg-dark-700 border border-white/[0.08] rounded-lg text-text-secondary hover:bg-dark-600 hover:text-text-primary transition-colors"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {preferences.excluded_tickers.map((ticker) => (
                <span
                  key={ticker}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-dark-700 border border-white/[0.08] text-xs font-mono text-text-primary"
                >
                  {ticker}
                  <button
                    onClick={() => removeExcludedTicker(ticker)}
                    className="text-text-muted hover:text-loss transition-colors"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              {preferences.excluded_tickers.length === 0 && (
                <span className="text-xs text-text-muted">No tickers excluded</span>
              )}
            </div>
          </div>

          {/* Hard Rules */}
          <div>
            <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-2">
              Hard Rules
            </label>
            <textarea
              rows={4}
              placeholder="Enter custom rules, one per line...&#10;e.g. Never short small-cap stocks&#10;Max 3 positions in a single sector"
              value={preferences.hard_rules}
              onChange={(e) => updateField('hard_rules', e.target.value)}
              className="w-full bg-dark-700 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50 transition-colors resize-none"
            />
          </div>
        </div>

        {/* Section 5: Rebalance Schedule */}
        <div className="card lg:col-span-2">
          <div className="flex items-center gap-2 mb-5">
            <CalendarClock className="w-4 h-4 text-info" />
            <h3 className="text-sm font-semibold text-text-primary">Rebalance Schedule</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Frequency */}
            <div>
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-3">
                Frequency
              </label>
              <div className="space-y-2">
                {(['daily', 'weekly', 'monthly', 'quarterly'] as const).map((freq) => (
                  <label
                    key={freq}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                      preferences.rebalance_frequency === freq
                        ? 'bg-info/10 border border-info/20'
                        : 'bg-dark-700 border border-white/[0.08] hover:bg-dark-600'
                    }`}
                  >
                    <input
                      type="radio"
                      name="rebalance_frequency"
                      value={freq}
                      checked={preferences.rebalance_frequency === freq}
                      onChange={() => updateField('rebalance_frequency', freq)}
                      className="sr-only"
                    />
                    <div
                      className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${
                        preferences.rebalance_frequency === freq
                          ? 'border-info'
                          : 'border-white/20'
                      }`}
                    >
                      {preferences.rebalance_frequency === freq && (
                        <div className="w-2 h-2 rounded-full bg-info" />
                      )}
                    </div>
                    <span
                      className={`text-sm ${
                        preferences.rebalance_frequency === freq
                          ? 'text-info font-medium'
                          : 'text-text-secondary'
                      }`}
                    >
                      {freq.charAt(0).toUpperCase() + freq.slice(1)}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* Drift Tolerance */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-xs font-medium text-text-muted uppercase tracking-wider">
                  Drift Tolerance
                </label>
                <span className="text-sm font-semibold text-text-primary">
                  {preferences.drift_tolerance}%
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={20}
                step={1}
                value={preferences.drift_tolerance}
                onChange={(e) => updateField('drift_tolerance', Number(e.target.value))}
                className="w-full h-1.5 bg-dark-600 rounded-full appearance-none cursor-pointer accent-info"
              />
              <div className="flex justify-between text-[10px] text-text-muted mt-1">
                <span>1%</span>
                <span>10%</span>
                <span>20%</span>
              </div>
              <p className="text-[11px] text-text-muted mt-3">
                Rebalance triggers when any asset class drifts more than {preferences.drift_tolerance}% from its target weight.
              </p>
            </div>

            {/* Auto-Rebalance Toggle */}
            <div>
              <label className="text-xs font-medium text-text-muted uppercase tracking-wider block mb-3">
                Auto-Rebalance
              </label>
              <button
                onClick={() => updateField('auto_rebalance', !preferences.auto_rebalance)}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg w-full transition-colors ${
                  preferences.auto_rebalance
                    ? 'bg-profit/10 border border-profit/20'
                    : 'bg-dark-700 border border-white/[0.08]'
                }`}
              >
                <div
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    preferences.auto_rebalance ? 'bg-profit' : 'bg-dark-500'
                  }`}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                      preferences.auto_rebalance ? 'translate-x-5' : 'translate-x-0.5'
                    }`}
                  />
                </div>
                <span
                  className={`text-sm font-medium ${
                    preferences.auto_rebalance ? 'text-profit' : 'text-text-secondary'
                  }`}
                >
                  {preferences.auto_rebalance ? 'Enabled' : 'Disabled'}
                </span>
              </button>
              <p className="text-[11px] text-text-muted mt-3">
                {preferences.auto_rebalance
                  ? 'Portfolio will be automatically rebalanced when drift exceeds tolerance.'
                  : 'You will be notified when rebalancing is recommended, but no automatic trades will be placed.'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex items-center justify-between">
        <div>
          {saveSuccess && (
            <div className="flex items-center gap-2 text-profit text-sm">
              <Check className="w-4 h-4" />
              <span>Preferences saved successfully</span>
            </div>
          )}
          {saveError && (
            <div className="flex items-center gap-2 text-loss text-sm">
              <AlertTriangle className="w-4 h-4" />
              <span>{saveError}</span>
            </div>
          )}
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-semibold transition-all ${
            saving
              ? 'bg-info/50 text-white/70 cursor-not-allowed'
              : 'bg-info hover:bg-info/90 text-white shadow-lg shadow-info/20'
          }`}
        >
          <Save className="w-4 h-4" />
          {saving ? 'Saving...' : 'Save Preferences'}
        </button>
      </div>
    </div>
  );
}
