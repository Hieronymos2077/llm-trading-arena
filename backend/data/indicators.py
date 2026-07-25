"""
Vectorized indicator computation over a full candle series.
Pure numpy/pandas, no external TA library dependency.

compute_indicators(df) -> dict of lists aligned to candles, None during warmup.
Also exposes raw float arrays for the engine via _arrays.

Indicators computed (all 26 from TradingView Technical Ratings panel):
  Oscillators: RSI(14), Stochastic %K/%D(14,3,3), CCI(20), ADX(14), AO, Momentum(10),
               MACD(12,26,9), Williams %R(14)
  Moving Averages: EMA/SMA for periods 10, 20, 30, 50, 100, 200
  Ichimoku (9, 26, 52, 26): Tenkan, Kijun, Senkou A, Senkou B
  Pivot Points (Classic, rolling 20-bar): P, R1, R2, S1, S2
  Volatility: ATR(14), Bollinger Bands(20, 2), Swing High/Low(20)
"""

from __future__ import annotations
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ema(series: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(series), np.nan)
    k = 2.0 / (period + 1)
    result[period - 1] = np.mean(series[:period])
    for i in range(period, len(series)):
        result[i] = series[i] * k + result[i - 1] * (1 - k)
    return result


def _sma(series: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(series).rolling(period, min_periods=period).mean().to_numpy()


def _rsi(series: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(series, prepend=np.nan)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.full(len(series), np.nan)
    avg_loss = np.full(len(series), np.nan)
    avg_gain[period] = np.mean(gain[1: period + 1])
    avg_loss[period] = np.mean(loss[1: period + 1])
    for i in range(period + 1, len(series)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = np.where(avg_loss == 0, np.inf, avg_gain / avg_loss)
    rsi = 100 - 100 / (1 + rs)
    rsi[:period] = np.nan
    return rsi


def _stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                k_period: int = 14, d_period: int = 3, smooth: int = 3):
    sh = pd.Series(high)
    sl = pd.Series(low)
    sc = pd.Series(close)
    lowest = sl.rolling(k_period, min_periods=k_period).min()
    highest = sh.rolling(k_period, min_periods=k_period).max()
    rng = (highest - lowest).replace(0, np.nan)
    raw_k = 100 * (sc - lowest) / rng
    stoch_k = raw_k.rolling(smooth, min_periods=smooth).mean()
    stoch_d = stoch_k.rolling(d_period, min_periods=d_period).mean()
    return stoch_k.to_numpy(), stoch_d.to_numpy()


def _cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20) -> np.ndarray:
    tp = pd.Series((high + low + close) / 3)
    sma = tp.rolling(period, min_periods=period).mean()
    mad = tp.rolling(period, min_periods=period).apply(
        lambda x: np.mean(np.abs(x - x.mean())), raw=True
    )
    cci = (tp - sma) / (0.015 * mad.replace(0, np.nan))
    return cci.to_numpy()


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14):
    n = len(close)
    tr = np.zeros(n)
    pdm = np.zeros(n)
    ndm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        pdm[i] = up if (up > dn and up > 0) else 0
        ndm[i] = dn if (dn > up and dn > 0) else 0

    atr_w = np.full(n, np.nan)
    s_pdm = np.full(n, np.nan)
    s_ndm = np.full(n, np.nan)
    if n <= period:
        return np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)

    atr_w[period] = np.sum(tr[1: period + 1])
    s_pdm[period] = np.sum(pdm[1: period + 1])
    s_ndm[period] = np.sum(ndm[1: period + 1])
    for i in range(period + 1, n):
        atr_w[i] = atr_w[i - 1] - atr_w[i - 1] / period + tr[i]
        s_pdm[i] = s_pdm[i - 1] - s_pdm[i - 1] / period + pdm[i]
        s_ndm[i] = s_ndm[i - 1] - s_ndm[i - 1] / period + ndm[i]

    pdi = np.full(n, np.nan)
    ndi = np.full(n, np.nan)
    dx = np.full(n, np.nan)
    adx = np.full(n, np.nan)

    for i in range(period, n):
        if atr_w[i] > 0:
            pdi[i] = 100 * s_pdm[i] / atr_w[i]
            ndi[i] = 100 * s_ndm[i] / atr_w[i]
        s = pdi[i] + ndi[i]
        if not np.isnan(s) and s > 0:
            dx[i] = 100 * abs(pdi[i] - ndi[i]) / s

    first_adx = 2 * period - 1
    if n > first_adx:
        window = dx[period: first_adx + 1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            adx[first_adx] = np.mean(valid)
        for i in range(first_adx + 1, n):
            if not np.isnan(dx[i]) and not np.isnan(adx[i - 1]):
                adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx, pdi, ndi


def _ao(high: np.ndarray, low: np.ndarray) -> np.ndarray:
    mid = pd.Series((high + low) / 2)
    return (mid.rolling(5, min_periods=5).mean() - mid.rolling(34, min_periods=34).mean()).to_numpy()


def _momentum(series: np.ndarray, period: int = 10) -> np.ndarray:
    return pd.Series(series).diff(period).to_numpy()


def _williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    sh = pd.Series(high)
    sl = pd.Series(low)
    sc = pd.Series(close)
    highest = sh.rolling(period, min_periods=period).max()
    lowest = sl.rolling(period, min_periods=period).min()
    wr = -100 * (highest - sc) / (highest - lowest).replace(0, np.nan)
    return wr.to_numpy()


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    atr = np.full(len(close), np.nan)
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, len(close)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _macd(series: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    macd_sig = _ema(np.where(np.isnan(macd_line), 0, macd_line), signal)
    macd_line[:slow - 1] = np.nan
    macd_sig[: slow + signal - 2] = np.nan
    return macd_line, macd_sig, macd_line - macd_sig


def _bollinger(series: np.ndarray, period: int = 20, num_std: float = 2.0):
    mid = np.full(len(series), np.nan)
    upper = np.full(len(series), np.nan)
    lower = np.full(len(series), np.nan)
    for i in range(period - 1, len(series)):
        window = series[i - period + 1: i + 1]
        m = np.mean(window)
        s = np.std(window, ddof=0)
        mid[i] = m
        upper[i] = m + num_std * s
        lower[i] = m - num_std * s
    return upper, mid, lower


def _ichimoku(high: np.ndarray, low: np.ndarray,
              tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    sh = pd.Series(high)
    sl = pd.Series(low)
    ten = (sh.rolling(tenkan, min_periods=tenkan).max() +
           sl.rolling(tenkan, min_periods=tenkan).min()) / 2
    kij = (sh.rolling(kijun, min_periods=kijun).max() +
           sl.rolling(kijun, min_periods=kijun).min()) / 2
    spa = (ten + kij) / 2
    spb = (sh.rolling(senkou_b, min_periods=senkou_b).max() +
           sl.rolling(senkou_b, min_periods=senkou_b).min()) / 2
    return ten.to_numpy(), kij.to_numpy(), spa.to_numpy(), spb.to_numpy()


def _pivot_points(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 20):
    sh = pd.Series(high)
    sl = pd.Series(low)
    sc = pd.Series(close)
    h = sh.shift(1).rolling(period, min_periods=period).max()
    l = sl.shift(1).rolling(period, min_periods=period).min()
    c = sc.shift(1)
    p = (h + l + c) / 3
    r1 = 2 * p - l
    r2 = p + (h - l)
    s1 = 2 * p - h
    s2 = p - (h - l)
    return p.to_numpy(), r1.to_numpy(), r2.to_numpy(), s1.to_numpy(), s2.to_numpy()


def _recent_swing(high: np.ndarray, low: np.ndarray, lookback: int = 20):
    n = len(high)
    swing_h = np.full(n, np.nan)
    swing_l = np.full(n, np.nan)
    for i in range(lookback - 1, n):
        window_h = high[max(0, i - lookback + 1): i]
        window_l = low[max(0, i - lookback + 1): i]
        if len(window_h) > 0:
            swing_h[i] = np.max(window_h)
            swing_l[i] = np.min(window_l)
    return swing_h, swing_l


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_indicators(df: pd.DataFrame) -> dict:
    """
    Compute all 26 indicators over the full OHLCV DataFrame.
    Returns a dict where each key maps to a list aligned to df rows (None during warmup).
    Also includes '_arrays' key with raw numpy arrays for engine slicing.
    """
    c = df["c"].to_numpy(dtype=float)
    h = df["h"].to_numpy(dtype=float)
    lo = df["l"].to_numpy(dtype=float)

    # EMAs
    ema10 = _ema(c, 10)
    ema20 = _ema(c, 20)
    ema30 = _ema(c, 30)
    ema50 = _ema(c, 50)
    ema100 = _ema(c, 100)
    ema200 = _ema(c, 200)

    # SMAs
    sma10 = _sma(c, 10)
    sma20 = _sma(c, 20)
    sma30 = _sma(c, 30)
    sma50 = _sma(c, 50)
    sma100 = _sma(c, 100)
    sma200 = _sma(c, 200)

    # Oscillators
    rsi14 = _rsi(c, 14)
    stoch_k, stoch_d = _stochastic(h, lo, c, 14, 3, 3)
    cci20 = _cci(h, lo, c, 20)
    adx14, plus_di, minus_di = _adx(h, lo, c, 14)
    ao = _ao(h, lo)
    momentum10 = _momentum(c, 10)
    williams_r14 = _williams_r(h, lo, c, 14)
    macd_line, macd_signal, macd_hist = _macd(c)

    # Volatility
    atr14 = _atr(h, lo, c, 14)
    bb_upper, bb_mid, bb_lower = _bollinger(c, 20)

    # Ichimoku
    ichimoku_tenkan, ichimoku_kijun, ichimoku_senkou_a, ichimoku_senkou_b = _ichimoku(h, lo)

    # Pivot Points
    pivot_p, pivot_r1, pivot_r2, pivot_s1, pivot_s2 = _pivot_points(h, lo, c)

    # Swing
    recent_swing_high, recent_swing_low = _recent_swing(h, lo, 20)

    def _to_list(arr: np.ndarray) -> list:
        return [None if np.isnan(v) else round(float(v), 6) for v in arr]

    arrays = {
        "ema10": ema10, "ema20": ema20, "ema30": ema30,
        "ema50": ema50, "ema100": ema100, "ema200": ema200,
        "sma10": sma10, "sma20": sma20, "sma30": sma30,
        "sma50": sma50, "sma100": sma100, "sma200": sma200,
        "rsi14": rsi14,
        "stoch_k": stoch_k, "stoch_d": stoch_d,
        "cci20": cci20,
        "adx14": adx14, "plus_di": plus_di, "minus_di": minus_di,
        "ao": ao,
        "momentum10": momentum10,
        "williams_r14": williams_r14,
        "macd": macd_line, "macd_signal": macd_signal, "macd_hist": macd_hist,
        "atr14": atr14,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
        "ichimoku_tenkan": ichimoku_tenkan, "ichimoku_kijun": ichimoku_kijun,
        "ichimoku_senkou_a": ichimoku_senkou_a, "ichimoku_senkou_b": ichimoku_senkou_b,
        "pivot_p": pivot_p, "pivot_r1": pivot_r1, "pivot_r2": pivot_r2,
        "pivot_s1": pivot_s1, "pivot_s2": pivot_s2,
        "recent_swing_high": recent_swing_high, "recent_swing_low": recent_swing_low,
    }

    result: dict = {k: _to_list(v) for k, v in arrays.items()}
    result["_arrays"] = arrays
    return result


def get_indicator_snapshot(ind_arrays: dict, i: int, tail: int = 30) -> dict:
    """
    Build the full indicator_snapshot for DecisionContext at bar index i.
    All 26 indicator values are included so the AI has a complete technical picture.
    """
    def _val(key: str) -> float | None:
        arr = ind_arrays.get(key)
        if arr is None:
            return None
        v = arr[i]
        return None if np.isnan(v) else round(float(v), 6)

    def _tail(key: str, n: int) -> list:
        arr = ind_arrays.get(key)
        if arr is None:
            return []
        start = max(0, i - n + 1)
        return [None if np.isnan(x) else round(float(x), 6) for x in arr[start: i + 1]]

    return {
        # Moving Averages
        "ema10": _val("ema10"),
        "ema20": _val("ema20"),
        "ema30": _val("ema30"),
        "ema50": _val("ema50"),
        "ema100": _val("ema100"),
        "ema200": _val("ema200"),
        "sma10": _val("sma10"),
        "sma20": _val("sma20"),
        "sma30": _val("sma30"),
        "sma50": _val("sma50"),
        "sma100": _val("sma100"),
        "sma200": _val("sma200"),
        # Oscillators
        "rsi14": _val("rsi14"),
        "stoch_k": _val("stoch_k"),
        "stoch_d": _val("stoch_d"),
        "cci20": _val("cci20"),
        "adx14": _val("adx14"),
        "plus_di": _val("plus_di"),
        "minus_di": _val("minus_di"),
        "ao": _val("ao"),
        "momentum10": _val("momentum10"),
        "williams_r14": _val("williams_r14"),
        "macd": _val("macd"),
        "macd_signal": _val("macd_signal"),
        "macd_hist": _val("macd_hist"),
        # Volatility / Bands
        "atr14": _val("atr14"),
        "bb_upper": _val("bb_upper"),
        "bb_mid": _val("bb_mid"),
        "bb_lower": _val("bb_lower"),
        # Ichimoku
        "ichimoku_tenkan": _val("ichimoku_tenkan"),
        "ichimoku_kijun": _val("ichimoku_kijun"),
        "ichimoku_senkou_a": _val("ichimoku_senkou_a"),
        "ichimoku_senkou_b": _val("ichimoku_senkou_b"),
        # Pivot Points (Classic, rolling 20-bar)
        "pivot_p": _val("pivot_p"),
        "pivot_r1": _val("pivot_r1"),
        "pivot_r2": _val("pivot_r2"),
        "pivot_s1": _val("pivot_s1"),
        "pivot_s2": _val("pivot_s2"),
        # Swing structure
        "recent_swing_high": _val("recent_swing_high"),
        "recent_swing_low": _val("recent_swing_low"),
        # Short series for trend context
        "ema20_series": _tail("ema20", tail),
        "rsi14_series": _tail("rsi14", tail),
    }
