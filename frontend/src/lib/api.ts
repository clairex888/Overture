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
  PortfolioProposal,
  ApproveResult,
  PortfolioListItem,
  PortfolioInitResult,
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
  AuthResponse,
  UserProfile,
} from '@/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Token management
let _token: string | null = null;

export function setAuthToken(token: string | null) {
  _token = token;
  if (token) {
    if (typeof window !== 'undefined') localStorage.setItem('overture_token', token);
  } else {
    if (typeof window !== 'undefined') localStorage.removeItem('overture_token');
  }
}

export function getAuthToken(): string | null {
  if (_token) return _token;
  if (typeof window !== 'undefined') {
    _token = localStorage.getItem('overture_token');
  }
  return _token;
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    cache: 'no-store',
  });
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${errorBody || res.statusText}`);
  }
  return res.json();
}

// Auth API
export const authAPI = {
  register: (email: string, password: string, displayName?: string) =>
    fetchAPI<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, display_name: displayName }),
    }),
  login: (email: string, password: string) =>
    fetchAPI<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => fetchAPI<UserProfile>('/api/auth/me'),
};

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
  list: () => fetchAPI<PortfolioListItem[]>('/api/portfolio/list'),
  overview: (portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<PortfolioOverview>(`/api/portfolio/${qs}`);
  },
  positions: (portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<Position[]>(`/api/portfolio/positions${qs}`);
  },
  risk: (portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<RiskMetrics>(`/api/portfolio/risk${qs}`);
  },
  performance: (portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<PerformanceMetrics>(`/api/portfolio/performance${qs}`);
  },
  allocation: (portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<AllocationBreakdown>(`/api/portfolio/allocation${qs}`);
  },
  rebalance: (portfolioId?: string) =>
    fetchAPI<Record<string, any>>('/api/portfolio/rebalance', {
      method: 'POST',
      body: JSON.stringify(portfolioId ? { portfolio_id: portfolioId } : {}),
    }),
  getPreferences: (portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<PortfolioPreferences>(`/api/portfolio/preferences${qs}`);
  },
  updatePreferences: (data: PortfolioPreferences, portfolioId?: string) => {
    const qs = portfolioId ? `?portfolio_id=${portfolioId}` : '';
    return fetchAPI<PortfolioPreferences>(`/api/portfolio/preferences${qs}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
  initialize: (amount: number, name?: string, portfolioId?: string) =>
    fetchAPI<PortfolioInitResult>('/api/portfolio/initialize', {
      method: 'POST',
      body: JSON.stringify({
        initial_amount: amount,
        ...(name ? { name } : {}),
        ...(portfolioId ? { portfolio_id: portfolioId } : {}),
      }),
    }),
  propose: (portfolioId: string, initialAmount: number, holdings: Record<string, any>[]) =>
    fetchAPI<PortfolioProposal>('/api/portfolio/propose', {
      method: 'POST',
      body: JSON.stringify({
        portfolio_id: portfolioId,
        initial_amount: initialAmount,
        holdings,
      }),
    }),
  approve: (portfolioId: string, initialAmount: number, holdings: Record<string, any>[]) =>
    fetchAPI<ApproveResult>('/api/portfolio/approve', {
      method: 'POST',
      body: JSON.stringify({
        portfolio_id: portfolioId,
        initial_amount: initialAmount,
        holdings,
      }),
    }),
  generateProposal: (portfolioId: string) =>
    fetchAPI<PortfolioProposal>('/api/portfolio/generate-proposal', {
      method: 'POST',
      body: JSON.stringify({ portfolio_id: portfolioId }),
    }),
  deletePortfolio: (portfolioId: string) =>
    fetchAPI<{ success: boolean; message: string }>(`/api/portfolio/${portfolioId}`, {
      method: 'DELETE',
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
    return fetchAPI<KnowledgeEntry[]>(`/api/knowledge/${qs}`);
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
  upload: async (file: File, opts: { title?: string; layer?: string; category?: string; is_public?: boolean; tags?: string }) => {
    const token = getAuthToken();
    const formData = new FormData();
    formData.append('file', file);
    if (opts.title) formData.append('title', opts.title);
    formData.append('layer', opts.layer || 'medium_term');
    formData.append('category', opts.category || 'research');
    formData.append('is_public', String(opts.is_public ?? true));
    if (opts.tags) formData.append('tags', opts.tags);
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}/api/knowledge/upload`, {
      method: 'POST',
      headers,
      body: formData,
      cache: 'no-store',
    });
    if (!res.ok) {
      const errorBody = await res.text().catch(() => '');
      throw new Error(`API error ${res.status}: ${errorBody || res.statusText}`);
    }
    return res.json() as Promise<KnowledgeEntry>;
  },
  togglePrivacy: (entryId: string, isPublic: boolean) =>
    fetchAPI<KnowledgeEntry>(`/api/knowledge/${entryId}/privacy`, {
      method: 'PATCH',
      body: JSON.stringify({ is_public: isPublic }),
    }),
  delete: (entryId: string) =>
    fetchAPI<{ success: boolean; message: string }>(`/api/knowledge/${entryId}`, {
      method: 'DELETE',
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
  info: (symbol: string, refresh = false) =>
    fetchAPI<AssetInfo>(`/api/market-data/info/${symbol}${refresh ? '?refresh=true' : ''}`),
  news: (symbol: string, refresh = false) =>
    fetchAPI<NewsItem[]>(`/api/market-data/news/${symbol}${refresh ? '?refresh=true' : ''}`),
  social: (symbol: string, refresh = false) =>
    fetchAPI<SocialPost[]>(`/api/market-data/social/${symbol}${refresh ? '?refresh=true' : ''}`),
  summary: (symbol: string, refresh = false) =>
    fetchAPI<AssetSummary>(`/api/market-data/summary/${symbol}${refresh ? '?refresh=true' : ''}`),
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
