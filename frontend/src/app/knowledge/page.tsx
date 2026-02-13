'use client';

import { useState } from 'react';
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
} from 'lucide-react';

// --- Mock Data ---

type LayerType = 'long_term' | 'mid_term' | 'short_term';

interface KnowledgeEntry {
  id: string;
  title: string;
  summary: string;
  category: string;
  source: string;
  credibility: number;
  timestamp: string;
  layer: LayerType;
}

const knowledgeEntries: KnowledgeEntry[] = [
  // Long-term
  {
    id: 'LT-001',
    title: 'AI Infrastructure Capex Supercycle',
    summary: 'Hyperscaler capex guidance indicates 40%+ YoY growth in AI infrastructure through 2027. Data center power consumption projected to double.',
    category: 'Macro Thesis',
    source: 'Goldman Sachs Research',
    credibility: 92,
    timestamp: '2025-04-20T10:00:00Z',
    layer: 'long_term',
  },
  {
    id: 'LT-002',
    title: 'Nuclear Renaissance for Data Centers',
    summary: 'Multiple tech companies signing nuclear PPAs. SMR technology advancing. Uranium supply constrained as mine restarts take 3-5 years.',
    category: 'Sector Thesis',
    source: 'Morgan Stanley',
    credibility: 88,
    timestamp: '2025-04-18T14:00:00Z',
    layer: 'long_term',
  },
  {
    id: 'LT-003',
    title: 'Demographic Shift: Aging Populations',
    summary: 'Japan, Europe, and China facing accelerating demographic decline. Healthcare and automation sectors to benefit structurally.',
    category: 'Macro Thesis',
    source: 'UN Population Division',
    credibility: 95,
    timestamp: '2025-04-15T08:00:00Z',
    layer: 'long_term',
  },
  {
    id: 'LT-004',
    title: 'De-dollarization Trend Analysis',
    summary: 'BRICS nations increasing bilateral trade settlement in local currencies. Gold reserves accumulation at record levels by central banks.',
    category: 'Macro Thesis',
    source: 'BIS Quarterly Review',
    credibility: 90,
    timestamp: '2025-04-12T11:00:00Z',
    layer: 'long_term',
  },
  // Mid-term
  {
    id: 'MT-001',
    title: 'CRE Maturity Wall Approaching',
    summary: '$1.5T in commercial real estate loans maturing through 2025-2026. Office vacancy rates at 19.6%. Regional banks most exposed.',
    category: 'Risk Factor',
    source: 'CBRE Research',
    credibility: 87,
    timestamp: '2025-04-20T09:00:00Z',
    layer: 'mid_term',
  },
  {
    id: 'MT-002',
    title: 'Fed Rate Cut Expectations',
    summary: 'Market pricing 3 rate cuts by end of 2025. PCE trending toward 2.3%. Labor market showing early signs of softening.',
    category: 'Monetary Policy',
    source: 'Federal Reserve',
    credibility: 94,
    timestamp: '2025-04-19T16:00:00Z',
    layer: 'mid_term',
  },
  {
    id: 'MT-003',
    title: 'Semiconductor Inventory Cycle',
    summary: 'Channel inventory normalization nearing completion. Auto and industrial demand recovery expected H2 2025. AI chip demand remains supply-constrained.',
    category: 'Sector Analysis',
    source: 'Gartner',
    credibility: 85,
    timestamp: '2025-04-17T10:00:00Z',
    layer: 'mid_term',
  },
  {
    id: 'MT-004',
    title: 'Earnings Growth Broadening',
    summary: 'S&P 500 earnings growth expected to broaden beyond Mag-7 in Q2-Q3. Small-cap earnings revisions turning positive.',
    category: 'Market Analysis',
    source: 'JP Morgan Strategy',
    credibility: 82,
    timestamp: '2025-04-16T14:00:00Z',
    layer: 'mid_term',
  },
  // Short-term
  {
    id: 'ST-001',
    title: 'NVDA Earnings Preview',
    summary: 'NVIDIA reports next week. Street expects $24.5B revenue. Whisper number at $26B. Key focus: data center margins and Blackwell ramp.',
    category: 'Earnings',
    source: 'Bloomberg',
    credibility: 91,
    timestamp: '2025-04-20T16:00:00Z',
    layer: 'short_term',
  },
  {
    id: 'ST-002',
    title: 'FOMC Meeting Minutes Released',
    summary: 'Minutes showed divided committee. Several members noted upside inflation risks. Market repriced rate expectations slightly hawkish.',
    category: 'Monetary Policy',
    source: 'Federal Reserve',
    credibility: 98,
    timestamp: '2025-04-20T14:00:00Z',
    layer: 'short_term',
  },
  {
    id: 'ST-003',
    title: 'VIX at Historical Lows',
    summary: 'VIX at 12.3, near multi-year lows. Put protection historically cheap. Elevated event risk ahead (FOMC + earnings season).',
    category: 'Volatility',
    source: 'CBOE',
    credibility: 96,
    timestamp: '2025-04-20T11:00:00Z',
    layer: 'short_term',
  },
  {
    id: 'ST-004',
    title: 'Unusual Options Activity: TSLA',
    summary: 'Large put spread bought in TSLA: 10K contracts of May 240/220 put spread. Potential institutional hedging or directional bet.',
    category: 'Flow Analysis',
    source: 'Options Clearing Corp',
    credibility: 85,
    timestamp: '2025-04-20T15:30:00Z',
    layer: 'short_term',
  },
];

