# AI Trading Arena, Master Spec & Contract

> **This file is the binding contract.** Multiple agents build different parts in parallel.
> Every schema, path, function signature, and endpoint here is authoritative. Do not deviate.
> If something is ambiguous, prefer the simplest implementation that satisfies the schema exactly.

---

## 0. What we are building

An **AI trading competition arena**. Different AI models (Claude, Gemini, OpenAI, OpenRouter-hosted)
each act as a discretionary trader on the **same historical candlestick data**. They see only past
data (no lookahead), output a trade (direction + entry + stop-loss + take-profit + rationale), and we
**forward-simulate** the market bar-by-bar to see if TP or SL hits. Repeat until each model has taken
30 to 100 trades. Then we rank them.

Two modes:
- **Tournament**, N models trade the SAME dataset; ranked on a leaderboard; raced side-by-side.
- **Solo**, one model on one dataset, for review/commentary videos.

The whole thing must be **watchable**: the frontend replays the run bar-by-bar with animated
candlesticks + a live equity curve + trade markers, with play / pause / speed / scrub controls so a
host can narrate over it.

**Key performance idea:** the LLM is called ONLY at decision points. Forward simulation of each trade
is pure Python (fast). Indicators are precomputed once over the whole series (vectorized). The run is
computed ONCE into a "run record" JSON; the frontend then replays that record infinitely, smoothly,
with no further compute. Compute-once / replay-many is the core architecture.

---

## 1. Tech stack & ports

- **Backend:** Python 3.11+, FastAPI + Uvicorn. Port **7070**.
- **Frontend:** Next.js 15 (App Router) + React 19 + TypeScript + Tailwind. Port **7071**.
  - Charts: **lightweight-charts** (TradingView) v5 for both candles and equity line.
  - State: **zustand**. Animation: **framer-motion** for UI (NOT for the chart playback loop).
- **Storage:** JSON files under `data_store/` (no DB). One file per run / tournament / dataset.
- Project root: the repository root. Every path in this spec is relative to it.

---

## 2. Directory layout (authoritative)

```
llm-trading-arena/
├── backend/
│   ├── app.py                 # FastAPI app, all endpoints, background tasks, SSE   [CORE agent]
│   ├── config.py              # settings, env loading, paths, default config         [CORE agent]
│   ├── store.py               # save/load run+tournament+dataset JSON                [CORE agent]
│   ├── schemas.py             # ALL pydantic models (shared contract types)          [CORE agent]
│   ├── data/
│   │   ├── providers.py       # Binance / MT5 / CSV -> unified OHLCV DataFrame        [CORE agent]
│   │   └── indicators.py      # vectorized indicator computation                      [CORE agent]
│   ├── engine/
│   │   ├── backtest.py        # decision-point loop + forward simulation             [CORE agent]
│   │   ├── arena.py           # tournament orchestration + leaderboard               [CORE agent]
│   │   └── context.py         # build DecisionContext (the prompt payload)           [CORE agent]
│   └── adapters/
│       ├── base.py            # ModelAdapter ABC + Decision parsing/validation       [ADAPTERS agent]
│       ├── claude_cli.py      # claude -p subprocess (subscription, no key)          [ADAPTERS agent]
│       ├── openai_adapter.py  # OpenAI structured output                             [ADAPTERS agent]
│       ├── gemini_adapter.py  # Google Gemini JSON mode                              [ADAPTERS agent]
│       ├── openrouter_adapter.py # OpenRouter (Llama/DeepSeek/Grok/Mistral/...)      [ADAPTERS agent]
│       └── registry.py        # MODEL_REGISTRY + get_adapter(id) + list_models()     [ADAPTERS agent]
├── frontend/                  # Next.js app                                          [FRONTEND agent]
├── data_store/
│   ├── runs/                  # <run_id>.json
│   ├── tournaments/           # <tournament_id>.json
│   ├── datasets/              # uploaded CSV datasets <dataset_id>.json
│   └── sample/                # a committed sample run for the frontend to demo offline
├── .env.example
├── .env                       # real keys (gitignored)
├── requirements.txt
├── start.ps1                  # starts backend + frontend
├── README.md
└── docs/ARENA_SPEC.md         # this file
```

