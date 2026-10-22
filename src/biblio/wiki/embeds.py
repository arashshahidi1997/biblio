"""Files that wiki pages embed (``![alt](path)``), and figures from papers (W17).

In a DataLad dataset images are annexed: the working tree holds a symlink into
``.git/annex`` (locked) or, after ``datalad unlock``, a regular file. Obsidian
ignores symlinks, so a locked figure does not display there; a figure whose
content was never fetched displays nowhere. ``biblio wiki embeds`` reports
the state of every embedded file and can fetch and unlock them.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from .pages import Page, load_pages
from .schema import WikiConfig

FIGURES_REL = Path("bib") / "derivatives" / "figures"
_POINTER_MAX = 1024  # an unlocked file without content is a small "/annex/objects/..." pointer


def file_state(path: Path) -> str:
    """'missing', 'absent' (annexed, content not here), 'locked' (annex symlink) or 'file'."""
    if path.is_symlink():
        target = os.readlink(path)
        if ".git/annex/objects" not in target.replace(os.sep, "/"):
            return "file" if path.exists() else "missing"
        return "locked" if path.exists() else "absent"
    if not path.exists():
        return "missing"
    if path.is_file() and path.stat().st_size < _POINTER_MAX:
        try:
            if path.read_bytes().startswith(b"/annex/objects/"):
                return "absent"
        except OSError:
            pass
    return "file"


def figure_citekey(cfg: WikiConfig, path: Path) -> str | None:
    """The paper a figure comes from, for files under bib/derivatives/figures/<citekey>/."""
    try:
        rel = Path(os.path.normpath(path)).relative_to(cfg.repo_root / FIGURES_REL)
    except ValueError:
        return None
    return rel.parts[0] if len(rel.parts) >= 2 else None


@dataclass
class Embed:
    page: Page
    line: int
    target: str
    path: Path
    state: str


def find_embeds(cfg: WikiConfig, pages: list[Page] | None = None) -> list[Embed]:
    pages = pages if pages is not None else load_pages(cfg.wiki_root)
    out = []
    for page in pages:
        for link in page.links:
            if link.embed and link.kind == "md":
                path = Path(os.path.normpath(page.path.parent / link.target))
                out.append(Embed(page, link.line, link.target, path, file_state(path)))
    return out


def _annex_cmd(action: str) -> list[str]:
    if shutil.which("datalad"):
        return ["datalad", action]
    return ["git", "annex", action]


def apply(cfg: WikiConfig, embeds: list[Embed], *, get: bool, unlock: bool) -> list[tuple[str, list[str], int]]:
    """Fetch absent and unlock locked embedded files. Returns (action, paths, returncode) per call."""
    runs = []
    rel = lambda e: os.path.relpath(e.path, cfg.repo_root)  # noqa: E731
    if get:
        paths = sorted({rel(e) for e in embeds if e.state == "absent"})
        if paths:
            proc = subprocess.run([*_annex_cmd("get"), *paths], cwd=cfg.repo_root)
            runs.append(("get", paths, proc.returncode))
            for e in embeds:
                e.state = file_state(e.path)
    if unlock:
        paths = sorted({rel(e) for e in embeds if e.state == "locked"})
        if paths:
            proc = subprocess.run([*_annex_cmd("unlock"), *paths], cwd=cfg.repo_root)
            runs.append(("unlock", paths, proc.returncode))
            for e in embeds:
                e.state = file_state(e.path)
    return runs


# ---------------------------------------------------------------------------
# Figure snippets from biblio figures' manifest (D10)
# ---------------------------------------------------------------------------

# words that really end in "f": a following "i"/"l" word is not a split ligature
_F_WORDS = {"of", "if", "off", "half", "self", "itself", "himself", "herself", "themselves", "ourselves",
            "brief", "chief", "proof", "leaf", "staff", "cliff", "stiff", "belief", "relief", "roof",
            "thief", "beef", "reef", "chef", "serif", "motif", "cf", "ref"}
_LIGATURE = re.compile(r"(?<![\w-])(\w*f) (?=[il]\w)")
_LOST_DASH = re.compile(r"\b\d{4,}\s?(?:ms|s|Hz|µm|um|mm|µV|mV|%|min)\b")


def clean_caption(text: str) -> tuple[str, list[str]]:
    """Caption text with docling's split ligatures joined ("f iltered" -> "filtered"), and warnings
    for digit runs that look like a lost dash ("12040 ms" for "120-40 ms")."""
    text = " ".join(str(text or "").split())
    text = _LIGATURE.sub(lambda m: m.group(1) if m.group(1).lower() not in _F_WORDS else m.group(0), text)
    warnings = [f"'{m.group(0)}' may have lost a dash; check the paper" for m in _LOST_DASH.finditer(text)]
    return text, warnings


def _caption_title(caption: str, label: str) -> str:
    """The caption's first sentence without its "Figure N." label."""
    body = re.sub(r"^\s*(?:Figure|Fig\.?)\s*\w+[.:]?\s*", "", caption, flags=re.I)
    body = re.split(r"[:.;,]?\s+\(?[Aa]\)\s", body, maxsplit=1)[0]   # stop where panel (A) starts
    m = re.match(r"(.+?[.!?])(?:\s|$)", body)
    return (m.group(1) if m else body).strip() or label


