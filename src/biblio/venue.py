"""Backfill the venue (``journal``) of @article entries that lack one.

Entries imported from OpenAlex before the DOI registry became the metadata
source carry a DOI and an OpenAlex URL but no journal, which bibliography
renderers (pybtex, mkdocs-bibtex) reject. The venue comes from the DOI
registry (CSL ``container-title``); a cached OpenAlex work is used only when
the registry has none and the work carries the same DOI.

The bib file is edited in place: one ``journal = {...}`` line is inserted
after each entry's opening line, so the rest of the file is unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ._pybtex_utils import parse_bibtex_file


@dataclass
class VenueBackfillResult:
    bib_path: str
    candidates: int = 0  # @article entries with a DOI and no journal
    filled: dict[str, str] = field(default_factory=dict)  # citekey -> venue
    sources: dict[str, str] = field(default_factory=dict)  # citekey -> "registry" | "openalex"
    unresolved: list[str] = field(default_factory=list)
    no_doi: list[str] = field(default_factory=list)
    dry_run: bool = True


def _csl_container(item: Mapping[str, Any] | None) -> str | None:
    if not item:
        return None
    value = item.get("container-title")
    if isinstance(value, list):
        value = value[0] if value else None
    text = " ".join(str(value or "").split())
    return text or None


def _openalex_venue(work: Mapping[str, Any] | None, doi: str) -> str | None:
    from .ingest import openalex_matches_doi

    if not work or not openalex_matches_doi(work, doi):
        return None
    source = (work.get("primary_location") or {}).get("source") or {}
    text = " ".join(str(source.get("display_name") or "").split()) if isinstance(source, Mapping) else ""
    return text or None


def _openalex_id(url: str | None) -> str | None:
    m = re.search(r"openalex\.org/(W\d+)", url or "")
    return m.group(1) if m else None


def _insert_field(text: str, citekey: str, name: str, value: str) -> str:
    from .ingest import _bibtex_escape

    pattern = re.compile(r"^(@[A-Za-z]+\s*\{\s*" + re.escape(citekey) + r"\s*,[ \t]*\n)", re.M)
    m = pattern.search(text)
    if not m:
        raise ValueError(f"entry {citekey} not found as '@type{{{citekey},' on its own line")
    line = f"  {name} = {{{_bibtex_escape(value)}}},\n"
    return text[: m.end()] + line + text[m.end():]


def backfill_venues(
    bib_path: str | Path,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    fetch_csl: Callable[[str], Mapping[str, Any] | None] | None = None,
    load_openalex_work: Callable[[str], Mapping[str, Any] | None] | None = None,
) -> VenueBackfillResult:
    """Fill ``journal`` on @article entries of ``bib_path`` that have a DOI but no journal.

    ``fetch_csl`` defaults to the DOI registry lookup; ``load_openalex_work``
    (OpenAlex work id -> cached payload) is optional and never fetches.
    """
    from .ingest import _normalize_doi, fetch_doi_csl

    fetch_csl = fetch_csl or fetch_doi_csl
    path = Path(bib_path).expanduser().resolve()
    db = parse_bibtex_file(path)
    result = VenueBackfillResult(bib_path=str(path), dry_run=dry_run)

    todo: list[tuple[str, str, str | None]] = []
    for key, entry in db.entries.items():
        if entry.type.lower() != "article" or (entry.fields.get("journal") or "").strip():
            continue
        doi = _normalize_doi(entry.fields.get("doi"))
        if not doi:
            result.no_doi.append(key)
            continue
        todo.append((key, doi, entry.fields.get("url")))
    result.candidates = len(todo)
    if limit is not None:
        todo = todo[:limit]

    for key, doi, url in todo:
        venue = _csl_container(fetch_csl(doi))
        source = "registry"
        if venue is None and load_openalex_work is not None:
            work_id = _openalex_id(url)
            venue = _openalex_venue(load_openalex_work(work_id), doi) if work_id else None
            source = "openalex"
        if venue is None:
            result.unresolved.append(key)
            continue
        result.filled[key] = venue
        result.sources[key] = source

    if result.filled and not dry_run:
        text = path.read_text(encoding="utf-8")
        for key, venue in result.filled.items():
            text = _insert_field(text, key, "journal", venue)
        path.write_text(text, encoding="utf-8")
    return result


def cached_openalex_loader(cache: Any) -> Callable[[str], Mapping[str, Any] | None]:
    """OpenAlex work id -> cached payload (no network)."""
    def _load(work_id: str) -> Mapping[str, Any] | None:
        return cache.load_json(cache.path_for_work_id(work_id))
    return _load
