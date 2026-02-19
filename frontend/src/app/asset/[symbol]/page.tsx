'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Search,
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Minus,
  Newspaper,
  MessageCircle,
  Brain,
  Info,
  AlertTriangle,
  Target,
  Loader2,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Clock,
} from 'lucide-react';
import { marketDataAPI, portfolioAPI } from '@/lib/api';
import type { AssetInfo, NewsItem, SocialPost, AssetSummary, Position } from '@/types';

function formatNumber(n: number | null | undefined, opts?: { currency?: boolean; compact?: boolean; pct?: boolean }) {
  if (n == null) return '--';
  if (opts?.pct) return `${(n * 100).toFixed(2)}%`;
  if (opts?.compact) {
    if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
    if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
    if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
    if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  }
  if (opts?.currency) return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return n.toLocaleString();
}

const outlookColors: Record<string, string> = {
  bullish: 'text-profit bg-profit-muted',
  bearish: 'text-loss bg-loss-muted',
  neutral: 'text-warning bg-warning-muted',
};

export default function AssetDetailPage() {
  const params = useParams();
  const router = useRouter();
  const symbol = (params.symbol as string)?.toUpperCase() || '';

  const [searchQuery, setSearchQuery] = useState('');
  const [positions, setPositions] = useState<Position[]>([]);
  const [info, setInfo] = useState<AssetInfo | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [social, setSocial] = useState<SocialPost[]>([]);
  const [summary, setSummary] = useState<AssetSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'news' | 'social' | 'summary'>('overview');

  const fetchAssetData = useCallback(async (sym: string, refresh = false) => {
    if (refresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      const [infoData, newsData, socialData, summaryData] = await Promise.all([
        marketDataAPI.info(sym, refresh).catch(() => null),
        marketDataAPI.news(sym, refresh).catch(() => []),
        marketDataAPI.social(sym, refresh).catch(() => []),
        marketDataAPI.summary(sym, refresh).catch(() => null),
      ]);
      setInfo(infoData);
      setNews(newsData);
      setSocial(socialData);
      setSummary(summaryData);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleRefresh = () => {
    if (symbol && !refreshing) {
      fetchAssetData(symbol, true);
    }
  };

  useEffect(() => {
    portfolioAPI.positions().catch(() => []).then(setPositions);
  }, []);

  useEffect(() => {
    if (symbol) {
      fetchAssetData(symbol);
    }
  }, [symbol, fetchAssetData]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchQuery.trim().toUpperCase();
    if (q) {
      router.push(`/asset/${q}`);
    }
  };

  const changeColor = (val: number | null | undefined) =>
    val == null ? 'text-text-secondary' : val >= 0 ? 'text-profit' : 'text-loss';

  return (
    <div className="space-y-6">
      {/* Header with search */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link href="/" className="p-2 rounded-lg bg-dark-700 hover:bg-dark-600 transition-colors">
            <ArrowLeft className="w-4 h-4 text-text-secondary" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-text-primary">
              {info?.name || symbol || 'Asset Detail'}
            </h1>
            {symbol && (
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm font-mono text-info">{symbol}</span>
                {info?.sector && (
                  <span className="text-xs text-text-muted px-2 py-0.5 rounded bg-dark-700">
                    {info.sector}
                  </span>
                )}
                {info?.asset_class && (
                  <span className="text-xs text-text-muted px-2 py-0.5 rounded bg-dark-700 capitalize">
                    {info.asset_class}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search ticker..."
              className="pl-9 pr-4 py-2 w-48 rounded-lg bg-dark-700 border border-white/[0.08] text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-info/50"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-info/10 text-info text-sm font-medium hover:bg-info/20 transition-colors"
          >
            Go
          </button>
        </form>
      </div>

      {/* Portfolio positions quick select */}
      {positions.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-text-muted">Portfolio:</span>
          {positions.map((p) => (
            <Link
              key={p.id}
              href={`/asset/${p.symbol}`}
              className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                p.symbol === symbol
                  ? 'bg-info/10 text-info border border-info/20'
                  : 'bg-dark-700 text-text-secondary hover:text-text-primary hover:bg-dark-600'
              }`}
            >
              {p.symbol}
            </Link>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 text-info animate-spin" />
            <span className="text-sm text-text-muted">Loading {symbol} data...</span>
          </div>
        </div>
      ) : (
        <>
          {/* Price header card */}
          <div className="card">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-baseline gap-3">
                  <span className="text-3xl font-bold text-text-primary">
                    {formatNumber(info?.price, { currency: true })}
                  </span>
                  <span className={`text-lg font-semibold ${changeColor(info?.change)}`}>
                    {info?.change != null && (info.change >= 0 ? '+' : '')}
                    {formatNumber(info?.change, { currency: true })}
                  </span>
                  <span className={`text-sm font-medium ${changeColor(info?.change_pct)}`}>
                    ({info?.change_pct != null ? `${(info.change_pct * 100).toFixed(2)}%` : '--'})
                  </span>
                </div>
                <p className="text-xs text-text-muted mt-1">
                  Previous close: {formatNumber(info?.previous_close, { currency: true })}
                </p>
              </div>
              {info?.change_pct != null && (
                <div className={`p-3 rounded-xl ${info.change_pct >= 0 ? 'bg-profit-muted' : 'bg-loss-muted'}`}>
                  {info.change_pct >= 0 ? (
                    <ArrowUpRight className="w-6 h-6 text-profit" />
                  ) : (
                    <ArrowDownRight className="w-6 h-6 text-loss" />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Cache status bar */}
          <div className="flex items-center justify-between px-4 py-2 rounded-lg bg-dark-800 border border-white/[0.06]">
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Clock className="w-3.5 h-3.5" />
              {info?.cached ? (
                <span>
                  Cached data from{' '}
                  <span className="text-text-secondary font-medium">
                    {info.fetched_at ? new Date(info.fetched_at).toLocaleString() : 'unknown'}
                  </span>
                </span>
              ) : (
                <span>
                  Fetched live at{' '}
                  <span className="text-text-secondary font-medium">
                    {info?.fetched_at ? new Date(info.fetched_at).toLocaleString() : info?.updated_at ? new Date(info.updated_at).toLocaleString() : 'just now'}
                  </span>
                </span>
              )}
            </div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                refreshing
                  ? 'bg-dark-600 text-text-muted cursor-not-allowed'
                  : 'bg-info/10 text-info hover:bg-info/20'
              }`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-1 border-b border-white/[0.08] pb-0">
            {(['overview', 'news', 'social', 'summary'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
                  activeTab === tab
                    ? 'text-info border-info'
                    : 'text-text-muted hover:text-text-secondary border-transparent'
                }`}
              >
                {tab === 'overview' && <Info className="w-3.5 h-3.5 inline mr-1.5" />}
                {tab === 'news' && <Newspaper className="w-3.5 h-3.5 inline mr-1.5" />}
                {tab === 'social' && <MessageCircle className="w-3.5 h-3.5 inline mr-1.5" />}
                {tab === 'summary' && <Brain className="w-3.5 h-3.5 inline mr-1.5" />}
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Key metrics grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: 'Market Cap', value: formatNumber(info?.market_cap, { compact: true }) },
                  { label: 'P/E Ratio', value: info?.pe_ratio?.toFixed(2) ?? '--' },
                  { label: 'Forward P/E', value: info?.forward_pe?.toFixed(2) ?? '--' },
                  { label: 'EPS', value: formatNumber(info?.eps, { currency: true }) },
                  { label: 'Beta', value: info?.beta?.toFixed(2) ?? '--' },
                  { label: 'Div Yield', value: info?.dividend_yield ? `${(info.dividend_yield * 100).toFixed(2)}%` : '--' },
                  { label: 'Volume', value: info?.volume?.toLocaleString() ?? '--' },
                  { label: 'Avg Volume', value: info?.avg_volume?.toLocaleString() ?? '--' },
                ].map((m) => (
                  <div key={m.label} className="p-3 rounded-lg bg-dark-800">
                    <p className="text-xs text-text-muted">{m.label}</p>
                    <p className="text-sm font-semibold text-text-primary mt-1">{m.value}</p>
                  </div>
                ))}
              </div>

              {/* Day range and 52-week range */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="card">
                  <h4 className="text-xs font-semibold text-text-muted mb-3">Day Range</h4>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-text-secondary">{formatNumber(info?.day_low, { currency: true })}</span>
                    <span className="text-text-secondary">{formatNumber(info?.day_high, { currency: true })}</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-dark-600 relative">
                    {info?.day_low != null && info?.day_high != null && info?.price != null && info.day_high > info.day_low && (
                      <div
                        className="absolute top-0 w-3 h-2 rounded-full bg-info"
                        style={{
                          left: `${((info.price - info.day_low) / (info.day_high - info.day_low)) * 100}%`,
                          transform: 'translateX(-50%)',
                        }}
                      />
                    )}
                  </div>
                </div>
                <div className="card">
                  <h4 className="text-xs font-semibold text-text-muted mb-3">52-Week Range</h4>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-text-secondary">{formatNumber(info?.fifty_two_week_low, { currency: true })}</span>
                    <span className="text-text-secondary">{formatNumber(info?.fifty_two_week_high, { currency: true })}</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-dark-600 relative">
                    {info?.fifty_two_week_low != null && info?.fifty_two_week_high != null && info?.price != null && info.fifty_two_week_high > info.fifty_two_week_low && (
                      <div
                        className="absolute top-0 w-3 h-2 rounded-full bg-accent"
                        style={{
                          left: `${((info.price - info.fifty_two_week_low) / (info.fifty_two_week_high - info.fifty_two_week_low)) * 100}%`,
                          transform: 'translateX(-50%)',
                        }}
                      />
                    )}
                  </div>
                </div>
              </div>

              {/* About */}
              {info?.description && (
                <div className="card">
                  <h4 className="text-sm font-semibold text-text-primary mb-2">About {info.name || symbol}</h4>
                  <p className="text-xs text-text-secondary leading-relaxed line-clamp-4">
                    {info.description}
                  </p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'news' && (
            <div className="space-y-3">
              {news.length === 0 ? (
                <div className="card text-center py-12">
                  <Newspaper className="w-8 h-8 text-text-muted mx-auto mb-2" />
                  <p className="text-sm text-text-muted">No recent news found for {symbol}</p>
                </div>
              ) : (
                news.map((item, i) => (
                  <a
                    key={i}
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="card block hover:bg-dark-750 transition-colors group"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <h4 className="text-sm font-medium text-text-primary group-hover:text-info transition-colors">
                          {item.title}
                        </h4>
                        {item.summary && (
                          <p className="text-xs text-text-secondary mt-1 line-clamp-2">
                            {item.summary}
                          </p>
                        )}
                        <div className="flex items-center gap-3 mt-2">
                          <span className="text-[10px] text-text-muted">{item.source}</span>
                          {item.published_at && (
                            <span className="text-[10px] text-text-muted">{item.published_at}</span>
                          )}
                          <div className="flex gap-1">
                            {item.tickers.map((t) => (
                              <span key={t} className="px-1.5 py-0.5 rounded bg-dark-500 text-[10px] font-mono text-text-secondary">
                                {t}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                      <ExternalLink className="w-4 h-4 text-text-muted shrink-0 mt-1" />
                    </div>
                  </a>
                ))
              )}
            </div>
          )}

          {activeTab === 'social' && (
            <div className="space-y-3">
              {social.length === 0 ? (
                <div className="card text-center py-12">
                  <MessageCircle className="w-8 h-8 text-text-muted mx-auto mb-2" />
                  <p className="text-sm text-text-muted">No recent social posts found for {symbol}</p>
                </div>
              ) : (
                social.map((post, i) => (
                  <a
                    key={i}
                    href={post.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="card block hover:bg-dark-750 transition-colors group"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] text-accent font-medium">{post.source}</span>
                          {post.author && (
                            <span className="text-[10px] text-text-muted">u/{post.author}</span>
                          )}
                          {post.sentiment && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              post.sentiment === 'positive' ? 'text-profit bg-profit-muted' :
                              post.sentiment === 'negative' ? 'text-loss bg-loss-muted' :
                              'text-text-muted bg-dark-600'
                            }`}>
                              {post.sentiment}
                            </span>
                          )}
                        </div>
                        <h4 className="text-sm font-medium text-text-primary group-hover:text-info transition-colors">
                          {post.title}
                        </h4>
                        {post.content && (
                          <p className="text-xs text-text-secondary mt-1 line-clamp-2">
                            {post.content}
                          </p>
                        )}
                        <div className="flex items-center gap-4 mt-2">
                          <span className="flex items-center gap-1 text-[10px] text-text-muted">
                            <ThumbsUp className="w-3 h-3" /> {post.score}
                          </span>
                          <span className="flex items-center gap-1 text-[10px] text-text-muted">
                            <MessageCircle className="w-3 h-3" /> {post.comments}
                          </span>
                          {post.published_at && (
                            <span className="text-[10px] text-text-muted">{post.published_at}</span>
                          )}
                        </div>
                      </div>
                      <ExternalLink className="w-4 h-4 text-text-muted shrink-0 mt-1" />
                    </div>
                  </a>
                ))
              )}
            </div>
          )}

          {activeTab === 'summary' && (
            <div className="space-y-4">
              {!summary ? (
                <div className="card text-center py-12">
                  <Brain className="w-8 h-8 text-text-muted mx-auto mb-2" />
                  <p className="text-sm text-text-muted">Summary unavailable for {symbol}</p>
                </div>
              ) : (
                <>
                  {/* AI Summary text */}
                  <div className="card">
                    <div className="flex items-center gap-2 mb-3">
                      <Brain className="w-4 h-4 text-accent" />
                      <h3 className="text-sm font-semibold text-text-primary">AI Market Analysis</h3>
                    </div>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {summary.summary}
                    </p>
                  </div>

                  {/* Outlook badges */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="card">
                      <h4 className="text-xs font-semibold text-text-muted mb-2">Short-Term Outlook</h4>
                      <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${outlookColors[summary.short_term_outlook] || outlookColors.neutral}`}>
                        {summary.short_term_outlook === 'bullish' ? <TrendingUp className="w-4 h-4" /> :
                         summary.short_term_outlook === 'bearish' ? <TrendingDown className="w-4 h-4" /> :
                         <Minus className="w-4 h-4" />}
                        {summary.short_term_outlook}
                      </span>
                    </div>
                    <div className="card">
                      <h4 className="text-xs font-semibold text-text-muted mb-2">Medium-Term Outlook</h4>
                      <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium capitalize ${outlookColors[summary.medium_term_outlook] || outlookColors.neutral}`}>
                        {summary.medium_term_outlook === 'bullish' ? <TrendingUp className="w-4 h-4" /> :
                         summary.medium_term_outlook === 'bearish' ? <TrendingDown className="w-4 h-4" /> :
                         <Minus className="w-4 h-4" />}
                        {summary.medium_term_outlook}
                      </span>
                    </div>
                  </div>

                  {/* Key factors, risks, opportunities */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="card">
                      <div className="flex items-center gap-2 mb-3">
                        <Info className="w-4 h-4 text-info" />
                        <h4 className="text-xs font-semibold text-text-primary">Key Factors</h4>
                      </div>
                      <ul className="space-y-1.5">
                        {summary.key_factors.map((f, i) => (
                          <li key={i} className="text-xs text-text-secondary flex items-start gap-2">
                            <span className="text-info mt-0.5">-</span>
                            {f}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="card">
                      <div className="flex items-center gap-2 mb-3">
                        <AlertTriangle className="w-4 h-4 text-loss" />
                        <h4 className="text-xs font-semibold text-text-primary">Risks</h4>
                      </div>
                      <ul className="space-y-1.5">
                        {summary.risks.map((r, i) => (
                          <li key={i} className="text-xs text-text-secondary flex items-start gap-2">
                            <span className="text-loss mt-0.5">-</span>
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="card">
                      <div className="flex items-center gap-2 mb-3">
                        <Target className="w-4 h-4 text-profit" />
                        <h4 className="text-xs font-semibold text-text-primary">Opportunities</h4>
                      </div>
                      <ul className="space-y-1.5">
                        {summary.opportunities.map((o, i) => (
                          <li key={i} className="text-xs text-text-secondary flex items-start gap-2">
                            <span className="text-profit mt-0.5">-</span>
                            {o}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Sentiment */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="card">
                      <h4 className="text-xs font-semibold text-text-muted mb-1">News Sentiment</h4>
                      <span className={`text-sm font-medium capitalize ${
                        summary.news_sentiment === 'positive' ? 'text-profit' :
                        summary.news_sentiment === 'negative' ? 'text-loss' : 'text-warning'
                      }`}>
                        {summary.news_sentiment}
                      </span>
                    </div>
                    <div className="card">
                      <h4 className="text-xs font-semibold text-text-muted mb-1">Social Sentiment</h4>
                      <span className={`text-sm font-medium capitalize ${
                        summary.social_sentiment === 'positive' ? 'text-profit' :
                        summary.social_sentiment === 'negative' ? 'text-loss' : 'text-warning'
                      }`}>
                        {summary.social_sentiment}
                      </span>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