def _figure_label(entry: dict) -> str:
    """'Figure 3', 'Figure S2', 'Extended Data Fig. 4', 'Graphical abstract', or the file stem."""
    kind, number = entry.get("kind"), str(entry.get("number") or "")
    if kind == "graphical-abstract" or number.upper() == "GA":
        return "Graphical abstract"
    if kind == "extended-data" or number.upper().startswith("ED"):
        return f"Extended Data Fig. {number[2:] if number.upper().startswith('ED') else number}"
    return f"Figure {number}" if number else Path(str(entry.get("file", ""))).stem


def figure_embed(cfg: WikiConfig, citekey: str, number: str, page: Path | None = None,
                 caption: str = "title") -> tuple[str, list[str]]:
    """Markdown that embeds figure ``number`` of ``citekey`` with its caption and citation.

    ``number`` is a figure number ("3") or a file stem ("pic-02"). Paths are relative to ``page``
    (default: the wiki's ``sources/`` folder). ``caption``: ``title`` (the caption's first sentence,
    default), ``full`` or ``none``. Returns (markdown, warnings about the caption text).
    """
    fig_dir = cfg.repo_root / FIGURES_REL / citekey
    manifest_path = fig_dir / "manifest.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no figures for {citekey}: run `biblio figures run --key {citekey}`")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    figures = manifest.get("figures") or []
    want = str(number).strip()
    entry = next((f for f in figures if str(f.get("number") or "").lower() == want.lower()), None) or next(
        (f for f in figures if Path(str(f.get("file", ""))).stem.lower() == want.lower()), None)
    if entry is None:
        known = ", ".join(str(f.get("number") or Path(str(f.get("file", ""))).stem) for f in figures)
        raise LookupError(f"{citekey} has no figure {number}; known: {known}")
    base = page.parent if page is not None else cfg.wiki_root / "sources"
    rel = os.path.relpath(fig_dir / entry["file"], base).replace(os.sep, "/")
    label = _figure_label(entry)
    full, warnings = clean_caption(entry.get("caption") or "")
    if caption == "full":
        text = full or label
    elif caption == "none":
        text = label
    else:
        title = _caption_title(full, label) if full else label
        text = f"{label}. {title}" if title != label else label
        warnings = [w for w in warnings if w.split("'")[1] in text]
        if full and len(full) > len(text) + 20:
            text += " (full caption in the paper)"
    return f"![{label} of {citekey}]({rel})\n\n*{text}* [@{citekey}]\n", warnings
