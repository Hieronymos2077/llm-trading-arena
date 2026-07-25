"""
AI Trading Arena, FastAPI backend (port 7070).
All endpoints from spec §6. Long runs as background tasks. SSE for progress.
"""

from __future__ import annotations
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.config import FRONTEND_ORIGIN
from backend.schemas import (
    Config,
    DataPreviewRequest,
    DatasetSpec,
    SoloRunRequest,
    TournamentRequest,
)
from backend.store import (
    delete_run,
    list_runs,
    list_tournaments,
    load_run,
    load_tournament,
    save_dataset,
    save_run,
    save_tournament,
    list_datasets,
)

# ---------------------------------------------------------------------------
# Resilient adapter import (adapters/ may not exist yet)
# ---------------------------------------------------------------------------

_get_adapter = None
_list_models = None

try:
    from backend.adapters.registry import get_adapter as _get_adapter_import
    from backend.adapters.registry import list_models as _list_models_import
    _get_adapter = _get_adapter_import
    _list_models = _list_models_import
except Exception:
    pass


def get_adapter(model_id: str):
    if _get_adapter is None:
        raise HTTPException(status_code=503, detail="Model adapters not yet installed")
    return _get_adapter(model_id)


def list_models_safe() -> list[dict]:
    if _list_models is None:
        return []
    try:
        return _list_models()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# SSE event bus: run_id / tournament_id -> list of queues
# ---------------------------------------------------------------------------

_sse_queues: dict[str, list[asyncio.Queue]] = {}


