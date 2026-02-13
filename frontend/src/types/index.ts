// Core types matching backend models

export interface Idea {
  id: string;
  title: string;
  description: string;
  source: 'news' | 'screen' | 'agent' | 'user' | 'aggregated';
  source_url?: string;
  asset_class: string;
  tickers: string[];
  thesis: string;
  status: 'generated' | 'validating' | 'validated' | 'rejected' | 'executing' | 'monitoring' | 'closed';
  confidence_score: number;
  expected_return?: number;
  risk_level: 'low' | 'medium' | 'high' | 'extreme';
  timeframe: 'intraday' | 'short_term' | 'medium_term' | 'long_term';
  validation_results?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface Trade {
  id: string;
  idea_id: string;
  status: 'planned' | 'pending_approval' | 'approved' | 'executing' | 'open' | 'closing' | 'closed' | 'cancelled';
  direction: 'long' | 'short';
  tickers: string[];
  instrument_type: 'equity' | 'option' | 'future' | 'etf' | 'bond' | 'crypto';
  entry_price?: number;
  exit_price?: number;
  current_price?: number;
  quantity: number;
  stop_loss?: number;
  take_profit?: number;
  pnl?: number;
  pnl_pct?: number;
  execution_plan?: Record<string, any>;
  created_at: string;
}

export interface Portfolio {
  id: string;
  name: string;
  total_value: number;
  cash: number;
  invested: number;
  pnl: number;
  pnl_pct: number;
  risk_score: number;
  preferences: Record<string, any>;
  status: 'active' | 'paused';
}

export interface Position {
  id: string;
  portfolio_id: string;
  ticker: string;
  direction: 'long' | 'short';
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
  weight: number;
  asset_class: string;
}

export interface KnowledgeEntry {
  id: string;
  title: string;
  content: string;
  summary: string;
  category: 'fundamental' | 'technical' | 'macro' | 'event' | 'research' | 'education';
  layer: 'long_term' | 'mid_term' | 'short_term';
  source: string;
  source_credibility_score: number;
  tags: string[];
  created_at: string;
}

export interface AgentStatus {
  name: string;
  type: string;
  status: 'running' | 'idle' | 'error';
  last_action?: string;
  last_action_at?: string;
  tasks_completed: number;
  tasks_failed: number;
}

export interface RiskMetrics {
  total_value: number;
  daily_var: number;
  volatility: number;
  beta: number;
  sharpe: number;
  max_drawdown: number;
  concentration_hhi: number;
  sector_exposure: Record<string, number>;
}

export interface MarketOutlook {
  layer: 'long_term' | 'mid_term' | 'short_term';
  asset_class: string;
  outlook: 'bullish' | 'neutral' | 'bearish';
  confidence: number;
  rationale: string;
}

export interface Alert {
  id: string;
  type: 'trade' | 'risk' | 'idea' | 'system';
  level: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  action_required: boolean;
  action_url?: string;
  created_at: string;
}

export interface RLStats {
  agent_name: string;
  total_episodes: number;
  avg_reward: number;
  reward_trend: number[];
  best_episode_reward: number;
  insights: string[];
}
