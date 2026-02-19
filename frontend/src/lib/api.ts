import type {
  Idea,
  IdeaStats,
  Trade,
  PendingSummary,
  ActiveSummary,
  PortfolioOverview,
  Position,
  RiskMetrics,
  PerformanceMetrics,
  AllocationBreakdown,
  PortfolioPreferences,
  AllAgentsStatus,
  AgentLogEntry,
  LoopControlResponse,
  KnowledgeEntry,
  MarketOutlook,
  SourceCredibility,
  EducationalContent,
  Alert,
  AgentRLStats,
  RLEpisode,
  ReplayBufferStats,
  AssetInfo,
  NewsItem,
  SocialPost,
  AssetSummary,
} from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${errorBody || res.statusText}`);
  }
  return res.json();
}

// Ideas API
export const ideasAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<Idea[]>(`/api/ideas${qs}`);
  },
  get: (id: string) => fetchAPI<Idea>(`/api/ideas/${id}`),
  create: (data: Record<string, any>) =>
    fetchAPI<Idea>('/api/ideas', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Record<string, any>) =>
    fetchAPI<Idea>(`/api/ideas/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    fetchAPI<void>(`/api/ideas/${id}`, { method: 'DELETE' }),
  generate: (data?: Record<string, any>) =>
    fetchAPI<Idea[]>('/api/ideas/generate', {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),
  validate: (id: string) =>
    fetchAPI<Idea>(`/api/ideas/${id}/validate`, { method: 'POST' }),
  execute: (id: string) =>
    fetchAPI<Idea>(`/api/ideas/${id}/execute`, { method: 'POST' }),
  stats: () => fetchAPI<IdeaStats>('/api/ideas/stats'),
};

// Portfolio API
export const portfolioAPI = {
  overview: () => fetchAPI<PortfolioOverview>('/api/portfolio'),
  positions: () => fetchAPI<Position[]>('/api/portfolio/positions'),
  risk: () => fetchAPI<RiskMetrics>('/api/portfolio/risk'),
  performance: () => fetchAPI<PerformanceMetrics>('/api/portfolio/performance'),
  allocation: () => fetchAPI<AllocationBreakdown>('/api/portfolio/allocation'),
  rebalance: () =>
    fetchAPI<Record<string, any>>('/api/portfolio/rebalance', {
      method: 'POST',
    }),
  getPreferences: () => fetchAPI<PortfolioPreferences>('/api/portfolio/preferences'),
  updatePreferences: (data: PortfolioPreferences) =>
    fetchAPI<PortfolioPreferences>('/api/portfolio/preferences', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

// Trades API
export const tradesAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<Trade[]>(`/api/trades${qs}`);
  },
  get: (id: string) => fetchAPI<Trade>(`/api/trades/${id}`),
  pending: () => fetchAPI<PendingSummary>('/api/trades/pending'),
  active: () => fetchAPI<ActiveSummary>('/api/trades/active'),
  approve: (id: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/approve`, { method: 'POST' }),
  reject: (id: string, reason: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  adjust: (id: string, data: Record<string, any>) =>
    fetchAPI<Trade>(`/api/trades/${id}/adjust`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  close: (id: string, data?: Record<string, any>) =>
    fetchAPI<Trade>(`/api/trades/${id}/close`, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    }),
};

// Agents API
export const agentsAPI = {
  status: () => fetchAPI<AllAgentsStatus>('/api/agents/status'),
  logs: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<AgentLogEntry[]>(`/api/agents/logs${qs}`);
  },
  startIdeaLoop: () =>
    fetchAPI<LoopControlResponse>('/api/agents/idea-loop/start', {
      method: 'POST',
    }),
  stopIdeaLoop: () =>
    fetchAPI<LoopControlResponse>('/api/agents/idea-loop/stop', {
      method: 'POST',
    }),
  startPortfolioLoop: () =>
    fetchAPI<LoopControlResponse>('/api/agents/portfolio-loop/start', {
      method: 'POST',
    }),
  stopPortfolioLoop: () =>
    fetchAPI<LoopControlResponse>('/api/agents/portfolio-loop/stop', {
      method: 'POST',
    }),
};

// Knowledge API
export const knowledgeAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<KnowledgeEntry[]>(`/api/knowledge${qs}`);
  },
  get: (id: string) => fetchAPI<KnowledgeEntry>(`/api/knowledge/${id}`),
  create: (data: Record<string, any>) =>
    fetchAPI<KnowledgeEntry>('/api/knowledge', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  outlook: () => fetchAPI<MarketOutlook>('/api/knowledge/outlook'),
  updateOutlook: (layer: string, data: Record<string, any>) =>
    fetchAPI<Record<string, any>>(`/api/knowledge/outlook/${layer}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  sources: () => fetchAPI<SourceCredibility[]>('/api/knowledge/sources'),
  education: () => fetchAPI<EducationalContent[]>('/api/knowledge/education'),
  triggerPipeline: () =>
    fetchAPI<Record<string, any>>('/api/knowledge/data-pipeline/trigger', {
      method: 'POST',
    }),
};

// Alerts API
export const alertsAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<Alert[]>(`/api/alerts${qs}`);
  },
  dismiss: (id: string) =>
    fetchAPI<Record<string, any>>(`/api/alerts/${id}/dismiss`, {
      method: 'POST',
    }),
  dismissAll: () =>
    fetchAPI<Record<string, any>>('/api/alerts/dismiss-all', {
      method: 'POST',
    }),
};

