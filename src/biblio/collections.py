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


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_by_name(data: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((c for c in data["collections"] if c.get("name") == name), None)


def is_smart(col: dict[str, Any]) -> bool:
    """Return True if the collection is query-driven (smart)."""
    return "query" in col and col["query"] is not None


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_collection(
    cfg: BiblioConfig,
    name: str,
    parent: str | None = None,
    *,
    query: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    data = load_collections(cfg)
    col: dict[str, Any] = {"id": _new_id(), "name": name, "parent": parent}
    if query is not None:
        # Smart collection — validate query syntax eagerly
        from .query import parse_query
        parse_query(query)  # raises ParseError on bad syntax
        col["query"] = query
    else:
        col["citekeys"] = []
    if description:
        col["description"] = description
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


# ── Smart collection support ─────────────────────────────────────────────────

def update_query(cfg: BiblioConfig, col_id: str, query: str) -> dict[str, Any] | None:
    """Update the query of a smart collection. Validates syntax first."""
    from .query import parse_query

    parse_query(query)  # raises ParseError on bad syntax
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return None
    col["query"] = query
    col.pop("citekeys", None)  # smart collections don't store static citekeys
    save_collections(cfg, data)
    return col


def convert_to_smart(cfg: BiblioConfig, col_id: str, query: str) -> dict[str, Any] | None:
    """Convert a manual collection to a smart (query-driven) collection."""
    from .query import parse_query

    parse_query(query)  # raises ParseError on bad syntax
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return None
    col["query"] = query
    col.pop("citekeys", None)
    save_collections(cfg, data)
    return col


def resolve_smart(
    cfg: BiblioConfig,
    col_id: str,
    library: dict[str, dict[str, Any]] | None = None,
    bib_entries: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Resolve a smart collection's query and return matching citekeys.

    For manual collections, returns the stored citekeys list.
    """
    data = load_collections(cfg)
    col = _get(data, col_id)
    if col is None:
        return []
    if not is_smart(col):
        return list(col.get("citekeys") or [])

    from .query import query_citekeys

    if library is None:
        from .library import load_library
        library = load_library(cfg)
    return query_citekeys(col["query"], library, bib_entries)


def list_collections_summary(
    cfg: BiblioConfig,
    library: dict[str, dict[str, Any]] | None = None,
    bib_entries: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return a summary list of all collections with membership counts."""
    data = load_collections(cfg)
    summaries: list[dict[str, Any]] = []
    for col in data.get("collections", []):
        entry: dict[str, Any] = {
            "id": col["id"],
            "name": col["name"],
            "parent": col.get("parent"),
            "smart": is_smart(col),
        }
        if is_smart(col):
            entry["query"] = col["query"]
            resolved = resolve_smart(cfg, col["id"], library, bib_entries)
            entry["resolved_count"] = len(resolved)
            entry["resolved_citekeys"] = resolved
        else:
            entry["citekeys"] = list(col.get("citekeys") or [])
            entry["count"] = len(entry["citekeys"])
        if col.get("description"):
            entry["description"] = col["description"]
        summaries.append(entry)
    return summaries
