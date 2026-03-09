from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig

VALID_STATUSES = {"unread", "reading", "processed", "archived"}
VALID_PRIORITIES = {"low", "normal", "high"}


def library_path(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / "bib" / "config" / "library.yml").resolve()


def load_library(cfg: BiblioConfig) -> dict[str, dict[str, Any]]:
    """Load the library ledger. Returns {citekey: {status, tags, priority}}."""
    path = library_path(cfg)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    papers = payload.get("papers") or {}
    if not isinstance(papers, dict):
        return {}
    return {str(k): dict(v) if isinstance(v, dict) else {} for k, v in papers.items()}


def save_library(cfg: BiblioConfig, papers: dict[str, dict[str, Any]]) -> Path:
    path = library_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"papers": papers}, sort_keys=True, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def update_entry(cfg: BiblioConfig, citekey: str, **kwargs: Any) -> dict[str, Any]:
    """Update one paper's library entry. Pass None to remove a field."""
    papers = load_library(cfg)
    entry = dict(papers.get(citekey) or {})
    for k, v in kwargs.items():
        if v is None:
            entry.pop(k, None)
        else:
            entry[k] = v
    # Clean empty entry
    if entry:
        papers[citekey] = entry
    else:
        papers.pop(citekey, None)
    save_library(cfg, papers)
    return entry


def get_entry(cfg: BiblioConfig, citekey: str) -> dict[str, Any]:
    return load_library(cfg).get(citekey, {})


def notes_path(cfg: BiblioConfig, citekey: str) -> Path:
    return (cfg.repo_root / "bib" / "notes" / f"{citekey}.md").resolve()
