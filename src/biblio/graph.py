from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from .citekeys import add_citekeys_md, load_active_citekeys
from .ingest import (
    OPENALEX_ENTRY_TYPES,
    IngestRecord,
    assign_citekeys,
    default_import_bib_path,
    fetch_doi_csl,
    openalex_matches_doi,
    record_from_csl,
    render_bibtex,
    write_import_bib,
)
from .openalex.openalex_cache import OpenAlexCache
from .openalex.openalex_client import OpenAlexClient, OpenAlexClientConfig
from ._pybtex_utils import parse_bibtex_file


@dataclass(frozen=True)
class GraphExpandResult:
    total_inputs: int
    seeds_with_openalex: int
    candidates: int
    output_path: Path
    local_edges: int = 0
    local_edges_path: Path | None = None


LOCAL_EDGES_NAME = "local_edges.json"


def _seed_citekeys(records: list[dict[str, Any]]) -> dict[str, str]:
    out = {}
    for record in records:
        sid = _normalize_openalex_id(record.get("openalex_id"))
        if sid and record.get("citekey"):
            out[sid] = str(record["citekey"])
    return out


def _local_edge(seed_by_id: dict[str, str], source_id: str, target_id: str) -> dict[str, Any]:
    return {
        "source_citekey": seed_by_id.get(source_id),
        "target_citekey": seed_by_id.get(target_id),
        "source_openalex_id": source_id,
        "target_openalex_id": target_id,
        "relation": "references",
    }


