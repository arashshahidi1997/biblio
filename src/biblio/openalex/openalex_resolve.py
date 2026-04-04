from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .._pybtex_utils import parse_bibtex_file, require_pybtex
from .openalex_cache import OpenAlexCache, normalize_doi
from .openalex_client import OpenAlexClient, OpenAlexClientConfig


def _title_norm(s: str) -> str:
    return " ".join((s or "").lower().replace("{", "").replace("}", "").split())


def _year_from_entry(entry: Any) -> int | None:
    try:
        year = entry.fields.get("year")
    except Exception:
        return None
    if not year:
        return None
    try:
        return int(str(year).strip().split("-", 1)[0])
    except Exception:
        return None


def _doi_from_entry(entry: Any) -> str | None:
    try:
        doi = entry.fields.get("doi")
    except Exception:
        return None
    d = normalize_doi(str(doi)) if doi else None
    return d


def _title_from_entry(entry: Any) -> str | None:
    try:
        title = entry.fields.get("title")
    except Exception:
        return None
    if not title:
        return None
    return str(title).strip().strip("{}").strip() or None


def _pick_best_title_match(title: str, candidates: list[dict[str, Any]], year: int | None) -> tuple[dict[str, Any] | None, float]:
    target = _title_norm(title)
    if not target:
        return (None, 0.0)
    best: dict[str, Any] | None = None
    best_score = 0.0
    for cand in candidates:
        name = str(cand.get("display_name") or "")
        score = SequenceMatcher(a=target, b=_title_norm(name)).ratio()
        if year is not None:
            try:
                y = int(cand.get("publication_year"))
            except Exception:
                y = None
            if y is not None and y == year:
                score = min(1.0, score + 0.05)
        if score > best_score:
            best_score = score
            best = cand
    return best, float(best_score)


@dataclass(frozen=True)
class ResolveOptions:
    prefer_doi: bool
    fallback_title_search: bool
    per_page: int
    strict: bool
    force: bool


def iter_srcbib_entries(src_dir: Path, src_glob: str) -> Iterator[tuple[str, Path, Any]]:
    require_pybtex("OpenAlex resolution")

    for bib_path in sorted(p for p in src_dir.glob(src_glob) if p.is_file()):
        db = parse_bibtex_file(bib_path)
        for citekey, entry in sorted(db.entries.items(), key=lambda kv: kv[0]):
            yield citekey, bib_path, entry


def _work_to_minimal(work: dict[str, Any]) -> dict[str, Any]:
    return {
        "openalex_id": work.get("id"),
        "openalex_url": (work.get("ids") or {}).get("openalex") if isinstance(work.get("ids"), dict) else work.get("id"),
        "display_name": work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "authorships": work.get("authorships") if isinstance(work.get("authorships"), list) else None,
        "topics": work.get("topics") if isinstance(work.get("topics"), list) else None,
        "primary_topic": work.get("primary_topic") if isinstance(work.get("primary_topic"), dict) else None,
        "keywords": work.get("keywords") if isinstance(work.get("keywords"), list) else None,
        "type": work.get("type"),
        "is_retracted": work.get("is_retracted"),
        "counts_by_year": work.get("counts_by_year") if isinstance(work.get("counts_by_year"), list) else None,
        "referenced_works_count": len(work.get("referenced_works") or []) if isinstance(work.get("referenced_works"), list) else None,
    }


