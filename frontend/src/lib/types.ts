// §3 data types, mirror of backend schemas

export interface Candle {
  t: string;  // ISO 8601 UTC
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Decision {
  action: 'long' | 'short' | 'flat';
  entry: number | null;
  stop_loss: number;
  take_profit: number;
  confidence: number;
  rationale: string;
  indicators_used?: string[];
  parse_error?: string | null;
}

export interface TradeRecord {
  id: number;
  model_id: string;
  direction: 'long' | 'short';
  decision_index: number;
  entry_bar: number;
  entry_time: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  exit_bar: number;
  exit_time: string;
  exit_price: number;
  outcome: 'tp' | 'sl' | 'timeout' | 'eod';
  r_multiple: number;
  risk_amount: number;
  pnl_abs: number;
  pnl_pct: number;
  equity_after: number;
  confidence: number;
  rationale: string;
  mae_r?: number;
  mfe_r?: number;
}

export interface EquityPoint {
  bar: number;
  t: string;
  equity: number;
  floating: number;
  open_trade_id: number | null;
}

export interface DecisionLogEntry {
  bar: number;
  time: string;
  action: 'long' | 'short' | 'flat';
  rationale: string;
  confidence: number;
  trade_id: number | null;
}

export interface Indicators {
  // Core (always rendered on chart)
  ema20: (number | null)[];
  ema50: (number | null)[];
  rsi14: (number | null)[];
  atr14: (number | null)[];
  macd: (number | null)[];
  macd_signal: (number | null)[];
  macd_hist: (number | null)[];
  bb_upper: (number | null)[];
  bb_mid: (number | null)[];
  bb_lower: (number | null)[];
  // Extended indicators (all 26, passed to AI context, stored in run record)
  [key: string]: (number | null)[];
}

export interface Metrics {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_r: number;
  expectancy_r: number;
  profit_factor: number;
  net_pnl: number;
  net_pnl_pct: number;
  final_equity: number;
  max_drawdown_pct: number;
  max_drawdown_r: number;
  avg_win_r: number;
  avg_loss_r: number;
  avg_confidence: number;
  sharpe: number;
  longest_win_streak: number;
  longest_loss_streak: number;
  avg_trade_bars: number;
}

export interface DatasetInfo {
  source: string;
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  bar_count: number;
}

export interface RunConfig {
  starting_equity: number;
  risk_per_trade_pct: number;
  target_trades: number;
  decision_cadence: number;
  lookback: number;
  max_trade_bars: number;
  decision_trigger: 'signals' | 'cadence';
  allow_short: boolean;
  indicators: string[];
}

export interface RunRecord {
  run_id: string;
  mode: 'solo' | 'tournament';
  tournament_id: string | null;
  model_id: string;
  model_label: string;
  model_color: string;
  model_provider: string;
  dataset: DatasetInfo;
  config: RunConfig;
  candles: Candle[];
  indicators: Indicators;
  trades: TradeRecord[];
  decisions: DecisionLogEntry[];
  equity_curve: EquityPoint[];
  metrics: Metrics;
  status: 'queued' | 'running' | 'complete' | 'error';
  progress: { trades_done: number; target: number; bars_processed: number; bars_total: number; decisions_made?: number };
  error: string | null;
  created_at: string;
  duration_sec: number;
}

export interface LeaderboardEntry {
  rank: number;
  model_id: string;
  model_label: string;
  model_color: string;
  net_pnl_pct: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  max_drawdown_pct: number;
  sharpe: number;
}

export interface TournamentRecord {
  tournament_id: string;
  name: string;
  dataset: DatasetInfo;
  config: RunConfig;
  model_ids: string[];
  run_ids: Record<string, string>;
  leaderboard: LeaderboardEntry[];
  status: 'queued' | 'running' | 'complete' | 'error';
  progress: { models_done: number; models_total: number };
  created_at: string;
}

export interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  color: string;
  available: boolean;
  model_name: string;
  default_in_tournament: boolean;
}

export interface DatasetSpec {
  source: 'binance' | 'mt5' | 'csv';
  symbol: string;
  timeframe: string;
  limit: number;
  csv_dataset_id?: string | null;
  start?: string | null;
  end?: string | null;
}

export type ArenaMode = 'solo' | 'tournament';
