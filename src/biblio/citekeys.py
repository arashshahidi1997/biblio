from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import BiblioConfig

_KEY = r"([A-Za-z0-9][A-Za-z0-9_:.+-]*)"
_LIST_ITEM_RE = re.compile(rf"^\s*[-*]\s+@{_KEY}\b")
_BARE_RE = re.compile(rf"^\s*@{_KEY}\b")


def load_active_citekeys(cfg: BiblioConfig) -> list[str]:
    """Return all citekeys from the merged bibliography.

    This is the canonical source of "active" citekeys — every entry in the
    merged bib is considered active.  Falls back to parsing srcbib directly
    if the merge output does not exist yet.
    """
    from ._pybtex_utils import parse_bibtex_file, require_pybtex

    merged = cfg.bibtex_merge.out_bib
    if merged.exists():
        require_pybtex("citekey listing")
        db = parse_bibtex_file(merged)
        return sorted(db.entries.keys())

    # Fallback: read srcbib directly
    src_dir = cfg.bibtex_merge.src_dir
    if src_dir.exists():
        require_pybtex("citekey listing")
        keys: list[str] = []
        seen: set[str] = set()
        for bib_path in sorted(src_dir.glob(cfg.bibtex_merge.src_glob)):
            db = parse_bibtex_file(bib_path)
            for k in sorted(db.entries.keys()):
                if k not in seen:
                    keys.append(k)
                    seen.add(k)
        return keys

    return []


def parse_citekeys_from_markdown(markdown_text: str) -> list[str]:
    """
    Extract citekeys from a markdown "citekeys list" file.

    Intended format:
      - @my_citekey
      - @another_key

    Parsing rules (to avoid surprising matches):
    - Only reads list items (`- @key` / `* @key`) or bare lines (`@key`).
    - Skips headings/comment-style lines starting with '#'.
    - Skips fenced code blocks.

    Returns ordered unique keys WITHOUT '@'.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    in_fence = False
    fence = ""
    for raw in (markdown_text or "").splitlines():
        line = raw.rstrip("\n")
        stripped = line.lstrip()

        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence = marker
            elif marker == fence:
                in_fence = False
                fence = ""
            continue
        if in_fence:
            continue

        if stripped.startswith("#"):
            continue

        match = _LIST_ITEM_RE.match(line) or _BARE_RE.match(line)
        if not match:
            continue

        key = match.group(1)
        if key in seen:
            continue
        ordered.append(key)
        seen.add(key)

    return ordered


def load_citekeys_md(path: str | Path) -> list[str]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return parse_citekeys_from_markdown(text)


def _render_citekeys_md(keys: list[str]) -> str:
    lines = ["# Citekeys", ""]
    for key in keys:
        k = key.lstrip("@")
        lines.append(f"- @{k}")
    lines.append("")
    return "\n".join(lines)


def add_citekeys_md(path: str | Path, keys_to_add: list[str]) -> list[str]:
    path = Path(path)
    existing = load_citekeys_md(path) if path.exists() else []
    existing_set = set(existing)
    updated = list(existing)
    for key in keys_to_add:
        k = key.lstrip("@")
        if k in existing_set:
            continue
        updated.append(k)
        existing_set.add(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_citekeys_md(updated), encoding="utf-8")
    return updated


def remove_citekeys_md(path: str | Path, keys_to_remove: list[str]) -> list[str]:
    path = Path(path)
    existing = load_citekeys_md(path) if path.exists() else []
    remove_set = {k.lstrip("@") for k in keys_to_remove}
    updated = [k for k in existing if k not in remove_set]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_citekeys_md(updated), encoding="utf-8")
    return updated