---

## 3. Core data types (JSON shapes, the contract)

All times are **ISO 8601 UTC strings**. All money in account currency (abstract USD). Bar indices are
0-based integers into the `candles` array.

### 3.1 Candle
```json
{ "t": "2024-01-01T00:00:00Z", "o": 42000.0, "h": 42150.0, "l": 41900.0, "c": 42100.0, "v": 1234.5 }
```

### 3.2 Decision  (what a model returns at one decision point)
```json
{
  "action": "long",            // "long" | "short" | "flat"
  "entry": 42100.0,            // number | null. null => market at next bar open
  "stop_loss": 41800.0,        // number; required if action != flat
  "take_profit": 42700.0,      // number; required if action != flat
  "confidence": 0.72,          // 0..1
  "rationale": "EMA20>EMA50, RSI rising off 45, breakout of prior swing high.",
  "indicators_used": ["ema20","ema50","rsi14"]   // optional, for commentary
}
```
Validation rules (enforced in `adapters/base.py::parse_decision`):
- If `action == "flat"`: ignore price fields.
- If `action == "long"`: require `stop_loss < entry_ref < take_profit`.
- If `action == "short"`: require `take_profit < entry_ref < stop_loss`.
  (`entry_ref` = `entry` if given else the latest close passed in context.)
- If invalid geometry, coerce to `flat` (do NOT crash). Record `parse_error` string on the decision.
- Always return a valid `Decision` object; never raise to the engine.

### 3.3 DecisionContext (engine -> adapter input)
```json
{
  "symbol": "BTCUSDT", "timeframe": "1h",
  "bar_index": 350,
  "now_time": "2024-...Z",
  "lookback_candles": [ {Candle}, ... ],   // last N candles up to and INCLUDING current bar (no future)
  "indicator_snapshot": {                  // latest values + short tails, all <= current bar
      "ema20": 42050.1, "ema50": 41980.4, "rsi14": 58.2, "atr14": 220.5,
      "macd": 35.1, "macd_signal": 20.4, "bb_upper": 42500, "bb_lower": 41600,
      "recent_swing_high": 42300, "recent_swing_low": 41500,
      "ema20_series": [...last 30...], "rsi14_series": [...last 30...]
  },
  "account": { "equity": 10250.0, "starting_equity": 10000.0, "risk_per_trade_pct": 1.0, "open_position": null },
  "trades_taken": 12, "target_trades": 50,
  "instruction": "You only see data up to now. Output ONE trade decision as JSON."
}
```

### 3.4 TradeRecord (after forward simulation)
```json
{
  "id": 1, "model_id": "claude-haiku", "direction": "long",
  "decision_index": 5,
  "entry_bar": 351, "entry_time": "...Z", "entry_price": 42100.0,
  "stop_loss": 41800.0, "take_profit": 42700.0,
  "exit_bar": 366, "exit_time": "...Z", "exit_price": 42700.0,
  "outcome": "tp",                 // "tp" | "sl" | "timeout" | "eod"
  "r_multiple": 2.0,               // (exit-entry)/(entry-sl) signed by direction
  "risk_amount": 100.0,            // $ risked = equity_at_entry * risk_pct/100
  "pnl_abs": 200.0,                // r_multiple * risk_amount
  "pnl_pct": 1.96,                 // pnl_abs / equity_at_entry * 100
  "equity_after": 10200.0,
  "confidence": 0.72, "rationale": "...",
  "mae_r": -0.4, "mfe_r": 2.1      // max adverse / favorable excursion in R (optional but preferred)
}
```

