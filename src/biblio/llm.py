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
# Short model name for the claude CLI; the API backend maps it below.
# Override with BIBLIO_LLM_MODEL (a short name or a full API model ID).
DEFAULT_MODEL = os.environ.get("BIBLIO_LLM_MODEL", "sonnet")


def _backend() -> str:
    return os.environ.get("BIBLIO_LLM_BACKEND", DEFAULT_BACKEND).lower()


def _claude_candidates() -> list[Path]:
    """Usual install places of the claude CLI that a non-interactive shell may not have on PATH."""
    home = Path.home()
    found = sorted((home / ".nvm" / "versions" / "node").glob("*/bin/claude"), reverse=True)
    return found + [home / ".local" / "bin" / "claude", home / ".claude" / "local" / "claude",
                    Path("/usr/local/bin/claude"), Path("/opt/homebrew/bin/claude")]


def _find_claude_cli() -> str | None:
    """$BIBLIO_CLAUDE_CLI, else PATH, else the usual install places (nvm, ~/.local/bin, ~/.claude/local)."""
    explicit = os.environ.get("BIBLIO_CLAUDE_CLI")
    if explicit:
        return explicit if Path(explicit).is_file() else None
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    return next((str(p) for p in _claude_candidates() if p.is_file() and os.access(p, os.X_OK)), None)


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
        where = os.environ.get("BIBLIO_CLAUDE_CLI") or "PATH and " + ", ".join(
            str(p) for p in _claude_candidates()[-4:])
        return {"text": None, "error": f"claude CLI not found (looked in {where}); "
                                       "set BIBLIO_CLAUDE_CLI to its path"}

    full_prompt = f"{system}\n\n---\n\n{prompt}"

    cmd = [claude_bin, "-p", "--model", model]

    import tempfile
    timeout = int(os.environ.get("BIBLIO_LLM_TIMEOUT", "900"))   # a whole-paper digest can take minutes
    try:
        # a neutral working directory: the CLI must not pick up the current project's settings,
        # CLAUDE.md or trust prompt (it refuses untrusted folders that carry .claude/settings.json)
        with tempfile.TemporaryDirectory(prefix="biblio-llm-") as cwd:
            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
    except subprocess.TimeoutExpired:
        return {"text": None, "error": f"claude CLI timed out after {timeout}s"}
    except FileNotFoundError:
        return {"text": None, "error": "claude CLI not found"}

    if result.returncode != 0:
        # the CLI prints some failures (e.g. an expired login) on stdout, not stderr
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()[:500]
        hint = " (run `claude` once interactively and /login)" if "authenticat" in detail.lower() else ""
        return {"text": None, "error": f"claude CLI failed (exit {result.returncode}): {detail}{hint}"}

    text = (result.stdout or "").strip()
    if not text:
        return {"text": None, "error": "claude CLI returned empty output"}

    return {"text": text, "error": None}


# ── Anthropic API backend (fallback) ────────────────────────────────────

# Map short CLI model names to full API model IDs (current models, 2026-10)
_API_MODEL_MAP = {
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
    "haiku": "claude-haiku-4-5",
    "fable": "claude-fable-5-1",
}

# Models whose safety classifiers can decline a request; for these the call
# opts into server-side fallbacks, which re-run a declined request on the
# model Anthropic recommends for that refusal category.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Thinking is on by default on current models and its tokens count toward
# max_tokens, so callers' small output caps get headroom. The cap is a
# ceiling; only generated tokens are billed.
_MIN_MAX_TOKENS = 16000


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
    request = dict(
        model=api_model,
        max_tokens=max(max_tokens, _MIN_MAX_TOKENS),
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        if api_model in _FALLBACK_MODELS:
            message = client.beta.messages.create(
                **request, betas=[_FALLBACK_BETA], extra_body={"fallbacks": "default"},
            )
        else:
            message = client.messages.create(**request)
    except Exception as exc:
        return {"text": None, "error": str(exc)}

    if getattr(message, "stop_reason", None) == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        return {"text": None, "error": f"model declined the request (refusal: {category or 'unspecified'})"}
    # Responses can start with thinking blocks; take the text blocks.
    text = "".join(
        getattr(block, "text", "") for block in (message.content or [])
        if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        return {"text": None, "error": f"no text in response (stop_reason: {getattr(message, 'stop_reason', None)})"}
    return {"text": text, "error": None}
