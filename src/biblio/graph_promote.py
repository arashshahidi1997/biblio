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
    seed_citekeys: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Read graph_candidates.json, filter, deduplicate, and feed to ingest.

    ``graph_candidates.json`` accumulates the candidates of every seed ever
    expanded. ``seed_citekeys`` limits the promotion to the candidates of those
    seed papers (matched on ``seed_openalex_id``); an unknown or unresolved
    seed citekey is an error rather than an empty filter.

    Returns counts of promoted/skipped/filtered papers, new citekeys, and
    ``by_seed`` (selected candidates per seed citekey).
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
    candidates_total = len(candidates)

    from .graph import _normalize_openalex_id, _seed_citekeys, load_openalex_seed_records

    resolved_path = cfg.repo_root / "bib" / "derivatives" / "openalex" / "resolved.jsonl"
    seed_by_id = _seed_citekeys(load_openalex_seed_records(resolved_path))

    def _seed_of(cand: dict[str, Any]) -> str:
        sid = _normalize_openalex_id(cand.get("seed_openalex_id"))
        return seed_by_id.get(sid or "", sid or "<unknown>")

    if seed_citekeys:
        wanted_ids = {sid for sid, ck in seed_by_id.items() if ck in set(seed_citekeys)}
        unknown = sorted(set(seed_citekeys) - {seed_by_id[sid] for sid in wanted_ids})
        if unknown:
            return {
                "error": f"seed citekeys not found in {resolved_path.name} (no OpenAlex id): {', '.join(unknown)}",
                "hint": "Run OpenAlex resolution for them, then `biblio graph expand --keys ...`.",
            }
        candidates = [
            c for c in candidates
            if _normalize_openalex_id(c.get("seed_openalex_id")) in wanted_ids
        ]

    # Deduplicate against existing library
    from .ingest import find_existing_dois

    existing_dois = find_existing_dois(cfg.repo_root)

    filtered: list[dict[str, Any]] = []
    seen_dois: set[str] = set()
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
        if doi_norm in seen_dois:  # the same work found from several seeds
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

        seen_dois.add(doi_norm)
        filtered.append(cand)

    # Sort by citations descending, take top_n
    filtered.sort(key=lambda c: c.get("cited_by_count") or 0, reverse=True)
    if top_n is not None:
        filtered = filtered[:top_n]

    dois_to_promote = [c["doi"] for c in filtered if c.get("doi")]
    by_seed: dict[str, int] = {}
    for c in filtered:
        by_seed[_seed_of(c)] = by_seed.get(_seed_of(c), 0) + 1
    scope: dict[str, Any] = {"seed_citekeys": list(seed_citekeys or []), "by_seed": by_seed}
    if not seed_citekeys and len(by_seed) > 1:
        scope["warning"] = (
            f"candidates from {len(by_seed)} seeds are selected; pass seed_citekeys "
            "(CLI: --seed) to promote one paper's references"
        )

    if dry_run or not dois_to_promote:
        return {
            "promoted": 0,
            "candidates_selected": len(dois_to_promote),
            "dois": dois_to_promote[:50],  # cap preview length
            "skipped_existing": skipped_existing,
            "skipped_no_doi": skipped_no_doi,
            "filtered_out": filtered_out,
            "candidates_in_scope": len(candidates),
            "candidates_total": candidates_total,
            **scope,
            "dry_run": dry_run,
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
        "candidates_in_scope": len(candidates),
        "candidates_total": candidates_total,
        **scope,
        "dry_run": False,
    }
