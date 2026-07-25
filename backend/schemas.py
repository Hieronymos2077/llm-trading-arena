"""All pydantic models, the shared contract types."""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Basic building blocks
# ---------------------------------------------------------------------------

class Candle(BaseModel):
    t: str  # ISO 8601 UTC
    o: float
    h: float
    l: float
    c: float
    v: float


class DatasetSpec(BaseModel):
    source: str = "binance"          # "binance" | "mt5" | "csv"
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    limit: int = 1500
    csv_dataset_id: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


class Config(BaseModel):
    starting_equity: float = 10000
    risk_per_trade_pct: float = 1.0
    target_trades: int = 50
    decision_cadence: int = 3
    lookback: int = 120
    max_trade_bars: int = 60
    decision_trigger: str = "signals"   # "signals" | "cadence"
    allow_short: bool = True
    indicators: list[str] = Field(
        default_factory=lambda: ["ema20", "ema50", "rsi14", "atr14", "macd", "bb"]
    )


# ---------------------------------------------------------------------------
# Engine outputs
# ---------------------------------------------------------------------------

class TradeRecord(BaseModel):
    id: int
    model_id: str
    direction: str                      # "long" | "short"
    decision_index: int                 # bar index where decision was made
    entry_bar: int
    entry_time: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_bar: int
    exit_time: str
    exit_price: float
    outcome: str                        # "tp" | "sl" | "timeout" | "eod"
    r_multiple: float
    risk_amount: float
    pnl_abs: float
    pnl_pct: float
    equity_after: float
    confidence: float
    rationale: str
    mae_r: Optional[float] = None
    mfe_r: Optional[float] = None


class EquityPoint(BaseModel):
    bar: int
    t: str
    equity: float
    floating: float
    open_trade_id: Optional[int] = None


class Metrics(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_r: float
    expectancy_r: float
    profit_factor: float
    net_pnl: float
    net_pnl_pct: float
    final_equity: float
    max_drawdown_pct: float
    max_drawdown_r: float
    avg_win_r: float
    avg_loss_r: float
    avg_confidence: float
    sharpe: float
    longest_win_streak: int
    longest_loss_streak: int
    avg_trade_bars: float


class DecisionEntry(BaseModel):
    bar: int
    time: str
    action: str                         # "long" | "short" | "flat"
    rationale: str
    confidence: float
    trade_id: Optional[int] = None


class DatasetInfo(BaseModel):
    source: str
    symbol: str
    timeframe: str
    start: str
    end: str
    bar_count: int


class RunProgress(BaseModel):
    trades_done: int
    target: int
    bars_processed: int
    bars_total: int


class RunRecord(BaseModel):
    run_id: str
    mode: str                           # "solo" | "tournament"
    tournament_id: Optional[str] = None
    model_id: str
    model_label: str
    model_color: str
    model_provider: str
    dataset: DatasetInfo
    config: dict[str, Any]
    candles: list[dict[str, Any]]       # serialised Candle dicts for frontend
    indicators: dict[str, list[Any]]    # aligned to candles, null during warmup
    trades: list[dict[str, Any]]        # serialised TradeRecord dicts
    decisions: list[dict[str, Any]]     # serialised DecisionEntry dicts
    equity_curve: list[dict[str, Any]]  # serialised EquityPoint dicts
    metrics: Optional[dict[str, Any]] = None
    status: str = "queued"              # "queued" | "running" | "complete" | "error"
    progress: dict[str, Any] = Field(
        default_factory=lambda: {"trades_done": 0, "target": 0, "bars_processed": 0, "bars_total": 0}
    )
    error: Optional[str] = None
    created_at: str = ""
    duration_sec: float = 0.0


class LeaderboardEntry(BaseModel):
    rank: int
    model_id: str
    model_label: str
    model_color: str
    net_pnl_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int
    max_drawdown_pct: float
    sharpe: float


class TournamentRecord(BaseModel):
    tournament_id: str
    name: str
    dataset: DatasetInfo
    config: dict[str, Any]
    model_ids: list[str]
    run_ids: dict[str, str]
    leaderboard: list[dict[str, Any]]
    status: str = "queued"
    progress: dict[str, Any] = Field(
        default_factory=lambda: {"models_done": 0, "models_total": 0}
    )
    created_at: str = ""


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class SoloRunRequest(BaseModel):
    model_id: str
    dataset: DatasetSpec
    config: Optional[Config] = None


class TournamentRequest(BaseModel):
    name: Optional[str] = None
    model_ids: list[str]
    dataset: DatasetSpec
    config: Optional[Config] = None


class DataPreviewRequest(BaseModel):
    source: str = "binance"
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    limit: int = 1500
    csv_dataset_id: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
