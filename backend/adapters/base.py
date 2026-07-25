"""
base.py, Decision dataclass, ModelAdapter ABC, build_prompt, parse_decision.
Contract: adapters/base.py per ARENA_SPEC.md §5.1
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Decision dataclass  (§3.2 + parse_error)
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    action: str                         # "long" | "short" | "flat"
    entry: Optional[float] = None       # null => market at next bar open
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.5
    rationale: str = ""
    indicators_used: list = field(default_factory=list)
    parse_error: Optional[str] = None   # set when we had to coerce/fallback


# ---------------------------------------------------------------------------
# ModelAdapter ABC  (§5.1)
# ---------------------------------------------------------------------------

class ModelAdapter(ABC):
    id: str
    label: str
    provider: str
    color: str
    model_name: str

    def __init__(self, id: str, label: str, provider: str, color: str, model_name: str):
        self.id = id
        self.label = label
        self.provider = provider
        self.color = color
        self.model_name = model_name

    @abstractmethod
    def available(self) -> bool:
        """Return True if this adapter can make calls (key present / CLI found)."""

    @abstractmethod
    async def decide(self, context: dict) -> Decision:
        """Given a DecisionContext dict, return a Decision. Never raises."""


# ---------------------------------------------------------------------------
# build_prompt  (§5.1)
# ---------------------------------------------------------------------------

_DECISION_SCHEMA = """{
  "action": "long|short|flat",
  "entry": <number or null>,
  "stop_loss": <number, required if not flat>,
  "take_profit": <number, required if not flat>,
  "confidence": <0.0-1.0>,
  "rationale": "<one-sentence reason>",
  "indicators_used": ["ema20", ...]
}"""

_SYSTEM_PROMPT = f"""You are a professional discretionary trader making ONE trade decision based solely on historical price data and indicators provided. You have NO knowledge of future bars.

OUTPUT FORMAT: Respond with ONLY a single valid JSON object, no prose, no fences, no explanation before or after. The exact schema:
{_DECISION_SCHEMA}

Rules:
- action "long": stop_loss MUST be below entry, take_profit MUST be above entry.
- action "short": take_profit MUST be below entry, stop_loss MUST be above entry.
- action "flat": no trade; omit or null all price fields.
- entry null means fill at next bar open (market order).
- confidence: your conviction 0.0-1.0.
- Keep rationale under 30 words.
- Never use a dash of any kind in the rationale. Use commas, colons or periods.
- Respond ONLY with the JSON object. Nothing else.

Trading bias: You are called ONLY when a genuine setup signal fires (EMA cross, RSI extreme, MACD cross, BB touch, swing breakout, or engulfing candle). When the signal is present and the setup is reasonably clear, take the trade, long or short as appropriate. Reserve "flat" strictly for genuinely ambiguous or conflicting signals. Do NOT default to flat out of excessive caution; you are expected to trade when given a real setup. Place SL just beyond the nearest structural support/resistance (1 to 2× ATR), and TP at 2 to 3× the SL distance for a positive R:R."""


def build_prompt(context: dict) -> tuple[str, str]:
    """Build (system, user) prompt from a DecisionContext dict. Target < 2k tokens."""
    symbol = context.get("symbol", "?")
    timeframe = context.get("timeframe", "?")
    now_time = context.get("now_time", "?")
    bar_index = context.get("bar_index", "?")
    trades_taken = context.get("trades_taken", 0)
    target_trades = context.get("target_trades", 50)

    candles = context.get("lookback_candles", [])
    # Last ~40 candles as compact table
    tail = candles[-40:] if len(candles) > 40 else candles
    rows = []
    for i, c in enumerate(tail):
        t = c.get("t", "")[:16].replace("T", " ")  # trim seconds
        rows.append(
            f"{i:3d}  {t}  {c.get('o',0):.2f}  {c.get('h',0):.2f}  "
            f"{c.get('l',0):.2f}  {c.get('c',0):.2f}  {c.get('v',0):.1f}"
        )
    candle_table = "\n".join(rows)

    snap = context.get("indicator_snapshot", {})
    # Only scalar indicators (skip *_series arrays)
    snap_lines = []
    for k, v in snap.items():
        if not k.endswith("_series") and isinstance(v, (int, float)) and v is not None:
            snap_lines.append(f"  {k}: {v:.4g}")
    indicators_text = "\n".join(snap_lines) if snap_lines else "  (none)"

    account = context.get("account", {})
    equity = account.get("equity", 10000)
    starting = account.get("starting_equity", 10000)
    risk_pct = account.get("risk_per_trade_pct", 1.0)
    open_pos = account.get("open_position", None)
    open_text = f"  open_position: {json.dumps(open_pos)}" if open_pos else "  open_position: none"

    user = f"""Symbol: {symbol}  Timeframe: {timeframe}
