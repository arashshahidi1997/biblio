"""Shared LLM invocation via Claude CLI.

Uses ``claude -p`` (print mode) to run prompts through the user's Claude
subscription (Pro/Max) rather than burning API tokens.  Falls back to
the Anthropic Python SDK when ``BIBLIO_LLM_BACKEND=api`` is set (e.g.
for CI or headless servers with an API key).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


# ── configuration ───────────────────────────────────────────────────────
# BIBLIO_LLM_BACKEND: "claude" (default) | "api"
# When "claude", uses `claude -p --model <model>` via subprocess.
# When "api", uses the anthropic Python SDK with ANTHROPIC_API_KEY.

DEFAULT_BACKEND = "claude"
DEFAULT_MODEL = "sonnet"  # claude CLI model name


def _backend() -> str:
    return os.environ.get("BIBLIO_LLM_BACKEND", DEFAULT_BACKEND).lower()


def _find_claude_cli() -> str | None:
    return shutil.which("claude")


def call_llm(
    *,
    system: str,
    prompt: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
) -> dict[str, str | None]:
    """Call an LLM and return the response text.

    Returns ``{"text": "...", "error": None}`` on success,
    ``{"text": None, "error": "..."}`` on failure.
    """
    backend = _backend()
    if backend == "api":
        return _call_api(system=system, prompt=prompt, model=model, max_tokens=max_tokens)
    return _call_claude_cli(system=system, prompt=prompt, model=model, max_tokens=max_tokens)


# ── Claude CLI backend ──────────────────────────────────────────────────

def _call_claude_cli(
    *,
    system: str,
    prompt: str,
    model: str,
    max_tokens: int,
) -> dict[str, str | None]:
    claude_bin = _find_claude_cli()
    if not claude_bin:
        return {"text": None, "error": "claude CLI not found on PATH"}

    full_prompt = f"{system}\n\n---\n\n{prompt}"

    cmd = [claude_bin, "-p", "--model", model]

    try:
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"text": None, "error": "claude CLI timed out after 300s"}
    except FileNotFoundError:
        return {"text": None, "error": "claude CLI not found"}

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return {"text": None, "error": f"claude CLI failed (exit {result.returncode}): {stderr}"}

    text = (result.stdout or "").strip()
    if not text:
        return {"text": None, "error": "claude CLI returned empty output"}

    return {"text": text, "error": None}


# ── Anthropic API backend (fallback) ────────────────────────────────────

# Map short CLI model names to full API model IDs
_API_MODEL_MAP = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}


def _call_api(
    *,
    system: str,
    prompt: str,
    model: str,
    max_tokens: int,
) -> dict[str, str | None]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"text": None, "error": "ANTHROPIC_API_KEY not set (needed for api backend)"}

    try:
        import anthropic
    except ImportError:
        return {"text": None, "error": "anthropic package not installed (needed for api backend)"}

    api_model = _API_MODEL_MAP.get(model, model)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=api_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        return {"text": text, "error": None}
    except Exception as exc:
        return {"text": None, "error": str(exc)}
