"""
Build the DecisionContext dict that is passed to each adapter.
Only includes data up to and including bar i, never future bars.
"""

from __future__ import annotations
from typing import Any
from backend.data.indicators import get_indicator_snapshot


def build_context(
    candles: list[dict],
    ind_arrays: dict,
    i: int,
    symbol: str,
    timeframe: str,
    equity: float,
    starting_equity: float,
    risk_per_trade_pct: float,
    open_position: dict | None,
    trades_taken: int,
    target_trades: int,
    lookback: int = 120,
    decision_trigger: str = "signals",
) -> dict:
    """
    Build DecisionContext for bar index i.
    Slices candles[i-lookback+1 : i+1], never includes i+1 or beyond.
    """
    lb_start = max(0, i - lookback + 1)
    lookback_candles = candles[lb_start : i + 1]  # inclusive of i, exclusive of future

    indicator_snapshot = get_indicator_snapshot(ind_arrays, i, tail=30)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bar_index": i,
        "now_time": candles[i]["t"],
        "lookback_candles": lookback_candles,
        "indicator_snapshot": indicator_snapshot,
        "account": {
            "equity": round(equity, 2),
            "starting_equity": round(starting_equity, 2),
            "risk_per_trade_pct": risk_per_trade_pct,
            "open_position": open_position,
        },
        "trades_taken": trades_taken,
        "target_trades": target_trades,
        "instruction": (
            "You only see data up to now. Output ONE trade decision as JSON."
        ),
    }
