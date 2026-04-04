"""Author and institution discovery via OpenAlex.

Higher-level discovery functions that build on OpenAlexClient to support
searching by name, institution-level queries, and author-position filtering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .author_search import AuthorRecord, WorkRecord, _extract_author, _extract_work
from .openalex.openalex_cache import OpenAlexCache
from .openalex.openalex_client import OpenAlexClient, OpenAlexClientConfig


@dataclass(frozen=True)
class InstitutionRecord:
    openalex_id: str
    ror: str | None
    display_name: str
    country_code: str | None
    type: str | None  # education, facility, healthcare, company, ...
    works_count: int
    cited_by_count: int


def _extract_institution(data: dict[str, Any]) -> InstitutionRecord:
    oa_id = str(data.get("id") or "").strip()
    if oa_id.startswith("http"):
        oa_id = oa_id.rstrip("/").split("/")[-1]
    ror = data.get("ror")
    if isinstance(ror, str) and ror.strip():
        ror = ror.strip()
    else:
        ror = None
    display_name = str(data.get("display_name") or "").strip() or "Unknown"
    country_code = data.get("country_code")
    if isinstance(country_code, str) and country_code.strip():
        country_code = country_code.strip()
    else:
        country_code = None
    inst_type = data.get("type")
    if isinstance(inst_type, str) and inst_type.strip():
        inst_type = inst_type.strip()
    else:
        inst_type = None
    works_count = int(data.get("works_count") or 0)
    cited_by_count = int(data.get("cited_by_count") or 0)
    return InstitutionRecord(
        openalex_id=oa_id,
        ror=ror,
        display_name=display_name,
        country_code=country_code,
        type=inst_type,
        works_count=works_count,
        cited_by_count=cited_by_count,
    )


# ------------------------------------------------------------------
# Author discovery
# ------------------------------------------------------------------


def search_authors_by_name(
    cfg: OpenAlexClientConfig,
    query: str,
    *,
    per_page: int = 10,
) -> list[AuthorRecord]:
    """Search OpenAlex authors by name (not ORCID).

    Returns ranked candidates with affiliation and metrics.
    """
    client = OpenAlexClient(cfg)
    try:
        results = client.search_authors(query, per_page=per_page)
        return [_extract_author(r) for r in results]
    finally:
        client.close()


def get_author_by_id(
    cfg: OpenAlexClientConfig,
    author_id: str,
    *,
    cache: OpenAlexCache | None = None,
    force: bool = False,
) -> AuthorRecord:
    """Fetch a single author by OpenAlex ID, with optional caching."""
    if cache is not None and not force:
        cached = cache.load_json(cache.path_for_author(author_id))
        if cached is not None:
            return _extract_author(cached)
    client = OpenAlexClient(cfg)
    try:
        data = client.get_author(author_id)
        if cache is not None:
            cache.save_json(cache.path_for_author(author_id), data)
        return _extract_author(data)
    finally:
        client.close()


# ------------------------------------------------------------------
# Institution discovery
# ------------------------------------------------------------------


def search_institutions_by_name(
    cfg: OpenAlexClientConfig,
    query: str,
    *,
    per_page: int = 10,
) -> list[InstitutionRecord]:
    """Search OpenAlex institutions by name."""
    client = OpenAlexClient(cfg)
    try:
        results = client.search_institutions(query, per_page=per_page)
        return [_extract_institution(r) for r in results]
    finally:
        client.close()


def get_institution_by_id(
    cfg: OpenAlexClientConfig,
    institution_id: str,
    *,
    cache: OpenAlexCache | None = None,
    force: bool = False,
) -> InstitutionRecord:
    """Fetch a single institution by OpenAlex ID, with optional caching."""
    if cache is not None and not force:
        cached = cache.load_json(cache.path_for_institution(institution_id))
        if cached is not None:
            return _extract_institution(cached)
    client = OpenAlexClient(cfg)
    try:
        data = client.get_institution(institution_id)
        if cache is not None:
            cache.save_json(cache.path_for_institution(institution_id), data)
        return _extract_institution(data)
    finally:
        client.close()


def get_institution_works(
    cfg: OpenAlexClientConfig,
    institution_id: str,
    *,
    per_page: int = 100,
    since_year: int | None = None,
    min_citations: int | None = None,
) -> list[WorkRecord]:
    """Fetch all works affiliated with an institution.

    Uses cursor pagination to retrieve the full result set.
    """
    institution_id = institution_id.strip()
    if not institution_id:
        raise ValueError("Empty institution_id")
    if institution_id.startswith("http"):
        institution_id = institution_id.rstrip("/").split("/")[-1]

    client = OpenAlexClient(cfg)
    works: list[WorkRecord] = []
    try:
        cursor = "*"
        while cursor:
            filter_expr = f"institutions.id:{institution_id}"
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


def get_institution_authors(
    cfg: OpenAlexClientConfig,
    institution_id: str,
    *,
    per_page: int = 100,
    min_works: int | None = None,
) -> list[AuthorRecord]:
    """Fetch authors affiliated with an institution (last known).

    Uses cursor pagination. Optionally filters by minimum publication count.
    """
    institution_id = institution_id.strip()
    if not institution_id:
        raise ValueError("Empty institution_id")
    if institution_id.startswith("http"):
        institution_id = institution_id.rstrip("/").split("/")[-1]

    client = OpenAlexClient(cfg)
    authors: list[AuthorRecord] = []
    try:
        cursor = "*"
        while cursor:
            filter_expr = f"last_known_institutions.id:{institution_id}"
            if min_works is not None:
                filter_expr += f",works_count:>{min_works - 1}"
            params: dict[str, Any] = {
                "filter": filter_expr,
                "per-page": str(per_page),
                "cursor": cursor,
                "sort": "works_count:desc",
            }
            data = client._get_json("authors", params=params)
            results = data.get("results")
            if not isinstance(results, list) or not results:
                break
            for item in results:
                if not isinstance(item, dict):
                    continue
                authors.append(_extract_author(item))
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
    return authors


# ------------------------------------------------------------------
# Author works with position filter
# ------------------------------------------------------------------


def get_author_works_by_position(
    cfg: OpenAlexClientConfig,
    author_id: str,
    *,
    position: str | None = None,
    per_page: int = 100,
    since_year: int | None = None,
    min_citations: int | None = None,
) -> list[WorkRecord]:
    """Fetch works by an author with optional author-position filtering.

    Args:
        author_id: OpenAlex author ID.
        position: Filter to papers where this author is "first", "middle",
            or "last". None returns all positions.
        since_year: Only include works from this year onward.
        min_citations: Minimum citation count.

    Position filtering is done client-side by inspecting the ``authorships``
    array returned by OpenAlex.
    """
    author_id = author_id.strip()
    if not author_id:
        raise ValueError("Empty author_id")
    if author_id.startswith("http"):
        author_id = author_id.rstrip("/").split("/")[-1]
    if position and position not in ("first", "middle", "last"):
        raise ValueError(f"Invalid position: {position!r} (must be first/middle/last)")

    # Normalize author ID for matching inside authorships
    author_id_url = f"https://openalex.org/{author_id}"

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
                # Need authorships for position filtering
                "select": "id,doi,display_name,publication_year,cited_by_count,"
                          "authorships,ids,open_access,primary_location,"
                          "topics,primary_topic,type,is_retracted",
            }
            data = client._get_json("works", params=params)
            results = data.get("results")
            if not isinstance(results, list) or not results:
                break
            for item in results:
                if not isinstance(item, dict):
                    continue
                # Client-side position filter
                if position:
                    authorships = item.get("authorships") or []
                    match = False
                    for a in authorships:
                        if not isinstance(a, dict):
                            continue
                        author_obj = a.get("author") or {}
                        aid = str(author_obj.get("id") or "").strip()
                        if aid in (author_id, author_id_url) and a.get("author_position") == position:
                            match = True
                            break
                    if not match:
                        continue
                w = _extract_work(item)
                if min_citations is not None and w.cited_by_count < min_citations:
                    continue
                works.append(w)
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
