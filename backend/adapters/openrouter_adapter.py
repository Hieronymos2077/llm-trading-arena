"""
openrouter_adapter.py, OpenRouter adapter (OpenAI-compatible, many models).
Contract: ARENA_SPEC.md §5.5
"""
from __future__ import annotations

import os

from .base import Decision, ModelAdapter, build_prompt, parse_decision

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterAdapter(ModelAdapter):
    """Call OpenRouter-hosted models via the OpenAI-compatible API."""

    def available(self) -> bool:
        return bool(os.environ.get("OPENROUTER_API_KEY")) and _OPENAI_AVAILABLE

    async def decide(self, context: dict) -> Decision:
        if not self.available():
            return Decision(
                action="flat",
                parse_error="openrouter_unavailable: key missing or openai sdk not installed",
            )

        system_prompt, user_prompt = build_prompt(context)

        try:
            client = AsyncOpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"],
                base_url=OPENROUTER_BASE_URL,
            )
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0.3,
                extra_headers={
                    "HTTP-Referer": "https://llm-trading-arena.local",
                    "X-Title": "LLM Trading Arena",
                },
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            return Decision(
                action="flat",
                parse_error=f"openrouter_api_error: {exc}",
                rationale=str(exc)[:200],
            )

        return parse_decision(raw, context)


DEEPSEEK = OpenRouterAdapter(
    id="deepseek",
    label="DeepSeek R2",
    provider="openrouter",
    color="#9B6DFF",
    model_name="deepseek/deepseek-r2",
)

LLAMA = OpenRouterAdapter(
    id="llama",
    label="Llama 4 Maverick",
    provider="openrouter",
    color="#9333EA",
    model_name="meta-llama/llama-4-maverick",
)

GROK = OpenRouterAdapter(
    id="grok",
    label="Grok 3",
    provider="openrouter",
    color="#E5E7EB",
    model_name="x-ai/grok-3",
)

MISTRAL = OpenRouterAdapter(
    id="mistral",
    label="Mistral Large",
    provider="openrouter",
    color="#FF7000",
    model_name="mistralai/mistral-large",
)

QWEN = OpenRouterAdapter(
    id="qwen",
    label="Qwen 2.5 72B",
    provider="openrouter",
    color="#A855F7",
    model_name="qwen/qwen-2.5-72b-instruct",
)

NEX_N2_PRO = OpenRouterAdapter(
    id="nex-n2-pro",
    label="Nex N2 Pro",
    provider="openrouter",
    color="#22D3EE",
    model_name="area/nex-n2-pro",
)

NEX_N2_MINI = OpenRouterAdapter(
    id="nex-n2-mini",
    label="Nex N2 Mini",
    provider="openrouter",
    color="#67E8F9",
    model_name="area/nex-n2-mini",
)
