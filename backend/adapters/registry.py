"""
registry.py, MODEL_REGISTRY, list_models(), get_adapter().
Contract: ARENA_SPEC.md §5.6

Provider imports are wrapped in try/except so this module ALWAYS imports
successfully even if SDKs are missing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ModelAdapter, Decision

# ---------------------------------------------------------------------------
# Safe provider imports
# ---------------------------------------------------------------------------

try:
    from .claude_cli import CLAUDE_OPUS, CLAUDE_SONNET, CLAUDE_HAIKU
    _claude_ok = True
except Exception:
    _claude_ok = False

try:
    from .openai_adapter import GPT5, GPT5_MINI
    _openai_ok = True
except Exception:
    _openai_ok = False

try:
    from .gemini_adapter import GEMINI_PRO, GEMINI_FLASH
    _gemini_ok = True
except Exception:
    _gemini_ok = False

try:
    from .openrouter_adapter import DEEPSEEK, LLAMA, GROK, MISTRAL, QWEN, NEX_N2_PRO, NEX_N2_MINI
    _openrouter_ok = True
except Exception:
    _openrouter_ok = False


# ---------------------------------------------------------------------------
# MODEL_REGISTRY, ordered list; colors from §5.6
# ---------------------------------------------------------------------------

MODEL_REGISTRY: list[dict] = [
    # Claude (subscription CLI)
    {
        "id": "claude-opus",
        "label": "Claude Opus 4.8",
        "provider": "claude",
        "model_name": "claude-opus-4-8",
        "color": "#D97757",
        "default_in_tournament": False,
    },
    {
        "id": "claude-sonnet",
        "label": "Claude Sonnet 4.6",
        "provider": "claude",
        "model_name": "claude-sonnet-4-6",
        "color": "#C15F3C",
        "default_in_tournament": False,
    },
    {
        "id": "claude-haiku",
        "label": "Claude Haiku 4.5",
        "provider": "claude",
        "model_name": "claude-haiku-4-5-20251001",
        "color": "#E8A87C",
        "default_in_tournament": True,
    },
    # OpenAI
    {
        "id": "gpt-5",
        "label": "GPT-5",
        "provider": "openai",
        "model_name": "gpt-5",
        "color": "#10A37F",
        "default_in_tournament": False,
    },
    {
        "id": "gpt-5-mini",
        "label": "GPT-5 Mini",
        "provider": "openai",
        "model_name": "gpt-5-mini",
        "color": "#5FD0B0",
        "default_in_tournament": True,
    },
    # Gemini
    {
        "id": "gemini-pro",
        "label": "Gemini 2.5 Pro",
        "provider": "gemini",
        "model_name": "gemini-2.5-pro",
        "color": "#4285F4",
        "default_in_tournament": False,
    },
    {
        "id": "gemini-flash",
        "label": "Gemini 2.5 Flash",
        "provider": "gemini",
        "model_name": "gemini-2.5-flash",
        "color": "#7CACF8",
        "default_in_tournament": True,
    },
    # OpenRouter
    {
        "id": "deepseek",
        "label": "DeepSeek R2",
        "provider": "openrouter",
        "model_name": "deepseek/deepseek-r2",
        "color": "#9B6DFF",
        "default_in_tournament": False,
    },
    {
        "id": "llama",
        "label": "Llama 4 Maverick",
        "provider": "openrouter",
        "model_name": "meta-llama/llama-4-maverick",
        "color": "#9333EA",
        "default_in_tournament": False,
    },
    {
        "id": "grok",
        "label": "Grok 3",
        "provider": "openrouter",
        "model_name": "x-ai/grok-3",
        "color": "#E5E7EB",
        "default_in_tournament": False,
    },
    {
        "id": "mistral",
        "label": "Mistral Large",
        "provider": "openrouter",
        "model_name": "mistralai/mistral-large",
        "color": "#FF7000",
        "default_in_tournament": False,
    },
    {
        "id": "qwen",
        "label": "Qwen 2.5 72B",
        "provider": "openrouter",
        "model_name": "qwen/qwen-2.5-72b-instruct",
        "color": "#A855F7",
        "default_in_tournament": False,
    },
    {
        "id": "nex-n2-pro",
        "label": "Nex N2 Pro",
        "provider": "openrouter",
        "model_name": "area/nex-n2-pro",
        "color": "#22D3EE",
        "default_in_tournament": False,
    },
    {
        "id": "nex-n2-mini",
        "label": "Nex N2 Mini",
        "provider": "openrouter",
        "model_name": "area/nex-n2-mini",
        "color": "#67E8F9",
        "default_in_tournament": False,
    },
]


# ---------------------------------------------------------------------------
# Sentinel adapter returned when a provider module failed to import
# ---------------------------------------------------------------------------

class _UnavailableAdapter(ModelAdapter):
    def available(self) -> bool:
        return False

    async def decide(self, context: dict) -> Decision:
        return Decision(
            action="flat",
            parse_error=f"provider_import_failed for model {self.id}",
        )


def _make_unavailable(entry: dict) -> ModelAdapter:
    return _UnavailableAdapter(
        id=entry["id"],
        label=entry["label"],
        provider=entry["provider"],
        color=entry["color"],
        model_name=entry["model_name"],
    )


# ---------------------------------------------------------------------------
# Internal adapter lookup map
# ---------------------------------------------------------------------------

def _build_adapter_map() -> dict[str, ModelAdapter]:
    m: dict[str, ModelAdapter] = {}

    if _claude_ok:
        m["claude-opus"] = CLAUDE_OPUS
        m["claude-sonnet"] = CLAUDE_SONNET
        m["claude-haiku"] = CLAUDE_HAIKU

    if _openai_ok:
        m["gpt-5"] = GPT5
        m["gpt-5-mini"] = GPT5_MINI

    if _gemini_ok:
        m["gemini-pro"] = GEMINI_PRO
        m["gemini-flash"] = GEMINI_FLASH

    if _openrouter_ok:
        m["deepseek"] = DEEPSEEK
        m["llama"] = LLAMA
        m["grok"] = GROK
        m["mistral"] = MISTRAL
        m["qwen"] = QWEN
        m["nex-n2-pro"] = NEX_N2_PRO
        m["nex-n2-mini"] = NEX_N2_MINI

    # Fill in any missing entries with unavailable sentinels
    for entry in MODEL_REGISTRY:
        if entry["id"] not in m:
            m[entry["id"]] = _make_unavailable(entry)

    return m


_ADAPTER_MAP: dict[str, ModelAdapter] = _build_adapter_map()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_models() -> list[dict]:
    """Return MODEL_REGISTRY entries each augmented with 'available' bool."""
    result = []
    for entry in MODEL_REGISTRY:
        adapter = _ADAPTER_MAP.get(entry["id"])
        available = adapter.available() if adapter else False
        result.append({**entry, "available": available})
    return result


def get_adapter(model_id: str) -> ModelAdapter:
    """Return the adapter for model_id. Raises KeyError if unknown."""
    if model_id not in _ADAPTER_MAP:
        raise KeyError(f"Unknown model_id: {model_id!r}. Available: {list(_ADAPTER_MAP)}")
    return _ADAPTER_MAP[model_id]
