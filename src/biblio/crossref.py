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
