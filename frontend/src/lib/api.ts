import type {
  Idea,
  Trade,
  Portfolio,
  Position,
  KnowledgeEntry,
  AgentStatus,
  RiskMetrics,
  MarketOutlook,
  Alert,
  RLStats,
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
  create: (data: Partial<Idea>) =>
    fetchAPI<Idea>('/api/ideas', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Idea>) =>
    fetchAPI<Idea>(`/api/ideas/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    fetchAPI<void>(`/api/ideas/${id}`, { method: 'DELETE' }),
  generate: () =>
    fetchAPI<{ message: string; ideas: Idea[] }>('/api/ideas/generate', {
      method: 'POST',
    }),
  validate: (id: string) =>
    fetchAPI<{ message: string; validation: Record<string, any> }>(
      `/api/ideas/${id}/validate`,
      { method: 'POST' }
    ),
  stats: () =>
    fetchAPI<{
      total: number;
      by_status: Record<string, number>;
      by_source: Record<string, number>;
      avg_confidence: number;
    }>('/api/ideas/stats'),
};

// Portfolio API
export const portfolioAPI = {
  list: () => fetchAPI<Portfolio[]>('/api/portfolio'),
  get: (id: string) => fetchAPI<Portfolio>(`/api/portfolio/${id}`),
  create: (data: Partial<Portfolio>) =>
    fetchAPI<Portfolio>('/api/portfolio', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Portfolio>) =>
    fetchAPI<Portfolio>(`/api/portfolio/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  positions: (id: string) =>
    fetchAPI<Position[]>(`/api/portfolio/${id}/positions`),
  risk: (id: string) =>
    fetchAPI<RiskMetrics>(`/api/portfolio/${id}/risk`),
  rebalance: (id: string) =>
    fetchAPI<{ message: string }>(`/api/portfolio/${id}/rebalance`, {
      method: 'POST',
    }),
  history: (id: string, params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<{ date: string; value: number }[]>(
      `/api/portfolio/${id}/history${qs}`
    );
  },
};

// Trades API
export const tradesAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<Trade[]>(`/api/trades${qs}`);
  },
  get: (id: string) => fetchAPI<Trade>(`/api/trades/${id}`),
  create: (data: Partial<Trade>) =>
    fetchAPI<Trade>('/api/trades', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  approve: (id: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/approve`, { method: 'POST' }),
  reject: (id: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/reject`, { method: 'POST' }),
  execute: (id: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/execute`, { method: 'POST' }),
  close: (id: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/close`, { method: 'POST' }),
  cancel: (id: string) =>
    fetchAPI<Trade>(`/api/trades/${id}/cancel`, { method: 'POST' }),
};

// Agents API
export const agentsAPI = {
  list: () => fetchAPI<AgentStatus[]>('/api/agents'),
  get: (name: string) => fetchAPI<AgentStatus>(`/api/agents/${name}`),
  startLoop: (loopName: string) =>
    fetchAPI<{ message: string }>(`/api/agents/loops/${loopName}/start`, {
      method: 'POST',
    }),
  stopLoop: (loopName: string) =>
    fetchAPI<{ message: string }>(`/api/agents/loops/${loopName}/stop`, {
      method: 'POST',
    }),
  loopStatus: () =>
    fetchAPI<{ idea_loop: string; portfolio_loop: string }>(
      '/api/agents/loops/status'
    ),
  logs: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<
      { timestamp: string; agent: string; action: string; details: string }[]
    >(`/api/agents/logs${qs}`);
  },
};

// Knowledge API
export const knowledgeAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<KnowledgeEntry[]>(`/api/knowledge${qs}`);
  },
  get: (id: string) => fetchAPI<KnowledgeEntry>(`/api/knowledge/${id}`),
  create: (data: Partial<KnowledgeEntry>) =>
    fetchAPI<KnowledgeEntry>('/api/knowledge', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<KnowledgeEntry>) =>
    fetchAPI<KnowledgeEntry>(`/api/knowledge/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    fetchAPI<void>(`/api/knowledge/${id}`, { method: 'DELETE' }),
  outlook: () => fetchAPI<MarketOutlook[]>('/api/knowledge/outlook'),
  updateOutlook: (data: Partial<MarketOutlook>) =>
    fetchAPI<MarketOutlook>('/api/knowledge/outlook', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  sources: () =>
    fetchAPI<{ source: string; credibility: number; count: number }[]>(
      '/api/knowledge/sources'
    ),
  triggerPipeline: () =>
    fetchAPI<{ message: string }>('/api/knowledge/pipeline/trigger', {
      method: 'POST',
    }),
  pipelineStatus: () =>
    fetchAPI<{
      status: string;
      last_run: string;
      entries_processed: number;
    }>('/api/knowledge/pipeline/status'),
};

// RL Training API
export const rlAPI = {
  stats: () => fetchAPI<RLStats[]>('/api/rl/stats'),
  agentStats: (agentName: string) =>
    fetchAPI<RLStats>(`/api/rl/stats/${agentName}`),
  startTraining: (agentName: string, config?: Record<string, any>) =>
    fetchAPI<{ message: string }>(`/api/rl/train/${agentName}`, {
      method: 'POST',
      body: JSON.stringify(config || {}),
    }),
  stopTraining: (agentName: string) =>
    fetchAPI<{ message: string }>(`/api/rl/train/${agentName}/stop`, {
      method: 'POST',
    }),
  episodes: (agentName: string, params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<
      { episode: number; reward: number; steps: number; timestamp: string }[]
    >(`/api/rl/episodes/${agentName}${qs}`);
  },
  replayBufferStats: () =>
    fetchAPI<{
      size: number;
      capacity: number;
      avg_reward: number;
      sample_distribution: Record<string, number>;
    }>('/api/rl/replay-buffer/stats'),
};

// Alerts API
export const alertsAPI = {
  list: (params?: Record<string, string>) => {
    const qs = params ? `?${new URLSearchParams(params)}` : '';
    return fetchAPI<Alert[]>(`/api/alerts${qs}`);
  },
  dismiss: (id: string) =>
    fetchAPI<void>(`/api/alerts/${id}/dismiss`, { method: 'POST' }),
  dismissAll: () =>
    fetchAPI<void>('/api/alerts/dismiss-all', { method: 'POST' }),
};