def write_local_edges(path: Path, edges: list[dict[str, Any]], *, merge: bool = True) -> list[dict[str, Any]]:
    """Write citation edges between held papers, merged with the existing file."""
    existing: list[dict[str, Any]] = []
    if merge and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        existing = [e for e in payload if isinstance(e, dict)] if isinstance(payload, list) else []
    by_key = {(e.get("source_openalex_id"), e.get("target_openalex_id")): e for e in existing}
    for edge in edges:
        by_key[(edge["source_openalex_id"], edge["target_openalex_id"])] = edge
    out = sorted(by_key.values(), key=lambda e: (str(e.get("source_citekey")), str(e.get("target_citekey"))))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def build_local_edges(
    *,
    cfg: OpenAlexClientConfig,
    cache: OpenAlexCache,
    records: list[dict[str, Any]],
    out_path: str | Path,
    fetch_missing: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Citation edges between held papers from their OpenAlex ``referenced_works``.

    Reads seed works from the OpenAlex cache; with ``fetch_missing`` it fetches
    the seeds that are not cached. Returns (edges written, seeds without a work).
    """
    seed_by_id = _seed_citekeys(records)
    edges: list[dict[str, Any]] = []
    missing = 0
    client = OpenAlexClient(cfg) if fetch_missing else None
    try:
        for seed_id in sorted(seed_by_id):
            work = cache.load_json(cache.path_for_work_id(seed_id))
            if work is None and client is not None:
                work = _load_or_fetch_work(client=client, cache=cache, openalex_id=seed_id, force=False)
            if work is None:
                missing += 1
                continue
            for raw_ref in work.get("referenced_works") or []:
                ref_id = _normalize_openalex_id(raw_ref) if isinstance(raw_ref, str) else None
                if ref_id and ref_id != seed_id and ref_id in seed_by_id:
                    edges.append(_local_edge(seed_by_id, seed_id, ref_id))
    finally:
        if client is not None:
            client.close()
    return write_local_edges(Path(out_path), edges), missing


@dataclass(frozen=True)
class AddPaperResult:
    citekey: str
    output_path: Path
    citekeys_path: Path
    openalex_id: str | None
    doi: str | None


def load_openalex_seed_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return records
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _normalize_openalex_id(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("http"):
        raw = raw.rstrip("/").split("/")[-1]
    return raw or None


def _load_or_fetch_work(
    *,
    client: OpenAlexClient,
    cache: OpenAlexCache,
    openalex_id: str,
    force: bool,
) -> dict[str, Any]:
    cache_path = cache.path_for_work_id(openalex_id)
    cached = None if force else cache.load_json(cache_path)
    if cached is not None:
        return cached
    payload = client.get_work(openalex_id)
    cache.save_json(cache_path, payload)
    return payload


def _openalex_url(openalex_id: str | None) -> str | None:
    return f"https://openalex.org/{openalex_id}" if openalex_id else None


def _work_to_candidate(*, seed_id: str, work: dict[str, Any], direction: str) -> dict[str, Any] | None:
    target_id = _normalize_openalex_id(str(work.get("id") or ""))
    if not target_id:
        return None
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    doi = ids.get("doi") if isinstance(ids, dict) else None
    return {
        "source": "openalex_graph_expansion",
        "seed_openalex_id": seed_id,
        "openalex_id": target_id,
        "openalex_url": _openalex_url(target_id),
        "direction": direction,
        "display_name": work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "doi": doi,
    }


def _collect_existing_citekeys(repo_root: Path) -> set[str]:
    keys: set[str] = set()
    # Load active citekeys from merged bib (or srcbib fallback)
    from .config import load_biblio_config
    try:
        _cfg = load_biblio_config(".projio/biblio/biblio.yml", root=repo_root)
        keys.update(load_active_citekeys(_cfg))
    except Exception:
        pass  # config missing — srcbib scan below is sufficient
    src_dir = repo_root / "bib" / "srcbib"
    if src_dir.exists():
        for bib_path in sorted(src_dir.glob("*.bib")):
            db = parse_bibtex_file(bib_path)
            keys.update(str(k) for k in db.entries.keys())
    main_bib = repo_root / "bib" / "main.bib"
    if main_bib.exists():
        db = parse_bibtex_file(main_bib)
        keys.update(str(k) for k in db.entries.keys())
    return keys


def _unique_assign_record(record: IngestRecord, *, existing: set[str]) -> tuple[str, IngestRecord]:
    base = assign_citekeys([record])[0][0]
    citekey = base
    idx = 2
    while citekey in existing:
        citekey = f"{base}{idx}"
        idx += 1
    existing.add(citekey)
    return citekey, record


def _work_authors(work: dict[str, Any]) -> tuple[str, ...]:
    authors: list[str] = []
    authorships = work.get("authorships")
    if isinstance(authorships, list):
        for item in authorships:
            if not isinstance(item, dict):
                continue
            author = item.get("author")
            if isinstance(author, dict):
                name = str(author.get("display_name") or "").strip()
                if name:
                    authors.append(name)
    return tuple(authors)


def _doi_from_work(work: dict[str, Any]) -> str | None:
    ids = work.get("ids")
    if isinstance(ids, dict):
        doi = ids.get("doi")
        if isinstance(doi, str) and doi.strip():
            raw = doi.strip()
            if raw.lower().startswith("https://doi.org/"):
                return raw[len("https://doi.org/") :]
            return raw
    doi = work.get("doi")
    if isinstance(doi, str) and doi.strip():
        return doi.strip()
    return None


def add_openalex_work_to_bib(
    *,
    cfg: OpenAlexClientConfig,
    cache: OpenAlexCache,
    repo_root: str | Path,
    doi: str | None = None,
    openalex_id: str | None = None,
    out_path: str | Path | None = None,
    citekeys_path: str | Path | None = None,
    force: bool = False,
) -> AddPaperResult:
    root = Path(repo_root).expanduser().resolve()
    output_path = Path(out_path).expanduser().resolve() if out_path is not None else default_import_bib_path(root)
    ck_path = Path(citekeys_path).expanduser().resolve() if citekeys_path is not None else (root / "bib" / "config" / "citekeys.md").resolve()
    # For a DOI, bibliographic metadata comes from the DOI registry; OpenAlex
    # supplies the work ID, and the record only when the registry has none and
    # the OpenAlex work carries the same DOI.
    registry = fetch_doi_csl(doi) if doi and not openalex_id else None
    client = OpenAlexClient(cfg)
    work: dict[str, Any] | None = None
    try:
        normalized_id = _normalize_openalex_id(openalex_id)
        if normalized_id:
            work = _load_or_fetch_work(client=client, cache=cache, openalex_id=normalized_id, force=force)
        elif doi:
            try:
                work = client.get_work_by_doi(doi)
            except Exception:
                if registry is None:
                    raise
                work = None
            if work is not None and not openalex_matches_doi(work, doi):
                work = None
            normalized_id = _normalize_openalex_id(str((work or {}).get("id") or ""))
            if normalized_id and work is not None:
                cache.save_json(cache.path_for_work_id(normalized_id), work)
        else:
            raise ValueError("Either doi or openalex_id is required")
    finally:
        client.close()

    if registry is not None:
        csl_record = record_from_csl(registry, source_type="doi_add", source_ref=str(doi))
        record = replace(
            csl_record,
            doi=csl_record.doi or doi,
            url=_openalex_url(normalized_id) if normalized_id else csl_record.url,
            raw_id=normalized_id or doi,
        )
    elif work is not None:
        record = IngestRecord(
            source_type="openalex_add",
            source_ref=doi or (normalized_id or ""),
            entry_type=OPENALEX_ENTRY_TYPES.get(str(work.get("type") or "article"), "misc"),
            title=str(work.get("display_name") or "").strip() or None,
            authors=_work_authors(work),
            year=str(work.get("publication_year") or "").strip() or None,
            doi=_doi_from_work(work),
            url=_openalex_url(normalized_id),
            journal=None,
            booktitle=None,
            raw_id=normalized_id or doi,
            file=None,
        )
    else:
        raise ValueError(f"No metadata for DOI {doi}: the registry has no record and OpenAlex returned a different work")
    existing = _collect_existing_citekeys(root)
    citekey, assigned_record = _unique_assign_record(record, existing=existing)
    bibtex_text = render_bibtex([(citekey, assigned_record)])
    write_import_bib(output_path, bibtex_text)
    add_citekeys_md(ck_path, [citekey])
    return AddPaperResult(
        citekey=citekey,
        output_path=output_path,
        citekeys_path=ck_path,
        openalex_id=normalized_id,
        doi=record.doi,
    )


def _load_existing_candidates(output_path: Path) -> tuple[list[dict[str, Any]], set[str], int]:
    """Load existing graph_candidates.json.

    Returns (existing_items, existing_keys, max_hop).
    existing_keys is the set of "{seed}|{direction}|{target}" strings already stored.
    """
    if not output_path.exists():
        return [], set(), 0
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return [], set(), 0
    if not isinstance(payload, list):
        return [], set(), 0
    items = [item for item in payload if isinstance(item, dict)]
    keys = {
        f"{item.get('seed_openalex_id')}|{item.get('direction', 'references')}|{item.get('openalex_id')}"
        for item in items
        if item.get("seed_openalex_id") and item.get("openalex_id")
    }
    max_hop = max((int(item.get("hop", 1)) for item in items), default=0)
    return items, keys, max_hop


def expand_openalex_reference_graph(
    *,
    cfg: OpenAlexClientConfig,
    cache: OpenAlexCache,
    records: list[dict[str, Any]],
    out_path: str | Path,
    direction: str = "references",
    force: bool = False,
    merge: bool = True,
    seed_citekeys: list[str] | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> GraphExpandResult:
    """Expand the OpenAlex reference graph.

    Args:
        merge: If True, load existing graph_candidates.json and append new results
               without re-processing already-seen (seed, direction, target) triples.
               Hop number is auto-incremented from the max hop in the existing file.
        seed_citekeys: If given, only expand seeds whose citekey is in this list.
                       Useful for per-paper expansion without touching the full corpus.
    """
    client = OpenAlexClient(cfg)
    output_path = Path(out_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Optionally filter to specific seeds
    active_records = records
    if seed_citekeys:
        wanted = set(seed_citekeys)
        active_records = [r for r in records if str(r.get("citekey") or "") in wanted]

    # All openalex IDs in the full corpus (not just active seeds) — used to skip known papers
    all_seed_ids = {
        sid
        for record in records
        for sid in [_normalize_openalex_id(record.get("openalex_id"))]
        if sid is not None
    }
    active_seed_ids = {
        sid
        for record in active_records
        for sid in [_normalize_openalex_id(record.get("openalex_id"))]
        if sid is not None
    }

    seed_by_id = _seed_citekeys(records)
    local_edges: list[dict[str, Any]] = []

    # Load existing candidates for merge mode
    existing_items: list[dict[str, Any]] = []
    candidates_seen: set[str] = set()
    current_hop = 1
    if merge:
        existing_items, candidates_seen, max_hop = _load_existing_candidates(output_path)
        current_hop = max_hop + 1

    discovered: list[dict[str, Any]] = []
    total = len(active_seed_ids)

    if progress_cb is not None:
        progress_cb({"phase": "start", "completed": 0, "total": total, "seed_openalex_id": None, "candidates": len(existing_items)})

    try:
        completed = 0
        for record in active_records:
            seed_id = _normalize_openalex_id(record.get("openalex_id"))
            if seed_id is None:
                continue

            work = _load_or_fetch_work(client=client, cache=cache, openalex_id=seed_id, force=force)
            if direction in {"references", "both"}:
                refs = work.get("referenced_works")
                if isinstance(refs, list):
                    for raw_ref in refs:
                        if not isinstance(raw_ref, str):
                            continue
                        ref_id = _normalize_openalex_id(raw_ref)
                        if ref_id is None:
                            continue
                        if ref_id in all_seed_ids:
                            # held paper: a corpus edge, not a candidate
                            if ref_id != seed_id:
                                local_edges.append(_local_edge(seed_by_id, seed_id, ref_id))
                            continue
                        key = f"{seed_id}|references|{ref_id}"
                        if key in candidates_seen:
                            continue
                        candidates_seen.add(key)
                        try:
                            ref_work = _load_or_fetch_work(client=client, cache=cache, openalex_id=ref_id, force=force)
                        except Exception:
                            ref_work = {"id": _openalex_url(ref_id)}
                        candidate = _work_to_candidate(seed_id=seed_id, work=ref_work, direction="references")
                        if candidate is not None:
                            candidate["hop"] = current_hop
                            discovered.append(candidate)
            if direction in {"citing", "both"}:
                citing_works = client.filter_works(filter_expr=f"cites:{seed_id}", per_page=cfg.per_page)
                for citing_work in citing_works:
                    candidate = _work_to_candidate(seed_id=seed_id, work=citing_work, direction="citing")
                    if candidate is None:
                        continue
                    ref_id = str(candidate["openalex_id"])
                    if ref_id in all_seed_ids:
                        if ref_id != seed_id:
                            local_edges.append(_local_edge(seed_by_id, ref_id, seed_id))
                        continue
                    key = f"{seed_id}|citing|{ref_id}"
                    if key in candidates_seen:
                        continue
                    candidates_seen.add(key)
                    candidate["hop"] = current_hop
                    discovered.append(candidate)
            completed += 1
            if progress_cb is not None:
                progress_cb({"phase": "expand", "completed": completed, "total": total, "seed_openalex_id": seed_id, "candidates": len(existing_items) + len(discovered)})
    finally:
        client.close()

    all_items = existing_items + discovered
    all_items.sort(key=lambda item: (int(item.get("hop", 1)), str(item.get("seed_openalex_id")), str(item.get("direction") or ""), str(item.get("openalex_id"))))
    output_path.write_text(json.dumps(all_items, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    local_path = output_path.parent / LOCAL_EDGES_NAME
    written_local = write_local_edges(local_path, local_edges, merge=merge)
    if progress_cb is not None:
        progress_cb({"phase": "done", "completed": total, "total": total, "seed_openalex_id": None, "candidates": len(all_items)})
    return GraphExpandResult(
        total_inputs=len(active_records),
        seeds_with_openalex=len(active_seed_ids),
        candidates=len(all_items),
        output_path=output_path,
        local_edges=len(written_local),
        local_edges_path=local_path,
    )
