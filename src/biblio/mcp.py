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
            # Add quality score
            try:
                from .quality import score_entry
                q = score_entry(
                    key,
                    {k: v for k, v in entry_data.items() if k not in ("type", "authors")},
                    authors=entry_data.get("authors"),
                    entry_type=entry_data.get("type", ""),
                )
                entry_data["_quality"] = {"tier": q.tier, "score": q.score, "issues": list(q.issues)}
            except Exception:
                pass
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

    # Extract DOI for pool matching (handles citekey mismatches)
    doi = bib_data.get("doi") or (lib_entry or {}).get("doi") or None

    # Docling excerpt (first ~2000 chars of markdown) — checks pool first
    from .docling import resolve_docling_outputs

    docling_out, docling_source = resolve_docling_outputs(cfg, key, doi=doi)
    docling_excerpt = None
    if docling_source != "missing" and docling_out.md_path.exists():
        text = docling_out.md_path.read_text(encoding="utf-8", errors="replace")
        docling_excerpt = text[:2000]

    # GROBID header (if processed) — checks pool first
    from .grobid import resolve_grobid_outputs

    grobid_out, grobid_source = resolve_grobid_outputs(cfg, key, doi=doi)
    grobid_header = None
    if grobid_source != "missing" and grobid_out.header_path.exists():
        try:
            grobid_header = json.loads(
                grobid_out.header_path.read_text(encoding="utf-8")
            )
        except Exception:
            pass

    # OpenAlex enrichment (topics, keywords, type, retraction status)
    openalex_enrichment = None
    try:
        from .openalex.openalex_enrich import load_enrichment

        openalex_enrichment = load_enrichment(root, key)
    except Exception:
        pass

    return {
        "citekey": key,
        "bib": bib_data,
        "library": lib_entry,
        "docling_excerpt": docling_excerpt,
        "docling_source": docling_source,
        "grobid_header": grobid_header,
        "grobid_source": grobid_source,
        "openalex": openalex_enrichment,
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


def citekey_normalize(
    *,
    root: Path,
    apply: bool = False,
    enrich: bool = False,
) -> dict[str, Any]:
    """Preview or apply citekey normalization (rename to canonical author_year_Title).

    Entries with incomplete metadata (missing author, year, or title) are
    reported in ``skipped`` and never renamed to ``anon_nd_Record``.

    Args:
        root: Repository root.
        apply: If True, rewrite bib files and log. If False (default),
            returns the plan without modifying anything.
        enrich: If True, attempt network metadata resolution
            (OpenAlex / GROBID / CrossRef) for entries missing authors.
            Default False so MCP agents stay offline-cheap.

    Returns dict with ``plan`` (renames, already_standard, skipped,
    enriched, total_scanned) and, when applied, ``run_id``.
    """
    from .normalize import apply_normalize_plan, build_normalize_plan

    cfg = _load_cfg(root)
    plan = build_normalize_plan(cfg, enrich=bool(enrich))
    result: dict[str, Any] = {
        "applied": False,
        "plan": plan.to_dict(),
    }
    if apply and plan.renames:
        applied = apply_normalize_plan(cfg, plan)
        result["applied"] = True
        result["run_id"] = applied.run_id
        result["affected_bibs"] = applied.affected_bibs
    elif apply:
        result["applied"] = True  # idempotent no-op
        result["run_id"] = ""
    return result


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
    force: bool = False,
) -> dict[str, Any]:
    """Ingest papers by DOI: resolve via OpenAlex, generate citekeys, write BibTeX.

    Optionally sets library ledger tags/status and adds citekeys to a collection.
    Skips DOIs that already exist in the library unless ``force=True``.

    Returns ``{"citekeys": [...], "count": N, "output_bib": str,
               "collection": str|null, "skipped": [...]}``.
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
            force=force,
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

    # Sync BibTeX keywords to library tags (best-effort, needs merged bib)
    keyword_tags: dict[str, list[str]] = {}
    if citekeys:
        try:
            cfg = _load_cfg(root)
            from .ingest import sync_bibtex_keywords_to_library

            keyword_tags = sync_bibtex_keywords_to_library(cfg, citekeys)
        except Exception:
            pass  # merged bib may not exist yet

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

    skipped_info = [
        {"doi": doi, "existing_citekey": ck} for doi, ck in result.skipped
    ]
    return {
        "citekeys": citekeys,
        "count": len(citekeys),
        "skipped": skipped_info,
        "skipped_count": len(skipped_info),
        "output_bib": str(result.output_path),
        "collection": collection,
        "collection_id": col_id,
        "keyword_tags": keyword_tags,
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


def openalex_resolve(
    *,
    root: Path,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Resolve all srcbib entries against OpenAlex.

    Writes ``bib/derivatives/openalex/resolved.jsonl``.  This step is
    required before ``enrich``, ``pdf_fetch_oa``, ``graph_expand``, and
    ``enrich_topic_tags`` can operate.

    Returns ``{"total": N, "resolved": R, "unresolved": U, "errors": E,
               "output_path": str}``.
    """
    cfg = _load_cfg(root)
    from .openalex.openalex_resolve import ResolveOptions, resolve_srcbib_to_openalex

    src_dir = cfg.repo_root / "bib" / "srcbib"
    out_path = cfg.repo_root / "bib" / "derivatives" / "openalex" / "resolved.jsonl"

    opts = ResolveOptions(
        prefer_doi=True,
        fallback_title_search=True,
        per_page=int(cfg.openalex_client.per_page),
        strict=False,
        force=force,
    )

    counts = resolve_srcbib_to_openalex(
        cfg=cfg.openalex_client,
        cache=cfg.openalex_cache,
        src_dir=src_dir,
        src_glob="*.bib",
        out_path=out_path,
        out_format="jsonl",
        limit=limit,
        opts=opts,
    )
    counts["output_path"] = str(out_path)
    return counts


