"""Files that wiki pages embed (``![alt](path)``), and figures from papers (W17).

In a DataLad dataset images are annexed: the working tree holds a symlink into
``.git/annex`` (locked) or, after ``datalad unlock``, a regular file. Obsidian
ignores symlinks, so a locked figure does not display there; a figure whose
content was never fetched displays nowhere. ``biblio wiki embeds`` reports
the state of every embedded file and can fetch and unlock them.
"""
from __future__ import annotations

import os
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

def figure_embed(cfg: WikiConfig, citekey: str, number: str, page: Path | None = None) -> str:
    """Markdown that embeds figure ``number`` of ``citekey`` with its caption and citation.

    ``number`` is a figure number ("3") or a file stem ("pic-02"). Paths are
    relative to ``page`` (default: the wiki's ``sources/`` folder).
    """
    fig_dir = cfg.repo_root / FIGURES_REL / citekey
    manifest_path = fig_dir / "manifest.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no figures for {citekey}: run `biblio figures run --key {citekey}`")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    figures = manifest.get("figures") or []
    entry = next((f for f in figures if str(f.get("number")) == str(number)), None) or next(
        (f for f in figures if Path(str(f.get("file", ""))).stem == str(number)), None)
    if entry is None:
        known = ", ".join(str(f.get("number") or Path(str(f.get("file", ""))).stem) for f in figures)
        raise LookupError(f"{citekey} has no figure {number}; known: {known}")
    base = page.parent if page is not None else cfg.wiki_root / "sources"
    rel = os.path.relpath(fig_dir / entry["file"], base).replace(os.sep, "/")
    label = f"Figure {entry['number']}" if entry.get("number") else Path(entry["file"]).stem
    caption = " ".join(str(entry.get("caption") or "").split())
    return f"![{label} of {citekey}]({rel})\n\n*{caption or label}* [@{citekey}]\n"
