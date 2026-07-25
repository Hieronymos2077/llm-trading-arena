// Typed API client, falls back to /sample fixtures when backend is unreachable
import type {
  RunRecord, TournamentRecord, ModelInfo, DatasetSpec, Candle,
} from './types';

const BASE = process.env.NEXT_PUBLIC_API ?? 'http://localhost:7077';

// Set NEXT_PUBLIC_API to an empty string to build a replay only deployment.
// Every call then short circuits to the committed /sample fixtures instead of
// firing requests at a backend that is known not to exist.
const BACKEND_CONFIGURED = BASE !== '';

async function get<T>(path: string): Promise<T> {
  if (!BACKEND_CONFIGURED) throw new Error('no backend configured (replay only build)');
  const res = await fetch(`${BASE}${path}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  if (!BACKEND_CONFIGURED) throw new Error('no backend configured (replay only build)');
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// The one committed run that came from real model calls rather than the
// deterministic fixture generator. Claude Haiku, BTCUSDT 1h, 1200 bars.
export const REAL_RUN_ID = 'run_BTCUSDT_claude-haiku_376eb0fb';

// ── Sample fixture loader (offline demo) ──────────────────────────────────────
async function loadSampleRun(filename: string): Promise<RunRecord> {
  const res = await fetch(`/sample/${filename}`);
  return res.json();
}

async function loadSampleTournament(): Promise<TournamentRecord> {
  const res = await fetch('/sample/tournament_sample.json');
  return res.json();
}

// ── Models ────────────────────────────────────────────────────────────────────
export async function getModels(): Promise<ModelInfo[]> {
  try {
    const d = await get<{ models: ModelInfo[] }>('/api/models');
    return d.models;
  } catch {
    // Fallback: return static list with available=false
    return [
      { id: 'claude-haiku', label: 'Claude Haiku 4.5', provider: 'claude', color: '#E8A87C', available: false, model_name: 'claude-haiku-4-5-20251001', default_in_tournament: true },
      { id: 'gemini-flash', label: 'Gemini 2.5 Flash', provider: 'gemini', color: '#7CACF8', available: false, model_name: 'gemini-2.5-flash', default_in_tournament: true },
      { id: 'gpt-5-mini', label: 'GPT-5 mini', provider: 'openai', color: '#5FD0B0', available: false, model_name: 'gpt-5-mini', default_in_tournament: true },
      { id: 'claude-sonnet', label: 'Claude Sonnet 4.6', provider: 'claude', color: '#C15F3C', available: false, model_name: 'claude-sonnet-4-6', default_in_tournament: false },
      { id: 'claude-opus', label: 'Claude Opus 4.8', provider: 'claude', color: '#D97757', available: false, model_name: 'claude-opus-4-8', default_in_tournament: false },
      { id: 'gemini-pro', label: 'Gemini 2.5 Pro', provider: 'gemini', color: '#4285F4', available: false, model_name: 'gemini-2.5-pro', default_in_tournament: false },
      { id: 'gpt-5', label: 'GPT-5', provider: 'openai', color: '#10A37F', available: false, model_name: 'gpt-5', default_in_tournament: false },
    ];
  }
}

// ── Data sources ──────────────────────────────────────────────────────────────
export async function getDataSources(): Promise<{ sources: string[]; status: Record<string, boolean> }> {
  try {
    return await get('/api/data/sources');
  } catch {
    return { sources: ['binance', 'csv'], status: { binance: true, csv: true, mt5: false } };
  }
}

export async function getSymbols(source: string): Promise<string[]> {
  try {
    const d = await get<{ symbols: string[] }>(`/api/data/symbols?source=${source}`);
    return d.symbols;
  } catch {
    return ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOTUSDT'];
  }
}

export async function previewData(spec: DatasetSpec): Promise<{ candles: Candle[]; bar_count: number; start: string; end: string }> {
  return post('/api/data/preview', spec);
}

export interface DatasetMeta { dataset_id: string; symbol: string; timeframe: string; bar_count: number; }
export async function getDatasets(): Promise<DatasetMeta[]> {
  try {
    const d = await get<{ datasets: DatasetMeta[] }>('/api/data/datasets');
    return d.datasets;
  } catch {
    return [];
  }
}

// ── Runs ──────────────────────────────────────────────────────────────────────
export async function getRun(runId: string): Promise<RunRecord> {
  // Check if it's a sample id
  if (runId === REAL_RUN_ID) return loadSampleRun('run_real_claude_haiku.json');
  if (runId === 'run_BTCUSDT_claude-haiku_c1f7418f') return loadSampleRun('run_sample_claude.json');
  if (runId === 'run_BTCUSDT_gemini-flash_21408f49') return loadSampleRun('run_sample_gemini.json');
  if (runId === 'run_BTCUSDT_gpt-5-mini_6f3c2c54') return loadSampleRun('run_sample_gpt.json');
  try {
    return await get<RunRecord>(`/api/run/${runId}`);
  } catch {
    return loadSampleRun('run_sample_claude.json');
  }
}

export async function getRuns(): Promise<RunRecord[]> {
  try {
    const d = await get<{ runs: RunRecord[] }>('/api/runs');
    return d.runs;
  } catch {
    const r = await loadSampleRun('run_real_claude_haiku.json');
    return [r];
  }
}

export async function startSoloRun(body: { model_id: string; dataset: DatasetSpec; config: Record<string, unknown> }): Promise<{ run_id: string }> {
  return post('/api/run/solo', body);
}

// ── Tournaments ───────────────────────────────────────────────────────────────
export async function getTournament(id: string): Promise<TournamentRecord> {
  if (id === 'trn_dcdf00ec') return loadSampleTournament();
  try {
    return await get<TournamentRecord>(`/api/tournament/${id}`);
  } catch {
    return loadSampleTournament();
  }
}

export async function getTournamentRuns(id: string): Promise<RunRecord[]> {
  if (id === 'trn_dcdf00ec') {
    const [claude, gemini, gpt] = await Promise.all([
      loadSampleRun('run_sample_claude.json'),
      loadSampleRun('run_sample_gemini.json'),
      loadSampleRun('run_sample_gpt.json'),
    ]);
    return [claude, gemini, gpt];
  }
  try {
    const d = await get<{ runs: RunRecord[] }>(`/api/tournament/${id}/runs`);
    return d.runs;
  } catch {
    const [claude, gemini, gpt] = await Promise.all([
      loadSampleRun('run_sample_claude.json'),
      loadSampleRun('run_sample_gemini.json'),
      loadSampleRun('run_sample_gpt.json'),
    ]);
    return [claude, gemini, gpt];
  }
}

export async function getTournaments(): Promise<TournamentRecord[]> {
  try {
    const d = await get<{ tournaments: TournamentRecord[] }>('/api/tournaments');
    return d.tournaments;
  } catch {
    const t = await loadSampleTournament();
    return [t];
  }
}

export async function startTournament(body: { name?: string; model_ids: string[]; dataset: DatasetSpec; config: Record<string, unknown> }): Promise<{ tournament_id: string }> {
  return post('/api/tournament', body);
}

// ── Health ────────────────────────────────────────────────────────────────────
export async function getHealth(): Promise<boolean> {
  try {
    await get('/health');
    return true;
  } catch {
    return false;
  }
}
