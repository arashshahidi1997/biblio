from __future__ import annotations

from pathlib import Path


def find_repo_root(start: str | Path | None = None) -> Path:
    """
    Find a sensible repo root for running biblio commands.

    Preference order when walking up from `start`:
      1) A directory containing `.projio/biblio/biblio.yml` (new layout)
      2) A directory containing `bib/config/biblio.yml` (legacy layout)
      3) A directory containing `.git` or `pyproject.toml`
      4) Fallback to the resolved start directory
    """
    start_path = Path(start) if start is not None else Path.cwd()
    start_path = start_path.expanduser().resolve()

    fallback: Path | None = None
    for p in [start_path, *start_path.parents]:
        if (p / ".projio" / "biblio" / "biblio.yml").exists():
            return p
        if (p / "bib" / "config" / "biblio.yml").exists():
            return p
        if fallback is None and ((p / ".git").exists() or (p / "pyproject.toml").exists()):
            fallback = p
    return fallback or start_path

