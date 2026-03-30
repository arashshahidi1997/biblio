"""Comparison table generation for multiple papers.

Produces a structured markdown comparison table across configurable dimensions,
with optional prose synthesis via LLM.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import default_config_path, load_biblio_config

COMPARE_DIR_REL = Path("bib/derivatives/comparisons")

DEFAULT_DIMENSIONS = ("method", "dataset", "metrics", "key findings", "limitations")

SYSTEM_PROMPT = """\
You are a research paper comparison assistant. Given context for multiple papers, \
produce a comparison consisting of:

1. A markdown table with columns: Paper (citekey) and one column per dimension.
2. A prose synthesis paragraph (3-5 sentences) highlighting key similarities, \
differences, and complementary strengths.

Dimensions to compare: {dimensions}

Format your response as:

## Comparison Table

| Paper | {dim_headers} |
|-------|{dim_separators}|
(one row per paper)

## Synthesis

(prose paragraph)

Be concise. Use technical language appropriate for researchers.\
"""

DEFAULT_MODEL = "sonnet"


def _compare_dir(root: Path) -> Path:
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    return (cfg.repo_root / COMPARE_DIR_REL).resolve()


def _slug_from_citekeys(citekeys: list[str]) -> str:
    """Deterministic slug from sorted citekeys."""
    sorted_keys = sorted(k.lstrip("@") for k in citekeys)
    joined = "_".join(sorted_keys)
    if len(joined) > 80:
        h = hashlib.md5(joined.encode()).hexdigest()[:8]
        joined = f"{sorted_keys[0]}__{len(sorted_keys)}papers_{h}"
    return joined


def _compare_path(root: Path, citekeys: list[str]) -> Path:
    return _compare_dir(root) / f"{_slug_from_citekeys(citekeys)}.md"


def _assemble_multi_context(citekeys: list[str], root: Path) -> str:
    """Gather paper contexts for all citekeys."""
    from .mcp import paper_context

    parts: list[str] = []
    for ck in citekeys:
        key = ck.lstrip("@")
        ctx = paper_context(key, root=root)
        bib = ctx.get("bib") or {}
        section = [f"## {key}"]
        if bib.get("title"):
            section.append(f"**Title:** {bib['title']}")
        if bib.get("authors"):
            section.append(f"**Authors:** {', '.join(bib['authors'])}")
        if bib.get("year"):
            section.append(f"**Year:** {bib['year']}")
        if bib.get("abstract"):
            section.append(f"**Abstract:** {bib['abstract']}")

        grobid_header = ctx.get("grobid_header") or {}
        if not bib.get("abstract") and grobid_header.get("abstract"):
            section.append(f"**Abstract:** {grobid_header['abstract']}")

        # Include summary if available
        cfg = load_biblio_config(default_config_path(root=root), root=root)
        from .summarize import summary_path_for_key

        summary_path = summary_path_for_key(cfg, key)
        if summary_path.exists():
            text = summary_path.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            section.append(f"**Summary:**\n{text[:1500]}")

        docling_excerpt = ctx.get("docling_excerpt")
        if docling_excerpt:
            section.append(f"**Excerpt:**\n{docling_excerpt[:1000]}")

        parts.append("\n".join(section))

    return "\n\n---\n\n".join(parts)


def _render_comparison_md(
    citekeys: list[str],
    comparison_text: str,
    dimensions: tuple[str, ...] | list[str],
    model_used: str,
) -> str:
    """Render a comparison markdown file with YAML frontmatter."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keys_str = ", ".join(k.lstrip("@") for k in citekeys)
    lines = [
        "---",
        f"citekeys: [{keys_str}]",
        f"dimensions: [{', '.join(dimensions)}]",
        f"date_generated: {now}",
        f"model_used: {model_used}",
        "---",
        "",
        f"# Comparison: {keys_str}",
        "",
        comparison_text.strip(),
        "",
    ]
    return "\n".join(lines)


def compare(
    citekeys: list[str],
    root: Path,
    *,
    dimensions: list[str] | tuple[str, ...] | None = None,
    prompt_only: bool = False,
    force: bool = False,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Compare multiple papers across specified dimensions.

    Returns dict with keys: citekeys, prompt, comparison_text, comparison_path, skipped.
    """
    keys = [ck.lstrip("@") for ck in citekeys]
    if len(keys) < 2:
        return {"error": "Need at least 2 citekeys to compare", "citekeys": keys}

    dims = tuple(dimensions) if dimensions else DEFAULT_DIMENSIONS
    out_path = _compare_path(root, keys)

    # Check cache
    if not force and not prompt_only and out_path.exists():
        return {
            "citekeys": keys,
            "prompt": None,
            "comparison_text": out_path.read_text(encoding="utf-8"),
            "comparison_path": str(out_path),
            "skipped": True,
        }

    context_text = _assemble_multi_context(keys, root)
    dim_headers = " | ".join(dims)
    dim_separators = " | ".join("---" for _ in dims)
    system = SYSTEM_PROMPT.format(
        dimensions=", ".join(dims),
        dim_headers=dim_headers,
        dim_separators=dim_separators,
    )
    prompt_text = f"Compare these {len(keys)} papers:\n\n{context_text}"

    if prompt_only:
        return {
            "citekeys": keys,
            "prompt": prompt_text,
            "system_prompt": system,
            "comparison_text": None,
            "comparison_path": None,
            "skipped": False,
        }

    # Call LLM
    from .llm import call_llm

    result = call_llm(system=system, prompt=prompt_text, model=model, max_tokens=3000)
    if result["error"]:
        return {
            "citekeys": keys,
            "prompt": prompt_text,
            "comparison_text": None,
            "comparison_path": None,
            "skipped": False,
            "error": result["error"],
        }
    comparison_text = result["text"]

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_content = _render_comparison_md(keys, comparison_text, dims, model)
    out_path.write_text(md_content, encoding="utf-8")

    return {
        "citekeys": keys,
        "prompt": prompt_text,
        "comparison_text": md_content,
        "comparison_path": str(out_path),
        "skipped": False,
        "model_used": model,
    }
