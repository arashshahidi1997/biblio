"""Promote graph expansion candidates into the ingest pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import BiblioConfig


def promote_graph_candidates(
    cfg: BiblioConfig,
    *,
    top_n: int | None = None,
    min_citations: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    keyword_filter: str | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Read graph_candidates.json, filter, deduplicate, and feed to ingest.

    Returns counts of promoted/skipped/filtered papers and new citekeys.
    """
    candidates_path = (
        cfg.repo_root / "bib" / "derivatives" / "openalex" / "graph_candidates.json"
    )
    if not candidates_path.exists():
        return {
            "error": f"graph_candidates.json not found at {candidates_path}",
            "hint": "Run biblio_graph_expand first.",
        }

    raw = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates: list[dict[str, Any]] = raw if isinstance(raw, list) else []
    if not candidates:
        return {"error": "graph_candidates.json is empty or not a list"}

    # Deduplicate against existing library
    from .ingest import find_existing_dois

    existing_dois = find_existing_dois(cfg.repo_root)

    filtered: list[dict[str, Any]] = []
    skipped_existing = 0
    skipped_no_doi = 0
    filtered_out = 0

    for cand in candidates:
        doi = cand.get("doi")
        if not doi:
            skipped_no_doi += 1
            continue

        doi_norm = doi.lower().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
        if doi_norm in existing_dois:
            skipped_existing += 1
            continue

        # Apply filters
        if min_citations is not None and (cand.get("cited_by_count") or 0) < min_citations:
            filtered_out += 1
            continue
        pub_year = cand.get("publication_year") or cand.get("year")
        if min_year is not None and (pub_year or 0) < min_year:
            filtered_out += 1
            continue
        if max_year is not None and (pub_year or 9999) > max_year:
            filtered_out += 1
            continue
        if keyword_filter:
            name = (cand.get("display_name") or cand.get("title") or "").lower()
            if keyword_filter.lower() not in name:
                filtered_out += 1
                continue

        filtered.append(cand)

    # Sort by citations descending, take top_n
    filtered.sort(key=lambda c: c.get("cited_by_count") or 0, reverse=True)
    if top_n is not None:
        filtered = filtered[:top_n]

    dois_to_promote = [c["doi"] for c in filtered if c.get("doi")]

    if dry_run or not dois_to_promote:
        return {
            "promoted": 0,
            "candidates_selected": len(dois_to_promote),
            "dois": dois_to_promote[:50],  # cap preview length
            "skipped_existing": skipped_existing,
            "skipped_no_doi": skipped_no_doi,
            "filtered_out": filtered_out,
            "candidates_total": len(candidates),
            "dry_run": True,
        }

    # Feed to ingest
    from .mcp import ingest_dois

    result = ingest_dois(dois_to_promote, root=cfg.repo_root, tags=tags)
    return {
        "promoted": result.get("count", 0),
        "citekeys": result.get("citekeys", []),
        "skipped_existing": skipped_existing,
        "skipped_no_doi": skipped_no_doi,
        "filtered_out": filtered_out,
        "candidates_total": len(candidates),
        "dry_run": False,
    }
