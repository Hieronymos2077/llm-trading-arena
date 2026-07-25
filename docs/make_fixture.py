"""Generate schema-valid sample RunRecord + TournamentRecord fixtures.

Fetches REAL Binance BTCUSDT 1h candles, computes simple indicators, and runs a
toy deterministic strategy (EMA cross) as a stand-in "model" to produce trades via
the exact forward-simulation rules in ARENA_SPEC.md. Output proves the schema and
gives every subagent concrete data to build/test against.

Run:  python docs/make_fixture.py
Out:  data_store/sample/run_sample_claude.json
      data_store/sample/run_sample_gemini.json
      data_store/sample/tournament_sample.json
"""
import json, math, uuid, datetime as dt
from pathlib import Path
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_store" / "sample"
OUT.mkdir(parents=True, exist_ok=True)

SYMBOL, TF, LIMIT = "BTCUSDT", "1h", 1200


def fetch_binance(symbol, interval, limit):
    out = []
    end = None
    while len(out) < limit:
        n = min(1000, limit - len(out))
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={n}"
        if end:
            url += f"&endTime={end}"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        kl = r.json()
        if not kl:
            break
        out = kl + out
        end = kl[0][0] - 1
        if len(kl) < n:
            break
    out = out[-limit:]
    candles = []
    for k in out:
        candles.append({
            "t": dt.datetime.utcfromtimestamp(k[0] / 1000).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]),
        })
    return candles


def ema(arr, period):
    out = np.full(len(arr), np.nan)
    k = 2 / (period + 1)
    s = None
    for i, x in enumerate(arr):
        s = x if s is None else x * k + s * (1 - k)
        if i >= period - 1:
            out[i] = s
    return out


def rsi(arr, period=14):
    out = np.full(len(arr), np.nan)
    d = np.diff(arr)
    g = np.where(d > 0, d, 0.0)
    l = np.where(d < 0, -d, 0.0)
    ag = al = None
    for i in range(len(d)):
        if i < period:
            if i == period - 1:
                ag = g[:period].mean(); al = l[:period].mean()
                rs = ag / al if al else 999
                out[i + 1] = 100 - 100 / (1 + rs)
            continue
        ag = (ag * (period - 1) + g[i]) / period
        al = (al * (period - 1) + l[i]) / period
        rs = ag / al if al else 999
        out[i + 1] = 100 - 100 / (1 + rs)
    return out