const sourceRankings = [
  { name: 'Federal Reserve', score: 96, totalIdeas: 24, profitablePct: 78, avgReturn: 4.2 },
  { name: 'Goldman Sachs Research', score: 92, totalIdeas: 67, profitablePct: 65, avgReturn: 3.8 },
  { name: 'Bloomberg', score: 91, totalIdeas: 142, profitablePct: 61, avgReturn: 2.9 },
  { name: 'BIS Quarterly Review', score: 90, totalIdeas: 12, profitablePct: 75, avgReturn: 5.1 },
  { name: 'Morgan Stanley', score: 88, totalIdeas: 53, profitablePct: 62, avgReturn: 3.4 },
  { name: 'CBRE Research', score: 87, totalIdeas: 18, profitablePct: 72, avgReturn: 4.5 },
  { name: 'Options Clearing Corp', score: 85, totalIdeas: 31, profitablePct: 58, avgReturn: 2.1 },
  { name: 'Gartner', score: 85, totalIdeas: 22, profitablePct: 64, avgReturn: 3.0 },
  { name: 'JP Morgan Strategy', score: 82, totalIdeas: 45, profitablePct: 60, avgReturn: 2.7 },
  { name: 'Reuters', score: 79, totalIdeas: 198, profitablePct: 55, avgReturn: 1.8 },
];

const marketOutlook = [
  { asset: 'Equities', outlook: 'Bullish', confidence: 72, drivers: 'AI capex, earnings broadening, rate cuts' },
  { asset: 'Bonds', outlook: 'Neutral', confidence: 55, drivers: 'Rate cut expectations vs fiscal deficit supply' },
  { asset: 'Commodities', outlook: 'Bullish', confidence: 68, drivers: 'Gold on rate cuts, energy on geopolitics' },
  { asset: 'Crypto', outlook: 'Neutral', confidence: 48, drivers: 'ETF flows positive but regulatory uncertainty' },
];

const learningRecommendations = [
  {
    title: 'Understanding Volatility Surface Dynamics',
    description: 'Deep dive into how implied volatility surfaces change around earnings events and macro catalysts.',
    category: 'Options',
    difficulty: 'Advanced',
    estimatedTime: '45 min',
  },
  {
    title: 'CRE Risk Transmission Mechanisms',
    description: 'How commercial real estate losses propagate through the banking system and impact credit markets.',
    category: 'Risk',
    difficulty: 'Intermediate',
    estimatedTime: '30 min',
  },
  {
    title: 'Reinforcement Learning for Portfolio Optimization',
    description: 'How RL agents learn optimal allocation strategies through reward shaping and experience replay.',
    category: 'AI/ML',
    difficulty: 'Advanced',
    estimatedTime: '60 min',
  },
  {
    title: 'Reading FOMC Minutes: A Practical Guide',
    description: 'Key phrases, voting patterns, and dissents that signal shifts in monetary policy direction.',
    category: 'Macro',
    difficulty: 'Beginner',
    estimatedTime: '20 min',
  },
];

const outlookColors: Record<string, string> = {
  Bullish: 'text-profit',
  Neutral: 'text-warning',
  Bearish: 'text-loss',
};

const outlookIcons: Record<string, typeof ArrowUp> = {
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
  Intermediate: 'text-warning bg-warning-muted',
  Advanced: 'text-loss bg-loss-muted',
};