def resolve_srcbib_to_openalex(
    *,
    cfg: OpenAlexClientConfig,
    cache: OpenAlexCache,
    src_dir: Path,
    src_glob: str,
    out_path: Path,
    out_format: str,
    limit: int | None,
    opts: ResolveOptions,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, int]:
    """
    Resolve srcbib entries to OpenAlex works and write JSONL/CSV.

    Returns counts: {"total": N, "resolved": R, "unresolved": U, "errors": E}
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    client = OpenAlexClient(cfg)
    total = 0
    resolved = 0
    unresolved = 0
    errors = 0

    records: list[dict[str, Any]] = []
    entries = list(iter_srcbib_entries(src_dir, src_glob))
    if limit is not None:
        entries = entries[: int(limit)]
    total = len(entries)
    if progress_cb is not None:
        progress_cb(
            {
                "phase": "start",
                "completed": 0,
                "total": total,
                "citekey": None,
                "resolved": 0,
                "unresolved": 0,
                "errors": 0,
            }
        )
    try:
        # -- Batch DOI pre-resolution: fetch uncached DOIs in batches of 50 --
        if opts.prefer_doi:
            uncached_dois: list[str] = []
            for _ck, _bp, _entry in entries:
                d = _doi_from_entry(_entry)
                if d and (opts.force or cache.load_json(cache.path_for_doi(d)) is None):
                    uncached_dois.append(d)
            if uncached_dois:
                try:
                    batch_results = client.get_works_by_dois(uncached_dois)
                    for work_data in batch_results:
                        w_doi = work_data.get("doi") or ""
                        if isinstance(w_doi, str) and w_doi.strip():
                            norm = normalize_doi(w_doi)
                            if norm:
                                cache.save_json(cache.path_for_doi(norm), work_data)
                except Exception:
                    pass  # Fall back to per-entry resolution

        for index, (citekey, bib_path, entry) in enumerate(entries, start=1):
            doi = _doi_from_entry(entry)
            title = _title_from_entry(entry)
            year = _year_from_entry(entry)

            rec: dict[str, Any] = {
                "citekey": citekey,
                "source_bib": str(bib_path.name),
                "doi": doi,
                "title_bib": title,
                "year_bib": year,
                "resolution_method": "unresolved",
                "resolution_confidence": 0.0,
                "error": None,
            }

            try:
                work: dict[str, Any] | None = None
                if opts.prefer_doi and doi:
                    cache_path = cache.path_for_doi(doi)
                    cached = None if opts.force else cache.load_json(cache_path)
                    if cached is None:
                        # Single-DOI fallback for entries missed by batch
                        cached = client.get_work_by_doi(doi)
                        cache.save_json(cache_path, cached)
                    work = cached
                    rec["resolution_method"] = "doi"
                    rec["resolution_confidence"] = 1.0

                if work is None and opts.fallback_title_search and title:
                    q = title
                    cache_path = cache.path_for_search(q)
                    cached = None if opts.force else cache.load_json(cache_path)
                    if cached is None:
                        results = client.search_works(q, per_page=opts.per_page)
                        cached = {"results": results}
                        cache.save_json(cache_path, cached)
                    results = cached.get("results") if isinstance(cached, dict) else None
                    candidates = [c for c in (results or []) if isinstance(c, dict)]
                    best, score = _pick_best_title_match(title, candidates, year)
                    if best is not None and score >= 0.70:
                        work = best
                        rec["resolution_method"] = "title_search"
                        rec["resolution_confidence"] = score

                if work is None:
                    unresolved += 1
                else:
                    rec.update(_work_to_minimal(work))
                    resolved += 1
            except Exception as e:
                errors += 1
                rec["error"] = str(e)
                if opts.strict:
                    raise

            records.append(rec)
            if progress_cb is not None:
                progress_cb(
                    {
                        "phase": "resolve",
                        "completed": index,
                        "total": total,
                        "citekey": citekey,
                        "resolved": resolved,
                        "unresolved": unresolved,
                        "errors": errors,
                    }
                )
    finally:
        client.close()

    # Deterministic ordering: by source_bib then citekey
    records.sort(key=lambda r: (str(r.get("source_bib") or ""), str(r.get("citekey") or "")))

    if out_format == "jsonl":
        with out_path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    elif out_format == "csv":
        # Flatten lists/dicts as JSON strings for CSV stability.
        fieldnames = sorted({k for rec in records for k in rec.keys()})
        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for rec in records:
                row: dict[str, Any] = {}
                for k in fieldnames:
                    v = rec.get(k)
                    if isinstance(v, (dict, list)):
                        row[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
                    else:
                        row[k] = v
                w.writerow(row)
    else:
        raise ValueError(f"Unsupported format: {out_format!r}")

    if progress_cb is not None:
        progress_cb(
            {
                "phase": "done",
                "completed": total,
                "total": total,
                "citekey": None,
                "resolved": resolved,
                "unresolved": unresolved,
                "errors": errors,
            }
        )

    return {"total": total, "resolved": resolved, "unresolved": unresolved, "errors": errors}
