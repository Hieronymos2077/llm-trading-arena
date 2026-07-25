"""
Data providers: Binance / MT5 / CSV -> unified OHLCV DataFrame.

DataFrame columns: t (UTC datetime64), o, h, l, c, v (float64)
Rows: ascending by time, deduped.
"""

from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import requests

from backend.config import BINANCE_BASE_URL
from backend.store import load_dataset

if TYPE_CHECKING:
    from backend.schemas import DatasetSpec, Candle

# ---------------------------------------------------------------------------
# MT5 guard
# ---------------------------------------------------------------------------

_mt5_available: bool | None = None  # cached


def mt5_available() -> bool:
    global _mt5_available
    if _mt5_available is not None:
        return _mt5_available
    try:
        import MetaTrader5 as mt5  # noqa: F401
        ok = mt5.initialize()
        mt5.shutdown()
        _mt5_available = ok
    except Exception:
        _mt5_available = False
    return _mt5_available


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------

_BINANCE_TF_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}

_TOP_USDT_PAIRS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "TRXUSDT", "MATICUSDT",
    "LTCUSDT", "BCHUSDT", "ETCUSDT", "XLMUSDT", "ATOMUSDT", "NEARUSDT",
    "ALGOUSDT", "FTMUSDT", "VETUSDT", "ICPUSDT", "FILUSDT", "SANDUSDT",
    "MANAUSDT", "AXSUSDT", "SHIBUSDT", "UNIUSDT", "AAVEUSDT", "GRTUSDT",
    "MKRUSDT", "COMPUSDT", "YFIUSDT", "SNXUSDT", "CRVUSDT", "1INCHUSDT",
    "ENJUSDT", "CHZUSDT", "HBARUSDT", "OPUSDT",
]


def get_binance_symbols() -> list[str]:
    try:
        r = requests.get(
            f"{BINANCE_BASE_URL}/api/v3/ticker/24hr",
            timeout=10,
            params={"type": "MINI"},
        )
        r.raise_for_status()
        data = r.json()
        usdt = sorted(
            [x["symbol"] for x in data if x["symbol"].endswith("USDT")],
            key=lambda s: float(
                next((x["quoteVolume"] for x in data if x["symbol"] == s), 0)
            ),
            reverse=True,
        )
        return usdt[:40] if usdt else _TOP_USDT_PAIRS
    except Exception:
        return _TOP_USDT_PAIRS


