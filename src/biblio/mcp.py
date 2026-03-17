"""MCP API functions for biblio — called by projio's MCP server.

Module-only (no FastMCP dependency). Follows the same pattern as codio.mcp.
All functions accept ``root`` and handle config loading internally.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_cfg(root: Path):
    from .config import BiblioConfig, default_config_path, load_biblio_config

    config_path = default_config_path(root=root)
    return load_biblio_config(config_path, root=root)


def _bib_entry_to_dict(entry) -> dict[str, Any]:
    """Convert a pybtex Entry into a plain dict."""
    fields = dict(entry.fields)
    authors = []
    for person_list in entry.persons.values():
        for person in person_list:
            parts = []
            if person.first_names:
                parts.extend(person.first_names)
            if person.last_names:
                parts.extend(person.last_names)
            authors.append(" ".join(parts))
    return {
        "type": entry.type,
        "authors": authors,
        **{k: str(v) for k, v in fields.items()},
    }


def _load_bib_database(cfg):
    """Load the merged .bib file and return a pybtex BibliographyData."""
    from ._pybtex_utils import parse_bibtex_file

    bib_path = cfg.bibtex_merge.out_bib
    if not bib_path.exists():
        return None
    return parse_bibtex_file(bib_path)


def resolve_citekeys(citekeys: list[str], *, root: Path) -> dict[str, Any]:
    """Resolve citekeys to metadata (title/authors/year/doi/abstract/tags/status).

    Returns ``{"results": {citekey: {...}}, "missing": [...]}``.
    """
    cfg = _load_cfg(root)
    from .library import load_library

    library = load_library(cfg)
    bib_db = _load_bib_database(cfg)

    results: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for ck in citekeys:
        key = ck.lstrip("@")
        entry_data: dict[str, Any] = {}

        # Merge bib entry metadata
        if bib_db and key in bib_db.entries:
            entry_data.update(_bib_entry_to_dict(bib_db.entries[key]))

        # Merge library ledger metadata (status, tags, priority)
        lib_entry = library.get(key, {})
        if lib_entry:
            entry_data.update(lib_entry)

        if entry_data:
            results[key] = entry_data
        else:
            missing.append(key)

    return {"results": results, "missing": missing}


def paper_context(citekey: str, *, root: Path) -> dict[str, Any]:
    """Full structured context for a paper: bib entry + docling excerpt + local refs.

    Returns ``{"citekey": ..., "bib": {...}, "docling_excerpt": str|null,
               "library": {...}, "grobid_header": {...}|null}``.
    """
    cfg = _load_cfg(root)
    key = citekey.lstrip("@")

    # Bib entry
    bib_data: dict[str, Any] = {}
    bib_db = _load_bib_database(cfg)
    if bib_db and key in bib_db.entries:
        bib_data = _bib_entry_to_dict(bib_db.entries[key])

    # Library ledger
    from .library import get_entry

    lib_entry = get_entry(cfg, key)

    # Docling excerpt (first ~2000 chars of markdown)
    from .docling import outputs_for_key

    docling_out = outputs_for_key(cfg, key)
    docling_excerpt = None
    if docling_out.md_path.exists():
        text = docling_out.md_path.read_text(encoding="utf-8", errors="replace")
        docling_excerpt = text[:2000]

    # GROBID header (if processed)
    from .grobid import grobid_outputs_for_key

    grobid_out = grobid_outputs_for_key(cfg, key)
    grobid_header = None
    if grobid_out.header_path.exists():
        try:
            grobid_header = json.loads(
                grobid_out.header_path.read_text(encoding="utf-8")
            )
        except Exception:
            pass

    return {
        "citekey": key,
        "bib": bib_data,
        "library": lib_entry,
        "docling_excerpt": docling_excerpt,
        "grobid_header": grobid_header,
    }


def absent_refs(citekey: str, *, root: Path) -> dict[str, Any]:
    """References in the paper not matched locally (GROBID unresolved refs).

    Returns ``{"citekey": ..., "absent": [...]}``.
    """
    cfg = _load_cfg(root)
    key = citekey.lstrip("@")

    from .grobid import get_absent_refs

    absent = get_absent_refs(cfg, key)
    return {"citekey": key, "absent": absent, "count": len(absent)}


def library_get(citekey: str, *, root: Path) -> dict[str, Any]:
    """Return library ledger entry (status/tags/priority) for a citekey.

    Returns ``{"citekey": ..., "entry": {...}}``.
    """
    cfg = _load_cfg(root)
    key = citekey.lstrip("@")

    from .library import get_entry

    entry = get_entry(cfg, key)
    return {"citekey": key, "entry": entry}


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------


def ingest_dois(
    dois: list[str],
    *,
    root: Path,
    tags: list[str] | None = None,
    status: str = "unread",
    collection: str | None = None,
) -> dict[str, Any]:
    """Ingest papers by DOI: resolve via OpenAlex, generate citekeys, write BibTeX.

    Optionally sets library ledger tags/status and adds citekeys to a collection.

    Returns ``{"citekeys": [...], "count": N, "output_bib": str,
               "collection": str|null}``.
    """
    import tempfile

    from .ingest import ingest_file

    # Write DOIs to a temp file for ingest_file()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        for doi in dois:
            tmp.write(doi.strip() + "\n")
        tmp_path = Path(tmp.name)

    try:
        result, _bibtex_text = ingest_file(
            repo_root=root,
            source_type="dois",
            input_path=tmp_path,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    citekeys = list(result.citekeys)

    # Set library metadata if requested
    if (tags or status) and citekeys:
        cfg = _load_cfg(root)
        from .library import update_entry

        kwargs: dict[str, Any] = {}
        if status:
            kwargs["status"] = status
        if tags:
            kwargs["tags"] = tags
        for ck in citekeys:
            update_entry(cfg, ck, **kwargs)

    # Add to collection if requested
    col_id = None
    if collection and citekeys:
        cfg = _load_cfg(root)
        from .collections import add_papers, create_collection, load_collections

        cols_data = load_collections(cfg)
        # Find existing collection by name, or create new
        existing = [
            c for c in cols_data.get("collections", []) if c.get("name") == collection
        ]
        if existing:
            col_id = existing[0]["id"]
        else:
            new_col = create_collection(cfg, collection)
            col_id = new_col["id"]
        add_papers(cfg, col_id, citekeys)

    return {
        "citekeys": citekeys,
        "count": len(citekeys),
        "output_bib": str(result.output_path),
        "collection": collection,
        "collection_id": col_id,
    }


def library_set_bulk(
    citekeys: list[str],
    *,
    root: Path,
    status: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    """Bulk-update library ledger entries for multiple citekeys.

    Returns ``{"updated": [...], "count": N}``.
    """
    cfg = _load_cfg(root)
    from .library import update_entry

    kwargs: dict[str, Any] = {}
    if status is not None:
        kwargs["status"] = status
    if tags is not None:
        kwargs["tags"] = tags
    if priority is not None:
        kwargs["priority"] = priority

    updated: list[str] = []
    for ck in citekeys:
        key = ck.lstrip("@")
        update_entry(cfg, key, **kwargs)
        updated.append(key)

    return {"updated": updated, "count": len(updated)}