### 3.5 EquityPoint (per bar, for the animated curve)
```json
{ "bar": 351, "t": "...Z", "equity": 10000.0, "floating": 10040.0, "open_trade_id": 1 }
```
- `equity` = realized equity as of this bar's close (steps at trade exits).
- `floating` = mark-to-market equity incl. open trade's unrealized PnL (moves every bar a trade is open). `open_trade_id` null when flat.
- Length == `len(candles)`. This array drives the equity animation.

### 3.6 RunRecord  (the master output for ONE model on ONE dataset)
```json
{
  "run_id": "run_<symbol>_<model>_<short-uuid>",
  "mode": "tournament",            // "solo" | "tournament"
  "tournament_id": "trn_..." ,     // null in solo
  "model_id": "claude-haiku",
  "model_label": "Claude Haiku 4.5",
  "model_color": "#F5B43C",
  "model_provider": "claude",
  "dataset": { "source":"binance","symbol":"BTCUSDT","timeframe":"1h",
               "start":"...Z","end":"...Z","bar_count": 1500 },
  "config": { "starting_equity":10000,"risk_per_trade_pct":1.0,"target_trades":50,
              "decision_cadence":3,"lookback":120,"max_trade_bars":60,
              "decision_trigger":"signals","allow_short":true,
              "indicators":["ema20","ema50","rsi14","atr14","macd","bb"] },
  "candles":   [ {Candle}, ... ],            // FULL series for replay
  "indicators":{ "ema20":[...], "ema50":[...], "rsi14":[...], "atr14":[...],
                 "macd":[...], "macd_signal":[...], "macd_hist":[...],
                 "bb_upper":[...], "bb_mid":[...], "bb_lower":[...] },  // aligned to candles, null during warmup
  "trades":    [ {TradeRecord}, ... ],
  "decisions": [ { "bar":350,"time":"...Z","action":"flat","rationale":"...","confidence":0.3,
                   "trade_id":null } , ... ],   // includes flats, for the commentary log
  "equity_curve":[ {EquityPoint}, ... ],
  "metrics":  { ...see 3.7... },
  "status": "complete",            // "queued" | "running" | "complete" | "error"
  "progress": { "trades_done": 50, "target": 50, "bars_processed": 1500, "bars_total": 1500 },
  "error": null,
  "created_at": "...Z",
  "duration_sec": 42.1
}
```

### 3.7 Metrics
```json
{
  "total_trades": 50, "wins": 31, "losses": 19, "win_rate": 62.0,
  "total_r": 24.5, "expectancy_r": 0.49, "profit_factor": 2.1,
  "net_pnl": 2450.0, "net_pnl_pct": 24.5, "final_equity": 12450.0,
  "max_drawdown_pct": 8.3, "max_drawdown_r": 4.2,
  "avg_win_r": 1.6, "avg_loss_r": -1.0, "avg_confidence": 0.61,
  "sharpe": 1.8,                  // mean(R)/std(R)*sqrt(total_trades), 0 if std==0
  "longest_win_streak": 6, "longest_loss_streak": 3,
  "avg_trade_bars": 14.2
}
```
Ranking metric for leaderboard = `net_pnl_pct` (primary), tiebreak `profit_factor` then `win_rate`.

### 3.8 TournamentRecord
```json
{
  "tournament_id": "trn_...", "name": "BTC 1h Showdown",
  "dataset": { ...same as run.dataset... },
  "config": { ...same shape as run.config... },
  "model_ids": ["claude-haiku","gemini-flash","gpt-mini"],
  "run_ids": { "claude-haiku":"run_..","gemini-flash":"run_..","gpt-mini":"run_.." },
  "leaderboard": [ { "rank":1,"model_id":"..","model_label":"..","model_color":"..",
                     "net_pnl_pct":24.5,"win_rate":62.0,"profit_factor":2.1,
                     "total_trades":50,"max_drawdown_pct":8.3,"sharpe":1.8 }, ... ],
  "status": "running",            // "queued" | "running" | "complete" | "error"
  "progress": { "models_done": 1, "models_total": 3 },
  "created_at": "...Z"
}
```

