// Replay engine, zustand store for playhead state
// Everything derived from playhead: candles shown, equity, open trade, leaderboard, commentary
import { create } from 'zustand';
import type { RunRecord, TradeRecord, EquityPoint, DecisionLogEntry } from './types';

export interface ReplayState {
  // Config
  runs: RunRecord[];           // 1 for solo, N for tournament
  focusModelId: string | null; // which model's candle chart to show

  // Playhead
  playhead: number;            // current bar index (0-based)
  totalBars: number;
  playing: boolean;
  speed: number;               // 1 = ~1 bar/200ms; multiply for faster

  // Follow mode: while a run is computing and user hasn't manually scrubbed, track latest bar
  following: boolean;

  // Derived (updated when playhead changes)
  currentEquity: Record<string, number>;    // modelId -> floating equity at playhead
  openTrades: Record<string, TradeRecord | null>;
  completedTrades: Record<string, TradeRecord[]>;
  visibleDecisions: Record<string, DecisionLogEntry[]>;
  leaderboard: Array<{ modelId: string; equity: number; pnlPct: number }>;

  // Actions
  setRuns: (runs: RunRecord[]) => void;
  /** Update runs from a poll without resetting playhead; clamps playhead to new totalBars-1.
   *  If following=true, advances playhead to bars_processed from the first run's progress. */
  updateRuns: (runs: RunRecord[]) => void;
  setFocusModel: (id: string) => void;
  setPlayhead: (bar: number) => void;
  setFollowing: (v: boolean) => void;
  setPlaying: (v: boolean) => void;
  setSpeed: (v: number) => void;
  stepForward: () => void;
  stepBack: () => void;
  restart: () => void;
  tick: () => void;
}

function deriveState(runs: RunRecord[], playhead: number) {
  const currentEquity: Record<string, number> = {};
  const openTrades: Record<string, TradeRecord | null> = {};
  const completedTrades: Record<string, TradeRecord[]> = {};
  const visibleDecisions: Record<string, DecisionLogEntry[]> = {};

  for (const run of runs) {
    const eq = run.equity_curve[playhead];
    currentEquity[run.model_id] = eq ? eq.floating : run.config.starting_equity;

    const completed = run.trades.filter(t => t.exit_bar <= playhead);
    completedTrades[run.model_id] = completed;

    const openId = eq?.open_trade_id;
    openTrades[run.model_id] = openId
      ? (run.trades.find(t => t.id === openId) ?? null)
      : null;

    visibleDecisions[run.model_id] = run.decisions.filter(d => d.bar <= playhead);
  }

  const leaderboard = runs
    .map(r => ({
      modelId: r.model_id,
      equity: currentEquity[r.model_id],
      pnlPct: ((currentEquity[r.model_id] - r.config.starting_equity) / r.config.starting_equity) * 100,
    }))
    .sort((a, b) => b.pnlPct - a.pnlPct);

  return { currentEquity, openTrades, completedTrades, visibleDecisions, leaderboard };
}

export const useReplayStore = create<ReplayState>((set, get) => ({
  runs: [],
  focusModelId: null,
  playhead: 0,
  totalBars: 0,
  playing: false,
  speed: 1,
  following: true,
  currentEquity: {},
  openTrades: {},
  completedTrades: {},
  visibleDecisions: {},
  leaderboard: [],

  setRuns: (runs) => {
    const totalBars = runs[0]?.candles.length ?? 0;
    const focusModelId = runs[0]?.model_id ?? null;
    const derived = deriveState(runs, 0);
    set({ runs, totalBars, focusModelId, playhead: 0, following: true, ...derived });
  },

  updateRuns: (runs) => {
    const totalBars = runs[0]?.candles.length ?? 0;
    const { playhead: currentPlayhead, focusModelId, following } = get();

    let playhead: number;
    if (following) {
      // Advance playhead to the latest processed bar from progress
      const barsProcessed = (runs[0]?.progress as { bars_processed?: number } | undefined)?.bars_processed;
      if (barsProcessed != null && barsProcessed > 0) {
        playhead = Math.max(0, Math.min(barsProcessed - 1, totalBars - 1));
      } else {
        playhead = totalBars > 0 ? Math.min(currentPlayhead, totalBars - 1) : 0;
      }
    } else {
      // Clamp playhead to new range without resetting
      playhead = totalBars > 0 ? Math.min(currentPlayhead, totalBars - 1) : 0;
    }

    const derived = deriveState(runs, playhead);
    // Preserve focusModelId if it still exists in the new runs
    const newFocusModelId = runs.find(r => r.model_id === focusModelId)
      ? focusModelId
      : (runs[0]?.model_id ?? null);
    set({ runs, totalBars, playhead, focusModelId: newFocusModelId, ...derived });
  },

  setFocusModel: (id) => set({ focusModelId: id }),

  setPlayhead: (bar) => {
    const { runs, totalBars } = get();
    const playhead = Math.max(0, Math.min(bar, totalBars - 1));
    const derived = deriveState(runs, playhead);
    // Manual scrub: stop following
    set({ playhead, following: false, ...derived });
  },

  setFollowing: (following) => set({ following }),

  setPlaying: (playing) => set({ playing }),

  setSpeed: (speed) => set({ speed }),

  stepForward: () => {
    const { playhead, totalBars, runs } = get();
    const next = Math.min(playhead + 1, totalBars - 1);
    const derived = deriveState(runs, next);
    set({ playhead: next, following: false, ...derived });
  },

  stepBack: () => {
    const { playhead, runs } = get();
    const prev = Math.max(playhead - 1, 0);
    const derived = deriveState(runs, prev);
    set({ playhead: prev, following: false, ...derived });
  },

  restart: () => {
    const { runs } = get();
    const derived = deriveState(runs, 0);
    set({ playhead: 0, playing: false, following: false, ...derived });
  },

  tick: () => {
    const { playhead, totalBars, playing, runs } = get();
    if (!playing) return;
    const next = playhead + 1;
    if (next >= totalBars) {
      set({ playing: false });
      return;
    }
    const derived = deriveState(runs, next);
    set({ playhead: next, ...derived });
  },
}));

// Speed -> ms per bar
export function speedToMs(speed: number): number {
  // At speed=1, one bar per 200ms; 8x = 25ms
  return Math.max(16, Math.round(200 / speed));
}

export function getEquityAtBar(run: RunRecord, bar: number): EquityPoint | null {
  return run.equity_curve[bar] ?? null;
}

export function getOpenTradeAtBar(run: RunRecord, bar: number): TradeRecord | null {
  const eq = run.equity_curve[bar];
  if (!eq?.open_trade_id) return null;
  return run.trades.find(t => t.id === eq.open_trade_id) ?? null;
}

export function getCompletedTradesUpTo(run: RunRecord, bar: number): TradeRecord[] {
  return run.trades.filter(t => t.exit_bar <= bar);
}