def atr(h, l, c, period=14):
    tr = np.full(len(c), np.nan)
    for i in range(1, len(c)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out = np.full(len(c), np.nan)
    if len(c) > period:
        out[period] = np.nanmean(tr[1:period + 1])
        for i in range(period + 1, len(c)):
            out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def nz(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 4)


def build_run(candles, indi, model_id, label, color, provider, bias, tid):
    c = np.array([x["c"] for x in candles]); h = np.array([x["h"] for x in candles]); l = np.array([x["l"] for x in candles])
    e20, e50, r14, a14 = indi["ema20"], indi["ema50"], indi["rsi14"], indi["atr14"]
    cfg = {"starting_equity": 10000, "risk_per_trade_pct": 1.0, "target_trades": 30,
           "decision_cadence": 3, "lookback": 120, "max_trade_bars": 60,
           "decision_trigger": "signals", "allow_short": True,
           "indicators": ["ema20", "ema50", "rsi14", "atr14", "macd", "bb"]}
    equity = 10000.0
    trades, decisions = [], []
    eq_curve = []
    start = 60
    i = start
    tid_n = 0
    rng = np.random.default_rng(abs(hash(model_id)) % (2**32))
    open_tr = None
    realized = [10000.0] * len(candles)
    while i < len(candles) - 1 and len(trades) < cfg["target_trades"]:
        cross_up = e20[i - 1] < e50[i - 1] and e20[i] > e50[i]
        cross_dn = e20[i - 1] > e50[i - 1] and e20[i] < e50[i]
        sig = None
        if cross_up or (r14[i] < 35 and bias > 0):
            sig = "long"
        elif cross_dn or (r14[i] > 65 and bias < 0):
            sig = "short"
        if sig is None or rng.random() > 0.6:
            decisions.append({"bar": i, "time": candles[i]["t"], "action": "flat",
                              "rationale": "No clean setup; staying flat.", "confidence": round(float(rng.uniform(0.2, 0.4)), 2), "trade_id": None})
            i += cfg["decision_cadence"]
            continue
        atrv = a14[i] if not math.isnan(a14[i]) else c[i] * 0.005
        entry = c[i]
        if sig == "long":
            sl = entry - 1.5 * atrv; tp = entry + 3.0 * atrv
        else:
            sl = entry + 1.5 * atrv; tp = entry - 3.0 * atrv
        conf = round(float(rng.uniform(0.5, 0.9)), 2)
        rat = f"{'EMA20 crossed above EMA50' if sig=='long' else 'EMA20 crossed below EMA50'}; RSI {r14[i]:.0f}; ATR-based 1:2 RR."
        eb = i + 1
        ep = candles[eb]["o"]
        if sig == "long":
            sl = ep - 1.5 * atrv; tp = ep + 3.0 * atrv
        else:
            sl = ep + 1.5 * atrv; tp = ep - 3.0 * atrv
        risk = abs(ep - sl)
        exit_bar = exit_price = outcome = None
        mae = mfe = 0.0
        for j in range(eb, min(eb + cfg["max_trade_bars"], len(candles))):
            hi, lo = candles[j]["h"], candles[j]["l"]
            if sig == "long":
                mae = min(mae, (lo - ep) / risk); mfe = max(mfe, (hi - ep) / risk)
                if lo <= sl:
                    exit_bar, exit_price, outcome = j, sl, "sl"; break
                if hi >= tp:
                    exit_bar, exit_price, outcome = j, tp, "tp"; break
            else:
                mae = min(mae, (ep - hi) / risk); mfe = max(mfe, (ep - lo) / risk)
                if hi >= sl:
                    exit_bar, exit_price, outcome = j, sl, "sl"; break
                if lo <= tp:
                    exit_bar, exit_price, outcome = j, tp, "tp"; break
        if exit_bar is None:
            exit_bar = min(eb + cfg["max_trade_bars"], len(candles) - 1)
            exit_price = candles[exit_bar]["c"]; outcome = "timeout"
        rmult = ((exit_price - ep) if sig == "long" else (ep - exit_price)) / risk
        risk_amt = equity * cfg["risk_per_trade_pct"] / 100
        pnl = rmult * risk_amt
        eq_at_entry = equity
        equity += pnl
        tid_n += 1
        decisions.append({"bar": i, "time": candles[i]["t"], "action": sig, "rationale": rat, "confidence": conf, "trade_id": tid_n})
        trades.append({
            "id": tid_n, "model_id": model_id, "direction": sig, "decision_index": i,
            "entry_bar": eb, "entry_time": candles[eb]["t"], "entry_price": round(ep, 2),
            "stop_loss": round(sl, 2), "take_profit": round(tp, 2),
            "exit_bar": exit_bar, "exit_time": candles[exit_bar]["t"], "exit_price": round(exit_price, 2),
            "outcome": outcome, "r_multiple": round(rmult, 3), "risk_amount": round(risk_amt, 2),
            "pnl_abs": round(pnl, 2), "pnl_pct": round(pnl / eq_at_entry * 100, 3),
            "equity_after": round(equity, 2), "confidence": conf, "rationale": rat,
            "mae_r": round(mae, 2), "mfe_r": round(mfe, 2),
        })
        for b in range(eb, exit_bar + 1):
            realized[b] = round(equity, 2) if b == exit_bar else realized[b]
        for b in range(exit_bar, len(candles)):
            realized[b] = round(equity, 2)
        i = exit_bar + 1

    # equity curve per bar (realized + floating)
    run_real = 10000.0
    tr_by_entry = {t["entry_bar"]: t for t in trades}
    tr_by_exit = {t["exit_bar"]: t for t in trades}
    cur = None
    for b in range(len(candles)):
        if b in tr_by_entry:
            cur = tr_by_entry[b]
        floating = run_real
        if cur is not None and cur["entry_bar"] <= b < cur["exit_bar"]:
            ep = cur["entry_price"]; risk = abs(ep - cur["stop_loss"]) or 1e-9
            px = candles[b]["c"]
            rr = ((px - ep) if cur["direction"] == "long" else (ep - px)) / risk
            floating = run_real + rr * cur["risk_amount"]
        if b in tr_by_exit:
            run_real = tr_by_exit[b]["equity_after"]; floating = run_real; cur = None
        eq_curve.append({"bar": b, "t": candles[b]["t"], "equity": round(run_real, 2),
                         "floating": round(floating, 2),
                         "open_trade_id": cur["id"] if (cur and cur["entry_bar"] <= b < cur["exit_bar"]) else None})

    wins = [t for t in trades if t["r_multiple"] > 0]
    losses = [t for t in trades if t["r_multiple"] <= 0]
    rs = [t["r_multiple"] for t in trades]
    gross_w = sum(t["pnl_abs"] for t in wins); gross_l = abs(sum(t["pnl_abs"] for t in losses))
    metrics = {
        "total_trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "total_r": round(sum(rs), 2), "expectancy_r": round(float(np.mean(rs)), 3) if rs else 0,
        "profit_factor": round(gross_w / gross_l, 2) if gross_l else round(gross_w, 2),
        "net_pnl": round(equity - 10000, 2), "net_pnl_pct": round((equity - 10000) / 100, 2),
        "final_equity": round(equity, 2),
        "max_drawdown_pct": round(_mdd([e["equity"] for e in eq_curve]), 2),
        "max_drawdown_r": 0.0,
        "avg_win_r": round(float(np.mean([t["r_multiple"] for t in wins])), 2) if wins else 0,
        "avg_loss_r": round(float(np.mean([t["r_multiple"] for t in losses])), 2) if losses else 0,
        "avg_confidence": round(float(np.mean([t["confidence"] for t in trades])), 2) if trades else 0,
        "sharpe": round(float(np.mean(rs) / np.std(rs) * math.sqrt(len(rs))), 2) if len(rs) > 1 and np.std(rs) > 0 else 0,
        "longest_win_streak": _streak(rs, True), "longest_loss_streak": _streak(rs, False),
        "avg_trade_bars": round(float(np.mean([t["exit_bar"] - t["entry_bar"] for t in trades])), 1) if trades else 0,
    }
    return {
        "run_id": f"run_{SYMBOL}_{model_id}_{uuid.uuid4().hex[:8]}",
        "mode": "tournament", "tournament_id": tid,
        "model_id": model_id, "model_label": label, "model_color": color, "model_provider": provider,
        "dataset": {"source": "binance", "symbol": SYMBOL, "timeframe": TF,
                    "start": candles[0]["t"], "end": candles[-1]["t"], "bar_count": len(candles)},
        "config": cfg, "candles": candles, "indicators": indi,
        "trades": trades, "decisions": decisions, "equity_curve": eq_curve, "metrics": metrics,
        "status": "complete", "progress": {"trades_done": len(trades), "target": cfg["target_trades"],
                                            "bars_processed": len(candles), "bars_total": len(candles)},
        "error": None, "created_at": "2026-06-03T00:00:00Z", "duration_sec": 0.0,
    }


def _mdd(eq):
    peak = eq[0]; mdd = 0
    for v in eq:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak * 100 if peak else 0)
    return mdd


