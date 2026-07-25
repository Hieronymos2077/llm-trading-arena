"""
Backtest engine.

run_backtest(candles, indicators, adapter, config, hooks=None) -> dict (RunRecord shape)

Algorithm follows spec §4 exactly:
- Warmup to max indicator period
- Decision triggers: cadence or signals
- Non-overlapping trades, forward-simulation, SL-before-TP same bar
- MAE/MFE in R
- Full equity curve (realized + floating) per bar
- Metrics §3.7
"""

from __future__ import annotations
import asyncio
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import numpy as np

from backend.engine.context import build_context

# ---------------------------------------------------------------------------
# Warmup period
# ---------------------------------------------------------------------------

# ema50 (50), bb/macd slow26+signal9=34 -> 50 is the longest
WARMUP_BARS = 60  # safe margin above max(50, 34)


# ---------------------------------------------------------------------------
# Signal triggers for "signals" mode
# ---------------------------------------------------------------------------

def _has_signal(candles: list[dict], ind_arrays: dict, i: int) -> bool:
    """Return True if any trigger fires at bar i."""
    if i < 1:
        return False

    c = candles
    a = ind_arrays

    def _v(arr, idx) -> float | None:
        v = arr[idx]
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)

    ema20 = _v(a["ema20"], i)
    ema50 = _v(a["ema50"], i)
    ema20_p = _v(a["ema20"], i - 1)
    ema50_p = _v(a["ema50"], i - 1)
    rsi = _v(a["rsi14"], i)
    rsi_p = _v(a["rsi14"], i - 1)
    macd = _v(a["macd"], i)
    macd_sig = _v(a["macd_signal"], i)
    macd_p = _v(a["macd"], i - 1)
    macd_sig_p = _v(a["macd_signal"], i - 1)
    bb_upper = _v(a["bb_upper"], i)
    bb_lower = _v(a["bb_lower"], i)
    swing_h = _v(a["recent_swing_high"], i)
    swing_l = _v(a["recent_swing_low"], i)

    curr = c[i]
    prev = c[i - 1]

    # EMA cross
    if None not in (ema20, ema50, ema20_p, ema50_p):
        if (ema20_p < ema50_p and ema20 > ema50) or (ema20_p > ema50_p and ema20 < ema50):
            return True

    # RSI cross 30/70
    if None not in (rsi, rsi_p):
        if (rsi_p < 30 and rsi >= 30) or (rsi_p > 70 and rsi <= 70):
            return True
        if rsi < 30 or rsi > 70:
            return True

    # MACD cross
    if None not in (macd, macd_sig, macd_p, macd_sig_p):
        if (macd_p < macd_sig_p and macd > macd_sig) or (macd_p > macd_sig_p and macd < macd_sig):
            return True

    # BB touch
    if None not in (bb_upper, bb_lower):
        if curr["h"] >= bb_upper or curr["l"] <= bb_lower:
            return True

    # Swing breakout
    if swing_h is not None and curr["c"] > swing_h:
        return True
    if swing_l is not None and curr["c"] < swing_l:
        return True

    # Bullish / bearish engulfing
    p_body = abs(prev["c"] - prev["o"])
    c_body = abs(curr["c"] - curr["o"])
    if p_body > 0 and c_body > p_body:
        # bullish engulf
        if prev["c"] < prev["o"] and curr["c"] > curr["o"] and curr["o"] <= prev["c"]:
            return True
        # bearish engulf
        if prev["c"] > prev["o"] and curr["c"] < curr["o"] and curr["o"] >= prev["c"]:
            return True

    return False


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(trades: list[dict], equity_curve: list[dict], starting_equity: float) -> dict:
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "total_r": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0,
            "net_pnl": 0.0, "net_pnl_pct": 0.0, "final_equity": starting_equity,
            "max_drawdown_pct": 0.0, "max_drawdown_r": 0.0,
            "avg_win_r": 0.0, "avg_loss_r": 0.0, "avg_confidence": 0.0,
            "sharpe": 0.0, "longest_win_streak": 0, "longest_loss_streak": 0,
            "avg_trade_bars": 0.0,
        }

    rs = [t["r_multiple"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    confidences = [t["confidence"] for t in trades]

    total_r = sum(rs)
    expectancy_r = total_r / len(rs)
    gross_profit = sum(w for w in wins)
    gross_loss = abs(sum(l for l in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

    final_equity = trades[-1]["equity_after"]
    net_pnl = final_equity - starting_equity
    net_pnl_pct = round(net_pnl / starting_equity * 100, 4)

    # Max drawdown on equity curve
    equities = [pt["equity"] for pt in equity_curve]
    peak = equities[0]
    max_dd_pct = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd_pct:
            max_dd_pct = dd

    # Max drawdown in R
    max_dd_r = 0.0
    running_r = 0.0
    peak_r = 0.0
    for r in rs:
        running_r += r
        if running_r > peak_r:
            peak_r = running_r
        dd_r = peak_r - running_r
        if dd_r > max_dd_r:
            max_dd_r = dd_r

    # Sharpe: mean(R)/std(R)*sqrt(n)
    if len(rs) > 1:
        std_r = float(np.std(rs, ddof=1))
        sharpe = (sum(rs) / len(rs)) / std_r * math.sqrt(len(rs)) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # Streaks
    longest_win = 0
    longest_loss = 0
    cur_win = 0
    cur_loss = 0
    for r in rs:
        if r > 0:
            cur_win += 1
            cur_loss = 0
            longest_win = max(longest_win, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            longest_loss = max(longest_loss, cur_loss)

    avg_trade_bars = sum(t["exit_bar"] - t["entry_bar"] for t in trades) / len(trades)

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "total_r": round(total_r, 4),
        "expectancy_r": round(expectancy_r, 4),
        "profit_factor": round(profit_factor, 4),
        "net_pnl": round(net_pnl, 2),
        "net_pnl_pct": round(net_pnl_pct, 4),
        "final_equity": round(final_equity, 2),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "max_drawdown_r": round(max_dd_r, 4),
        "avg_win_r": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss_r": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "avg_confidence": round(sum(confidences) / len(confidences), 4),
        "sharpe": round(sharpe, 4),
        "longest_win_streak": longest_win,
        "longest_loss_streak": longest_loss,
        "avg_trade_bars": round(avg_trade_bars, 2),
    }


# ---------------------------------------------------------------------------
# Hooks no-op
# ---------------------------------------------------------------------------

class _NoopHooks:
    async def on_decision(self, bar, decision): pass
    async def on_trade(self, trade): pass
    async def on_progress(self, trades_done, target, bars_processed, bars_total): pass
    async def on_done(self, record): pass
    async def on_partial(self, record): pass


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

async def run_backtest(
    candles: list[dict],
    indicators: dict,
    adapter: Any,
    config: Any,
    hooks: Any = None,
    model_id: str = "unknown",
    model_label: str = "Unknown",
    model_color: str = "#FFFFFF",
    model_provider: str = "unknown",
    mode: str = "solo",
    tournament_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict:
    """
    Run one backtest. Returns a RunRecord-shaped dict.
    """
    started = time.time()
    if hooks is None:
        hooks = _NoopHooks()

    # Unpack config
    if hasattr(config, "__dict__") or hasattr(config, "model_fields"):
        cfg = config if hasattr(config, "starting_equity") else config
        starting_equity = float(getattr(cfg, "starting_equity", 10000))
        risk_pct = float(getattr(cfg, "risk_per_trade_pct", 1.0))
        target_trades = int(getattr(cfg, "target_trades", 50))
        decision_cadence = int(getattr(cfg, "decision_cadence", 3))
        lookback = int(getattr(cfg, "lookback", 120))
        max_trade_bars = int(getattr(cfg, "max_trade_bars", 60))
        decision_trigger = str(getattr(cfg, "decision_trigger", "signals"))
        allow_short = bool(getattr(cfg, "allow_short", True))
        ind_list = list(getattr(cfg, "indicators", ["ema20", "ema50", "rsi14", "atr14", "macd", "bb"]))
    else:
        # dict-like
        starting_equity = float(config.get("starting_equity", 10000))
        risk_pct = float(config.get("risk_per_trade_pct", 1.0))
        target_trades = int(config.get("target_trades", 50))
        decision_cadence = int(config.get("decision_cadence", 3))
        lookback = int(config.get("lookback", 120))
        max_trade_bars = int(config.get("max_trade_bars", 60))
        decision_trigger = str(config.get("decision_trigger", "signals"))
        allow_short = bool(config.get("allow_short", True))
        ind_list = list(config.get("indicators", ["ema20", "ema50", "rsi14", "atr14", "macd", "bb"]))

    if run_id is None:
        short = uuid.uuid4().hex[:8]
        sym = candles[0]["t"].replace(":", "").replace("-", "")[:8] if candles else "X"
        run_id = f"run_{candles[0].get('t', '')[:10].replace('-', '')}_{model_id}_{short}"
        # Cleaner format matching sample fixture
        sym_clean = ""  # will use symbol from context
        run_id = f"run_{'UNKNOWN'}_{model_id}_{short}"

    n = len(candles)
    ind_arrays = indicators.get("_arrays", {})

    # Rebuild arrays if not present (support pre-serialized indicator dicts from saved runs)
    if not ind_arrays:
        import numpy as np
        def _arr(key):
            lst = indicators.get(key, [])
            return np.array([float("nan") if v is None else float(v) for v in lst])
        _all_ind_keys = [
            "ema10", "ema20", "ema30", "ema50", "ema100", "ema200",
            "sma10", "sma20", "sma30", "sma50", "sma100", "sma200",
            "rsi14", "stoch_k", "stoch_d", "cci20",
            "adx14", "plus_di", "minus_di", "ao", "momentum10", "williams_r14",
            "macd", "macd_signal", "macd_hist",
            "atr14", "bb_upper", "bb_mid", "bb_lower",
            "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a", "ichimoku_senkou_b",
            "pivot_p", "pivot_r1", "pivot_r2", "pivot_s1", "pivot_s2",
            "recent_swing_high", "recent_swing_low",
        ]
        ind_arrays = {k: _arr(k) for k in _all_ind_keys if k in indicators}

    equity = starting_equity
    trades: list[dict] = []
    decisions: list[dict] = []

    # Equity curve, one entry per bar
    equity_curve: list[dict] = []
    # We build this as we go; initially all flat at starting_equity

    # Track open trade
    in_trade = False
    trade_exit_bar = -1

    # last_decision_bar for cadence fallback in signals mode
    last_decision_bar = WARMUP_BARS - 1
    force_every = 3 * decision_cadence

    i = WARMUP_BARS
    bar_equity: list[float] = [starting_equity] * n  # realized equity per bar
    bar_floating: list[float] = [starting_equity] * n
    bar_trade_id: list[Optional[int]] = [None] * n

    open_trade_ref: Optional[dict] = None  # current open trade for equity calc

    # Serialize indicators once (reused by _build_record)
    ind_serialized = {k: v for k, v in indicators.items() if k != "_arrays"}

    # Config dict (reused by _build_record)
    cfg_dict = {
        "starting_equity": starting_equity,
        "risk_per_trade_pct": risk_pct,
        "target_trades": target_trades,
        "decision_cadence": decision_cadence,
        "lookback": lookback,
        "max_trade_bars": max_trade_bars,
        "decision_trigger": decision_trigger,
        "allow_short": allow_short,
        "indicators": ind_list,
    }

    ds_info = {
        "source": "unknown",
        "symbol": "UNKNOWN",
        "timeframe": "1h",
        "start": candles[0]["t"] if candles else "",
        "end": candles[-1]["t"] if candles else "",
        "bar_count": n,
    }

    now_created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Throttle: track last persist time + current bar for progress
    _last_partial_time: list[float] = [0.0]
    _current_bar: list[int] = [WARMUP_BARS]

    def _build_record(status: str) -> dict:
        """Build a RunRecord from the current state of trades/decisions/equity."""
        # Build equity curve for processed bars only (flat at starting_equity beyond last processed bar)
        ec: list[dict] = []

        # Rebuild realized equity step-function
        ec_realized = [starting_equity] * n
        for trade in trades:
            for b in range(trade["exit_bar"], n):
                ec_realized[b] = trade["equity_after"]

        for b in range(n):
            open_id = bar_trade_id[b]
            if open_id is not None:
                floating = bar_floating[b]
            else:
                floating = ec_realized[b]
            ec.append({
                "bar": b,
                "t": candles[b]["t"],
                "equity": round(ec_realized[b], 2),
                "floating": round(floating, 2),
                "open_trade_id": open_id,
            })

        metrics = compute_metrics(list(trades), ec, starting_equity)

        return {
            "run_id": run_id,
            "mode": mode,
            "tournament_id": tournament_id,
            "model_id": model_id,
            "model_label": model_label,
            "model_color": model_color,
            "model_provider": model_provider,
            "dataset": ds_info,
            "config": cfg_dict,
            "candles": candles,
            "indicators": ind_serialized,
            "trades": list(trades),
            "decisions": list(decisions),
            "equity_curve": ec,
            "metrics": metrics,
            "status": status,
            "progress": {
                "trades_done": len(trades),
                "target": target_trades,
                "bars_processed": _current_bar[0],
                "bars_total": n,
                "decisions_made": len(decisions),
            },
            "error": None,
            "created_at": now_created,
            "duration_sec": round(time.time() - started, 2),
        }

    async def _maybe_partial(force: bool = False) -> None:
        """Persist a partial record, throttled to ~1s unless force=True."""
        now = time.time()
        if force or (now - _last_partial_time[0]) >= 1.0:
            _last_partial_time[0] = now
            await hooks.on_partial(_build_record("running"))

    # Emit initial partial so frontend sees candles immediately
    await hooks.on_partial(_build_record("running"))

    _first_decision = True  # always persist immediately on first decision

    while i < n - 1 and len(trades) < target_trades:
        # Skip if inside a trade
        if in_trade and i <= trade_exit_bar:
            # update floating equity while in trade
            if open_trade_ref is not None:
                t = open_trade_ref
                curr_c = candles[i]["c"]
                if t["direction"] == "long":
                    unrealized = (curr_c - t["entry_price"]) / (t["entry_price"] - t["stop_loss"]) * t["risk_amount"]
                else:
                    unrealized = (t["entry_price"] - curr_c) / (t["stop_loss"] - t["entry_price"]) * t["risk_amount"]
                bar_floating[i] = equity + unrealized
                bar_trade_id[i] = t["id"]
            i += 1
            continue

        # No longer in trade (or never was)
        in_trade = False
        open_trade_ref = None

        # Determine if this is a decision point
        is_decision = False
        if decision_trigger == "cadence":
            is_decision = (i - WARMUP_BARS) % decision_cadence == 0
        else:  # signals
            is_decision = _has_signal(candles, ind_arrays, i)
            # Fallback: force decision every force_every bars
            if not is_decision and (i - last_decision_bar) >= force_every:
                is_decision = True

        if not is_decision:
            i += 1
            continue

        last_decision_bar = i
        _current_bar[0] = i

        # Build context
        ctx = build_context(
            candles=candles,
            ind_arrays=ind_arrays,
            i=i,
            symbol="UNKNOWN",
            timeframe="1h",
            equity=equity,
            starting_equity=starting_equity,
            risk_per_trade_pct=risk_pct,
            open_position=None,
            trades_taken=len(trades),
            target_trades=target_trades,
            lookback=lookback,
            decision_trigger=decision_trigger,
        )

        # Ask adapter
        try:
            decision = await adapter.decide(ctx)
        except Exception as e:
            # record as flat, continue
            decisions.append({
                "bar": i,
                "time": candles[i]["t"],
                "action": "flat",
                "rationale": f"adapter error: {e}",
                "confidence": 0.0,
                "trade_id": None,
            })
            await hooks.on_decision(i, None)
            force = _first_decision
            _first_decision = False
            await _maybe_partial(force=force)
            i += 1
            continue

        action = getattr(decision, "action", "flat")
        confidence = float(getattr(decision, "confidence", 0.5))
        rationale = str(getattr(decision, "rationale", ""))
        entry_price_req = getattr(decision, "entry", None)
        stop_loss = getattr(decision, "stop_loss", None)
        take_profit = getattr(decision, "take_profit", None)

        if action == "flat" or (not allow_short and action == "short"):
            decisions.append({
                "bar": i,
                "time": candles[i]["t"],
                "action": "flat",
                "rationale": rationale,
                "confidence": confidence,
                "trade_id": None,
            })
            await hooks.on_decision(i, decision)
            force = _first_decision
            _first_decision = False
            await _maybe_partial(force=force)
            i += 1
            continue

        # --- Forward simulation ---
        # Entry fills at next bar
        next_bar = i + 1
        nb = candles[next_bar]

        # Determine entry price
        if entry_price_req is not None:
            ep = float(entry_price_req)
            if nb["l"] <= ep <= nb["h"]:
                entry_price = ep
            else:
                entry_price = float(nb["o"])
        else:
            entry_price = float(nb["o"])

        sl = float(stop_loss)
        tp = float(take_profit)
        direction = action  # "long" or "short"

        # Validate geometry
        valid = True
        if direction == "long":
            if not (sl < entry_price < tp):
                valid = False
        else:
            if not (tp < entry_price < sl):
                valid = False

        if not valid:
            decisions.append({
                "bar": i,
                "time": candles[i]["t"],
                "action": "flat",
                "rationale": f"invalid geometry coerced to flat",
                "confidence": confidence,
                "trade_id": None,
            })
            await hooks.on_decision(i, decision)
            force = _first_decision
            _first_decision = False
            await _maybe_partial(force=force)
            i += 1
            continue

        risk_amount = equity * risk_pct / 100

        # Forward sim from next_bar
        exit_bar = next_bar
        exit_price = entry_price
        outcome = "eod"
        mae = 0.0  # in R
        mfe = 0.0  # in R

        sl_dist = abs(entry_price - sl)

        for fwd in range(next_bar, min(next_bar + max_trade_bars, n)):
            bar = candles[fwd]
            high = float(bar["h"])
            low = float(bar["l"])

            # Floating R for MAE/MFE
            if direction == "long":
                adverse_r = (low - entry_price) / sl_dist if sl_dist > 0 else 0.0
                favor_r = (high - entry_price) / sl_dist if sl_dist > 0 else 0.0
            else:
                adverse_r = (entry_price - high) / sl_dist if sl_dist > 0 else 0.0
                favor_r = (entry_price - low) / sl_dist if sl_dist > 0 else 0.0

            mae = min(mae, adverse_r)
            mfe = max(mfe, favor_r)

            # SL check first (SL before TP on same bar)
            if direction == "long":
                if low <= sl:
                    exit_bar = fwd
                    exit_price = sl
                    outcome = "sl"
                    break
                elif high >= tp:
                    exit_bar = fwd
                    exit_price = tp
                    outcome = "tp"
                    break
            else:
                if high >= sl:
                    exit_bar = fwd
                    exit_price = sl
                    outcome = "sl"
                    break
                elif low <= tp:
                    exit_bar = fwd
                    exit_price = tp
                    outcome = "tp"
                    break
        else:
            # max_trade_bars reached
            if next_bar + max_trade_bars >= n:
                outcome = "eod"
                exit_bar = n - 1
            else:
                outcome = "timeout"
                exit_bar = next_bar + max_trade_bars
            exit_price = float(candles[exit_bar]["c"])

        # Compute R multiple
        if direction == "long":
            r_multiple = (exit_price - entry_price) / sl_dist if sl_dist > 0 else 0.0
        else:
            r_multiple = (entry_price - exit_price) / sl_dist if sl_dist > 0 else 0.0

        pnl_abs = r_multiple * risk_amount
        equity_before = equity
        equity += pnl_abs
        pnl_pct = pnl_abs / equity_before * 100

        trade_id = len(trades) + 1
        trade = {
            "id": trade_id,
            "model_id": model_id,
            "direction": direction,
            "decision_index": i,
            "entry_bar": next_bar,
            "entry_time": candles[next_bar]["t"],
            "entry_price": round(entry_price, 8),
            "stop_loss": round(sl, 8),
            "take_profit": round(tp, 8),
            "exit_bar": exit_bar,
            "exit_time": candles[exit_bar]["t"],
            "exit_price": round(exit_price, 8),
            "outcome": outcome,
            "r_multiple": round(r_multiple, 4),
            "risk_amount": round(risk_amount, 2),
            "pnl_abs": round(pnl_abs, 2),
            "pnl_pct": round(pnl_pct, 4),
            "equity_after": round(equity, 2),
            "confidence": round(confidence, 4),
            "rationale": rationale,
            "mae_r": round(mae, 4),
            "mfe_r": round(mfe, 4),
        }
        trades.append(trade)

        # Update realized equity from entry to exit
        for b in range(next_bar, exit_bar + 1):
            bar_trade_id[b] = trade_id
            # floating: mark-to-market
            curr_c = candles[b]["c"]
            if direction == "long":
                unreal = (curr_c - entry_price) / sl_dist * risk_amount if sl_dist > 0 else 0.0
            else:
                unreal = (entry_price - curr_c) / sl_dist * risk_amount if sl_dist > 0 else 0.0
            bar_floating[b] = equity_before + unreal

        # Realized equity steps at exit
        for b in range(exit_bar, n):
            if b >= exit_bar:
                bar_equity[b] = equity  # will be overwritten by later trades
            # We'll build final equity array below

        decisions.append({
            "bar": i,
            "time": candles[i]["t"],
            "action": direction,
            "rationale": rationale,
            "confidence": confidence,
            "trade_id": trade_id,
        })

        _current_bar[0] = exit_bar
        _first_decision = False  # type: ignore[assignment]

        await hooks.on_decision(i, decision)
        await hooks.on_trade(trade)
        await hooks.on_progress(len(trades), target_trades, exit_bar, n)
        await _maybe_partial(force=True)  # always persist immediately on a trade

        in_trade = True
        trade_exit_bar = exit_bar
        open_trade_ref = trade
        i = exit_bar + 1

    # Build final record via helper, override duration and bars_processed to final values
    _current_bar[0] = n - 1
    record = _build_record("complete")
    record["duration_sec"] = round(time.time() - started, 2)
    record["progress"]["bars_processed"] = n
    record["progress"]["decisions_made"] = len(decisions)

    await hooks.on_done(record)
    return record
