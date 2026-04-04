"""ORCID-based author search and publication listing via OpenAlex."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .openalex.openalex_client import OpenAlexClient, OpenAlexClientConfig


@dataclass(frozen=True)
class AuthorRecord:
    openalex_id: str
    orcid: str | None
    display_name: str
    affiliation: str | None
    works_count: int
    cited_by_count: int
    h_index: int | None
    affiliations: list[dict] | None = None


@dataclass(frozen=True)
class WorkRecord:
    openalex_id: str
    doi: str | None
    title: str
    year: int | None
    journal: str | None
    cited_by_count: int
    is_oa: bool
    type: str | None = None
    is_retracted: bool = False
    topics: list[dict] | None = None


def _extract_author(data: dict[str, Any]) -> AuthorRecord:
    oa_id = str(data.get("id") or "").strip()
    if oa_id.startswith("http"):
        oa_id = oa_id.rstrip("/").split("/")[-1]
    orcid = data.get("orcid")
    if isinstance(orcid, str) and orcid.strip():
        orcid = orcid.strip()
    else:
        orcid = None
    display_name = str(data.get("display_name") or "").strip() or "Unknown"
    aff = None
    last_known = data.get("last_known_institutions") or data.get("last_known_institution")
    if isinstance(last_known, list) and last_known:
        inst = last_known[0]
        if isinstance(inst, dict):
            aff = str(inst.get("display_name") or "").strip() or None
    elif isinstance(last_known, dict):
        aff = str(last_known.get("display_name") or "").strip() or None
    works_count = int(data.get("works_count") or 0)
    cited_by_count = int(data.get("cited_by_count") or 0)
    h_index = None
    summary = data.get("summary_stats")
    if isinstance(summary, dict):
        h = summary.get("h_index")
        if h is not None:
            h_index = int(h)

    # Full affiliations history: list of {institution, years}
    affiliations_out: list[dict] | None = None
    raw_affiliations = data.get("affiliations")
    if isinstance(raw_affiliations, list) and raw_affiliations:
        affiliations_out = []
        for a in raw_affiliations:
            if not isinstance(a, dict):
                continue
            inst = a.get("institution") or {}
            entry = {
                "institution_id": inst.get("id") if isinstance(inst, dict) else None,
                "institution_name": inst.get("display_name") if isinstance(inst, dict) else None,
                "years": a.get("years") if isinstance(a.get("years"), list) else [],
            }
            affiliations_out.append(entry)

    return AuthorRecord(
        openalex_id=oa_id,
        orcid=orcid,
        display_name=display_name,
        affiliation=aff,
        works_count=works_count,
        cited_by_count=cited_by_count,
        h_index=h_index,
        affiliations=affiliations_out,
    )


def _extract_work(data: dict[str, Any]) -> WorkRecord:
    oa_id = str(data.get("id") or "").strip()
    if oa_id.startswith("http"):
        oa_id = oa_id.rstrip("/").split("/")[-1]

    doi = None
    ids = data.get("ids")
    if isinstance(ids, dict):
        raw_doi = ids.get("doi")
        if isinstance(raw_doi, str) and raw_doi.strip():
            doi = raw_doi.strip()
            if doi.lower().startswith("https://doi.org/"):
                doi = doi[len("https://doi.org/"):]
    if not doi:
        raw_doi = data.get("doi")
        if isinstance(raw_doi, str) and raw_doi.strip():
            doi = raw_doi.strip()
            if doi.lower().startswith("https://doi.org/"):
                doi = doi[len("https://doi.org/"):]

    title = str(data.get("display_name") or data.get("title") or "").strip() or "Untitled"
    year = data.get("publication_year")
    if year is not None:
        year = int(year)

    journal = None
    primary_loc = data.get("primary_location")
    if isinstance(primary_loc, dict):
        source = primary_loc.get("source")
        if isinstance(source, dict):
            journal = str(source.get("display_name") or "").strip() or None

    cited_by_count = int(data.get("cited_by_count") or 0)

    is_oa = False
    oa = data.get("open_access")
    if isinstance(oa, dict):
        is_oa = bool(oa.get("is_oa"))

    work_type = data.get("type")
    work_type = str(work_type).strip() if isinstance(work_type, str) and work_type.strip() else None

    is_retracted = bool(data.get("is_retracted", False))

    # Topics: primary_topic + topics list with hierarchy and scores
    topics_out: list[dict] | None = None
    raw_topics = data.get("topics")
    primary_topic = data.get("primary_topic")
    if isinstance(raw_topics, list) and raw_topics:
        topics_out = []
        for t in raw_topics:
            if not isinstance(t, dict):
                continue
            entry: dict = {
                "id": t.get("id"),
                "display_name": t.get("display_name"),
                "score": t.get("score"),
                "subfield": (t.get("subfield") or {}).get("display_name") if isinstance(t.get("subfield"), dict) else None,
                "field": (t.get("field") or {}).get("display_name") if isinstance(t.get("field"), dict) else None,
                "domain": (t.get("domain") or {}).get("display_name") if isinstance(t.get("domain"), dict) else None,
            }
            topics_out.append(entry)
    elif isinstance(primary_topic, dict):
        topics_out = [{
            "id": primary_topic.get("id"),
            "display_name": primary_topic.get("display_name"),
            "score": primary_topic.get("score"),
            "subfield": (primary_topic.get("subfield") or {}).get("display_name") if isinstance(primary_topic.get("subfield"), dict) else None,
            "field": (primary_topic.get("field") or {}).get("display_name") if isinstance(primary_topic.get("field"), dict) else None,
            "domain": (primary_topic.get("domain") or {}).get("display_name") if isinstance(primary_topic.get("domain"), dict) else None,
        }]

    return WorkRecord(
        openalex_id=oa_id,
        doi=doi,
        title=title,
        year=year,
        journal=journal,
        cited_by_count=cited_by_count,
        is_oa=is_oa,
        type=work_type,
        is_retracted=is_retracted,
        topics=topics_out,
    )


def search_by_orcid(
    cfg: OpenAlexClientConfig,
    orcid: str,
) -> AuthorRecord:
    """Look up an author by ORCID via OpenAlex."""
    orcid = orcid.strip()
    if not orcid:
        raise ValueError("Empty ORCID")
    client = OpenAlexClient(cfg)
    try:
        # OpenAlex accepts filter queries for authors by ORCID
        data = client._get_json("authors", skip_select=True, params={"filter": f"orcid:{orcid}"})
        results = data.get("results")
        if not isinstance(results, list) or not results:
            raise ValueError(f"No author found for ORCID {orcid}")
        return _extract_author(results[0])
    finally:
        client.close()


def search_by_name(
    cfg: OpenAlexClientConfig,
    query: str,
    *,
    per_page: int = 10,
) -> list[AuthorRecord]:
    """Search OpenAlex authors by display name."""
    query = (query or "").strip()
    if not query:
        raise ValueError("Empty query")
    client = OpenAlexClient(cfg)
    try:
        results = client.search_authors(query, per_page=per_page)
        return [_extract_author(r) for r in results]
    finally:
        client.close()


def get_author_by_id(
    cfg: OpenAlexClientConfig,
    author_id: str,
) -> AuthorRecord:
    """Fetch a single author by OpenAlex author ID."""
    author_id = (author_id or "").strip()
    if not author_id:
        raise ValueError("Empty author_id")
    client = OpenAlexClient(cfg)
    try:
        data = client.get_author(author_id)
        return _extract_author(data)
    finally:
        client.close()


def get_author_works(
    cfg: OpenAlexClientConfig,
    author_id: str,
    *,
    per_page: int = 100,
    since_year: int | None = None,
    min_citations: int | None = None,
) -> list[WorkRecord]:
    """Fetch all works by an author, with optional filters.

    Args:
        cfg: OpenAlex client config.
        author_id: OpenAlex author ID (e.g. "A1234567890").
        per_page: Page size for API pagination.
        since_year: Only include works from this year onward.
        min_citations: Only include works with at least this many citations.
    """
    author_id = author_id.strip()
    if not author_id:
        raise ValueError("Empty author_id")
    if author_id.startswith("http"):
        author_id = author_id.rstrip("/").split("/")[-1]

    client = OpenAlexClient(cfg)
    works: list[WorkRecord] = []
    try:
        cursor = "*"
        while cursor:
            filter_expr = f"author.id:{author_id}"
            if since_year is not None:
                filter_expr += f",from_publication_date:{since_year}-01-01"
            params: dict[str, Any] = {
                "filter": filter_expr,
                "per-page": str(per_page),
                "cursor": cursor,
                "sort": "publication_year:desc",
            }
            data = client._get_json("works", params=params)
            results = data.get("results")
            if not isinstance(results, list) or not results:
                break
            for item in results:
                if not isinstance(item, dict):
                    continue
                w = _extract_work(item)
                if min_citations is not None and w.cited_by_count < min_citations:
                    continue
                works.append(w)
            # Cursor pagination
            meta = data.get("meta")
            if isinstance(meta, dict):
                next_cursor = meta.get("next_cursor")
                if next_cursor and next_cursor != cursor:
                    cursor = next_cursor
                else:
                    break
            else:
                break
    finally:
        client.close()

    return works