def _push_event(id_: str, event: dict) -> None:
    for q in _sse_queues.get(id_, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# Hooks for backtest, publishes progress via SSE
# ---------------------------------------------------------------------------

class _SSEHooks:
    def __init__(self, sse_channel_id: str, model_id: str, save_run_id: str, dataset_info: Optional[dict] = None):
        self.run_id = sse_channel_id       # SSE channel (= tournament_id for tournaments)
        self.save_run_id = save_run_id     # real run_id used for save_run()
        self.model_id = model_id
        self.dataset_info = dataset_info   # patch correct dataset into partial records

    async def on_decision(self, bar, decision):
        action = "flat"
        if decision and hasattr(decision, "action"):
            action = decision.action
        _push_event(self.run_id, {
            "type": "decision",
            "run_id": self.save_run_id,
            "model_id": self.model_id,
            "payload": {"bar": bar, "action": action},
        })

    async def on_trade(self, trade: dict):
        _push_event(self.run_id, {
            "type": "trade",
            "run_id": self.save_run_id,
            "model_id": self.model_id,
            "payload": trade,
        })

    async def on_progress(self, trades_done, target, bars_processed, bars_total):
        _push_event(self.run_id, {
            "type": "progress",
            "run_id": self.save_run_id,
            "model_id": self.model_id,
            "payload": {
                "trades_done": trades_done, "target": target,
                "bars_processed": bars_processed, "bars_total": bars_total,
            },
        })

    async def on_partial(self, record: dict):
        record = dict(record)
        record["run_id"] = self.save_run_id
        if self.dataset_info:
            record["dataset"] = self.dataset_info
        save_run(record)
        _push_event(self.run_id, {
            "type": "partial",
            "run_id": self.save_run_id,
            "model_id": self.model_id,
            "payload": {
                "status": record.get("status"),
                "progress": record.get("progress"),
            },
        })

    async def on_done(self, record: dict):
        _push_event(self.run_id, {
            "type": "done",
            "run_id": self.save_run_id,
            "model_id": self.model_id,
            "payload": {"status": record.get("status")},
        })


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Trading Arena", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@app.get("/api/models")
async def api_models():
    return {"models": list_models_safe()}


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------

@app.get("/api/data/sources")
async def api_data_sources():
    from backend.data.providers import mt5_available
    return {
        "sources": ["binance", "mt5", "csv"],
        "status": {
            "binance": True,
            "mt5": mt5_available(),
            "csv": True,
        },
    }


@app.get("/api/data/datasets")
async def api_data_datasets():
    """List uploaded CSV datasets with metadata (for the setup UI)."""
    from backend.store import list_datasets, load_dataset
    out = []
    for did in list_datasets():
        d = load_dataset(did) or {}
        out.append({
            "dataset_id": did,
            "symbol": d.get("symbol", "?"),
            "timeframe": d.get("timeframe", "?"),
            "bar_count": d.get("bar_count", len(d.get("candles", []))),
        })
    return {"datasets": out}


@app.get("/api/data/symbols")
async def api_data_symbols(source: str = "binance"):
    from backend.data.providers import get_binance_symbols, mt5_available
    if source == "binance":
        return {"symbols": get_binance_symbols()}
    elif source == "mt5":
        if not mt5_available():
            return {"symbols": []}
        try:
            import MetaTrader5 as mt5
            mt5.initialize()
            symbols = [s.name for s in mt5.symbols_get() or []]
            mt5.shutdown()
            return {"symbols": sorted(symbols)}
        except Exception:
            return {"symbols": []}
    elif source == "csv":
        from backend.store import list_datasets as _ld
        return {"symbols": _ld()}
    return {"symbols": []}


@app.post("/api/data/preview")
async def api_data_preview(body: DataPreviewRequest):
    from backend.data.providers import load_ohlcv, df_to_candles
    spec = DatasetSpec(
        source=body.source,
        symbol=body.symbol,
        timeframe=body.timeframe,
        limit=min(body.limit, 2000),
        csv_dataset_id=body.csv_dataset_id,
        start=body.start,
        end=body.end,
    )
    try:
        df = load_ohlcv(spec)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    candles = df_to_candles(df)
    last200 = candles[-200:] if len(candles) > 200 else candles
    return {
        "candles": last200,
        "bar_count": len(candles),
        "start": candles[0]["t"] if candles else None,
        "end": candles[-1]["t"] if candles else None,
        "symbol": spec.symbol,
        "timeframe": spec.timeframe,
    }


@app.post("/api/data/upload")
async def api_data_upload(
    file: UploadFile = File(...),
    symbol: str = Form("CUSTOM"),
    timeframe: str = Form("1h"),
):
    from backend.data.providers import parse_csv_upload, df_to_candles
    content = await file.read()
    try:
        df = parse_csv_upload(content, symbol, timeframe)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dataset_id = f"csv_{uuid.uuid4().hex[:8]}"
    candles = df_to_candles(df)
    dataset_doc = {
        "dataset_id": dataset_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": candles,
        "bar_count": len(candles),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    save_dataset(dataset_id, dataset_doc)
    return {"dataset_id": dataset_id, "bar_count": len(candles), "symbol": symbol, "timeframe": timeframe}


# ---------------------------------------------------------------------------
# Solo run
# ---------------------------------------------------------------------------

async def _do_solo_run(run_id: str, model_id: str, spec: DatasetSpec, config: Config):
    from backend.data.providers import load_ohlcv, df_to_candles
    from backend.data.indicators import compute_indicators
    from backend.engine.backtest import run_backtest

    # Mark running
    existing = load_run(run_id)
    if existing:
        existing["status"] = "running"
        save_run(existing)

    try:
        df = load_ohlcv(spec)
        candles = df_to_candles(df)
        indicators = compute_indicators(df)

        adapter = get_adapter(model_id)
        model_info = {}
        for m in list_models_safe():
            if m["id"] == model_id:
                model_info = m
                break

        ds_info = {
            "source": spec.source,
            "symbol": spec.symbol,
            "timeframe": spec.timeframe,
            "start": candles[0]["t"] if candles else "",
            "end": candles[-1]["t"] if candles else "",
            "bar_count": len(candles),
        }

        hooks = _SSEHooks(run_id, model_id, save_run_id=run_id, dataset_info=ds_info)

        record = await run_backtest(
            candles=candles,
            indicators=indicators,
            adapter=adapter,
            config=config,
            hooks=hooks,
            model_id=model_id,
            model_label=model_info.get("label", model_id),
            model_color=model_info.get("color", "#FFFFFF"),
            model_provider=model_info.get("provider", "unknown"),
            mode="solo",
            tournament_id=None,
            run_id=run_id,
        )
        record["dataset"] = ds_info
        record["run_id"] = run_id
        save_run(record)
        _push_event(run_id, {"type": "done", "run_id": run_id, "model_id": model_id, "payload": {"status": "complete"}})
    except Exception as e:
        err_record = load_run(run_id) or {}
        err_record.update({
            "run_id": run_id,
            "status": "error",
            "error": str(e),
        })
        save_run(err_record)
        _push_event(run_id, {"type": "error", "run_id": run_id, "model_id": model_id, "payload": {"error": str(e)}})


@app.post("/api/run/solo")
async def api_run_solo(body: SoloRunRequest, background_tasks: BackgroundTasks):
    config = body.config or Config()
    short = uuid.uuid4().hex[:8]
    run_id = f"run_{body.dataset.symbol}_{body.model_id}_{short}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    model_info = {}
    for m in list_models_safe():
        if m["id"] == body.model_id:
            model_info = m
            break

    stub = {
        "run_id": run_id,
        "mode": "solo",
        "tournament_id": None,
        "model_id": body.model_id,
        "model_label": model_info.get("label", body.model_id),
        "model_color": model_info.get("color", "#FFFFFF"),
        "model_provider": model_info.get("provider", "unknown"),
        "dataset": {"source": body.dataset.source, "symbol": body.dataset.symbol,
                    "timeframe": body.dataset.timeframe, "start": "", "end": "", "bar_count": 0},
        "config": config.model_dump(),
        "candles": [], "indicators": {}, "trades": [], "decisions": [], "equity_curve": [],
        "metrics": None,
        "status": "queued",
        "progress": {"trades_done": 0, "target": config.target_trades, "bars_processed": 0, "bars_total": 0},
        "error": None,
        "created_at": now,
        "duration_sec": 0.0,
    }
    save_run(stub)
    background_tasks.add_task(_do_solo_run, run_id, body.model_id, body.dataset, config)
    return {"run_id": run_id}


# ---------------------------------------------------------------------------
# Tournament
# ---------------------------------------------------------------------------

async def _do_tournament(
    tournament_id: str,
    name: str,
    model_ids: list[str],
    spec: DatasetSpec,
    config: Config,
):
    from backend.data.providers import load_ohlcv, df_to_candles
    from backend.data.indicators import compute_indicators
    from backend.engine.arena import run_tournament

    tournament = load_tournament(tournament_id) or {}
    tournament["status"] = "running"
    save_tournament(tournament)

    try:
        df = load_ohlcv(spec)
        candles = df_to_candles(df)
        indicators = compute_indicators(df)

        adapters = []
        for mid in model_ids:
            try:
                adapters.append(get_adapter(mid))
            except Exception:
                pass

        if not adapters:
            raise ValueError("No valid adapters found for given model_ids")

        ds_info = {
            "source": spec.source,
            "symbol": spec.symbol,
            "timeframe": spec.timeframe,
            "start": candles[0]["t"] if candles else "",
            "end": candles[-1]["t"] if candles else "",
            "bar_count": len(candles),
        }

        # Pre-assign deterministic run_ids so /tournament/{id}/runs works while computing
        pre_run_ids: dict[str, str] = {}
        for mid in model_ids:
            short = uuid.uuid4().hex[:8]
            pre_run_ids[mid] = f"run_{spec.symbol}_{mid}_{short}"

        # Persist pre-assigned run_ids to the tournament record immediately
        t_record = load_tournament(tournament_id) or {}
        t_record["run_ids"] = pre_run_ids
        t_record["dataset"] = ds_info
        save_tournament(t_record)

        def hooks_factory(mid):
            real_run_id = pre_run_ids.get(mid, f"run_{spec.symbol}_{mid}_{uuid.uuid4().hex[:8]}")
            return _SSEHooks(tournament_id, mid, save_run_id=real_run_id, dataset_info=ds_info)

        async def on_run_complete(record: dict):
            t = load_tournament(tournament_id) or {}
            done = t.get("progress", {}).get("models_done", 0) + 1
            t["progress"] = {"models_done": done, "models_total": len(model_ids)}
            save_tournament(t)
            _push_event(tournament_id, {
                "type": "progress",
                "run_id": record.get("run_id"),
                "model_id": record.get("model_id"),
                "payload": {"models_done": done, "models_total": len(model_ids)},
            })

        result = await run_tournament(
            candles=candles,
            indicators=indicators,
            adapters=adapters,
            config=config,
            tournament_id=tournament_id,
            name=name,
            dataset_info=ds_info,
            hooks_factory=hooks_factory,
            on_run_complete=on_run_complete,
            pre_run_ids=pre_run_ids,
        )
        _push_event(tournament_id, {"type": "done", "run_id": None, "model_id": None, "payload": {"status": "complete"}})
    except Exception as e:
        t = load_tournament(tournament_id) or {}
        t["status"] = "error"
        t["error"] = str(e)
        save_tournament(t)
        _push_event(tournament_id, {"type": "error", "run_id": None, "model_id": None, "payload": {"error": str(e)}})


@app.post("/api/tournament")
async def api_tournament(body: TournamentRequest, background_tasks: BackgroundTasks):
    config = body.config or Config()
    tournament_id = f"trn_{uuid.uuid4().hex[:8]}"
    name = body.name or f"{body.dataset.symbol} {body.dataset.timeframe} Showdown"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    stub = {
        "tournament_id": tournament_id,
        "name": name,
        "dataset": {"source": body.dataset.source, "symbol": body.dataset.symbol,
                    "timeframe": body.dataset.timeframe, "start": "", "end": "", "bar_count": 0},
        "config": config.model_dump(),
        "model_ids": body.model_ids,
        "run_ids": {},
        "leaderboard": [],
        "status": "queued",
        "progress": {"models_done": 0, "models_total": len(body.model_ids)},
        "created_at": now,
    }
    save_tournament(stub)
    background_tasks.add_task(
        _do_tournament, tournament_id, name, body.model_ids, body.dataset, config
    )
    return {"tournament_id": tournament_id}


# ---------------------------------------------------------------------------
# Run read endpoints
# ---------------------------------------------------------------------------

@app.get("/api/run/{run_id}")
async def api_get_run(run_id: str):
    record = load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record


@app.get("/api/run/{run_id}/status")
async def api_run_status(run_id: str):
    record = load_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "status": record.get("status"),
        "progress": record.get("progress"),
        "metrics": record.get("metrics"),
    }


@app.get("/api/runs")
async def api_list_runs():
    return {"runs": list_runs()}


@app.delete("/api/run/{run_id}")
async def api_delete_run(run_id: str):
    ok = delete_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Tournament read endpoints
# ---------------------------------------------------------------------------

@app.get("/api/tournament/{tid}")
async def api_get_tournament(tid: str):
    record = load_tournament(tid)
    if record is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return record


@app.get("/api/tournament/{tid}/runs")
async def api_tournament_runs(tid: str):
    t = load_tournament(tid)
    if t is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    runs = []
    for mid, rid in t.get("run_ids", {}).items():
        r = load_run(rid)
        if r:
            runs.append(r)
    return {"runs": runs}


@app.get("/api/tournaments")
async def api_list_tournaments():
    return {"tournaments": list_tournaments()}


# ---------------------------------------------------------------------------
# SSE events
# ---------------------------------------------------------------------------

@app.get("/api/events/{id_}")
async def api_events(id_: str):
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    if id_ not in _sse_queues:
        _sse_queues[id_] = []
    _sse_queues[id_].append(q)

    async def _gen() -> AsyncGenerator[str, None]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _sse_queues.get(id_, []).remove(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
