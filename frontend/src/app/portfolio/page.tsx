'use client';

import { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Wallet,
  PieChart as PieChartIcon,
  Shield,
  Activity,
  BarChart3,
  Target,
  AlertTriangle,
  ArrowUp,
  ArrowDown,
  Minus,
  Loader2,
  Rocket,
  CheckCircle2,
  RotateCcw,
  Plus,
  ChevronDown,
  X,
  Settings,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import { portfolioAPI, knowledgeAPI } from '@/lib/api';
import type {
  PortfolioOverview,
  Position,
  RiskMetrics,
  AllocationBreakdown,
  MarketOutlook,
  PortfolioListItem,
} from '@/types';

// ============================================================
// Constants & Helpers
// ============================================================

const MAX_PORTFOLIOS = 5;

const CATEGORY_COLORS: Record<string, string> = {
  equities: '#3b82f6',
  Equities: '#3b82f6',
  Equity: '#3b82f6',
  Stocks: '#3b82f6',
  fixed_income: '#8b5cf6',
  Bonds: '#8b5cf6',
  'Fixed Income': '#8b5cf6',
  commodities: '#f59e0b',
  Commodities: '#f59e0b',
  ETFs: '#00d084',
  ETF: '#00d084',
  cash: '#64748b',
  Cash: '#64748b',
  crypto: '#e879f9',
  Crypto: '#e879f9',
  Alternatives: '#f97316',
  'Real Estate': '#14b8a6',
  FX: '#6366f1',
  Options: '#ec4899',
  Futures: '#a855f7',
};

const DEFAULT_COLORS = ['#3b82f6', '#8b5cf6', '#f59e0b', '#00d084', '#64748b', '#e879f9', '#f97316', '#14b8a6'];

function getColorForCategory(category: string, index: number): string {
  return CATEGORY_COLORS[category] || DEFAULT_COLORS[index % DEFAULT_COLORS.length];
}

const outlookColors: Record<string, string> = {
  bullish: 'text-profit',
  neutral: 'text-warning',
  bearish: 'text-loss',
};

const outlookIcons: Record<string, typeof ArrowUp> = {
  bullish: ArrowUp,
  neutral: Minus,
  bearish: ArrowDown,
};

function formatCurrency(value: number): string {
  const absValue = Math.abs(value);
  const prefix = value < 0 ? '-' : '';
  return `${prefix}$${absValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatCurrencyDetailed(value: number): string {
  const absValue = Math.abs(value);
  const prefix = value >= 0 ? '+' : '-';
  return `${prefix}$${absValue.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function deriveRiskScore(risk: RiskMetrics): { score: string; label: string; colorClass: string } {
  const betaScore = Math.min(risk.portfolio_beta * 5, 5);
  const volScore = Math.min(risk.portfolio_volatility * 20, 5);
  const raw = betaScore + volScore;
  const score = Math.min(Math.max(raw, 0), 10);
  const rounded = Math.round(score * 10) / 10;

  let label: string;
  let colorClass: string;
  if (rounded <= 3) {
    label = 'Low';
    colorClass = 'text-profit';
  } else if (rounded <= 6) {
    label = 'Moderate';
    colorClass = 'text-warning';
  } else {
    label = 'High';
    colorClass = 'text-loss';
  }

  return { score: `${rounded.toFixed(1)}/10`, label, colorClass };
}

function CustomPieTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-dark-600 border border-white/10 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted mb-1">{payload[0].name}</p>
      <p className="text-sm font-semibold text-text-primary">{payload[0].value}%</p>
    </div>
  );
}

// ============================================================
// Portfolio Init / Reinitialize Modal
// ============================================================

function InitModal({
  open,
  onClose,
  mode,
  existingPortfolioId,
}: {
  open: boolean;
  onClose: () => void;
  mode: 'create' | 'reinitialize';
  existingPortfolioId?: string;
}) {
  const router = useRouter();
  const [amount, setAmount] = useState<string>('1000000');
  const [name, setName] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setAmount('1000000');
      setName('');
      setError(null);
      setLoading(false);
    }
  }, [open]);

  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [open, loading, onClose]);

  if (!open) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current && !loading) {
      onClose();
    }
  };

  const handleInitialize = async () => {
    const numAmount = parseFloat(amount);
    if (isNaN(numAmount) || numAmount <= 0) {
      setError('Please enter a valid amount greater than 0');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const portfolioId = mode === 'reinitialize' ? existingPortfolioId : undefined;
      const result = await portfolioAPI.initialize(numAmount, name || undefined, portfolioId);
      router.push(`/portfolio/preferences?portfolio_id=${result.portfolio_id}&init=true`);
    } catch (err: any) {
      setError(err.message || 'Failed to initialize portfolio');
      setLoading(false);
    }
  };

  const presets = [
    { label: '$100K', value: 100_000 },
    { label: '$500K', value: 500_000 },
    { label: '$1M', value: 1_000_000 },
    { label: '$5M', value: 5_000_000 },
    { label: '$10M', value: 10_000_000 },
  ];

  const title = mode === 'reinitialize' ? 'Reinitialize Portfolio' : 'Initialize New Portfolio';
  const subtitle =
    mode === 'reinitialize'
      ? 'Reset this portfolio with a new starting capital and re-run AI allocation'
      : 'Set your starting capital and our AI agents will propose an optimal allocation';

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-lg mx-4 card border border-white/[0.12] shadow-2xl animate-fade-in">
        {/* Close button */}
        <button
          onClick={() => !loading && onClose()}
          disabled={loading}
          className="absolute top-4 right-4 p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-dark-700 transition-colors disabled:opacity-50"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center">
            {mode === 'reinitialize' ? (
              <RotateCcw className="w-6 h-6 text-accent" />
            ) : (
              <Rocket className="w-6 h-6 text-accent" />
            )}
          </div>
          <div>
            <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
            <p className="text-sm text-text-muted">{subtitle}</p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Portfolio Name */}
          {mode === 'create' && (
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">
                Portfolio Name (optional)
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-4 py-3 bg-dark-800 border border-white/[0.08] rounded-lg text-text-primary text-sm focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20"
                placeholder="e.g. Growth Portfolio"
              />
            </div>
          )}

          {/* Amount */}
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Starting Capital (USD)
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted text-lg">$</span>
              <input
                type="text"
                value={amount}
                onChange={(e) => {
                  const raw = e.target.value.replace(/[^0-9.]/g, '');
                  setAmount(raw);
                }}
                className="w-full pl-8 pr-4 py-3 bg-dark-800 border border-white/[0.08] rounded-lg text-text-primary text-lg font-mono focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/20"
                placeholder="1,000,000"
              />
            </div>
            {amount && parseFloat(amount) > 0 && (
              <p className="text-xs text-text-muted mt-1">
                {formatCurrency(parseFloat(amount))}
              </p>
            )}
          </div>

          {/* Presets */}
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => (
              <button
                key={p.value}
                onClick={() => setAmount(p.value.toString())}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  parseFloat(amount) === p.value
                    ? 'bg-accent/20 text-accent border border-accent/30'
                    : 'bg-dark-700 text-text-muted border border-white/[0.08] hover:border-white/20 hover:text-text-secondary'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 rounded-lg bg-loss/10 border border-loss/20">
              <p className="text-sm text-loss">{error}</p>
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleInitialize}
            disabled={loading}
            className="w-full py-3 rounded-lg bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {mode === 'reinitialize' ? 'Reinitializing...' : 'Initializing...'}
              </>
            ) : (
              <>
                {mode === 'reinitialize' ? (
                  <RotateCcw className="w-4 h-4" />
                ) : (
                  <Rocket className="w-4 h-4" />
                )}
                {mode === 'reinitialize' ? 'Reinitialize' : 'Initialize'}
              </>
            )}
          </button>

          {/* Steps info */}
          <div className="pt-4 border-t border-white/[0.08]">
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
              What happens next
            </h3>
            <div className="space-y-2 text-xs text-text-secondary">
              <div className="flex items-start gap-2">
                <span className="text-accent font-medium mt-0.5">1.</span>
                <span>You will be directed to set your portfolio preferences and risk parameters</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-accent font-medium mt-0.5">2.</span>
                <span>AI agents analyze market conditions and your preferences to propose an optimal allocation</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-accent font-medium mt-0.5">3.</span>
                <span>Approve to execute — positions are filled at last close prices with simulated trading costs</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Portfolio Selector Dropdown
