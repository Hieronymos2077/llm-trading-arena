"""Download 1-minute OHLC candle data from MetaTrader 5 to a CSV file.

Picks the most liquid available symbol from a candidate list, pulls up to N
M1 bars, and writes them to data_store/csv/<symbol>_M1.csv with columns:
time,open,high,low,close,volume  (UTC ISO timestamps).

Run:  python scripts/download_mt5_m1.py [SYMBOL] [BARS]
"""
import sys
from pathlib import Path

import pandas as pd
import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data_store" / "csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

# Preference order, first one that exists in the terminal wins
CANDIDATES = [
    "EURUSD", "XAUUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
    "BTCUSD", "US30", "NAS100", "GER40", "SPX500",
    "EURUSDm", "XAUUSDm", "GBPUSDm",  # micro-account suffixes
]

want_symbol = sys.argv[1] if len(sys.argv) > 1 else None
N = int(sys.argv[2]) if len(sys.argv) > 2 else 100_000

if not mt5.initialize():
    print("MT5 initialize() failed:", mt5.last_error())
    sys.exit(1)

all_syms = [s.name for s in (mt5.symbols_get() or [])]
print(f"Terminal exposes {len(all_syms)} symbols.")

if want_symbol and want_symbol in all_syms:
    symbol = want_symbol
else:
    symbol = next((c for c in CANDIDATES if c in all_syms), None)
    if symbol is None:
        # fallback: any EUR/USD-ish forex pair, else first symbol
        symbol = next((s for s in all_syms if "EUR" in s and "USD" in s),
                      all_syms[0] if all_syms else None)

if symbol is None:
    print("No symbols available from terminal.")
    mt5.shutdown()
    sys.exit(1)

if not mt5.symbol_select(symbol, True):
    print(f"Could not select {symbol}:", mt5.last_error())
    mt5.shutdown()
    sys.exit(1)

print(f"Downloading {N} M1 bars for {symbol} ...")
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, N)
mt5.shutdown()

if rates is None or len(rates) == 0:
    print("No rates returned:", symbol)
    sys.exit(1)

df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
out = df[["time", "open", "high", "low", "close", "tick_volume"]].rename(
    columns={"tick_volume": "volume"}
)

path = CSV_DIR / f"{symbol}_M1.csv"
out.to_csv(path, index=False)
print(f"\nSYMBOL={symbol}  ROWS={len(out)}")
print(f"RANGE: {out['time'].iloc[0]}  ->  {out['time'].iloc[-1]}")
print(f"PATH={path}")
print("\nHEAD:\n" + out.head(3).to_string(index=False))
print("\nTAIL:\n" + out.tail(3).to_string(index=False))
