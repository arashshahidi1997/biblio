from __future__ import annotations

import json
import random
import string
from pathlib import Path
from typing import Any

from .config import BiblioConfig


def collections_path(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / "bib" / "config" / "collections.json").resolve()


def load_collections(cfg: BiblioConfig) -> dict[str, Any]:
    """Load collections. Returns {version, collections: [{id, name, parent, citekeys}]}."""
    p = collections_path(cfg)
    if not p.exists():
        return {"version": 1, "collections": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "collections": []}


def save_collections(cfg: BiblioConfig, data: dict[str, Any]) -> None:
    p = collections_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _new_id() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _get(data: dict[str, Any], col_id: str) -> dict[str, Any] | None:
    return next((c for c in data["collections"] if c["id"] == col_id), None)


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_collection(cfg: BiblioConfig, name: str, parent: str | None = None) -> dict[str, Any]:
    data = load_collections(cfg)
    col: dict[str, Any] = {"id": _new_id(), "name": name, "parent": parent, "citekeys": []}
    data["collections"].append(col)
    save_collections(cfg, data)
    return col


def rename_collection(cfg: BiblioConfig, col_id: str, name: str) -> dict[str, Any] | None:
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return None
    col["name"] = name
    save_collections(cfg, data)
    return col


def move_collection(cfg: BiblioConfig, col_id: str, new_parent: str | None) -> dict[str, Any] | None:
    """Re-parent a collection. Refuses if new_parent is a descendant (would create cycle)."""
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return None
    # Check for cycle: walk ancestors of new_parent
    if new_parent is not None:
        cursor = new_parent
        seen: set[str] = set()
        while cursor is not None:
            if cursor == col_id:
                return None  # cycle detected
            if cursor in seen:
                break
            seen.add(cursor)
            parent_col = _get(data, cursor)
            cursor = parent_col["parent"] if parent_col else None
    col["parent"] = new_parent
    save_collections(cfg, data)
    return col


def delete_collection(cfg: BiblioConfig, col_id: str) -> bool:
    """Delete a collection, re-parenting its children to its own parent."""
    data = load_collections(cfg)
    target = _get(data, col_id)
    if target is None:
        return False
    new_parent = target.get("parent")
    for col in data["collections"]:
        if col.get("parent") == col_id:
            col["parent"] = new_parent
    data["collections"] = [c for c in data["collections"] if c["id"] != col_id]
    save_collections(cfg, data)
    return True


# ── Membership ────────────────────────────────────────────────────────────────

def add_papers(cfg: BiblioConfig, col_id: str, citekeys: list[str]) -> dict[str, Any] | None:
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return None
    existing = set(col["citekeys"])
    col["citekeys"] = col["citekeys"] + [k for k in citekeys if k not in existing]
    save_collections(cfg, data)
    return col


def remove_papers(cfg: BiblioConfig, col_id: str, citekeys: list[str]) -> dict[str, Any] | None:
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return None
    drop = set(citekeys)
    col["citekeys"] = [k for k in col["citekeys"] if k not in drop]
    save_collections(cfg, data)
    return col
