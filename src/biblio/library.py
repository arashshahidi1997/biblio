from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig

VALID_STATUSES = {"unread", "reading", "processed", "archived"}
VALID_PRIORITIES = {"low", "normal", "high"}


def library_path(cfg: BiblioConfig) -> Path:
    new_path = (cfg.repo_root / ".projio" / "biblio" / "library.yml").resolve()
    if new_path.exists():
        return new_path
    # Fall back to legacy location
    legacy = (cfg.repo_root / "bib" / "config" / "library.yml").resolve()
    if legacy.exists():
        return legacy
    # Return new path as write target
    return new_path


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


def bulk_update(
    cfg: BiblioConfig,
    citekeys: list[str],
    *,
    status: str | None = None,
    priority: str | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Update multiple papers' library entries in one write."""
    papers = load_library(cfg)
    results: dict[str, dict[str, Any]] = {}
    for ck in citekeys:
        entry = dict(papers.get(ck) or {})
        if status is not None:
            entry["status"] = status
        if priority is not None:
            entry["priority"] = priority
        if add_tags:
            existing = list(entry.get("tags") or [])
            for t in add_tags:
                if t not in existing:
                    existing.append(t)
            entry["tags"] = existing
        if remove_tags:
            existing = list(entry.get("tags") or [])
            entry["tags"] = [t for t in existing if t not in remove_tags]
            if not entry["tags"]:
                entry.pop("tags", None)
        if entry:
            papers[ck] = entry
        else:
            papers.pop(ck, None)
        results[ck] = entry
    save_library(cfg, papers)
    return results


def get_entry(cfg: BiblioConfig, citekey: str) -> dict[str, Any]:
    return load_library(cfg).get(citekey, {})


def notes_path(cfg: BiblioConfig, citekey: str) -> Path:
    return (cfg.repo_root / "bib" / "notes" / f"{citekey}.md").resolve()