Current bar: #{bar_index}  Time: {now_time}
Trades taken: {trades_taken} / {target_trades} target
Account: equity={equity:.2f}, starting={starting:.2f}, risk_per_trade={risk_pct}%
{open_text}

--- CANDLES (idx  time  open  high  low  close  vol) ---
idx  time              open      high      low       close     vol
{candle_table}

--- INDICATORS (latest values) ---
{indicators_text}

You cannot see future bars. Decide NOW. Output ONLY the JSON object."""

    return _SYSTEM_PROMPT, user


# ---------------------------------------------------------------------------
# parse_decision  (§5.1 + §3.2 validation)
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict | None:
    """Robustly extract the first {...} JSON block from arbitrary text."""
    if not raw:
        return None

    # Strip ```json fences if present
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()

    # Find first { ... } block (handle nested braces)
    start = cleaned.find("{")
    if start == -1:
        return None

    depth = 0
    end = -1
    for i, ch in enumerate(cleaned[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        # Attempt partial, try to close it
        candidate = cleaned[start:] + "}"
        try:
            return json.loads(candidate)
        except Exception:
            return None

    try:
        return json.loads(cleaned[start:end])
    except json.JSONDecodeError:
        # Try with relaxed whitespace cleanup
        blob = cleaned[start:end]
        blob = re.sub(r",\s*}", "}", blob)   # trailing commas
        blob = re.sub(r",\s*]", "]", blob)
        try:
            return json.loads(blob)
        except Exception:
            return None


def _flat(reason: str) -> Decision:
    return Decision(action="flat", parse_error=reason)


def _strip_dashes(text: str) -> str:
    """Models emit em and en dashes; the UI style forbids them. Rewrite to commas."""
    for dash in ("—", "–", "−"):
        text = text.replace(f" {dash} ", ", ").replace(dash, ", ")
    return text.replace(" ,", ",").replace(",,", ",").strip()


def parse_decision(raw_text: str, context: dict) -> Decision:
    """
    Robustly extract a Decision from raw LLM text. Validates geometry per §3.2.
    Always returns a Decision; never raises.
    """
    try:
        data = _extract_json(raw_text)
    except Exception as exc:
        return _flat(f"json_extract_failed: {exc}")

    if data is None:
        return _flat(f"no_json_found in: {raw_text[:120]!r}")

    # Extract action
    action = str(data.get("action", "flat")).lower().strip()
    if action not in ("long", "short", "flat"):
        return _flat(f"invalid_action={action!r}")

    # Extract optional fields
    def _f(key) -> Optional[float]:
        v = data.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    entry = _f("entry")
    sl = _f("stop_loss")
    tp = _f("take_profit")
    confidence = _f("confidence")
    if confidence is None:
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    rationale = _strip_dashes(str(data.get("rationale", ""))[:500])
    indicators_used = data.get("indicators_used", [])
    if not isinstance(indicators_used, list):
        indicators_used = []

    if action == "flat":
        return Decision(
            action="flat",
            entry=None, stop_loss=None, take_profit=None,
            confidence=confidence, rationale=rationale,
            indicators_used=indicators_used,
            parse_error=None,
        )

    # For long/short we need SL and TP
    if sl is None or tp is None:
        return _flat(f"missing_sl_or_tp for action={action}")

    # Determine entry_ref: entry if given, else latest close
    if entry is not None:
        entry_ref = entry
    else:
        candles = context.get("lookback_candles", [])
        if candles:
            entry_ref = float(candles[-1].get("c", 0))
        else:
            return _flat("no_entry_and_no_candles_for_ref")

    # Geometry validation per §3.2
    if action == "long":
        # sl < entry_ref < tp
        if not (sl < entry_ref < tp):
            return _flat(
                f"long_geometry_invalid: sl={sl} entry_ref={entry_ref:.4f} tp={tp} "
                f"(need sl<entry_ref<tp)"
            )
    elif action == "short":
        # tp < entry_ref < sl
        if not (tp < entry_ref < sl):
            return _flat(
                f"short_geometry_invalid: tp={tp} entry_ref={entry_ref:.4f} sl={sl} "
                f"(need tp<entry_ref<sl)"
            )

    return Decision(
        action=action,
        entry=entry,
        stop_loss=sl,
        take_profit=tp,
        confidence=confidence,
        rationale=rationale,
        indicators_used=indicators_used,
        parse_error=None,
    )
