"""Download open-access PDFs from URLs stored in OpenAlex resolved records."""
from __future__ import annotations

import json
import shutil
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import BiblioConfig
from .fetch_queue import add_to_queue
from .ledger import append_jsonl, new_run_id, utc_now_iso

USER_AGENT = "biblio-tools (https://github.com/arashshahidi1997/biblio)"
_CHUNK = 1024 * 256  # 256 KB
_DEFAULT_TIMEOUT = 30

ALL_STATUSES = ("openalex", "unpaywall", "ezproxy", "pool_linked", "html_fallback", "skipped", "no_url", "error")


@dataclass
class OaFetchResult:
    citekey: str
    status: str          # "openalex" | "unpaywall" | "ezproxy" | "pool_linked" | "skipped" | "no_url" | "error"
    url: str | None
    dest: str | None
    error: str | None


def _oa_pdf_url(record: dict[str, Any]) -> str | None:
    """Return the best available OA PDF URL from an OpenAlex record."""
    boa = record.get("best_oa_location") or {}
    url = boa.get("pdf_url") or boa.get("url_for_pdf")
    if url:
        return str(url)
    oa = record.get("open_access") or {}
    url = oa.get("oa_url")
    if url:
        return str(url)
    pl = record.get("primary_location") or {}
    url = pl.get("pdf_url")
    if url:
        return str(url)
    return None


class _NotAPdfError(Exception):
    """Raised when a downloaded file is not a valid PDF."""


class FetchCancelledError(Exception):
    """Raised when a fetch operation is cancelled by the caller."""


