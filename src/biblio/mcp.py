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