export default function KnowledgePage() {
  const [activeLayer, setActiveLayer] = useState<LayerType>('short_term');
  const [searchQuery, setSearchQuery] = useState('');

  const layers: { key: LayerType; label: string; icon: typeof Layers }[] = [
    { key: 'long_term', label: 'Long-term', icon: Layers },
    { key: 'mid_term', label: 'Mid-term', icon: Clock },
    { key: 'short_term', label: 'Short-term', icon: Zap },
  ];

  const filteredEntries = knowledgeEntries.filter((entry) => {
    if (entry.layer !== activeLayer) return false;
    if (searchQuery && !entry.title.toLowerCase().includes(searchQuery.toLowerCase()) && !entry.summary.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

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
          <button className="btn-primary flex items-center gap-2">
            <Database className="w-4 h-4" />
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
                <span className={`ml-1 px-1.5 py-0.5 rounded-full text-[10px] ${
                  activeLayer === layer.key ? 'bg-info/20 text-info' : 'bg-dark-500 text-text-muted'
                }`}>
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
          {filteredEntries.map((entry) => (
            <div
              key={entry.id}
              className="p-4 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1.5">
                    <h4 className="text-sm font-medium text-text-primary">{entry.title}</h4>
                    <span className={`status-badge text-[10px] ${categoryColors[entry.category] || 'text-text-secondary bg-dark-500'}`}>
                      {entry.category}
                    </span>
                  </div>
                  <p className="text-xs text-text-secondary leading-relaxed mb-2">{entry.summary}</p>
                  <div className="flex items-center gap-4 text-[11px] text-text-muted">
                    <span className="flex items-center gap-1">
                      <ExternalLink className="w-3 h-3" />
                      {entry.source}
                    </span>
                    <span className="flex items-center gap-1">
                      <Star className="w-3 h-3" />
                      Credibility: {entry.credibility}/100
                    </span>
                    <span>
                      {new Date(entry.timestamp).toLocaleDateString()}{' '}
                      {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
                <div className="shrink-0 flex flex-col items-center">
                  <div
                    className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold ${
                      entry.credibility >= 90
                        ? 'bg-profit-muted text-profit'
                        : entry.credibility >= 80
                        ? 'bg-info-muted text-info'
                        : 'bg-warning-muted text-warning'
                    }`}
                  >
                    {entry.credibility}
                  </div>
                </div>
              </div>
            </div>
          ))}
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
                  <th className="table-header text-right px-4 py-3">Ideas</th>
                  <th className="table-header text-right px-4 py-3">Profitable %</th>
                  <th className="table-header text-right px-4 py-3">Avg Return</th>
                </tr>
              </thead>
              <tbody>
                {sourceRankings.map((source) => (
                  <tr
                    key={source.name}
                    className="border-b border-white/[0.05] hover:bg-dark-750 transition-colors"
                  >
                    <td className="table-cell">
                      <span className="text-text-primary text-xs font-medium">{source.name}</span>
                    </td>
                    <td className="table-cell text-right">
                      <span
                        className={`font-mono font-medium text-xs ${
                          source.score >= 90 ? 'text-profit' : source.score >= 85 ? 'text-info' : 'text-warning'
                        }`}
                      >
                        {source.score}
                      </span>
                    </td>
                    <td className="table-cell text-right font-mono text-xs">{source.totalIdeas}</td>
                    <td className="table-cell text-right font-mono text-xs">
                      <span className={source.profitablePct >= 65 ? 'text-profit' : 'text-text-secondary'}>
                        {source.profitablePct}%
                      </span>
                    </td>
                    <td className="table-cell text-right font-mono text-xs">
                      <span className="text-profit">+{source.avgReturn}%</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Market Outlook */}
        <div className="space-y-6">
          <div className="card">
            <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-profit" />
              Market Outlook by Asset Class
            </h3>
            <div className="space-y-3">
              {marketOutlook.map((item) => {
                const OutlookIcon = outlookIcons[item.outlook];
                return (
                  <div
                    key={item.asset}
                    className="p-3 rounded-lg bg-dark-800 border border-white/[0.05]"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm font-medium text-text-primary">{item.asset}</span>
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-semibold ${outlookColors[item.outlook]}`}>
                          {item.outlook}
                        </span>
                        <OutlookIcon className={`w-3.5 h-3.5 ${outlookColors[item.outlook]}`} />
                        <span className="text-[10px] text-text-muted">{item.confidence}%</span>
                      </div>
                    </div>
                    <p className="text-[11px] text-text-muted">{item.drivers}</p>
                    <div className="mt-2 w-full bg-dark-600 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${
                          item.outlook === 'Bullish' ? 'bg-profit' : item.outlook === 'Neutral' ? 'bg-warning' : 'bg-loss'
                        }`}
                        style={{ width: `${item.confidence}%` }}
                      />
                    </div>
                  </div>
                );
              })}
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
          {learningRecommendations.map((rec) => (
            <div
              key={rec.title}
              className="p-4 rounded-lg bg-dark-800 border border-white/[0.05] hover:border-white/[0.1] transition-colors cursor-pointer"
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="text-sm font-medium text-text-primary flex-1">{rec.title}</h4>
                <span className={`status-badge text-[10px] ml-2 shrink-0 ${difficultyColors[rec.difficulty]}`}>
                  {rec.difficulty}
                </span>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed mb-3">{rec.description}</p>
              <div className="flex items-center gap-3 text-[11px] text-text-muted">
                <span className="flex items-center gap-1">
                  <Tag className="w-3 h-3" />
                  {rec.category}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {rec.estimatedTime}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