---

## 4. The backtest algorithm (engine/backtest.py)  [CORE agent]

```
run_backtest(candles, indicators, adapter, config, hooks) -> RunRecord
```
Steps:
1. **Warmup:** first usable bar = max indicator period (e.g. 50 for ema50, +BB/MACD). Call it `start`.
2. **Decision points:** iterate bar `i` from `start` to `len-2` (need at least 1 future bar to fill).
   - If currently in a trade, skip to its exit bar (no overlapping positions).
   - Decide whether bar `i` is a decision point:
     - `decision_trigger == "cadence"`: every `decision_cadence` bars.
     - `decision_trigger == "signals"`: bar is a candidate if ANY trigger fires (EMA20/50 cross,
       RSI crosses 30/70, price breaks recent_swing_high/low, MACD cross, BB touch, bullish/bearish
       engulfing). This drastically cuts LLM calls and gives the model real setups. If no triggers in
       a stretch, still force a decision every `3*decision_cadence` bars so flats are sampled.
3. **Build context** (engine/context.py): slice candles `[i-lookback+1 : i+1]` and indicator values up
   to `i` ONLY. Never pass `i+1..`. Assemble `DecisionContext`.
4. **Ask adapter:** `decision = await adapter.decide(context)`.
   - Emit a `decisions[]` entry (incl. flats).
   - Call `hooks.on_decision(i, decision)` (for SSE progress).
5. **If trade:** entry fills at `entry` if it's between next bar's [low,high]; else market at next bar
   open (`candles[i+1].o`). Entry bar = `i+1`.
   - **Forward simulate** from entry bar to `min(entry+max_trade_bars, len-1)`:
     - long: if `low <= stop_loss` -> exit SL (assume SL hit first if same bar touches both); elif
       `high >= take_profit` -> exit TP. short symmetric.
     - track MAE/MFE in R.
     - if neither by `max_trade_bars` -> exit at that bar close, outcome `"timeout"`.
     - if run out of data -> outcome `"eod"`.
   - Position size: `risk_amount = equity * risk_per_trade_pct/100`. `r_multiple` from entry/SL/exit.
     `pnl_abs = r_multiple * risk_amount`. Update `equity`.
   - Append TradeRecord. Set `i = exit_bar` and continue.
6. **Stop** when `len(trades) >= target_trades` OR data exhausted.
7. **Equity curve:** build per-bar EquityPoint for the FULL series (flat before first trade at
   starting_equity; realized steps at exits; floating = realized + open trade unrealized).
8. Compute metrics. Return RunRecord.

**Efficiency requirements:**
- Indicators precomputed ONCE (numpy/pandas), sliced by index, never recomputed per bar.
- Forward sim is pure numpy/loop over a small window, no LLM.
- `signals` trigger keeps total LLM calls ~= number of real setups (target ~ 1.5 to 3× target_trades).
- In tournament, models run **concurrently** (`asyncio.gather`), each on its own copy of the data.

**hooks**: a small object with optional async callbacks `on_decision`, `on_trade`, `on_progress`,
`on_done`. Used by app.py to push SSE events. If None, no-op.

---

## 5. Model adapters  [ADAPTERS agent]

### 5.1 base.py
```python
@dataclass
class Decision: ...                  # fields from 3.2 + parse_error: str|None
class ModelAdapter(ABC):
    id: str; label: str; provider: str; color: str; model_name: str
    def available(self) -> bool: ...           # is the key present / CLI reachable
    async def decide(self, context: dict) -> Decision: ...   # context is DecisionContext dict
# helpers:
def build_prompt(context: dict) -> tuple[str,str]   # (system, user) text
def parse_decision(raw_text: str, context: dict) -> Decision   # robust JSON extraction + validation (3.2)
```
- `build_prompt`: compact. System = trader persona + STRICT json-only instruction + the exact JSON
  schema. User = symbol/timeframe, a compact candle table (last ~40 of the lookback as
  `idx t o h l c v`), indicator snapshot values, account state, "you cannot see the future", and
  "respond with ONLY the JSON object". Keep under ~2k tokens for speed.
