"""Presentation generation from paper context.

Assembles paper metadata, summary, and figures from docling output,
then optionally calls an LLM to produce a Marp markdown slide deck.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BiblioConfig, default_config_path, load_biblio_config

SLIDES_DIR_REL = Path("bib/derivatives/slides")

VALID_TEMPLATES = ("journal-club", "conference-talk", "lab-meeting")

TEMPLATE_DIR = Path(__file__).parent / "slide_templates"

SYSTEM_PROMPT = """\
You are a presentation designer for academic papers. Given paper context \
(metadata, summary, figures) and a template specification, produce a complete \
Marp markdown slide deck.

Rules:
- Output ONLY the Marp markdown (no explanation or wrapping)
- Do NOT include Marp frontmatter (it will be prepended automatically)
- Use `---` to separate slides
- For figures, use the exact image paths provided
- Keep bullet points concise
- Use speaker notes as HTML comments (<!-- ... -->) where helpful
- Follow the template structure closely\
"""


def slides_out_dir(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / SLIDES_DIR_REL).resolve()


def slides_path_for_key(cfg: BiblioConfig, citekey: str) -> Path:
    key = citekey.lstrip("@")
    return slides_out_dir(cfg) / f"{key}.md"


def load_template(name: str) -> str:
    """Load a slide template prompt by name."""
    if name not in VALID_TEMPLATES:
        raise ValueError(f"Unknown template: {name!r}. Choose from: {VALID_TEMPLATES}")
    path = TEMPLATE_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Template file not found: {path}")
    return path.read_text(encoding="utf-8")


def extract_figures(citekey: str, cfg: BiblioConfig) -> list[dict[str, Any]]:
    """Extract figure paths and captions from docling JSON output."""
    from .docling import outputs_for_key

    key = citekey.lstrip("@")
    out = outputs_for_key(cfg, key)
    artifacts_dir = out.outdir / f"{key}_artifacts"

    if not artifacts_dir.exists():
        return []

    # Build caption map from docling JSON
    caption_map: dict[str, str] = {}
    if out.json_path.exists():
        try:
            doc = json.loads(out.json_path.read_text(encoding="utf-8"))
            texts = doc.get("texts", [])
            for pic in doc.get("pictures", []):
                uri = (pic.get("image") or {}).get("uri", "")
                stem = Path(uri).name if uri else ""
                captions = pic.get("captions", [])
                if stem and captions:
                    ref = captions[0].get("$ref", "")
                    parts = ref.split("/")
                    if len(parts) == 3 and parts[1] == "texts":
                        idx = int(parts[2])
                        if 0 <= idx < len(texts):
                            caption_map[Path(stem).stem] = texts[idx].get("text", "")
        except Exception:
            pass

    figures = []
    for fpath in sorted(artifacts_dir.iterdir()):
        if fpath.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        # Relative path from slides/ directory to docling artifacts
        rel_path = f"../../derivatives/docling/{key}/{key}_artifacts/{fpath.name}"
        figures.append({
            "filename": fpath.name,
            "rel_path": rel_path,
            "abs_path": str(fpath),
            "caption": caption_map.get(fpath.stem, ""),
        })
    return figures


def assemble_slide_context(citekey: str, root: Path) -> dict[str, Any]:
    """Gather summary, figures, and BibTeX metadata for slide generation.

    Returns a structured dict with keys: citekey, bib, summary, figures, template_context.
    """
    from .mcp import paper_context
    from .summarize import summary_path_for_key

    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)

    # Paper context (bib, docling excerpt, grobid header, library)
    ctx = paper_context(key, root=root)
    summary_text = None
    summary_path = summary_path_for_key(cfg, key)
    if summary_path.exists():
        summary_text = summary_path.read_text(encoding="utf-8")

    # Figures from docling
    figures = extract_figures(key, cfg)

    return {
        "citekey": key,
        "bib": ctx.get("bib") or {},
        "grobid_header": ctx.get("grobid_header"),
        "docling_excerpt": ctx.get("docling_excerpt"),
        "library": ctx.get("library") or {},
        "summary": summary_text,
        "figures": figures,
    }


def _build_marp_frontmatter(bib: dict[str, Any]) -> str:
    """Build Marp YAML frontmatter from BibTeX metadata."""
    title = bib.get("title", "Untitled")
    authors = bib.get("authors", [])
    author_str = ", ".join(authors) if authors else "Unknown"

    lines = [
        "---",
        "marp: true",
        "theme: default",
        "paginate: true",
        f"header: \"{title}\"",
        f"footer: \"{author_str}\"",
        "---",
    ]
    return "\n".join(lines)


def _build_prompt(context: dict[str, Any], template_text: str) -> str:
    """Assemble the full LLM prompt from context and template."""
    parts: list[str] = []

    parts.append(template_text)
    parts.append("")
    parts.append("---")
    parts.append("")

    # Paper metadata
    bib = context.get("bib") or {}
    if bib:
        parts.append("# Paper Metadata")
        parts.append(f"**Title:** {bib.get('title', 'Unknown')}")
        authors = bib.get("authors", [])
        if authors:
            parts.append(f"**Authors:** {', '.join(authors)}")
        for field in ("year", "journal", "booktitle", "doi"):
            val = bib.get(field)
            if val:
                parts.append(f"**{field.title()}:** {val}")
        parts.append("")

    # Summary
    summary = context.get("summary")
    if summary:
        parts.append("# Paper Summary")
        parts.append(summary)
        parts.append("")

    # Docling excerpt (if no summary)
    if not summary:
        excerpt = context.get("docling_excerpt")
        if excerpt:
            parts.append("# Full Text (excerpt)")
            parts.append(excerpt)
            parts.append("")

    # Figures
    figures = context.get("figures") or []
    if figures:
        parts.append("# Available Figures")
        parts.append("Use these exact paths in your markdown image references:")
        parts.append("")
        for i, fig in enumerate(figures, 1):
            caption = fig.get("caption") or "No caption"
            parts.append(f"Figure {i}: `{fig['rel_path']}`")
            parts.append(f"  Caption: {caption}")
        parts.append("")

    return "\n".join(parts)


def generate_slides(
    citekey: str,
    root: Path,
    *,
    template: str = "journal-club",
    prompt_only: bool = False,
    force: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Assemble context and optionally call LLM to generate a Marp slide deck.

    Returns a dict with keys: citekey, prompt, slides_path, slides_text,
    model_used, skipped, template.
    """
    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    out_path = slides_path_for_key(cfg, key)

    # Assemble context
    context = assemble_slide_context(key, root)

    # Load template
    template_text = load_template(template)

    # Build prompt
    prompt_text = _build_prompt(context, template_text)

    if prompt_only:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "slides_path": None,
            "slides_text": None,
            "model_used": None,
            "skipped": False,
            "template": template,
        }

    # Check existing
    if out_path.exists() and not force:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "slides_path": str(out_path),
            "slides_text": out_path.read_text(encoding="utf-8"),
            "model_used": None,
            "skipped": True,
            "template": template,
        }

    # Call LLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "slides_path": None,
            "slides_text": None,
            "model_used": None,
            "skipped": False,
            "template": template,
            "error": "ANTHROPIC_API_KEY not set",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "slides_path": None,
            "slides_text": None,
            "model_used": None,
            "skipped": False,
            "template": template,
            "error": "anthropic package not installed",
        }

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
    )
    slides_body = message.content[0].text

    # Prepend Marp frontmatter
    frontmatter = _build_marp_frontmatter(context.get("bib") or {})
    full_md = frontmatter + "\n\n" + slides_body.strip() + "\n"

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_md, encoding="utf-8")

    return {
        "citekey": key,
        "prompt": prompt_text,
        "slides_path": str(out_path),
        "slides_text": full_md,
        "model_used": model,
        "skipped": False,
        "template": template,
    }


def export_slides(
    citekey: str,
    root: Path,
    *,
    fmt: str = "html",
) -> dict[str, Any]:
    """Export a Marp slide deck to HTML, PDF, or PPTX using marp-cli.

    Returns ``{"citekey": ..., "output_path": ..., "format": ...}``
    or ``{"error": ...}`` if marp-cli is not available.
    """
    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    slides_path = slides_path_for_key(cfg, key)

    if not slides_path.exists():
        return {"error": f"Slides not found: {slides_path}. Run 'biblio present' first."}

    marp = shutil.which("marp")
    if marp is None:
        return {"error": "marp-cli not found on PATH. Install with: npm install -g @marp-team/marp-cli"}

    out_ext = {"html": ".html", "pdf": ".pdf", "pptx": ".pptx"}.get(fmt)
    if out_ext is None:
        return {"error": f"Unsupported export format: {fmt!r}. Choose from: html, pdf, pptx"}

    out_path = slides_path.with_suffix(out_ext)
    cmd = [marp, str(slides_path), "-o", str(out_path)]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {"error": f"marp-cli failed: {proc.stderr.strip()}"}

    return {
        "citekey": key,
        "output_path": str(out_path),
        "format": fmt,
    }
