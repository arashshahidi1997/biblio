"""Unpaywall API client with local caching."""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable


_USER_AGENT = "biblio-tools (https://github.com/arashshahidi1997/biblio)"
_API_BASE = "https://api.unpaywall.org/v2"
_DEFAULT_TIMEOUT = 30


def _doi_slug(doi: str) -> str:
    """Convert a DOI to a safe filename slug."""
    return re.sub(r"[^\w.-]", "_", doi.strip().strip("/"))


def _cache_dir(repo_root: Path) -> Path:
    return repo_root / "bib" / "derivatives" / "unpaywall"


def _cached_path(repo_root: Path, doi: str) -> Path:
    return _cache_dir(repo_root) / f"{_doi_slug(doi)}.json"


def query_unpaywall(
    doi: str,
    email: str,
    *,
    repo_root: Path | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict[str, Any] | None:
    """Query the Unpaywall API for a single DOI.

    Returns the JSON response dict, or None on error.
    Caches responses in bib/derivatives/unpaywall/ when repo_root is provided.
    """
    doi = doi.strip().strip("/")
    if not doi or not email:
        return None

    # Check cache first
    if repo_root is not None:
        cached = _cached_path(repo_root, doi)
        if cached.exists():
            try:
                return json.loads(cached.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    url = f"{_API_BASE}/{doi}?email={email}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

    # Cache response
    if repo_root is not None and isinstance(data, dict):
        cache_path = _cached_path(repo_root, doi)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    return data


def best_pdf_url(response: dict[str, Any] | None) -> str | None:
    """Extract the best PDF URL from an Unpaywall response.

    Priority order:
    1. best_oa_location.url_for_pdf
    2. best_oa_location.url
    3. first oa_locations[].url_for_pdf that is non-null
    """
    if not response or not isinstance(response, dict):
        return None

    boa = response.get("best_oa_location") or {}
    if isinstance(boa, dict):
        url = boa.get("url_for_pdf")
        if url:
            return str(url)
        url = boa.get("url")
        if url:
            return str(url)

    locations = response.get("oa_locations") or []
    if isinstance(locations, list):
        for loc in locations:
            if isinstance(loc, dict):
                url = loc.get("url_for_pdf")
                if url:
                    return str(url)

    return None


def batch_query(
    dois: list[str],
    email: str,
    *,
    repo_root: Path | None = None,
    delay: float = 1.0,
    timeout: int = _DEFAULT_TIMEOUT,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict[str, str | None]:
    """Query Unpaywall for multiple DOIs, returning {doi: url_or_none}.

    Respects rate limits with configurable delay between calls.
    """
    results: dict[str, str | None] = {}
    total = len(dois)

    for idx, doi in enumerate(dois):
        doi = doi.strip().strip("/")
        if not doi:
            continue

        resp = query_unpaywall(doi, email, repo_root=repo_root, timeout=timeout)
        results[doi] = best_pdf_url(resp)

        if progress_cb:
            progress_cb(idx + 1, total)

        # Rate-limit delay (skip for cached responses to go faster)
        if delay > 0 and idx < total - 1:
            cached = repo_root is not None and _cached_path(repo_root, doi).exists()
            if not cached:
                time.sleep(delay)

    return results
