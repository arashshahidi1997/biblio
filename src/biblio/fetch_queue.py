from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig
from .ledger import utc_now_iso

VALID_OA_STATUSES = {"no_url", "error", "manual"}


def queue_path(cfg: BiblioConfig) -> Path:
    return cfg.fetch_queue_path


def load_queue(cfg: BiblioConfig) -> dict[str, dict[str, Any]]:
    """Load the fetch queue. Returns {citekey: {added, doi, url, oa_status, note}}."""
    path = queue_path(cfg)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = payload.get("queue") or {}
    if not isinstance(entries, dict):
        return {}
    return {str(k): dict(v) if isinstance(v, dict) else {} for k, v in entries.items()}


def save_queue(cfg: BiblioConfig, entries: dict[str, dict[str, Any]]) -> Path:
    path = queue_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"queue": entries}, sort_keys=True, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def add_to_queue(
    cfg: BiblioConfig,
    citekey: str,
    *,
    doi: str | None = None,
    url: str | None = None,
    oa_status: str = "manual",
    note: str | None = None,
) -> dict[str, Any]:
    """Add or update a citekey in the fetch queue. Returns the stored entry."""
    entries = load_queue(cfg)
    existing = dict(entries.get(citekey) or {})
    entry: dict[str, Any] = {
        "added": existing.get("added") or utc_now_iso(),
    }
    if doi is not None:
        entry["doi"] = doi
    elif existing.get("doi"):
        entry["doi"] = existing["doi"]
    if url is not None:
        entry["url"] = url
    elif existing.get("url"):
        entry["url"] = existing["url"]
    entry["oa_status"] = oa_status
    if note is not None:
        entry["note"] = note
    elif existing.get("note"):
        entry["note"] = existing["note"]
    entries[citekey] = entry
    save_queue(cfg, entries)
    return entry


def remove_from_queue(cfg: BiblioConfig, citekey: str) -> bool:
    """Remove a citekey from the queue. Returns True if it was present."""
    entries = load_queue(cfg)
    if citekey not in entries:
        return False
    del entries[citekey]
    save_queue(cfg, entries)
    return True


def get_queue_entry(cfg: BiblioConfig, citekey: str) -> dict[str, Any]:
    return load_queue(cfg).get(citekey, {})