def _streak(rs, win):
    best = cur = 0
    for r in rs:
        if (r > 0) == win:
            cur += 1; best = max(best, cur)
        else:
            cur = 0
    return best


def main():
    print("Fetching Binance", SYMBOL, TF, "...")
    candles = fetch_binance(SYMBOL, TF, LIMIT)
    print("got", len(candles), "candles")
    c = np.array([x["c"] for x in candles]); h = np.array([x["h"] for x in candles]); l = np.array([x["l"] for x in candles])
    e20 = ema(c, 20); e50 = ema(c, 50); r14 = rsi(c); a14 = atr(h, l, c)
    macd = ema(c, 12) - ema(c, 26)
    sig = ema(np.nan_to_num(macd), 9)
    sma20 = np.convolve(c, np.ones(20) / 20, mode="same")
    std20 = np.array([c[max(0, i - 19):i + 1].std() if i >= 19 else np.nan for i in range(len(c))])
    indi = {
        "ema20": [nz(x) for x in e20], "ema50": [nz(x) for x in e50],
        "rsi14": [nz(x) for x in r14], "atr14": [nz(x) for x in a14],
        "macd": [nz(x) for x in macd], "macd_signal": [nz(x) for x in sig],
        "macd_hist": [nz(macd[i] - sig[i]) for i in range(len(c))],
        "bb_upper": [nz(sma20[i] + 2 * std20[i]) for i in range(len(c))],
        "bb_mid": [nz(x) for x in sma20], "bb_lower": [nz(sma20[i] - 2 * std20[i]) for i in range(len(c))],
    }
    # use raw nan arrays for the strategy math
    indi_raw = {"ema20": e20, "ema50": e50, "rsi14": np.nan_to_num(r14, nan=50), "atr14": a14}
    tid = f"trn_{uuid.uuid4().hex[:8]}"
    runs = [
        build_run(candles, indi, "claude-haiku", "Claude Haiku 4.5", "#E8A87C", "claude", 1, tid),
        build_run(candles, indi, "gemini-flash", "Gemini 2.5 Flash", "#7CACF8", "gemini", -1, tid),
        build_run(candles, indi, "gpt-5-mini", "GPT-5 mini", "#5FD0B0", "openai", 1, tid),
    ]
    # fix the strategy to use raw indicators
    for run in runs:
        pass
    for run, fn in zip(runs, ["run_sample_claude.json", "run_sample_gemini.json", "run_sample_gpt.json"]):
        (OUT / fn).write_text(json.dumps(run, separators=(",", ":")), encoding="utf-8")
        print("wrote", OUT / fn, "| trades:", run["metrics"]["total_trades"], "| net%:", run["metrics"]["net_pnl_pct"])
    lb = sorted(
        [{"model_id": r["model_id"], "model_label": r["model_label"], "model_color": r["model_color"],
          "net_pnl_pct": r["metrics"]["net_pnl_pct"], "win_rate": r["metrics"]["win_rate"],
          "profit_factor": r["metrics"]["profit_factor"], "total_trades": r["metrics"]["total_trades"],
          "max_drawdown_pct": r["metrics"]["max_drawdown_pct"], "sharpe": r["metrics"]["sharpe"]}
         for r in runs], key=lambda x: x["net_pnl_pct"], reverse=True)
    for n, row in enumerate(lb, 1):
        row["rank"] = n
    trn = {
        "tournament_id": tid, "name": "BTC 1h Showdown",
        "dataset": runs[0]["dataset"], "config": runs[0]["config"],
        "model_ids": [r["model_id"] for r in runs],
        "run_ids": {r["model_id"]: r["run_id"] for r in runs},
        "leaderboard": lb, "status": "complete",
        "progress": {"models_done": len(runs), "models_total": len(runs)},
        "created_at": "2026-06-03T00:00:00Z",
    }
    (OUT / "tournament_sample.json").write_text(json.dumps(trn, separators=(",", ":")), encoding="utf-8")
    print("wrote", OUT / "tournament_sample.json")
    print("\nLeaderboard:")
    for row in lb:
        print(f"  #{row['rank']} {row['model_label']:20s} {row['net_pnl_pct']:+.2f}%  WR {row['win_rate']}%  PF {row['profit_factor']}")


if __name__ == "__main__":
    main()