def _load_binance(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Paginate Binance klines REST (max 1000/req) to reach limit."""
    tf = _BINANCE_TF_MAP.get(interval, interval)
    rows: list[list] = []
    end_time: int | None = None

    while len(rows) < limit:
        fetch = min(1000, limit - len(rows))
        params: dict = {"symbol": symbol, "interval": tf, "limit": fetch}
        if end_time is not None:
            params["endTime"] = end_time

        r = requests.get(
            f"{BINANCE_BASE_URL}/api/v3/klines", params=params, timeout=20
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        rows = batch + rows  # prepend older data
        end_time = int(batch[0][0]) - 1  # go further back

        if len(batch) < fetch:
            break
        time.sleep(0.05)  # gentle rate limit

    if not rows:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])

    df = pd.DataFrame(rows, columns=[
        "open_time", "o", "h", "l", "c", "v",
        "close_time", "qv", "n", "tbbv", "tbqv", "ignore"
    ])
    df["t"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
    df = df[["t", "o", "h", "l", "c", "v"]].copy()
    for col in ["o", "h", "l", "c", "v"]:
        df[col] = df[col].astype(float)
    df = df.drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return df.tail(limit).reset_index(drop=True)


# ---------------------------------------------------------------------------
# MT5
# ---------------------------------------------------------------------------

_MT5_TF_MAP = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 16385, "4h": 16388, "1d": 16408,
}


def _load_mt5(symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
    import MetaTrader5 as mt5  # guarded
    if not mt5.initialize():
        raise RuntimeError("MT5 terminal not available")

    tf_id = _MT5_TF_MAP.get(timeframe, _MT5_TF_MAP.get(timeframe.lower(), 16385))
    rates = mt5.copy_rates_from_pos(symbol, tf_id, 0, limit)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])

    df = pd.DataFrame(rates)
    df["t"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "tick_volume": "v"})
    df = df[["t", "o", "h", "l", "c", "v"]].drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# CSV dataset
# ---------------------------------------------------------------------------

def _load_csv_dataset(dataset_id: str, limit: int | None = None) -> pd.DataFrame:
    data = load_dataset(dataset_id)
    if data is None:
        raise ValueError(f"Dataset {dataset_id} not found")
    candles = data.get("candles", [])
    if not candles:
        raise ValueError(f"Dataset {dataset_id} has no candles")
    df = pd.DataFrame(candles)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    for col in ["o", "h", "l", "c", "v"]:
        df[col] = df[col].astype(float)
    df = df[["t", "o", "h", "l", "c", "v"]].drop_duplicates("t").sort_values("t").reset_index(drop=True)
    if limit and len(df) > limit:
        # Pick the contiguous window with the highest summed true-range (most volatile segment)
        # True range = max(h-l, |h-prev_c|, |l-prev_c|)
        prev_c = df["c"].shift(1).fillna(df["o"])
        tr = pd.concat([
            df["h"] - df["l"],
            (df["h"] - prev_c).abs(),
            (df["l"] - prev_c).abs(),
        ], axis=1).max(axis=1)
        # Sliding window sum of true-range; argmax gives the start index
        roll_sum = tr.rolling(limit).sum()
        best_end = int(roll_sum.idxmax())
        best_start = max(0, best_end - limit + 1)
        df = df.iloc[best_start: best_end + 1].reset_index(drop=True)
    return df


def parse_csv_upload(content: bytes, symbol: str, timeframe: str) -> pd.DataFrame:
    """Parse uploaded CSV bytes -> clean OHLCV DataFrame."""
    import io
    df = pd.read_csv(io.BytesIO(content))
    df.columns = [c.strip().lower() for c in df.columns]

    # Map time column
    time_col = next((c for c in df.columns if c in {"time", "date", "datetime", "timestamp"}), None)
    if time_col is None:
        raise ValueError("CSV must have a time/date/datetime column")
    df["t"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    df = df.dropna(subset=["t"])

    # Map OHLCV
    col_map = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}
    for src, dst in col_map.items():
        if src in df.columns:
            df[dst] = pd.to_numeric(df[src], errors="coerce")
    df = df[["t", "o", "h", "l", "c", "v"]].dropna()
    return df.drop_duplicates("t").sort_values("t").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Unified loader
# ---------------------------------------------------------------------------

def load_ohlcv(spec) -> pd.DataFrame:
    """
    Load OHLCV data from spec.source.
    Returns DataFrame with columns [t, o, h, l, c, v], UTC, ascending, deduped.
    """
    source = getattr(spec, "source", "binance")
    symbol = getattr(spec, "symbol", "BTCUSDT")
    timeframe = getattr(spec, "timeframe", "1h")
    limit = getattr(spec, "limit", 1500)

    if source == "binance":
        return _load_binance(symbol, timeframe, limit)
    elif source == "mt5":
        if not mt5_available():
            raise RuntimeError("MT5 is not available on this machine")
        return _load_mt5(symbol, timeframe, limit)
    elif source == "csv":
        did = getattr(spec, "csv_dataset_id", None)
        if not did:
            raise ValueError("csv_dataset_id required for csv source")
        return _load_csv_dataset(did, limit)
    else:
        raise ValueError(f"Unknown source: {source}")


# ---------------------------------------------------------------------------
# Helper: DataFrame -> list[Candle dict]
# ---------------------------------------------------------------------------

def df_to_candles(df: pd.DataFrame) -> list[dict]:
    """Convert OHLCV DataFrame to list of Candle-shaped dicts."""
    candles = []
    for _, row in df.iterrows():
        t = row["t"]
        if hasattr(t, "isoformat"):
            ts = t.isoformat().replace("+00:00", "Z")
        else:
            ts = str(t)
        candles.append({
            "t": ts,
            "o": round(float(row["o"]), 8),
            "h": round(float(row["h"]), 8),
            "l": round(float(row["l"]), 8),
            "c": round(float(row["c"]), 8),
            "v": round(float(row["v"]), 5),
        })
    return candles
