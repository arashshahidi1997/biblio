"""Citation paragraph drafting.

Uses RAG (indexio) to find relevant passages from indexed papers, then
optionally calls an LLM to draft a paragraph grounding a claim in those sources.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .rag import default_rag_config_path

SYSTEM_PROMPT = """\
You are a scientific writing assistant. Given a claim or section heading and \
a set of relevant passages from academic papers (with citekeys), draft a concise \
paragraph that grounds the claim in the cited sources.

Use {cite_fmt} citation format. Only cite papers whose passages actually support \
the claim. Do not fabricate references — only use citekeys from the provided passages.

Write in formal academic style. Be precise and concise.\
"""

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _extract_citekey_from_source(source_path: str) -> str | None:
    """Extract a citekey from a docling source path like bib/derivatives/docling/Smith_2024_Title/full.md."""
    if not source_path:
        return None
    parts = Path(source_path).parts
    for i, part in enumerate(parts):
        if part == "docling" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _query_rag(root: Path, text: str, max_refs: int) -> list[dict[str, Any]]:
    """Query the RAG index for passages relevant to the given text."""
    rag_cfg_path = default_rag_config_path(root)
    if not rag_cfg_path.exists():
        return []

    try:
        from indexio.query import query_index
    except ImportError:
        return []

    try:
        data = query_index(
            config_path=rag_cfg_path,
            root=root,
            query=text,
            k=max_refs * 2,  # fetch extra, deduplicate by citekey
            corpus="bib",
        )
    except FileNotFoundError:
        return []

    # Deduplicate by citekey, keeping best (first) match per paper
    seen_keys: set[str] = set()
    passages: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        source_path = item.get("source_path") or ""
        citekey = _extract_citekey_from_source(source_path)
        if not citekey or citekey in seen_keys:
            continue
        seen_keys.add(citekey)
        passages.append({
            "citekey": citekey,
            "snippet": item.get("snippet", ""),
            "source_path": source_path,
        })
        if len(passages) >= max_refs:
            break

    return passages


def _format_passages(passages: list[dict[str, Any]]) -> str:
    """Format retrieved passages for the LLM prompt."""
    parts: list[str] = []
    for p in passages:
        parts.append(f"## @{p['citekey']}\n{p['snippet']}")
    return "\n\n---\n\n".join(parts)


def _cite_format_hint(style: str) -> str:
    if style == "pandoc":
        return "[@citekey]"
    return "\\cite{citekey}"


def assemble_cite_prompt(
    text: str,
    passages: list[dict[str, Any]],
    style: str = "latex",
) -> str:
    """Build the user prompt for citation drafting."""
    cite_fmt = _cite_format_hint(style)
    passages_text = _format_passages(passages)
    citekeys = [p["citekey"] for p in passages]
    return (
        f"Claim or section heading: {text}\n\n"
        f"Citation format: {cite_fmt}\n"
        f"Available citekeys: {', '.join(citekeys)}\n\n"
        f"# Retrieved Passages\n\n{passages_text}"
    )


def cite_draft(
    text: str,
    root: Path,
    *,
    style: str = "latex",
    max_refs: int = 5,
    prompt_only: bool = False,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Draft a citation paragraph grounding a claim in indexed papers.

    Returns dict with keys: text, style, passages, prompt, system_prompt,
    draft, model_used, error.
    """
    passages = _query_rag(root, text, max_refs)

    if not passages:
        return {
            "text": text,
            "style": style,
            "passages": [],
            "prompt": None,
            "draft": None,
            "model_used": None,
            "error": "No relevant passages found in the RAG index. Build the index first.",
        }

    cite_fmt = _cite_format_hint(style)
    system = SYSTEM_PROMPT.format(cite_fmt=cite_fmt)
    prompt_text = assemble_cite_prompt(text, passages, style=style)

    if prompt_only:
        return {
            "text": text,
            "style": style,
            "passages": passages,
            "prompt": prompt_text,
            "system_prompt": system,
            "draft": None,
            "model_used": None,
        }

    # Call LLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "text": text,
            "style": style,
            "passages": passages,
            "prompt": prompt_text,
            "draft": None,
            "model_used": None,
            "error": "ANTHROPIC_API_KEY not set",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "text": text,
            "style": style,
            "passages": passages,
            "prompt": prompt_text,
            "draft": None,
            "model_used": None,
            "error": "anthropic package not installed",
        }

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": prompt_text}],
    )
    draft_text = message.content[0].text

    return {
        "text": text,
        "style": style,
        "passages": passages,
        "prompt": prompt_text,
        "draft": draft_text,
        "model_used": model,
    }
