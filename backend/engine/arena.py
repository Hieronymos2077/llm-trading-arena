"""
Tournament orchestration.
run_tournament(...) runs N models concurrently via asyncio.gather,
builds leaderboard, saves each run + the tournament record.
"""

from __future__ import annotations
import asyncio
import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.engine.backtest import run_backtest
from backend.store import save_run, save_tournament


def _make_leaderboard(run_records: list[dict]) -> list[dict]:
    """Sort by net_pnl_pct desc, tiebreak profit_factor, then win_rate."""
    complete = [r for r in run_records if r.get("status") == "complete" and r.get("metrics")]
    errored = [r for r in run_records if r.get("status") != "complete"]

    sorted_runs = sorted(
        complete,
        key=lambda r: (
            r["metrics"]["net_pnl_pct"],
            r["metrics"]["profit_factor"],
            r["metrics"]["win_rate"],
        ),
        reverse=True,
    )

    leaderboard = []
    for rank, r in enumerate(sorted_runs + errored, start=1):
        m = r.get("metrics") or {}
        leaderboard.append({
            "rank": rank,
            "model_id": r["model_id"],
            "model_label": r["model_label"],
            "model_color": r["model_color"],
            "net_pnl_pct": m.get("net_pnl_pct", 0.0),
            "win_rate": m.get("win_rate", 0.0),
            "profit_factor": m.get("profit_factor", 0.0),
            "total_trades": m.get("total_trades", 0),
            "max_drawdown_pct": m.get("max_drawdown_pct", 0.0),
            "sharpe": m.get("sharpe", 0.0),
        })

    return leaderboard


