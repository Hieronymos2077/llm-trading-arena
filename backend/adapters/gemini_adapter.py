"""
gemini_adapter.py, Google Gemini adapter (JSON mode).
Contract: ARENA_SPEC.md §5.4
"""
from __future__ import annotations

import os

from .base import Decision, ModelAdapter, build_prompt, parse_decision

try:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


class GeminiAdapter(ModelAdapter):
    """Call Gemini models via google-generativeai with JSON mime type."""

    def available(self) -> bool:
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        return bool(key) and _GENAI_AVAILABLE

    async def decide(self, context: dict) -> Decision:
        if not self.available():
            return Decision(
                action="flat",
                parse_error="gemini_unavailable: key missing or sdk not installed",
            )

        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        system_prompt, user_prompt = build_prompt(context)

        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    max_output_tokens=512,
                    temperature=0.3,
                ),
            )
            response = await model.generate_content_async(user_prompt)
            raw = response.text or ""
        except Exception as exc:
            return Decision(
                action="flat",
                parse_error=f"gemini_api_error: {exc}",
                rationale=str(exc)[:200],
            )

        return parse_decision(raw, context)


GEMINI_PRO = GeminiAdapter(
    id="gemini-pro",
    label="Gemini 2.5 Pro",
    provider="gemini",
    color="#4285F4",
    model_name="gemini-2.5-pro",
)

GEMINI_FLASH = GeminiAdapter(
    id="gemini-flash",
    label="Gemini 2.5 Flash",
    provider="gemini",
    color="#7CACF8",
    model_name="gemini-2.5-flash",
)
