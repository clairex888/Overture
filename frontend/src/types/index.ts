// Core types matching backend API response schemas

export interface Ticker {
  symbol: string;
  direction: string;
  weight?: number;
}

export interface Idea {
  id: string;
  title: string;
  thesis: string;
  asset_class: string;
  timeframe: string;
  tickers: Ticker[];
  conviction: number;
  status: string;
  source: string;
  tags: string[];
  notes: string | null;
  validation_result: Record<string, any> | null;
  execution_plan: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface IdeaStats {
  total: number;
  by_status: Record<string, number>;
  by_asset_class: Record<string, number>;
  by_source: Record<string, number>;
  avg_conviction: number;
}

export interface Trade {
  id: string;
  idea_id: string | null;
  symbol: string;
  direction: string;
  instrument_type: string;
  quantity: number;
  limit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  status: string;
  fill_price: number | null;
  fill_quantity: number | null;
  pnl: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PendingSummary {
  count: number;
  trades: Trade[];
}

export interface ActiveSummary {
  count: number;
  total_exposure: number;
  trades: Trade[];
}

export interface PortfolioOverview {
  total_value: number;
  cash: number;
  invested: number;
  total_pnl: number;
  total_pnl_pct: number;
  day_pnl: number;
  day_pnl_pct: number;
  positions_count: number;
  last_updated: string;
}

export interface Position {
  id: string;
  symbol: string;
  direction: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  weight: number;
  asset_class: string;
  opened_at: string;
}

export interface RiskMetrics {
  var_95: number;
  var_99: number;
  portfolio_volatility: number;
  portfolio_beta: number;
  sharpe_ratio: number;
  max_drawdown: number;
  concentration_top5: number;
  sector_concentration: Record<string, number>;
  correlation_risk: string;
  last_calculated: string;
}

export interface PerformanceMetrics {
  total_return: number;
  total_return_pct: number;
  annualized_return_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  max_drawdown_duration_days: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  calmar_ratio: number;
  period_start: string;
  period_end: string;
}

export interface AllocationEntry {
  category: string;
  current_weight: number;
  target_weight: number;
  drift: number;
}

export interface AllocationBreakdown {
  by_asset_class: AllocationEntry[];
  by_sector: AllocationEntry[];
  by_geography: AllocationEntry[];
  last_updated: string;
}

export interface AgentStatusEntry {
  name: string;
  display_name: string;
  status: string;
  current_task: string | null;
  last_run: string | null;
  run_count: number;
  error_count: number;
  uptime_seconds: number;
}

export interface AllAgentsStatus {
  agents: AgentStatusEntry[];
  idea_loop_running: boolean;
  portfolio_loop_running: boolean;
  last_updated: string;
}

export interface AgentLogEntry {
  id: string;
  timestamp: string;
  agent_name: string;
  action: string;
  status: string;
  details: Record<string, any>;
  duration_ms: number | null;
}

export interface LoopControlResponse {
  loop: string;
  action: string;
  success: boolean;
  message: string;
  timestamp: string;
}

export interface KnowledgeEntry {
  id: string;
  title: string;
  content: string;
  category: string;
  layer: string;
  asset_class: string | null;
  tickers: string[];
  source: string;
  confidence: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface OutlookLayer {
  layer: string;
  sentiment: string;
  confidence: number;
  summary: string;
  key_factors: string[];
  risks: string[];
  opportunities: string[];
  last_updated: string;
}

export interface MarketOutlook {
  long_term: OutlookLayer;
  medium_term: OutlookLayer;
  short_term: OutlookLayer;
  consensus_sentiment: string;
  last_updated: string;
}

export interface SourceCredibility {
  name: string;
  type: string;
  credibility_score: number;
  accuracy_history: number;
  total_entries: number;
  last_fetched: string | null;
}

export interface EducationalContent {
  id: string;
  title: string;
  summary: string;
  category: string;
  difficulty: string;
  relevance_score: number;
  url: string | null;
  created_at: string;
}

export interface Alert {
  id: string;
  type: string;
  level: string;
  title: string;
  message: string;
  action_required: boolean;
  action_url?: string;
  dismissed: boolean;
  created_at: string;
}

export interface AgentRLStats {
  agent_name: string;
  total_episodes: number;
  avg_reward: number;
  best_episode_reward: number;
  worst_episode_reward: number;
  status: string;
  learning_rate: number;
  epsilon: number;
  reward_trend: number[];
  insights: string[];
  last_updated: string;
}

export interface RLEpisode {
  id: string;
  agent_name: string;
  steps: number;
  total_reward: number;
  outcome: string;
  duration_seconds: number;
  timestamp: string;
}

export interface ReplayBufferStats {
  size: number;
  capacity: number;
  avg_reward: number;
  min_reward: number;
  max_reward: number;
  samples_per_second: number;
}