// ============================================================

function PortfolioSelector({
  portfolios,
  activeId,
  onChange,
}: {
  portfolios: PortfolioListItem[];
  activeId: string;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const active = portfolios.find((p) => p.id === activeId);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  if (portfolios.length <= 1) return null;

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08] hover:border-white/20 transition-colors text-sm"
      >
        <span className="text-text-primary font-medium truncate max-w-[160px]">
          {active?.name || 'Portfolio'}
        </span>
        <ChevronDown className={`w-4 h-4 text-text-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-dark-700 border border-white/[0.12] rounded-xl shadow-2xl z-40 py-1 animate-fade-in">
          {portfolios.map((p) => (
            <button
              key={p.id}
              onClick={() => {
                onChange(p.id);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-3 hover:bg-dark-600 transition-colors ${
                p.id === activeId ? 'bg-dark-600' : ''
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-text-primary">{p.name}</p>
                  <p className="text-xs text-text-muted mt-0.5">
                    {formatCurrency(p.total_value)} &middot; {p.positions_count} position{p.positions_count !== 1 ? 's' : ''}
                  </p>
                </div>
                <span
                  className={`text-xs font-mono font-medium ${
                    p.pnl >= 0 ? 'text-profit' : 'text-loss'
                  }`}
                >
                  {p.pnl >= 0 ? '+' : ''}{p.pnl_pct.toFixed(2)}%
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Loading Skeleton
// ============================================================

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Portfolio</h1>
          <p className="text-sm text-text-muted mt-1">
            Real-time portfolio positions, allocation, and risk analytics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className="w-2 h-2 rounded-full bg-warning animate-pulse-slow" />
            <span className="text-xs text-text-secondary">Loading</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="card animate-fade-in">
            <div className="flex items-start justify-between">
              <div className="flex-1 space-y-2">
                <div className="h-3 w-20 bg-dark-600 rounded animate-pulse" />
                <div className="h-7 w-32 bg-dark-600 rounded animate-pulse" />
                <div className="h-3 w-24 bg-dark-600 rounded animate-pulse" />
              </div>
              <div className="w-10 h-10 rounded-lg bg-dark-600 animate-pulse" />
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card lg:col-span-1">
          <div className="h-4 w-28 bg-dark-600 rounded animate-pulse mb-4" />
          <div className="h-[260px] bg-dark-600 rounded animate-pulse" />
        </div>
        <div className="lg:col-span-2">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="card">
                <div className="h-3 w-20 bg-dark-600 rounded animate-pulse mb-2" />
                <div className="h-6 w-16 bg-dark-600 rounded animate-pulse mb-1" />
                <div className="h-3 w-12 bg-dark-600 rounded animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card overflow-hidden p-0">
        <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
          <div className="h-4 w-20 bg-dark-600 rounded animate-pulse" />
          <div className="h-3 w-28 bg-dark-600 rounded animate-pulse" />
        </div>
        <div className="p-4 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 bg-dark-600 rounded animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Main Portfolio Page — Monitoring Dashboard
// ============================================================

function PortfolioPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Portfolio list state
  const [portfolios, setPortfolios] = useState<PortfolioListItem[]>([]);
  const [activePortfolioId, setActivePortfolioId] = useState<string>('');
  const [listLoading, setListLoading] = useState(true);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'reinitialize'>('create');

  // Monitoring data
  const [sortField, setSortField] = useState<string>('weight');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [dataLoading, setDataLoading] = useState(false);

  const [overview, setOverview] = useState<PortfolioOverview>({
    total_value: 0,
    cash: 0,
    invested: 0,
    total_pnl: 0,
    total_pnl_pct: 0,
    day_pnl: 0,
    day_pnl_pct: 0,
    positions_count: 0,
    last_updated: '',
  });

  const [positions, setPositions] = useState<Position[]>([]);

  const [risk, setRisk] = useState<RiskMetrics>({
    var_95: 0,
    var_99: 0,
    portfolio_volatility: 0,
    portfolio_beta: 0,
    sharpe_ratio: 0,
    max_drawdown: 0,
    concentration_top5: 0,
    sector_concentration: {},
    correlation_risk: '',
    last_calculated: '',
  });

  const [allocation, setAllocation] = useState<AllocationBreakdown>({
    by_asset_class: [],
    by_sector: [],
    by_geography: [],
    last_updated: '',
  });

  const [outlook, setOutlook] = useState<MarketOutlook>({
    long_term: { layer: 'long_term', sentiment: 'neutral', confidence: 0, summary: '', key_factors: [], risks: [], opportunities: [], last_updated: '' },
    medium_term: { layer: 'medium_term', sentiment: 'neutral', confidence: 0, summary: '', key_factors: [], risks: [], opportunities: [], last_updated: '' },
    short_term: { layer: 'short_term', sentiment: 'neutral', confidence: 0, summary: '', key_factors: [], risks: [], opportunities: [], last_updated: '' },
    consensus_sentiment: 'neutral',
    last_updated: '',
  });

  // Success banner
  const [showApprovedBanner, setShowApprovedBanner] = useState(false);

  // Check for ?approved=true on mount
  useEffect(() => {
    if (searchParams.get('approved') === 'true') {
      setShowApprovedBanner(true);
      // Clean URL without reloading
      const url = new URL(window.location.href);
      url.searchParams.delete('approved');
      window.history.replaceState({}, '', url.pathname + url.search);
    }
  }, [searchParams]);

  // Fetch portfolio list on mount
  const fetchPortfolioList = useCallback(async () => {
    setListLoading(true);
    try {
      const list = await portfolioAPI.list();
      setPortfolios(list);

      if (list.length === 0) {
        // No portfolios — show first-time modal
        setModalMode('create');
        setModalOpen(true);
      } else {
        // Select first portfolio or keep current selection
        setActivePortfolioId((prev) => {
          const stillExists = list.find((p) => p.id === prev);
          return stillExists ? prev : list[0].id;
        });
      }
    } catch (err) {
      console.error('Failed to fetch portfolio list:', err);
      setPortfolios([]);
      setModalMode('create');
      setModalOpen(true);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPortfolioList();
  }, [fetchPortfolioList]);

  // Fetch monitoring data when active portfolio changes
  const fetchMonitoringData = useCallback(async (portfolioId: string) => {
    if (!portfolioId) return;
    setDataLoading(true);
    try {
      const [overviewData, positionsData, riskData, allocationData, outlookData] = await Promise.all([
        portfolioAPI.overview(portfolioId),
        portfolioAPI.positions(portfolioId),
        portfolioAPI.risk(portfolioId),
        portfolioAPI.allocation(portfolioId),
        knowledgeAPI.outlook(),
      ]);
      setOverview(overviewData);
      setPositions(positionsData);
      setRisk(riskData);
      setAllocation(allocationData);
      setOutlook(outlookData);
    } catch (err) {
      console.error('Failed to fetch portfolio monitoring data:', err);
    } finally {
      setDataLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activePortfolioId) {
      fetchMonitoringData(activePortfolioId);
    }
  }, [activePortfolioId, fetchMonitoringData]);

  // Handlers
  const handlePortfolioChange = (id: string) => {
    setActivePortfolioId(id);
  };

  const handleNewPortfolio = () => {
    setModalMode('create');
    setModalOpen(true);
  };

  const handleReinitialize = () => {
    setModalMode('reinitialize');
    setModalOpen(true);
  };

  const handleModalClose = () => {
    // Only allow closing if user has at least one portfolio
    if (portfolios.length > 0) {
      setModalOpen(false);
    }
  };

  // Sorting
  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  // Derived data
  const allocationData = allocation.by_asset_class.map((entry, index) => ({
    name: entry.category,
    value: Math.round(entry.current_weight * 100) / 100,
    color: getColorForCategory(entry.category, index),
  }));

  const computedPositions = positions.map((p) => ({
    ...p,
    pnlDollar: p.unrealized_pnl,
    pnlPct: p.unrealized_pnl_pct,
  }));

  const sortedPositions = [...computedPositions].sort((a, b) => {
    const aVal = sortField === 'pnl' ? a.pnlDollar : sortField === 'pnlPct' ? a.pnlPct : a.weight;
    const bVal = sortField === 'pnl' ? b.pnlDollar : sortField === 'pnlPct' ? b.pnlPct : b.weight;
    return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
  });

  const riskMetrics = [
    { label: 'Value at Risk (95%)', value: formatCurrency(risk.var_95), sublabel: '1-day VaR', icon: AlertTriangle, color: 'text-warning' },
    { label: 'Volatility', value: `${(risk.portfolio_volatility * 100).toFixed(1)}%`, sublabel: 'Annualized', icon: Activity, color: 'text-info' },
    { label: 'Max Drawdown', value: `${(risk.max_drawdown * 100).toFixed(1)}%`, sublabel: 'Since inception', icon: TrendingDown, color: 'text-loss' },
    { label: 'Sharpe Ratio', value: risk.sharpe_ratio.toFixed(2), sublabel: 'Risk-adj. return', icon: Target, color: 'text-profit' },
    { label: 'Beta', value: risk.portfolio_beta.toFixed(2), sublabel: 'vs S&P 500', icon: BarChart3, color: 'text-accent' },
    { label: 'Top-5 Conc.', value: `${(risk.concentration_top5 * 100).toFixed(0)}%`, sublabel: 'Concentration', icon: PieChartIcon, color: 'text-info-light' },
  ];

  const riskScore = deriveRiskScore(risk);
  const pnlIsPositive = overview.total_pnl >= 0;
  const pnlColorClass = pnlIsPositive ? 'text-profit' : 'text-loss';

  const outlookSections = [
    { title: 'Long-term (6-12 mo)', data: outlook.long_term },
    { title: 'Mid-term (1-6 mo)', data: outlook.medium_term },
    { title: 'Short-term (1-4 wk)', data: outlook.short_term },
  ];

  // Show loading skeleton while fetching portfolio list
  if (listLoading) {
    return (
      <>
        <LoadingSkeleton />
        <InitModal
          open={modalOpen}
          onClose={handleModalClose}
          mode={modalMode}
          existingPortfolioId={activePortfolioId || undefined}
        />
      </>
    );
  }

  // If we have no portfolios and the modal is not open yet, show a minimal state
  // (the modal should auto-open via the useEffect above)
  const hasPortfolios = portfolios.length > 0;

  return (
    <div className="space-y-6">
      {/* Init / Reinitialize Modal */}
      <InitModal
        open={modalOpen}
        onClose={handleModalClose}
        mode={modalMode}
        existingPortfolioId={activePortfolioId || undefined}
      />

      {/* Success Banner — shown after returning from approval */}
      {showApprovedBanner && (
        <div className="p-4 rounded-xl bg-profit/10 border border-profit/20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-profit" />
            <p className="text-sm text-profit font-medium">
              Portfolio approved and trades executed successfully!
            </p>
          </div>
          <button
            onClick={() => setShowApprovedBanner(false)}
            className="text-xs text-text-muted hover:text-text-secondary"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-text-primary">Portfolio</h1>
            <p className="text-sm text-text-muted mt-1">
              Real-time portfolio positions, allocation, and risk analytics
            </p>
          </div>
          {hasPortfolios && (
            <PortfolioSelector
              portfolios={portfolios}
              activeId={activePortfolioId}
              onChange={handlePortfolioChange}
            />
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasPortfolios && (
            <>
              <Link
                href={`/portfolio/preferences?portfolio_id=${activePortfolioId}`}
                className="btn-secondary flex items-center gap-2 text-xs"
              >
                <Settings className="w-3.5 h-3.5" />
                Preferences
              </Link>
              <button
                onClick={handleReinitialize}
                className="btn-secondary flex items-center gap-2 text-xs"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reinitialize
              </button>
            </>
          )}
          {portfolios.length < MAX_PORTFOLIOS && (
            <button
              onClick={handleNewPortfolio}
              className="btn-secondary flex items-center gap-2 text-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              New Portfolio
            </button>
          )}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-700 border border-white/[0.08]">
            <div className={`w-2 h-2 rounded-full ${hasPortfolios ? 'bg-profit' : 'bg-warning'} animate-pulse-slow`} />
            <span className="text-xs text-text-secondary">{hasPortfolios ? 'Live' : 'No Portfolio'}</span>
          </div>
        </div>
      </div>

      {/* If no portfolios, show empty state behind the modal */}
      {!hasPortfolios && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
            <Rocket className="w-8 h-8 text-accent" />
          </div>
          <h2 className="text-xl font-semibold text-text-primary mb-2">No portfolios yet</h2>
          <p className="text-sm text-text-muted max-w-md">
            Initialize your first portfolio to get started with AI-optimized allocation and real-time monitoring.
          </p>
          <button
            onClick={handleNewPortfolio}
            className="mt-6 px-6 py-3 rounded-lg bg-accent text-white font-medium text-sm hover:bg-accent/90 transition-colors flex items-center gap-2"
          >
            <Rocket className="w-4 h-4" />
            Initialize Portfolio
          </button>
        </div>
      )}

      {/* Monitoring Dashboard — only render when we have portfolios */}
      {hasPortfolios && (
        <>
          {dataLoading ? (
            <LoadingSkeleton />
          ) : overview.positions_count === 0 && overview.invested === 0 ? (
            /* Empty portfolio — guide user to set preferences and generate proposal */
            <div className="card max-w-lg mx-auto text-center py-12">
              <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center mx-auto mb-4">
                <Rocket className="w-6 h-6 text-accent" />
              </div>
              <p className="text-sm text-text-primary font-medium mb-2">Portfolio is empty</p>
              <p className="text-xs text-text-muted mb-6">
                Set your preferences and generate a proposal to start trading.
              </p>
              <Link
                href={`/portfolio/preferences?portfolio_id=${activePortfolioId}&init=true`}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent/90 transition-colors"
              >
                <Settings className="w-3.5 h-3.5" />
                Set Preferences & Generate Proposal
              </Link>
            </div>
          ) : (
            <>
              {/* Summary Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                <div className="card animate-fade-in">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Total Value</p>
                      <p className="text-2xl font-bold text-text-primary tracking-tight">{formatCurrency(overview.total_value)}</p>
                      <span className="text-xs text-text-muted">All positions + cash</span>
                    </div>
                    <div className="w-10 h-10 rounded-lg bg-info-muted flex items-center justify-center">
                      <DollarSign className="w-5 h-5 text-info" />
                    </div>
                  </div>
                </div>

                <div className="card animate-fade-in">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Cash</p>
                      <p className="text-2xl font-bold text-text-primary tracking-tight">{formatCurrency(overview.cash)}</p>
                      <span className="text-xs text-text-muted">
                        {overview.total_value > 0
                          ? `${((overview.cash / overview.total_value) * 100).toFixed(1)}% of portfolio`
                          : '0% of portfolio'}
                      </span>
                    </div>
                    <div className="w-10 h-10 rounded-lg bg-warning-muted flex items-center justify-center">
                      <Wallet className="w-5 h-5 text-warning" />
                    </div>
                  </div>
                </div>

                <div className="card animate-fade-in">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Invested</p>
                      <p className="text-2xl font-bold text-text-primary tracking-tight">{formatCurrency(overview.invested)}</p>
                      <span className="text-xs text-text-muted">{overview.positions_count} active position{overview.positions_count !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="w-10 h-10 rounded-lg bg-accent-muted flex items-center justify-center">
                      <PieChartIcon className="w-5 h-5 text-accent" />
                    </div>
                  </div>
                </div>

                <div className="card animate-fade-in">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Total P&L</p>
                      <p className={`text-2xl font-bold ${pnlColorClass} tracking-tight`}>{formatCurrencyDetailed(overview.total_pnl)}</p>
                      <span className={`text-xs ${pnlColorClass} font-medium`}>
                        {overview.total_pnl_pct >= 0 ? '+' : ''}{overview.total_pnl_pct.toFixed(2)}%
                      </span>
                      <span className="text-xs text-text-muted ml-1">all time</span>
                    </div>
                    <div className={`w-10 h-10 rounded-lg ${pnlIsPositive ? 'bg-profit-muted' : 'bg-loss-muted'} flex items-center justify-center`}>
                      {pnlIsPositive
                        ? <TrendingUp className="w-5 h-5 text-profit" />
                        : <TrendingDown className="w-5 h-5 text-loss" />
                      }
                    </div>
                  </div>
                </div>

                <div className="card animate-fade-in">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-1">Risk Score</p>
                      <p className={`text-2xl font-bold ${riskScore.colorClass} tracking-tight`}>{riskScore.score}</p>
                      <span className={`text-xs ${riskScore.colorClass}`}>{riskScore.label}</span>
                    </div>
                    <div className="w-10 h-10 rounded-lg bg-warning-muted flex items-center justify-center">
                      <Shield className="w-5 h-5 text-warning" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Allocation Chart + Risk Metrics */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="card lg:col-span-1">
                  <h3 className="text-sm font-semibold text-text-primary mb-4">Asset Allocation</h3>
                  {allocationData.length > 0 ? (
                    <>
                      <ResponsiveContainer width="100%" height={260}>
                        <PieChart>
                          <Pie
                            data={allocationData}
                            cx="50%"
                            cy="50%"
                            innerRadius={60}
                            outerRadius={95}
                            paddingAngle={3}
                            dataKey="value"
                            animationDuration={800}
                          >
                            {allocationData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                            ))}
                          </Pie>
                          <Tooltip content={<CustomPieTooltip />} />
                          <Legend
                            verticalAlign="bottom"
                            height={36}
                            formatter={(value: string) => (
                              <span className="text-xs text-text-secondary">{value}</span>
                            )}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="mt-2 space-y-1.5">
                        {allocationData.map((item) => (
                          <div key={item.name} className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-2">
                              <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
                              <span className="text-text-secondary">{item.name}</span>
                            </div>
                            <span className="text-text-primary font-medium">{item.value}%</span>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center justify-center h-[260px] text-text-muted text-sm">
                      No allocation data available
                    </div>
                  )}
                </div>

                <div className="lg:col-span-2">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {riskMetrics.map((metric) => {
                      const Icon = metric.icon;
                      return (
                        <div key={metric.label} className="card">
                          <div className="flex items-center gap-2 mb-2">
                            <Icon className={`w-4 h-4 ${metric.color}`} />
                            <span className="text-xs text-text-muted">{metric.label}</span>
                          </div>
                          <p className="text-xl font-bold text-text-primary">{metric.value}</p>
                          <span className="text-[11px] text-text-muted">{metric.sublabel}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Positions Table */}
              <div className="card overflow-hidden p-0">
                <div className="px-4 py-3 border-b border-white/[0.08] flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-text-primary">Positions</h3>
                  <span className="text-xs text-text-muted">{positions.length} active position{positions.length !== 1 ? 's' : ''}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/[0.08]">
                        <th className="table-header text-left px-4 py-3">Ticker</th>
                        <th className="table-header text-left px-4 py-3">Direction</th>
                        <th className="table-header text-right px-4 py-3">Qty</th>
                        <th className="table-header text-right px-4 py-3">Entry Price</th>
                        <th className="table-header text-right px-4 py-3">Current Price</th>
                        <th
                          className="table-header text-right px-4 py-3 cursor-pointer hover:text-text-secondary"
                          onClick={() => handleSort('pnl')}
                        >
                          P&L ($) {sortField === 'pnl' && (sortDir === 'desc' ? '\u25BC' : '\u25B2')}
                        </th>
                        <th
                          className="table-header text-right px-4 py-3 cursor-pointer hover:text-text-secondary"
                          onClick={() => handleSort('pnlPct')}
                        >
                          P&L (%) {sortField === 'pnlPct' && (sortDir === 'desc' ? '\u25BC' : '\u25B2')}
                        </th>
                        <th
                          className="table-header text-right px-4 py-3 cursor-pointer hover:text-text-secondary"
                          onClick={() => handleSort('weight')}
                        >
                          Weight {sortField === 'weight' && (sortDir === 'desc' ? '\u25BC' : '\u25B2')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedPositions.length === 0 ? (
                        <tr>
                          <td colSpan={8} className="text-center py-8 text-text-muted text-sm">
                            No positions in this portfolio
                          </td>
                        </tr>
                      ) : (
                        sortedPositions.map((pos) => {
                          const directionLabel = pos.direction.charAt(0).toUpperCase() + pos.direction.slice(1);
                          const isLong = pos.direction.toLowerCase() === 'long';
                          return (
                            <tr
                              key={pos.id}
                              className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                            >
                              <td className="table-cell">
                                <div className="flex items-center gap-2">
                                  <span className="px-1.5 py-0.5 rounded bg-dark-500 text-xs font-mono text-text-primary font-medium">
                                    {pos.symbol}
                                  </span>
                                  <span className="text-[11px] text-text-muted hidden lg:inline">{pos.asset_class}</span>
                                </div>
                              </td>
                              <td className="table-cell">
                                <span
                                  className={`status-badge ${
                                    isLong
                                      ? 'text-profit bg-profit-muted'
                                      : 'text-loss bg-loss-muted'
                                  }`}
                                >
                                  {directionLabel}
                                </span>
                              </td>
                              <td className="table-cell text-right font-mono">{pos.quantity.toLocaleString()}</td>
                              <td className="table-cell text-right font-mono">${pos.avg_entry_price.toFixed(2)}</td>
                              <td className="table-cell text-right font-mono">${pos.current_price.toFixed(2)}</td>
                              <td className={`table-cell text-right font-mono ${pos.pnlDollar >= 0 ? 'text-profit' : 'text-loss'}`}>
                                {pos.pnlDollar >= 0 ? '+' : ''}${pos.pnlDollar.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </td>
                              <td className={`table-cell text-right font-mono ${pos.pnlPct >= 0 ? 'text-profit' : 'text-loss'}`}>
                                {pos.pnlPct >= 0 ? '+' : ''}{pos.pnlPct.toFixed(2)}%
                              </td>
                              <td className="table-cell text-right font-mono text-text-primary">{pos.weight.toFixed(1)}%</td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Market Outlook */}
              <div className="card">
                <h3 className="text-sm font-semibold text-text-primary mb-4">Market Outlook by Timeframe</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {outlookSections.map((section) => {
                    const layer = section.data;
                    const sentiment = layer.sentiment.toLowerCase();
                    const sentimentLabel = sentiment.charAt(0).toUpperCase() + sentiment.slice(1);
                    const OutlookIcon = outlookIcons[sentiment] || Minus;
                    const colorClass = outlookColors[sentiment] || 'text-text-muted';

                    return (
                      <div key={section.title}>
                        <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
                          {section.title}
                        </h4>

                        <div className="flex items-center justify-between p-2.5 rounded-lg bg-dark-800 mb-2">
                          <span className="text-sm text-text-secondary">Sentiment</span>
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-medium ${colorClass}`}>
                              {sentimentLabel}
                            </span>
                            <OutlookIcon className={`w-3.5 h-3.5 ${colorClass}`} />
                            <span className="text-[10px] text-text-muted">{Math.round(layer.confidence * 100)}%</span>
                          </div>
                        </div>

                        {layer.summary && (
                          <p className="text-xs text-text-secondary mb-2 px-1 leading-relaxed">{layer.summary}</p>
                        )}

                        {layer.key_factors.length > 0 && (
                          <div className="space-y-1">
                            {layer.key_factors.map((factor, idx) => (
                              <div
                                key={idx}
                                className="flex items-center justify-between p-2.5 rounded-lg bg-dark-800"
                              >
                                <span className="text-sm text-text-secondary">{factor}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

// ============================================================
// Default export wraps in Suspense for useSearchParams
// ============================================================

export default function PortfolioPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 text-accent animate-spin" />
        </div>
      }
    >
      <PortfolioPageInner />
    </Suspense>
  );
}