def _download(url: str, dest: Path, timeout: int = _DEFAULT_TIMEOUT) -> None:
    """Download url to dest atomically. Validates the result is a real PDF.

    Raises _NotAPdfError if the response is HTML or doesn't start with %PDF-.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Reject HTML responses (paywall pages, login redirects)
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type:
                Path(tmp_path).unlink(missing_ok=True)
                raise _NotAPdfError(f"Response is HTML, not PDF (Content-Type: {content_type})")
            with open(tmp_fd, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
        # Validate PDF magic bytes
        with open(tmp_path, "rb") as f:
            header = f.read(5)
        if header != b"%PDF-":
            Path(tmp_path).unlink(missing_ok=True)
            raise _NotAPdfError(f"Downloaded file is not a PDF (header: {header!r})")
        Path(tmp_path).replace(dest)
    except _NotAPdfError:
        raise
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _download_html(url: str, dest: Path, timeout: int = _DEFAULT_TIMEOUT) -> bool:
    """Download a URL and save as HTML if the response is text/html.

    Returns True if HTML was saved, False otherwise.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                Path(tmp_path).unlink(missing_ok=True)
                return False
            with open(tmp_fd, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
        # Basic sanity: file should have some content
        if Path(tmp_path).stat().st_size < 100:
            Path(tmp_path).unlink(missing_ok=True)
            return False
        Path(tmp_path).replace(dest)
        return True
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _try_html_fallback(citekey: str, doi: str, cfg: BiblioConfig) -> Path | None:
    """Try to save the publisher landing page as HTML fallback.

    Saved to ``bib/derivatives/html/{citekey}/{citekey}.html`` for later
    docling extraction. Returns the path if saved, None otherwise.
    """
    if not doi:
        return None
    html_dir = cfg.repo_root / "bib" / "derivatives" / "html" / citekey
    html_path = html_dir / f"{citekey}.html"
    if html_path.exists():
        return html_path
    doi_url = f"https://doi.org/{doi}"
    if _download_html(doi_url, html_path):
        return html_path
    return None


def _try_unpaywall(doi: str, cfg: BiblioConfig, dest: Path) -> str | None:
    """Try to get a PDF URL from Unpaywall. Returns URL on success, None otherwise."""
    cascade = cfg.pdf_fetch_cascade
    if not cascade.unpaywall_email or not doi:
        return None
    from .unpaywall import query_unpaywall, best_pdf_url
    resp = query_unpaywall(doi, cascade.unpaywall_email, repo_root=cfg.repo_root)
    url = best_pdf_url(resp)
    if not url:
        return None
    try:
        _download(url, dest)
        return url
    except Exception:
        return None


def _try_ezproxy(doi: str, cfg: BiblioConfig, dest: Path) -> str | None:
    """Try to download via EZProxy using the DOI URL. Returns URL on success."""
    cascade = cfg.pdf_fetch_cascade
    if not cascade.ezproxy_base or not doi:
        return None
    from .ezproxy import download_via_proxy
    doi_url = f"https://doi.org/{doi}"
    ok = download_via_proxy(
        doi_url, cascade.ezproxy_base, dest,
        mode=cascade.ezproxy_mode,
        cookie=cascade.ezproxy_cookie,
    )
    if ok:
        return doi_url
    return None


def fetch_pdfs_oa(
    cfg: BiblioConfig,
    *,
    force: bool = False,
    delay: float | None = None,
    queue: bool = True,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    citekey_filter: set[str] | None = None,
) -> list[OaFetchResult]:
    """Download PDFs for all papers using a configurable source cascade.

    Cascade order is determined by cfg.pdf_fetch_cascade.sources:
      pool → openalex → unpaywall → ezproxy

    Reads cfg.openalex.out_jsonl; skips records with existing PDFs
    (unless force=True). Downloads to the configured pdf_root/pdf_pattern location.
    """
    cascade = cfg.pdf_fetch_cascade
    if delay is None:
        delay = cascade.delay

    jsonl_path = cfg.openalex.out_jsonl
    if not jsonl_path.exists():
        raise FileNotFoundError(f"OpenAlex data not found: {jsonl_path}. Run 'Resolve OpenAlex' first.")

    # Pre-load (pdf_root, pdf_pattern) for each pool in search order.
    pool_pdf_locs: list[tuple[Path, str]] = []
    if cfg.pool_search and "pool" in cascade.sources:
        from .pool import load_pool_config as _load_pool_config
        for _pool_root in cfg.pool_search:
            try:
                _pcfg = _load_pool_config(_pool_root)
                pool_pdf_locs.append((_pcfg.pdf_root, _pcfg.pdf_pattern))
            except Exception:
                pass

    records = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if citekey_filter is not None:
        records = [r for r in records if str(r.get("citekey") or "") in citekey_filter]

    results: list[OaFetchResult] = []
    run_id = new_run_id("pdf_fetch_oa")
    total = len(records)

    for idx, record in enumerate(records, start=1):
        citekey = str(record.get("citekey") or "").strip()
        if not citekey:
            continue

        if progress_cb:
            try:
                progress_cb({"completed": idx - 1, "total": total, "citekey": citekey})
            except FetchCancelledError:
                break

        dest = (cfg.pdf_root / cfg.pdf_pattern.format(citekey=citekey)).resolve()
        doi = str(record.get("doi") or "").strip() or None

        if dest.exists() and not force:
            results.append(OaFetchResult(citekey=citekey, status="skipped", url=None, dest=str(dest), error=None))
            continue

        # Walk through the configured source cascade
        fetched = False
        for source in cascade.sources:
            if source == "pool":
                pool_hit: Path | None = None
                for _pdf_root, _pdf_pat in pool_pdf_locs:
                    _candidate = (_pdf_root / _pdf_pat.format(citekey=citekey)).resolve()
                    if _candidate.exists():
                        pool_hit = _candidate
                        break
                if pool_hit is not None:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.is_symlink() or dest.exists():
                        dest.unlink()
                    dest.symlink_to(pool_hit)
                    results.append(OaFetchResult(citekey=citekey, status="pool_linked", url=None, dest=str(dest), error=None))
                    fetched = True
                    break

            elif source == "openalex":
                url = _oa_pdf_url(record)
                if url:
                    try:
                        _download(url, dest)
                        results.append(OaFetchResult(citekey=citekey, status="openalex", url=url, dest=str(dest), error=None))
                        fetched = True
                        if delay > 0:
                            time.sleep(delay)
                        break
                    except Exception:
                        pass  # fall through to next source

            elif source == "unpaywall":
                url = _try_unpaywall(doi, cfg, dest)
                if url:
                    results.append(OaFetchResult(citekey=citekey, status="unpaywall", url=url, dest=str(dest), error=None))
                    fetched = True
                    if delay > 0:
                        time.sleep(delay)
                    break

            elif source == "ezproxy":
                url = _try_ezproxy(doi, cfg, dest)
                if url:
                    results.append(OaFetchResult(citekey=citekey, status="ezproxy", url=url, dest=str(dest), error=None))
                    fetched = True
                    break

        if not fetched:
            # HTML fallback: save the publisher landing page for docling extraction
            html_path = _try_html_fallback(citekey, doi, cfg)
            if html_path is not None:
                results.append(OaFetchResult(
                    citekey=citekey, status="html_fallback",
                    url=f"https://doi.org/{doi}" if doi else None,
                    dest=str(html_path), error=None,
                ))
            else:
                if queue:
                    paper_url = str((record.get("primary_location") or {}).get("landing_page_url") or "").strip() or None
                    add_to_queue(cfg, citekey, doi=doi, url=paper_url, oa_status="no_url")
                results.append(OaFetchResult(citekey=citekey, status="no_url", url=None, dest=None, error=None))

    if progress_cb:
        progress_cb({"completed": total, "total": total, "citekey": None})

    counts = {s: sum(1 for r in results if r.status == s) for s in ALL_STATUSES}
    append_jsonl(
        cfg.ledger.docling_runs.parent.parent / "runs" / "pdf_fetch_oa.jsonl",
        {
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "stage": "pdf_fetch_oa",
            "status": "success",
            "force": force,
            **counts,
        },
    )

    return results
