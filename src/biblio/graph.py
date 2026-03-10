from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .citekeys import add_citekeys_md, load_citekeys_md
from .ingest import IngestRecord, assign_citekeys, default_import_bib_path, render_bibtex, write_import_bib
from .openalex.openalex_cache import OpenAlexCache
from .openalex.openalex_client import OpenAlexClient, OpenAlexClientConfig
from ._pybtex_utils import parse_bibtex_file


@dataclass(frozen=True)
class GraphExpandResult:
    total_inputs: int
    seeds_with_openalex: int
    candidates: int
    output_path: Path


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
    citekeys_path = repo_root / "bib" / "config" / "citekeys.md"
    if citekeys_path.exists():
        keys.update(load_citekeys_md(citekeys_path))
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
    client = OpenAlexClient(cfg)
    try:
        work: dict[str, Any]
        normalized_id = _normalize_openalex_id(openalex_id)
        if normalized_id:
            work = _load_or_fetch_work(client=client, cache=cache, openalex_id=normalized_id, force=force)
        elif doi:
            work = client.get_work_by_doi(doi)
            normalized_id = _normalize_openalex_id(str(work.get("id") or ""))
            if normalized_id:
                cache.save_json(cache.path_for_work_id(normalized_id), work)
        else:
            raise ValueError("Either doi or openalex_id is required")
    finally:
        client.close()

    record = IngestRecord(
        source_type="openalex_add",
        source_ref=doi or (normalized_id or ""),
        entry_type="article",
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
        doi=_doi_from_work(work),
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
                        if ref_id is None or ref_id in all_seed_ids:
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
    if progress_cb is not None:
        progress_cb({"phase": "done", "completed": total, "total": total, "seed_openalex_id": None, "candidates": len(all_items)})
    return GraphExpandResult(
        total_inputs=len(active_records),
        seeds_with_openalex=len(active_seed_ids),
        candidates=len(all_items),
        output_path=output_path,
    )
