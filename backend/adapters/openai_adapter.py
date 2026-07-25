"""
openai_adapter.py, OpenAI adapter (async SDK, JSON output).
Contract: ARENA_SPEC.md §5.3
"""
from __future__ import annotations

import os
from typing import Optional

from .base import Decision, ModelAdapter, build_prompt, parse_decision

try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False


class OpenAIAdapter(ModelAdapter):
    """Call OpenAI models via async SDK with JSON mode."""

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY")) and _OPENAI_AVAILABLE

    async def decide(self, context: dict) -> Decision:
        if not self.available():
            return Decision(
                action="flat",
                parse_error="openai_unavailable: key missing or sdk not installed",
            )

        system_prompt, user_prompt = build_prompt(context)

        try:
            client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
            response = await client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            return Decision(
                action="flat",
                parse_error=f"openai_api_error: {exc}",
                rationale=str(exc)[:200],
            )

        return parse_decision(raw, context)


GPT5 = OpenAIAdapter(
    id="gpt-5",
    label="GPT-5",
    provider="openai",
    color="#10A37F",
    model_name="gpt-5",
)

GPT5_MINI = OpenAIAdapter(
    id="gpt-5-mini",
    label="GPT-5 Mini",
    provider="openai",
    color="#5FD0B0",
    model_name="gpt-5-mini",
)