- `parse_decision`: extract first `{...}` JSON block (tolerate code fences / prose), validate geometry
  per 3.2, coerce invalid -> flat with `parse_error`. NEVER raise.

### 5.2 claude_cli.py  (subscription, NO API key)
- Find binary: env `CLAUDE_CLI_PATH`, else glob
  `~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe`, else `claude` on PATH.
- Spawn: `claude -p "<prompt>" --model <model_name> --output-format json` with
  **CLAUDECODE* / CLAUDE_CODE* env vars stripped** (critical, prevents nested-session detection).
  Use `asyncio.create_subprocess_exec`, timeout ~120s, `cwd` = a temp dir.
- The CLI returns JSON envelope `{ "result": "<assistant text>", ... }`. Parse `.result`, then
  `parse_decision` on it.
- Models: `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`.
- `available()` = binary found (always true on this machine).
- Concurrency note: each call spawns a process; that's fine. Keep prompts compact.

### 5.3 openai_adapter.py
- Key: `OPENAI_API_KEY`. Use `openai` SDK (async client). Structured output via
  `response_format={"type":"json_schema", ...}` or json_object; then `parse_decision`.
- Models: `gpt-5`, `gpt-5-mini` (use whatever ids; make `model_name` configurable in registry).
- `available()` = key present.

### 5.4 gemini_adapter.py
- Key: `GOOGLE_API_KEY` (or `GEMINI_API_KEY`). `google-generativeai`, `response_mime_type:
  "application/json"`. Models: `gemini-2.5-pro`, `gemini-2.5-flash`. `available()` = key present.

### 5.5 openrouter_adapter.py
- Key: `OPENROUTER_API_KEY`. OpenAI-compatible endpoint `https://openrouter.ai/api/v1`. One key
  unlocks many: DeepSeek, Llama, Grok, Mistral, Qwen. Model name = OpenRouter slug.
  `available()` = key present.

### 5.6 registry.py
```python
MODEL_REGISTRY: list[dict]   # each: {id,label,provider,model_name,color,default_in_tournament:bool}
def list_models() -> list[dict]   # each dict + "available": bool   (calls adapter.available())
def get_adapter(model_id: str) -> ModelAdapter
```
Signature colors (each model a distinct neon, gold reserved for current leader visual only):
- claude-opus → `#D97757` (Claude rust/orange), claude-sonnet → `#C15F3C`, claude-haiku → `#E8A87C`
- gemini-pro → `#4285F4`, gemini-flash → `#7CACF8`
- gpt-5 → `#10A37F`, gpt-5-mini → `#5FD0B0`
- deepseek → `#9B6DFF`, llama → `#9333EA`, grok → `#E5E7EB`, mistral → `#FF7000`, qwen → `#A855F7`
Include in default tournament: claude-haiku, gemini-flash, gpt-5-mini (cheap+fast), but all selectable.

---

## 6. API (backend/app.py, port 7070)  [CORE agent]

All JSON. CORS open to `http://localhost:7071`. Long runs execute as **FastAPI background tasks**;
status is polled or streamed via SSE.