async def run_tournament(
    candles: list[dict],
    indicators: dict,
    adapters: list[Any],            # list of ModelAdapter-like objects
    config: Any,
    tournament_id: Optional[str] = None,
    name: str = "Tournament",
    dataset_info: Optional[dict] = None,
    hooks_factory: Optional[Any] = None,  # callable(model_id) -> hooks
    on_run_complete: Optional[Any] = None,  # async callable(run_record)
    pre_run_ids: Optional[dict] = None,    # model_id -> run_id, pre-assigned by caller
) -> dict:
    """
    Run all adapters concurrently. Each gets its own copy of candles/indicators.
    One model's error does NOT abort others.
    Returns a TournamentRecord dict.
    """
    if tournament_id is None:
        tournament_id = f"trn_{uuid.uuid4().hex[:8]}"

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Config dict
    if hasattr(config, "__dict__") or hasattr(config, "model_fields"):
        cfg_dict = {
            "starting_equity": getattr(config, "starting_equity", 10000),
            "risk_per_trade_pct": getattr(config, "risk_per_trade_pct", 1.0),
            "target_trades": getattr(config, "target_trades", 50),
            "decision_cadence": getattr(config, "decision_cadence", 3),
            "lookback": getattr(config, "lookback", 120),
            "max_trade_bars": getattr(config, "max_trade_bars", 60),
            "decision_trigger": getattr(config, "decision_trigger", "signals"),
            "allow_short": getattr(config, "allow_short", True),
            "indicators": list(getattr(config, "indicators", ["ema20", "ema50", "rsi14", "atr14", "macd", "bb"])),
        }
    else:
        cfg_dict = dict(config)

    ds = dataset_info or {
        "source": "unknown", "symbol": "UNKNOWN", "timeframe": "1h",
        "start": candles[0]["t"] if candles else "",
        "end": candles[-1]["t"] if candles else "",
        "bar_count": len(candles),
    }

    model_ids = [a.id for a in adapters]

    # Resolve run_ids: use pre-assigned ones if provided, else generate
    resolved_run_ids: dict[str, str] = {}
    for adapter in adapters:
        if pre_run_ids and adapter.id in pre_run_ids:
            resolved_run_ids[adapter.id] = pre_run_ids[adapter.id]
        else:
            short = uuid.uuid4().hex[:8]
            sym = ds.get("symbol", "UNKNOWN")
            resolved_run_ids[adapter.id] = f"run_{sym}_{adapter.id}_{short}"

    # Build initial tournament record (with run_ids populated up front)
    tournament: dict = {
        "tournament_id": tournament_id,
        "name": name,
        "dataset": ds,
        "config": cfg_dict,
        "model_ids": model_ids,
        "run_ids": resolved_run_ids,
        "leaderboard": [],
        "status": "running",
        "progress": {"models_done": 0, "models_total": len(adapters)},
        "created_at": now,
    }
    save_tournament(tournament)

    # Save queued stubs for each run so /tournament/{id}/runs returns something immediately
    for adapter in adapters:
        rid = resolved_run_ids[adapter.id]
        stub = {
            "run_id": rid,
            "mode": "tournament",
            "tournament_id": tournament_id,
            "model_id": adapter.id,
            "model_label": getattr(adapter, "label", adapter.id),
            "model_color": getattr(adapter, "color", "#FFFFFF"),
            "model_provider": getattr(adapter, "provider", "unknown"),
            "dataset": ds,
            "config": cfg_dict,
            "candles": [], "indicators": {}, "trades": [], "decisions": [], "equity_curve": [],
            "metrics": None,
            "status": "queued",
            "progress": {"trades_done": 0, "target": cfg_dict.get("target_trades", 50), "bars_processed": 0, "bars_total": len(candles)},
            "error": None,
            "created_at": now,
            "duration_sec": 0.0,
        }
        save_run(stub)

    run_results: list[dict] = []

    async def _run_one(adapter: Any) -> dict:
        rid = resolved_run_ids[adapter.id]
        hooks = hooks_factory(adapter.id) if hooks_factory else None

        try:
            record = await run_backtest(
                candles=copy.deepcopy(candles),
                indicators=copy.deepcopy(indicators),
                adapter=adapter,
                config=config,
                hooks=hooks,
                model_id=adapter.id,
                model_label=getattr(adapter, "label", adapter.id),
                model_color=getattr(adapter, "color", "#FFFFFF"),
                model_provider=getattr(adapter, "provider", "unknown"),
                mode="tournament",
                tournament_id=tournament_id,
                run_id=rid,
            )
            # Patch dataset info
            record["dataset"] = ds
        except Exception as e:
            now2 = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record = {
                "run_id": rid,
                "mode": "tournament",
                "tournament_id": tournament_id,
                "model_id": adapter.id,
                "model_label": getattr(adapter, "label", adapter.id),
                "model_color": getattr(adapter, "color", "#FFFFFF"),
                "model_provider": getattr(adapter, "provider", "unknown"),
                "dataset": ds,
                "config": cfg_dict,
                "candles": [],
                "indicators": {},
                "trades": [],
                "decisions": [],
                "equity_curve": [],
                "metrics": None,
                "status": "error",
                "progress": {"trades_done": 0, "target": cfg_dict.get("target_trades", 50), "bars_processed": 0, "bars_total": len(candles)},
                "error": str(e),
                "created_at": now2,
                "duration_sec": 0.0,
            }

        save_run(record)
        if on_run_complete:
            try:
                await on_run_complete(record)
            except Exception:
                pass
        return record

    # Run all concurrently
    tasks = [_run_one(adapter) for adapter in adapters]
    run_results = await asyncio.gather(*tasks, return_exceptions=False)

    # Flatten any exceptions that slipped through (shouldn't, but safe)
    cleaned = []
    for r in run_results:
        if isinstance(r, Exception):
            cleaned.append({"status": "error", "model_id": "unknown", "metrics": None, "model_label": "Unknown", "model_color": "#FFFFFF"})
        else:
            cleaned.append(r)

    # Build leaderboard
    leaderboard = _make_leaderboard(cleaned)

    # Final tournament
    run_ids = {r["model_id"]: r["run_id"] for r in cleaned if "run_id" in r}
    tournament.update({
        "run_ids": run_ids,
        "leaderboard": leaderboard,
        "status": "complete",
        "progress": {"models_done": len(cleaned), "models_total": len(adapters)},
    })
    save_tournament(tournament)

    return tournament
