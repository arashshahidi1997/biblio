"""Paper summary generation pipeline.

Assembles paper context (BibTeX, docling markdown, GROBID header/references)
and optionally calls an LLM to produce a structured summary.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BiblioConfig

SUMMARY_SECTIONS = (
    "Contribution",
    "Method",
    "Key Findings",
    "Limitations",
    "Relevance",
)

SUMMARY_DIR_REL = Path("bib/derivatives/summaries")

SYSTEM_PROMPT = """\
You are a research paper summarizer. Given the full context of an academic paper \
(metadata, full text excerpt, and extracted references), produce a structured summary \
with exactly these sections:

## Contribution
What is the main contribution of this paper? (2-3 sentences)

## Method
What methodology or approach does the paper use? (2-4 sentences)

## Key Findings
What are the most important results or findings? (bullet list, 3-5 items)

## Limitations
What are the acknowledged or apparent limitations? (bullet list, 2-4 items)

## Relevance
How might this paper be relevant to the current research project? (2-3 sentences)

Be concise and precise. Use technical language appropriate for researchers.\
"""


def summary_out_dir(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / SUMMARY_DIR_REL).resolve()


def summary_path_for_key(cfg: BiblioConfig, citekey: str) -> Path:
    key = citekey.lstrip("@")
    return summary_out_dir(cfg) / f"{key}.md"


def assemble_context(citekey: str, root: Path) -> str:
    """Gather paper_context into a structured prompt input string."""
    from .mcp import paper_context

    ctx = paper_context(citekey, root=root)
    key = ctx["citekey"]

    parts: list[str] = []

    # BibTeX metadata
    bib = ctx.get("bib") or {}
    if bib:
        parts.append("# BibTeX Metadata")
        title = bib.get("title", "Unknown")
        authors = bib.get("authors", [])
        year = bib.get("year", "")
        parts.append(f"**Title:** {title}")
        if authors:
            parts.append(f"**Authors:** {', '.join(authors)}")
        if year:
            parts.append(f"**Year:** {year}")
        for field in ("journal", "booktitle", "doi", "abstract"):
            val = bib.get(field)
            if val:
                parts.append(f"**{field.title()}:** {val}")
        parts.append("")

    # GROBID header
    grobid_header = ctx.get("grobid_header") or {}
    if grobid_header:
        parts.append("# GROBID Header")
        for field in ("title", "abstract", "authors", "year", "doi"):
            val = grobid_header.get(field)
            if val:
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                parts.append(f"**{field.title()}:** {val}")
        parts.append("")

    # Docling full text excerpt
    docling_excerpt = ctx.get("docling_excerpt")
    if docling_excerpt:
        parts.append("# Full Text (excerpt)")
        parts.append(docling_excerpt)
        parts.append("")

    # GROBID references (load from file for full list)
    from .config import default_config_path, load_biblio_config
    from .grobid import grobid_outputs_for_key

    cfg = load_biblio_config(default_config_path(root=root), root=root)
    grobid_out = grobid_outputs_for_key(cfg, key)
    if grobid_out.references_path.exists():
        try:
            refs = json.loads(grobid_out.references_path.read_text(encoding="utf-8"))
            if refs:
                parts.append("# References (GROBID-extracted)")
                for i, ref in enumerate(refs[:30], 1):
                    ref_title = ref.get("title") or "Untitled"
                    ref_authors = ", ".join(ref.get("authors", [])[:3])
                    ref_year = ref.get("year") or ""
                    parts.append(f"{i}. {ref_title} ({ref_authors}, {ref_year})")
                if len(refs) > 30:
                    parts.append(f"... and {len(refs) - 30} more references")
                parts.append("")
        except Exception:
            pass

    # Library metadata
    lib = ctx.get("library") or {}
    if lib:
        parts.append("# Library Status")
        for field in ("status", "tags", "priority"):
            val = lib.get(field)
            if val:
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                parts.append(f"**{field.title()}:** {val}")
        parts.append("")

    return "\n".join(parts)


def _render_summary_md(
    citekey: str,
    summary_text: str,
    model_used: str,
) -> str:
    """Render a summary markdown file with YAML frontmatter."""
    key = citekey.lstrip("@")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        f"citekey: {key}",
        f"date_generated: {now}",
        f"model_used: {model_used}",
        "---",
        "",
        f"# Summary: {key}",
        "",
        summary_text.strip(),
        "",
    ]
    return "\n".join(lines)


def summarize(
    citekey: str,
    root: Path,
    *,
    prompt_only: bool = False,
    force: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Assemble context and optionally call LLM to generate a structured summary.

    Returns a dict with keys: citekey, prompt, summary_path, summary_text, model_used, skipped.
    """
    from .config import default_config_path, load_biblio_config

    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    out_path = summary_path_for_key(cfg, key)

    prompt_text = assemble_context(key, root)

    if prompt_only:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "summary_path": None,
            "summary_text": None,
            "model_used": None,
            "skipped": False,
        }

    # Check existing
    if out_path.exists() and not force:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "summary_path": str(out_path),
            "summary_text": out_path.read_text(encoding="utf-8"),
            "model_used": None,
            "skipped": True,
        }

    # Call LLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "summary_path": None,
            "summary_text": None,
            "model_used": None,
            "skipped": False,
            "error": "ANTHROPIC_API_KEY not set",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "summary_path": None,
            "summary_text": None,
            "model_used": None,
            "skipped": False,
            "error": "anthropic package not installed",
        }

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
    )
    summary_text = message.content[0].text

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_content = _render_summary_md(key, summary_text, model)
    out_path.write_text(md_content, encoding="utf-8")

    return {
        "citekey": key,
        "prompt": prompt_text,
        "summary_path": str(out_path),
        "summary_text": md_content,
        "model_used": model,
        "skipped": False,
    }