```
GET  /health                          -> {"status":"ok"}
GET  /api/models                      -> { models: [ {id,label,provider,color,available,model_name,default_in_tournament} ] }
GET  /api/data/sources                -> { sources: ["binance","mt5","csv"], status: {binance:true, mt5:bool, csv:true} }
GET  /api/data/symbols?source=binance -> { symbols: ["BTCUSDT", ...] }   # binance: top ~40; mt5: terminal symbols; csv: uploaded ids
POST /api/data/preview                 body: DatasetSpec -> { candles:[last 200], bar_count, start, end, symbol, timeframe }
POST /api/data/upload                  multipart csv (cols: time/date,open,high,low,close,volume) -> { dataset_id, bar_count, symbol, timeframe }

POST /api/run/solo                     body: { model_id, dataset: DatasetSpec, config: Config } -> { run_id }
POST /api/tournament                   body: { name?, model_ids:[..], dataset: DatasetSpec, config: Config } -> { tournament_id }

GET  /api/run/{run_id}                 -> RunRecord (full)
GET  /api/run/{run_id}/status          -> { status, progress, metrics? }
GET  /api/runs                         -> { runs: [ {run_id,model_label,model_color,dataset,metrics,status,created_at} ] }
DELETE /api/run/{run_id}               -> { ok:true }

GET  /api/tournament/{tid}             -> TournamentRecord
GET  /api/tournament/{tid}/runs        -> { runs: [RunRecord,...] }
GET  /api/tournaments                  -> { tournaments: [summary,...] }

GET  /api/events/{id}                  -> SSE stream of progress events for a run OR tournament id.
                                          event JSON: { type:"decision"|"trade"|"progress"|"done"|"error",
                                          run_id, model_id, payload }
```

**DatasetSpec**:
```json
{ "source":"binance", "symbol":"BTCUSDT", "timeframe":"1h", "limit":1500,
  "csv_dataset_id": null, "start": null, "end": null }
```
timeframes: 1m,5m,15m,1h,4h,1d (binance native; mt5 mapped; csv as-is).

**Config** (all optional, defaults shown):
```json
{ "starting_equity":10000, "risk_per_trade_pct":1.0, "target_trades":50,
  "decision_cadence":3, "lookback":120, "max_trade_bars":60,
  "decision_trigger":"signals", "allow_short":true,
  "indicators":["ema20","ema50","rsi14","atr14","macd","bb"] }
```

---

## 7. Data providers (data/providers.py)  [CORE agent]

`load_ohlcv(spec: DatasetSpec) -> pandas.DataFrame[ t(UTC datetime), o,h,l,c,v ]`
- **binance:** GET `https://api.binance.com/api/v3/klines?symbol=&interval=&limit=` (max 1000/req;
  paginate with `endTime` to reach `limit`). No key. Map intervals. `get_binance_symbols()` -> top USDT pairs.
- **mt5:** `import MetaTrader5 as mt5` guarded in try/except. `mt5.initialize()`; `copy_rates_from_pos`.
  Map timeframe -> mt5.TIMEFRAME_*. If package/terminal missing, `mt5_available()` returns False and
  source is reported unavailable (do NOT crash the server).
- **csv:** load saved dataset JSON from `data_store/datasets/<id>.json`. Upload parses flexible columns.
- Always return UTC, ascending by time, deduped, numeric dtype. Helper `df_to_candles(df) -> list[Candle]`.

---

## 8. Frontend  [FRONTEND agent]

Next.js 15 App Router, TS, Tailwind, lightweight-charts v5, zustand, framer-motion.
`NEXT_PUBLIC_API=http://localhost:7070`. Read API contract above. Ship a typed `lib/api.ts` and
`lib/types.ts` mirroring section 3.

### Design system (DARK BROADCAST TRADING TERMINAL, override the skill's light Y2K)
- **Mode:** dark only. Cinematic, esports-broadcast / pro-terminal feel.
- **Background:** near-black navy `#06090F` base, panels `#0C111B`, elevated `#121826`, hairline
  borders `#1E2636`. Subtle radial glow behind hero + faint grid lines. Optional 3% scanline overlay.