def pipeline_status(
    *,
    root: Path,
    citekeys: list[str] | None = None,
) -> dict[str, Any]:
    """Per-citekey pipeline completeness matrix."""
    cfg = _load_cfg(root)
    from .status import pipeline_status as _pipeline_status

    return _pipeline_status(cfg, citekeys=citekeys)


def crossref_resolve(
    *,
    root: Path,
    dois: list[str],
) -> dict[str, Any]:
    """Resolve DOIs via Crossref API.

    Returns ``{"resolved": N, "unresolved": N, "results": [...]}``.
    """
    from .crossref import resolve_dois_batch

    return resolve_dois_batch(dois)


def graph_promote(
    *,
    root: Path,
    top_n: int | None = None,
    min_citations: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    keyword_filter: str | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote graph expansion candidates into the bibliography."""
    cfg = _load_cfg(root)
    from .graph_promote import promote_graph_candidates

    return promote_graph_candidates(
        cfg,
        top_n=top_n,
        min_citations=min_citations,
        min_year=min_year,
        max_year=max_year,
        keyword_filter=keyword_filter,
        tags=tags,
        dry_run=dry_run,
    )


def extract(
    *,
    root: Path,
    citekey: str,
    force: bool = False,
    model: str = "sonnet",
) -> dict[str, Any]:
    """LLM-driven extraction of paper relevance against research questions."""
    cfg = _load_cfg(root)
    from .extract import extract_for_citekey

    return extract_for_citekey(cfg, citekey, force=force, model=model)


def graph_expand(
    *,
    root: Path,
    citekeys: list[str] | None = None,
    direction: str = "references",
    merge: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Expand the OpenAlex reference graph from resolved seed records.

    Returns ``{"total_inputs": N, "seeds_with_openalex": N, "candidates": N,
               "output_path": str}`` or ``{"error": ...}`` if no seeds found.
    """
    cfg = _load_cfg(root)
    from .graph import expand_openalex_reference_graph, load_openalex_seed_records

    resolved_path = cfg.repo_root / "bib" / "derivatives" / "openalex" / "resolved.jsonl"
    records = load_openalex_seed_records(resolved_path)
    if not records:
        return {
            "error": "No seed records found",
            "resolved_path": str(resolved_path),
            "hint": "Run OpenAlex resolution first to populate resolved.jsonl",
        }

    out_path = cfg.repo_root / "bib" / "derivatives" / "openalex" / "graph_candidates.json"
    result = expand_openalex_reference_graph(
        cfg=cfg.openalex_client,
        cache=cfg.openalex_cache,
        records=records,
        out_path=out_path,
        direction=direction,
        force=force,
        merge=merge,
        seed_citekeys=citekeys,
    )
    return {
        "total_inputs": result.total_inputs,
        "seeds_with_openalex": result.seeds_with_openalex,
        "candidates": result.candidates,
        "output_path": str(result.output_path),
    }


def author_works(
    *,
    root: Path,
    orcid: str,
    since_year: int | None = None,
    min_citations: int | None = None,
) -> dict[str, Any]:
    """Search OpenAlex for an author by ORCID and return their publications."""
    cfg = _load_cfg(root)
    from .author_search import search_by_orcid as _search, get_author_works as _get_works
    from .ingest import find_existing_dois

    author = _search(cfg.openalex_client, orcid)
    works = _get_works(
        cfg.openalex_client,
        author.openalex_id,
        since_year=since_year,
        min_citations=min_citations,
    )
    existing_dois = find_existing_dois(root)
    return {
        "author": {
            "openalex_id": author.openalex_id,
            "orcid": author.orcid,
            "display_name": author.display_name,
            "affiliation": author.affiliation,
            "affiliations": author.affiliations,
            "works_count": author.works_count,
            "cited_by_count": author.cited_by_count,
            "h_index": author.h_index,
        },
        "works": [
            {
                "openalex_id": w.openalex_id,
                "doi": w.doi,
                "title": w.title,
                "year": w.year,
                "journal": w.journal,
                "cited_by_count": w.cited_by_count,
                "is_oa": w.is_oa,
                "type": w.type,
                "is_retracted": w.is_retracted,
                "topics": w.topics,
                "in_library": bool(w.doi and w.doi.lower() in existing_dois),
            }
            for w in works
        ],
        "total": len(works),
    }


def discover_authors(
    *,
    root: Path,
    query: str | None = None,
    author_id: str | None = None,
    orcid: str | None = None,
) -> dict[str, Any]:
    """Search for authors by name, OpenAlex ID, or ORCID.

    Exactly one of ``query``, ``author_id``, or ``orcid`` must be provided.
    Returns ranked candidates with affiliation, h-index, and works count.
    """
    cfg = _load_cfg(root)
    if query:
        from .author_search import search_by_name
        authors = search_by_name(cfg.openalex_client, query)
        return {
            "query": query,
            "authors": [
                {
                    "openalex_id": a.openalex_id,
                    "orcid": a.orcid,
                    "display_name": a.display_name,
                    "affiliation": a.affiliation,
                    "affiliations": a.affiliations,
                    "works_count": a.works_count,
                    "cited_by_count": a.cited_by_count,
                    "h_index": a.h_index,
                }
                for a in authors
            ],
            "total": len(authors),
        }
    elif author_id:
        from .discovery import get_author_by_id
        a = get_author_by_id(cfg.openalex_client, author_id, cache=cfg.openalex_cache)
        return {
            "author": {
                "openalex_id": a.openalex_id,
                "orcid": a.orcid,
                "display_name": a.display_name,
                "affiliation": a.affiliation,
                "affiliations": a.affiliations,
                "works_count": a.works_count,
                "cited_by_count": a.cited_by_count,
                "h_index": a.h_index,
            },
        }
    elif orcid:
        from .author_search import search_by_orcid
        a = search_by_orcid(cfg.openalex_client, orcid)
        return {
            "author": {
                "openalex_id": a.openalex_id,
                "orcid": a.orcid,
                "display_name": a.display_name,
                "affiliation": a.affiliation,
                "affiliations": a.affiliations,
                "works_count": a.works_count,
                "cited_by_count": a.cited_by_count,
                "h_index": a.h_index,
            },
        }
    else:
        return {"error": "Provide one of: query, author_id, or orcid"}


def discover_institutions(
    *,
    root: Path,
    query: str | None = None,
    institution_id: str | None = None,
) -> dict[str, Any]:
    """Search for institutions by name or fetch by OpenAlex ID.

    Returns ranked candidates with country, type, and works count.
    """
    cfg = _load_cfg(root)
    if query:
        from .discovery import search_institutions_by_name
        institutions = search_institutions_by_name(cfg.openalex_client, query)
        return {
            "query": query,
            "institutions": [
                {
                    "openalex_id": i.openalex_id,
                    "ror": i.ror,
                    "display_name": i.display_name,
                    "country_code": i.country_code,
                    "type": i.type,
                    "works_count": i.works_count,
                    "cited_by_count": i.cited_by_count,
                }
                for i in institutions
            ],
            "total": len(institutions),
        }
    elif institution_id:
        from .discovery import get_institution_by_id
        i = get_institution_by_id(cfg.openalex_client, institution_id, cache=cfg.openalex_cache)
        return {
            "institution": {
                "openalex_id": i.openalex_id,
                "ror": i.ror,
                "display_name": i.display_name,
                "country_code": i.country_code,
                "type": i.type,
                "works_count": i.works_count,
                "cited_by_count": i.cited_by_count,
            },
        }
    else:
        return {"error": "Provide one of: query or institution_id"}


def institution_works(
    *,
    root: Path,
    institution_id: str,
    since_year: int | None = None,
    min_citations: int | None = None,
) -> dict[str, Any]:
    """Fetch all works affiliated with an institution.

    Returns publications with DOI, title, year, journal, citation count.
    Cross-references against the local library to flag papers already ingested.
    """
    cfg = _load_cfg(root)
    from .discovery import get_institution_works as _get_works
    from .ingest import find_existing_dois

    works = _get_works(
        cfg.openalex_client,
        institution_id,
        since_year=since_year,
        min_citations=min_citations,
    )
    existing_dois = find_existing_dois(root)
    return {
        "institution_id": institution_id,
        "works": [
            {
                "openalex_id": w.openalex_id,
                "doi": w.doi,
                "title": w.title,
                "year": w.year,
                "journal": w.journal,
                "cited_by_count": w.cited_by_count,
                "is_oa": w.is_oa,
                "type": w.type,
                "is_retracted": w.is_retracted,
                "topics": w.topics,
                "in_library": bool(w.doi and w.doi.lower() in existing_dois),
            }
            for w in works
        ],
        "total": len(works),
    }


def institution_authors(
    *,
    root: Path,
    institution_id: str,
    min_works: int | None = None,
) -> dict[str, Any]:
    """Fetch authors affiliated with an institution (last known affiliation).

    Returns authors ranked by publication count, with h-index and affiliation.
    """
    cfg = _load_cfg(root)
    from .discovery import get_institution_authors as _get_authors

    authors = _get_authors(
        cfg.openalex_client,
        institution_id,
        min_works=min_works,
    )
    return {
        "institution_id": institution_id,
        "authors": [
            {
                "openalex_id": a.openalex_id,
                "orcid": a.orcid,
                "display_name": a.display_name,
                "affiliation": a.affiliation,
                "affiliations": a.affiliations,
                "works_count": a.works_count,
                "cited_by_count": a.cited_by_count,
                "h_index": a.h_index,
            }
            for a in authors
        ],
        "total": len(authors),
    }


def author_works_by_position(
    *,
    root: Path,
    author_id: str | None = None,
    orcid: str | None = None,
    position: str | None = None,
    since_year: int | None = None,
    min_citations: int | None = None,
) -> dict[str, Any]:
    """Fetch works by an author with optional position filtering.

    Accepts ``author_id`` (OpenAlex ID) or ``orcid``. If ``position`` is
    provided (first/middle/last), only returns papers where the author
    holds that position.

    Use ``position="last"`` to find "lab papers" where the author is PI.
    """
    cfg = _load_cfg(root)
    from .ingest import find_existing_dois

    # Resolve author ID from ORCID if needed
    resolved_id = author_id
    author_info = None
    if not resolved_id and orcid:
        from .author_search import search_by_orcid
        author = search_by_orcid(cfg.openalex_client, orcid)
        resolved_id = author.openalex_id
        author_info = {
            "openalex_id": author.openalex_id,
            "orcid": author.orcid,
            "display_name": author.display_name,
            "affiliation": author.affiliation,
            "affiliations": author.affiliations,
            "works_count": author.works_count,
            "cited_by_count": author.cited_by_count,
            "h_index": author.h_index,
        }
    elif not resolved_id:
        return {"error": "Provide one of: author_id or orcid"}

    from .discovery import get_author_works_by_position as _get_works

    works = _get_works(
        cfg.openalex_client,
        resolved_id,
        position=position,
        since_year=since_year,
        min_citations=min_citations,
    )
    existing_dois = find_existing_dois(root)
    result: dict[str, Any] = {
        "author_id": resolved_id,
        "position_filter": position,
        "works": [
            {
                "openalex_id": w.openalex_id,
                "doi": w.doi,
                "title": w.title,
                "year": w.year,
                "journal": w.journal,
                "cited_by_count": w.cited_by_count,
                "is_oa": w.is_oa,
                "type": w.type,
                "is_retracted": w.is_retracted,
                "topics": w.topics,
                "in_library": bool(w.doi and w.doi.lower() in existing_dois),
            }
            for w in works
        ],
        "total": len(works),
    }
    if author_info:
        result["author"] = author_info
    return result


def tag_vocab(*, root: Path) -> dict[str, Any]:
    """Return the current tag vocabulary (namespaces, values, aliases).

    Returns ``{"namespaces": {...}, "aliases": {...}, "known_tags": [...]}``.
    """
    from .tag_vocab import default_tag_vocab_path, known_tags, load_tag_vocab

    vocab = load_tag_vocab(default_tag_vocab_path(root))
    return {
        "namespaces": vocab.get("namespaces", {}),
        "aliases": vocab.get("aliases", {}),
        "known_tags": sorted(known_tags(vocab)),
    }


def biblio_summarize(
    citekey: str,
    *,
    root: Path,
    prompt_only: bool = False,
    force: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Generate a structured summary for a paper.

    If ``prompt_only=True``, returns only the assembled context prompt (no LLM call).
    Otherwise calls the Anthropic API to produce a summary saved to
    ``bib/derivatives/summaries/{citekey}.md``.

    Returns ``{"citekey": ..., "prompt": ..., "summary_path": ...,
               "summary_text": ..., "model_used": ..., "skipped": bool}``.
    """
    from .summarize import summarize

    return summarize(citekey, root, prompt_only=prompt_only, force=force, model=model)


# ---------------------------------------------------------------------------
# Collection tools
# ---------------------------------------------------------------------------


def collection_create(
    name: str,
    *,
    root: Path,
    query: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a collection (manual or smart/query-driven).

    If ``query`` is provided, creates a smart collection whose membership is
    dynamically resolved from the query.  Otherwise creates a manual collection.

    Returns ``{"collection": {...}}``.
    """
    cfg = _load_cfg(root)
    from .collections import create_collection

    col = create_collection(cfg, name, query=query, description=description)
    return {"collection": col}


def collection_list(*, root: Path) -> dict[str, Any]:
    """List all collections with membership counts.

    Returns ``{"collections": [...]}``.
    """
    cfg = _load_cfg(root)
    from .collections import list_collections_summary

    return {"collections": list_collections_summary(cfg)}


def collection_show(name: str, *, root: Path) -> dict[str, Any]:
    """Show a collection's details and resolved members.

    For smart collections, membership is computed dynamically.

    Returns ``{"name": ..., "smart": bool, "query": str|null, "citekeys": [...], "count": N}``.
    """
    cfg = _load_cfg(root)
    from .collections import _find_by_name, is_smart, load_collections, resolve_smart

    data = load_collections(cfg)
    col = _find_by_name(data, name)
    if col is None:
        return {"error": f"Collection '{name}' not found"}
    if is_smart(col):
        citekeys = resolve_smart(cfg, col["id"])
    else:
        citekeys = col.get("citekeys") or []
    return {
        "name": col["name"],
        "id": col["id"],
        "smart": is_smart(col),
        "query": col.get("query"),
        "citekeys": citekeys,
        "count": len(citekeys),
    }


def collection_update_query(name: str, query: str, *, root: Path) -> dict[str, Any]:
    """Update the query of a smart collection.

    Returns ``{"collection": {...}}`` or ``{"error": ...}``.
    """
    cfg = _load_cfg(root)
    from .collections import _find_by_name, load_collections, update_query

    data = load_collections(cfg)
    col = _find_by_name(data, name)
    if col is None:
        return {"error": f"Collection '{name}' not found"}
    updated = update_query(cfg, col["id"], query)
    if updated is None:
        return {"error": "Failed to update collection"}
    return {"collection": updated}


def biblio_autotag(
    citekeys: list[str],
    *,
    root: Path,
    tiers: list[str] | None = None,
    force: bool = False,
    model: str = "claude-haiku-4-5-20251001",
    threshold: int = 3,
) -> dict[str, Any]:
    """Auto-tag papers via LLM classification and/or reference propagation.

    Tiers: ``["llm"]``, ``["propagate"]``, or ``["llm", "propagate"]`` (default).
    Results are cached under ``bib/derivatives/autotag/``.

    Returns ``{"results": [{citekey, tiers, all_tags}], "count": N}``.
    """
    from .autotag import autotag

    results = []
    for ck in citekeys:
        key = ck.lstrip("@")
        result = autotag(
            key,
            root,
            tiers=tiers,
            force=force,
            model=model,
            threshold=threshold,
        )
        results.append(result)
    return {"results": results, "count": len(results)}


def biblio_concepts(
    citekey: str,
    *,
    root: Path,
    prompt_only: bool = False,
    force: bool = False,
    model: str = "claude-haiku-4-5-20251001",
) -> dict[str, Any]:
    """Extract key concepts from a paper.

    Returns ``{"citekey": ..., "concepts": {methods, datasets, metrics, domains, techniques},
               "concepts_path": ..., "skipped": bool}``.
    """
    from .concepts import extract_concepts

    return extract_concepts(citekey, root, prompt_only=prompt_only, force=force, model=model)


def biblio_concept_search(query: str, *, root: Path) -> dict[str, Any]:
    """Search the concept index for papers matching a concept query.

    Returns ``{"query": ..., "matches": [{concept, citekeys}], "total_matches": N}``.
    """
    from .concepts import search_concepts

    return search_concepts(query, root)


def biblio_concept_index(*, root: Path) -> dict[str, Any]:
    """Build/rebuild the cross-paper concept index.

    Returns ``{"total_papers": N, "total_concepts": N, "index_path": ...}``.
    """
    from .concepts import build_concept_index

    return build_concept_index(root)


def biblio_compare(
    citekeys: list[str],
    *,
    root: Path,
    dimensions: list[str] | None = None,
    prompt_only: bool = False,
    force: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Compare multiple papers across specified dimensions.

    Default dimensions: method, dataset, metrics, key findings, limitations.

    Returns ``{"citekeys": [...], "comparison_text": ..., "comparison_path": ..., "skipped": bool}``.
    """
    from .compare import compare

    return compare(
        citekeys, root,
        dimensions=dimensions,
        prompt_only=prompt_only,
        force=force,
        model=model,
    )


def biblio_reading_list(
    question: str,
    *,
    root: Path,
    count: int = 5,
    prompt_only: bool = False,
    model: str = "claude-haiku-4-5-20251001",
) -> dict[str, Any]:
    """Curate a reading list for a research question from unread/queued papers.

    Returns ``{"question": ..., "candidates_count": N, "recommendations": [...]}``.
    """
    from .reading_list import reading_list

    return reading_list(question, root, count=count, prompt_only=prompt_only, model=model)


def library_lint(*, root: Path) -> dict[str, Any]:
    """Lint all library.yml tags against the tag vocabulary.

    Returns ``{"non_vocab": [...], "duplicates": [...], "suggestions": [...]}``.
    """
    cfg = _load_cfg(root)
    from .library import load_library
    from .tag_vocab import default_tag_vocab_path, lint_library_tags, load_tag_vocab

    vocab = load_tag_vocab(default_tag_vocab_path(root))
    library = load_library(cfg)
    return lint_library_tags(library, vocab)


def pdf_validate(*, root: Path, fix: bool = False) -> dict[str, Any]:
    """Scan bib/articles/ for files that aren't valid PDFs (e.g. HTML paywall pages).

    Returns ``{"total": N, "valid": N, "invalid": [...]}`` where each invalid
    entry has ``citekey``, ``path``, ``header`` (first bytes), and ``size``.

    Args:
        fix: If True, delete invalid files so they can be re-fetched.
    """
    cfg = _load_cfg(root)
    pdf_root = cfg.pdf_root
    if not pdf_root.exists():
        return {"total": 0, "valid": 0, "invalid": []}

    valid = 0
    invalid = []
    total = 0
    for pdf_path in sorted(pdf_root.rglob("*.pdf")):
        total += 1
        try:
            with open(pdf_path, "rb") as f:
                header = f.read(5)
            if header == b"%PDF-":
                valid += 1
            else:
                entry = {
                    "citekey": pdf_path.parent.name,
                    "path": str(pdf_path.relative_to(root)),
                    "header": repr(header),
                    "size": pdf_path.stat().st_size,
                }
                if fix:
                    pdf_path.unlink()
                    entry["action"] = "deleted"
                invalid.append(entry)
        except Exception as e:
            invalid.append({
                "citekey": pdf_path.parent.name,
                "path": str(pdf_path.relative_to(root)),
                "error": str(e),
            })

    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "fix_applied": fix,
    }


def library_quality(*, root: Path) -> dict[str, Any]:
    """Scan the merged bibliography for entry quality issues.

    Returns per-tier counts and lists of problematic entries (noise, stub, sparse)
    with specific issues for each.
    """
    cfg = _load_cfg(root)
    bib_db = _load_bib_database(cfg)
    if bib_db is None:
        return {"error": "No merged bibliography found. Run biblio_merge() first."}

    from .quality import score_bib_database
    scored = score_bib_database(bib_db)

    by_tier: dict[str, list] = {"good": [], "sparse": [], "stub": [], "noise": []}
    for q in scored:
        by_tier[q.tier].append({
            "citekey": q.citekey,
            "score": q.score,
            "issues": list(q.issues),
            "has_doi": q.has_doi,
            "has_authors": q.has_authors,
            "has_year": q.has_year,
            "field_count": q.field_count,
        })

    return {
        "total": len(scored),
        "counts": {tier: len(entries) for tier, entries in by_tier.items()},
        "noise": by_tier["noise"],
        "stubs": by_tier["stub"],
        "sparse": by_tier["sparse"][:20],
    }


def library_dedup(*, root: Path) -> dict[str, Any]:
    """Detect duplicate papers by DOI, title similarity, or OpenAlex ID.

    Returns ``{"groups": [...], "count": int}`` where each group contains
    ``citekeys``, ``reason``, ``confidence``, ``suggested_keep``, and ``detail``.
    """
    cfg = _load_cfg(root)
    from .dedup import find_duplicates

    groups = find_duplicates(root, cfg=cfg)
    return {"groups": groups, "count": len(groups)}


# ---------------------------------------------------------------------------
# Compile
# ---------------------------------------------------------------------------


def biblio_compile(
    *,
    root: Path,
    sources: list[str] | None = None,
    output: str | None = None,
) -> dict[str, Any]:
    """Compile multiple .bib intermediates into a single compiled.bib.

    If sources/output not given, reads from .projio/render.yml
    (bib_sources and bibliography fields).

    Returns ``{"sources_read": N, "entries": N, "output": str, "skipped": [str]}``.
    """
    import yaml

    render_yml = root / ".projio" / "render.yml"
    render_data: dict[str, Any] = {}
    if render_yml.is_file():
        render_data = yaml.safe_load(render_yml.read_text(encoding="utf-8")) or {}

    source_paths: list[Path]
    if sources:
        source_paths = [(root / s).resolve() for s in sources]
    else:
        bib_sources = render_data.get("bib_sources", [".projio/biblio/merged.bib"])
        source_paths = [(root / s).resolve() for s in bib_sources]

    if output:
        out_path = (root / output).resolve()
    else:
        out_path = (root / render_data.get("bibliography", ".projio/render/compiled.bib")).resolve()

    from .bibtex import compile_bib

    skipped = [str(s.relative_to(root)) for s in source_paths if not s.exists()]
    n_sources, n_entries = compile_bib(source_paths, out_path)

    return {
        "sources_read": n_sources,
        "entries": n_entries,
        "output": str(out_path.relative_to(root)),
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Citation drafting
# ---------------------------------------------------------------------------


def biblio_cite_draft(
    text: str,
    *,
    root: Path,
    style: str = "latex",
    max_refs: int = 5,
    prompt_only: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Draft a citation paragraph grounding a claim in indexed papers.

    Uses RAG to find relevant passages, then LLM drafts a paragraph with
    ``\\cite{citekey}`` (LaTeX) or ``[@citekey]`` (Pandoc) citations.

    Returns ``{"text": ..., "style": ..., "passages": [...], "draft": ...,
               "model_used": ...}``.
    """
    from .cite_draft import cite_draft

    return cite_draft(
        text, root,
        style=style,
        max_refs=max_refs,
        prompt_only=prompt_only,
        model=model,
    )


# ---------------------------------------------------------------------------
# Literature review
# ---------------------------------------------------------------------------


def biblio_review(
    question: str,
    *,
    root: Path,
    seeds: list[str] | None = None,
    style: str = "latex",
    prompt_only: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Literature review: query-driven synthesis or seed-based planning.

    If ``seeds`` are provided, generates a review plan (gap analysis, expansion
    directions). Otherwise performs query-driven synthesis using RAG.

    Returns ``{"question": ..., "synthesis"|"plan": ..., "model_used": ...}``.
    """
    if seeds:
        from .lit_review import review_plan

        clean_seeds = [s.lstrip("@") for s in seeds]
        return review_plan(
            clean_seeds, question, root,
            prompt_only=prompt_only,
            model=model,
        )
    else:
        from .lit_review import review_query

        return review_query(
            question, root,
            style=style,
            prompt_only=prompt_only,
            model=model,
        )


# ---------------------------------------------------------------------------
# Presentation generation
# ---------------------------------------------------------------------------


def biblio_present(
    citekey: str,
    *,
    root: Path,
    template: str = "journal-club",
    prompt_only: bool = False,
    force: bool = False,
    model: str = "claude-sonnet-4-20250514",
) -> dict[str, Any]:
    """Generate a Marp slide deck from paper context.

    Templates: ``journal-club``, ``conference-talk``, ``lab-meeting``.
    If ``prompt_only=True``, returns only the assembled prompt (no LLM call).
    Otherwise calls the Anthropic API to produce slides saved to
    ``bib/derivatives/slides/{citekey}.md``.

    Returns ``{"citekey": ..., "prompt": ..., "slides_path": ...,
               "slides_text": ..., "model_used": ..., "skipped": bool,
               "template": ...}``.
    """
    from .present import generate_slides

    return generate_slides(
        citekey, root,
        template=template,
        prompt_only=prompt_only,
        force=force,
        model=model,
    )


def pool_promote(
    citekeys: list[str],
    *,
    root: Path,
    target: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote project-local papers into a pool.

    Returns ``{"promoted": [...], "already_in_pool": [...], "errors": [...]}``.
    """
    cfg = _load_cfg(root)
    from .pool import promote_to_pool

    # Resolve pool root: explicit target > config
    if target:
        pool_root = Path(target).expanduser().resolve()
    elif cfg.common_pool_path:
        pool_root = cfg.common_pool_path
    else:
        return {"error": "No pool configured. Set pool.path in biblio.yml or pass target."}

    results = promote_to_pool(cfg, pool_root, citekeys, dry_run=dry_run)

    promoted = [r.citekey for r in results if r.status == "promoted"]
    already = [r.citekey for r in results if r.status == "already_in_pool"]
    no_pdf = [r.citekey for r in results if r.status == "no_local_pdf"]
    errors = [{"citekey": r.citekey, "error": r.error} for r in results if r.status == "error"]
    dry = [r.citekey for r in results if r.status == "dry_run"]

    out: dict[str, Any] = {
        "promoted": promoted,
        "already_in_pool": already,
        "no_local_pdf": no_pdf,
        "errors": errors,
        "pool_root": str(pool_root),
    }
    if dry_run:
        out["dry_run"] = dry
    return out


def export_bibtex_entries(
    citekeys: list[str],
    *,
    root: Path,
) -> dict[str, Any]:
    """Export BibTeX entries for the given citekeys.

    Returns ``{"ok": True, "bibtex": "<bib content>", "count": N}``
    or ``{"error": "..."}`` on failure.
    """
    from .bibtex_export import export_bibtex

    try:
        bib_text = export_bibtex(citekeys, repo_root=root)
        # Count entries actually exported
        count = bib_text.count("\n@")
        if bib_text.lstrip().startswith("@"):
            count = max(count, 1)
        return {"ok": True, "bibtex": bib_text, "count": count}
    except (FileNotFoundError, KeyError) as exc:
        return {"error": str(exc)}


def zotero_pull(
    *,
    root: Path,
    collection: str | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Pull items and PDFs from Zotero into the biblio workspace.

    Returns ``{"pulled": N, "skipped": N, "deleted": N, "pdfs_downloaded": N,
    "citekeys": [...], "errors": [...]}``.
    """
    import yaml
    from .zotero import load_zotero_config, pull as _pull

    cfg_path = _load_cfg(root).repo_root  # just need repo_root for config path
    # Re-read raw payload for zotero section
    from .config import default_config_path
    config_file = default_config_path(root=root)
    raw: dict[str, Any] = {}
    if config_file.exists():
        raw = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}

    zcfg = load_zotero_config(raw, root)
    if zcfg is None:
        return {"error": "No zotero section in biblio.yml. Add zotero.library_id to enable."}

    result = _pull(
        repo_root=root,
        zotero_cfg=zcfg,
        collection=collection,
        tags=tags,
        dry_run=dry_run,
    )
    return {
        "pulled": result.pulled,
        "skipped": result.skipped,
        "deleted": result.deleted,
        "pdfs_downloaded": result.pdfs_downloaded,
        "citekeys": result.citekeys,
        "errors": result.errors,
        "dry_run": result.dry_run,
    }


def zotero_status(*, root: Path) -> dict[str, Any]:
    """Return Zotero sync state for the project.

    Returns library info, last sync time, item counts.
    """
    import yaml
    from .zotero import load_zotero_config, status as _status

    from .config import default_config_path
    config_file = default_config_path(root=root)
    raw: dict[str, Any] = {}
    if config_file.exists():
        raw = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}

    zcfg = load_zotero_config(raw, root)
    if zcfg is None:
        return {"error": "No zotero section in biblio.yml. Add zotero.library_id to enable."}

    return _status(zotero_cfg=zcfg)


def zotero_push(
    *,
    root: Path,
    citekeys: list[str] | None = None,
    push_tags: bool = True,
    push_notes: bool = False,
    push_ids: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Push biblio enrichments back to Zotero items.

    Returns ``{"updated": N, "created": N, "skipped": N,
    "conflicts": [...], "errors": [...]}``.
    """
    import yaml
    from .zotero import load_zotero_config, push as _push

    from .config import default_config_path
    config_file = default_config_path(root=root)
    raw: dict[str, Any] = {}
    if config_file.exists():
        raw = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}

    zcfg = load_zotero_config(raw, root)
    if zcfg is None:
        return {"error": "No zotero section in biblio.yml. Add zotero.library_id to enable."}

    result = _push(
        repo_root=root,
        zotero_cfg=zcfg,
        citekeys=citekeys,
        push_tags=push_tags,
        push_notes=push_notes,
        push_ids=push_ids,
        force=force,
        dry_run=dry_run,
    )
    return {
        "updated": result.updated,
        "created": result.created,
        "skipped": result.skipped,
        "conflicts": result.conflicts,
        "errors": result.errors,
        "dry_run": result.dry_run,
    }


# ---------------------------------------------------------------------------
# Enrichment tools
# ---------------------------------------------------------------------------


def enrich(
    *,
    root: Path,
    citekeys: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run OpenAlex enrichment: persist topics/keywords/type per citekey.

    Reads resolved.jsonl and writes per-citekey YAML to
    ``bib/derivatives/openalex/{citekey}.yml``.

    Returns ``{"enriched": N, "skipped": N, "errors": [...], "output_dir": str}``.
    """
    try:
        from .openalex.openalex_enrich import enrich_resolved

        return enrich_resolved(root, citekeys=citekeys, force=force)
    except Exception as e:
        return {"error": str(e)}


def enrich_topic_tags(
    *,
    root: Path,
    citekeys: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Populate library.yml tags from OpenAlex enrichment data.

    Maps OpenAlex topics/keywords to ``oa:``-prefixed tags and adds them
    to library.yml entries (union merge — never removes existing tags).

    Returns ``{"updated": N, "unchanged": N, "missing_enrichment": N, ...}``.
    """
    try:
        from .openalex.topic_tags import populate_library_tags

        return populate_library_tags(root, citekeys=citekeys, dry_run=dry_run)
    except Exception as e:
        return {"error": str(e)}
