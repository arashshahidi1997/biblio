"""CrossRef DOI resolution utilities for biblio."""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, quote_plus
from urllib.request import Request, urlopen

CROSSREF_API = "https://api.crossref.org/works"
USER_AGENT = "biblio-tools (https://github.com/arashshahidi1997/biblio)"
_DEFAULT_ROWS = 5
_DEFAULT_TIMEOUT = 10


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def resolve_doi_by_title(
    title: str,
    *,
    rows: int = _DEFAULT_ROWS,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Query CrossRef for a DOI matching title.

    Returns a dict with keys:
        ok, doi, matched_title, similarity (0–1), candidates (list), error (str|None)
    """
    params = {"rows": str(rows), "query.bibliographic": title}
    url = CROSSREF_API + "?" + urlencode(params, quote_via=quote_plus)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        return {"ok": False, "error": f"CrossRef HTTP {e.code}", "doi": None, "matched_title": None, "similarity": 0.0, "candidates": []}
    except Exception as e:
        return {"ok": False, "error": str(e), "doi": None, "matched_title": None, "similarity": 0.0, "candidates": []}

    items = (data.get("message") or {}).get("items") or []
    candidates: list[dict[str, Any]] = []
    for item in items:
        raw_titles = item.get("title") or []
        if not raw_titles:
            continue
        ct = raw_titles[0] if isinstance(raw_titles, list) else str(raw_titles)
        sim = _similarity(title, ct)
        candidates.append({"doi": item.get("DOI"), "title": ct, "similarity": round(sim, 4)})

    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    best = candidates[0] if candidates else None

    return {
        "ok": True,
        "error": None,
        "doi": best["doi"] if best else None,
        "matched_title": best["title"] if best else None,
        "similarity": best["similarity"] if best else 0.0,
        "candidates": candidates,
    }


def _parse_authors(item: dict[str, Any]) -> list[str]:
    """Extract author names from a Crossref work item."""
    authors: list[str] = []
    for a in item.get("author") or []:
        family = a.get("family") or ""
        given = a.get("given") or ""
        if family:
            authors.append(f"{family}, {given}".strip(", "))
    return authors


def _parse_work(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Crossref work item into a standard metadata dict."""
    raw_titles = item.get("title") or []
    title = raw_titles[0] if isinstance(raw_titles, list) and raw_titles else str(raw_titles or "")
    issued = item.get("issued") or {}
    date_parts = (issued.get("date-parts") or [[None]])[0]
    year = date_parts[0] if date_parts else None
    container = item.get("container-title") or []
    journal = container[0] if isinstance(container, list) and container else str(container or "")

    return {
        "doi": item.get("DOI"),
        "title": title,
        "authors": _parse_authors(item),
        "year": year,
        "journal": journal,
        "type": item.get("type"),
        "is_referenced_by_count": item.get("is-referenced-by-count"),
        "url": item.get("URL"),
    }


def resolve_doi(
    doi: str,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Fetch full metadata for a DOI from Crossref.

    Returns ``{"ok": True, ...metadata}`` on success or
    ``{"ok": False, "error": "..."}`` on failure.
    """
    doi = doi.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    url = f"{CROSSREF_API}/{doi}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except HTTPError as e:
        return {"ok": False, "error": f"CrossRef HTTP {e.code}", "doi": doi}
    except Exception as e:
        return {"ok": False, "error": str(e), "doi": doi}

    item = (data.get("message") or {})
    if not item.get("DOI"):
        return {"ok": False, "error": "No result from Crossref", "doi": doi}

    result = _parse_work(item)
    result["ok"] = True
    result["error"] = None
    return result


def resolve_dois_batch(
    dois: list[str],
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Resolve multiple DOIs via Crossref.

    Returns ``{"resolved": N, "unresolved": N, "results": [...]}``.
    """
    results: list[dict[str, Any]] = []
    resolved = 0
    unresolved = 0

    for doi in dois:
        r = resolve_doi(doi, timeout=timeout)
        if r.get("ok"):
            r["status"] = "resolved"
            resolved += 1
        else:
            r["status"] = "unresolved"
            unresolved += 1
        results.append(r)

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "results": results,
    }