- **Up/down:** green `#16C784`, red `#EA3943` (candles + PnL). Neutral text `#E6EAF2`, muted `#8A93A6`.
- **Leader / winner accent:** gold `#F5B43C` (glow ring around the leading model, #1 row, trophy).
- **Per-model accent:** use each model's `model_color` from the run record everywhere that model
  appears (equity line, leaderboard row, avatar ring, trade markers).
- **Typography:** numbers/prices/metrics in monospace **JetBrains Mono** (or Fira Code); UI text in
  **Inter** (or Fira Sans). Big tabular-nums for live equity + PnL.
- **Effects:** glassmorphic panels (backdrop-blur, 1px inner highlight), soft outer glows on active
  elements, 150 to 300ms transitions, count-up number animations, animated gradient on the leader.
  Respect `prefers-reduced-motion`. No emoji icons, use lucide-react.

### Screens / components
1. **Home / Launcher** (`/`): hero ("AI TRADING ARENA"), two big cards: **Tournament** and **Solo**,
   plus a list of recent runs/tournaments (history). Live status of providers + which models are
   available (key present).
2. **Setup** (modal or `/setup`): pick mode → pick model(s) (cards with availability + color) →
   pick data source/symbol/timeframe/limit (with a live candle preview chart) → config sliders
   (starting equity, risk %, target trades, trigger mode, allow short) → **Launch**.
3. **Arena / Replay** (`/arena/[id]`): THE main screen. Loads RunRecord(s).
   - **Center:** big candlestick chart (lightweight-charts). Candles reveal bar-by-bar as the playhead
     advances. Overlays: EMA20/50 lines, BB band; markers for entries (▲/▼ in model color), exits
     (green/red). When a trade is open, draw entry/SL/TP price lines. Toggle indicator panes (RSI/MACD
     subcharts).
   - **Bottom:** transport controls, Play/Pause, Restart, step ±1 bar, **speed** (0.25× 0.5× 1× 2×
     4× 8×), scrubber (timeline), current bar/time, "trade N of M".
   - **Right rail (equity):** live equity curve (lightweight-charts line in model color), big
     count-up equity number, current PnL%, open trade card (dir, entry, SL, TP, floating PnL, bars
     held), and a scrolling **decision/commentary log** (each decision's rationale appears as its bar
     is reached, this is what the host narrates).
   - **Tournament extras:** multiple equity lines on ONE chart (all models, their colors) racing in
     real time as the playhead advances; a **live leaderboard** that re-sorts with animated row
     transitions (gold glow on #1); per-model toggles. A "focus model" selector swaps the candle
     chart to show that model's trades.
   - **Solo extras:** clean single-model layout optimized for a review video, model nameplate,
     big stats, the chart + equity + commentary log. A "broadcast mode" toggle that hides chrome for
     clean screen-recording.
   - The replay loop is driven by a single rAF/timer stepping `playhead` (bar index) at the chosen
     speed; everything (candles shown, equity value, open trade, leaderboard, log) is derived from
     `playhead`. Pausing freezes it; scrubbing sets it. THIS is the "candlesticks move forward, pause,
     resume, narrate" behavior the user wants. No backend calls during replay.
   - While a run is still computing (status running), poll status/SSE and show a "computing… N/target
     trades" state; begin replay once enough data exists (can replay completed portion live).

### Apply taste rules (mandatory)
The frontend agent MUST apply premium craft: real component architecture, hardware-accelerated CSS
(transform/opacity only for animation), no layout-thrash in the replay loop, expensive spacing/shadows,
cinematic but purposeful motion, cursor-pointer + hover/focus states, responsive down to 1024px
(desktop-first; this is a broadcast tool). Numbers use tabular-nums. Follow the pre-delivery checklist.

---

## 9. Env (.env.example)
```
# Claude uses the local CLI subscription, NO key needed.
CLAUDE_CLI_PATH=
OPENAI_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
ARENA_BACKEND_PORT=7070
ARENA_FRONTEND_PORT=7071
```

## 10. Conventions
- Report absolute paths in any user-facing message.
- Never let a provider/adapter error crash a run, capture into RunRecord.status="error"+error string,
  and (tournament) continue other models.
- All timestamps UTC ISO. All floats rounded to a sane precision in JSON (prices 8 sig, money 2dp).
- Keep prompts compact for speed. Default tournament models = fast/cheap tier.
- Backend must start and serve `/health` even with ZERO API keys (Claude CLI alone works).
```
```