// Market Data API
export const marketDataAPI = {
  price: (symbol: string) =>
    fetchAPI<Record<string, any>>(`/api/market-data/price/${symbol}`),
  prices: (symbols: string[]) =>
    fetchAPI<Record<string, any>[]>(`/api/market-data/prices?symbols=${symbols.join(',')}`),
  history: (symbol: string, period = '1mo', interval = '1d') =>
    fetchAPI<Record<string, any>>(`/api/market-data/history/${symbol}?period=${period}&interval=${interval}`),
  watchlist: (assetClass: string) =>
    fetchAPI<Record<string, any>>(`/api/market-data/watchlist/${assetClass}`),
  watchlists: () =>
    fetchAPI<Record<string, string[]>>('/api/market-data/watchlists'),
  info: (symbol: string) =>
    fetchAPI<AssetInfo>(`/api/market-data/info/${symbol}`),
  news: (symbol: string) =>
    fetchAPI<NewsItem[]>(`/api/market-data/news/${symbol}`),
  social: (symbol: string) =>
    fetchAPI<SocialPost[]>(`/api/market-data/social/${symbol}`),
  summary: (symbol: string) =>
    fetchAPI<AssetSummary>(`/api/market-data/summary/${symbol}`),
};

// Seed API
export const seedAPI = {
  seed: () =>
    fetchAPI<Record<string, any>>('/api/seed', { method: 'POST' }),
};

// RL Training API
export const rlAPI = {
  stats: () => fetchAPI<AgentRLStats[]>('/api/rl/stats'),
  agentStats: (agentName: string) =>
    fetchAPI<AgentRLStats>(`/api/rl/stats/${agentName}`),
  episodes: (agentName: string) =>
    fetchAPI<RLEpisode[]>(`/api/rl/episodes/${agentName}`),
  replayBufferStats: () =>
    fetchAPI<ReplayBufferStats>('/api/rl/replay-buffer/stats'),
  startTraining: (agentName: string) =>
    fetchAPI<Record<string, any>>(`/api/rl/train/${agentName}`, {
      method: 'POST',
    }),
  stopTraining: (agentName: string) =>
    fetchAPI<Record<string, any>>(`/api/rl/train/${agentName}/stop`, {
      method: 'POST',
    }),
};
