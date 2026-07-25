"""Settings, env loading, paths, default config."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project root = parent of backend/
PROJECT_ROOT = Path(__file__).parent.parent
DATA_STORE = PROJECT_ROOT / "data_store"
RUNS_DIR = DATA_STORE / "runs"
TOURNAMENTS_DIR = DATA_STORE / "tournaments"
DATASETS_DIR = DATA_STORE / "datasets"
SAMPLE_DIR = DATA_STORE / "sample"

for _d in [RUNS_DIR, TOURNAMENTS_DIR, DATASETS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

BACKEND_PORT: int = int(os.getenv("ARENA_BACKEND_PORT", "7077"))
FRONTEND_PORT: int = int(os.getenv("ARENA_FRONTEND_PORT", "7078"))
FRONTEND_ORIGIN: str = f"http://localhost:{FRONTEND_PORT}"

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
CLAUDE_CLI_PATH: str = os.getenv("CLAUDE_CLI_PATH", "")

DEFAULT_CONFIG = {
    "starting_equity": 10000,
    "risk_per_trade_pct": 1.0,
    "target_trades": 50,
    "decision_cadence": 3,
    "lookback": 120,
    "max_trade_bars": 60,
    "decision_trigger": "signals",
    "allow_short": True,
    "indicators": ["ema20", "ema50", "rsi14", "atr14", "macd", "bb"],
}

BINANCE_BASE_URL = "https://api.binance.com"
