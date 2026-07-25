"""
claude_cli.py, Claude via local CLI subscription (no API key).
Contract: ARENA_SPEC.md §5.2
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import subprocess
from typing import Optional

from .base import Decision, ModelAdapter, build_prompt, parse_decision

CLI_TIMEOUT_SECONDS = 240


def _find_claude_binary() -> Optional[str]:
    """Locate the claude.exe binary. Returns path or None."""
    # 1. Explicit env override
    env_path = os.environ.get("CLAUDE_CLI_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. Glob for VS Code extension binary (version-agnostic)
    pattern = os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"
    )
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[-1]  # latest version

    # 3. PATH fallback
    import shutil
    found = shutil.which("claude")
    if found:
        return found

    return None


def _strip_claude_env() -> dict:
    """Return os.environ copy with CLAUDECODE* and CLAUDE_CODE* vars removed."""
    return {
        k: v for k, v in os.environ.items()
        if not k.startswith("CLAUDECODE") and not k.startswith("CLAUDE_CODE")
    }


def _run_claude_cli(model_name: str, system_prompt: str, user_prompt: str) -> str:
    """Run one non-interactive `claude -p` turn and return the assistant text.

    Uses `--output-format json`, which wraps the answer in an envelope whose
    `result` field holds the model's text.
    """
    binary = _find_claude_binary()
    if not binary:
        raise RuntimeError(
            "claude CLI not found. Install Claude Code or set CLAUDE_CLI_PATH."
        )
    try:
        proc = subprocess.run(
            [
                binary, "-p", user_prompt,
                "--model", model_name,
                "--append-system-prompt", system_prompt,
                "--output-format", "json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLI_TIMEOUT_SECONDS,
            env=_strip_claude_env(),
        )
    except subprocess.TimeoutExpired:
        # The default message embeds the whole argv, which means the local binary
        # path and the entire prompt. Keep it short so it is safe to store.
        raise RuntimeError(f"claude CLI timed out after {CLI_TIMEOUT_SECONDS}s") from None
    except OSError as exc:
        raise RuntimeError(f"could not run the claude CLI: {exc.strerror}") from None
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude reported an error: {str(envelope.get('result'))[:300]}")
    return str(envelope.get("result", ""))


class ClaudeCliAdapter(ModelAdapter):
    """Call Claude models via the local `claude -p` CLI subscription."""

    def available(self) -> bool:
        return _find_claude_binary() is not None

    async def decide(self, context: dict) -> Decision:
        system_prompt, user_prompt = build_prompt(context)
        try:
            assistant_text = await asyncio.to_thread(
                _run_claude_cli, self.model_name, system_prompt, user_prompt
            )
        except Exception as exc:
            return Decision(
                action="flat",
                parse_error=f"subscription_cli_error: {str(exc)[:200]}",
                rationale=str(exc)[:200],
            )

        return parse_decision(assistant_text, context)


# ---------------------------------------------------------------------------
# Concrete adapter instances for each Claude model
# ---------------------------------------------------------------------------

CLAUDE_OPUS = ClaudeCliAdapter(
    id="claude-opus",
    label="Claude Opus 4.8",
    provider="claude",
    color="#D97757",
    model_name="claude-opus-4-8",
)

CLAUDE_SONNET = ClaudeCliAdapter(
    id="claude-sonnet",
    label="Claude Sonnet 4.6",
    provider="claude",
    color="#C15F3C",
    model_name="claude-sonnet-4-6",
)

CLAUDE_HAIKU = ClaudeCliAdapter(
    id="claude-haiku",
    label="Claude Haiku 4.5",
    provider="claude",
    color="#E8A87C",
    model_name="claude-haiku-4-5-20251001",
)
