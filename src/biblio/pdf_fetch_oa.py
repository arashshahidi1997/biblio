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


@dataclass
class OaFetchResult:
    citekey: str
    status: str          # "downloaded" | "skipped" | "no_url" | "error"
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


def _download(url: str, dest: Path, timeout: int = _DEFAULT_TIMEOUT) -> None:
    """Download url to dest atomically."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_fd, "wb") as f:
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                f.write(chunk)
        Path(tmp_path).replace(dest)
    except Exception:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise


def fetch_pdfs_oa(
    cfg: BiblioConfig,
    *,
    force: bool = False,
    delay: float = 1.0,
    queue: bool = True,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> list[OaFetchResult]:
    """Download OA PDFs for all papers in the OpenAlex resolved JSONL that lack local PDFs.

    Reads cfg.openalex.out_jsonl; skips records without an OA URL or with existing PDFs
    (unless force=True). Downloads to the configured pdf_root/pdf_pattern location.
    """
    jsonl_path = cfg.openalex.out_jsonl
    if not jsonl_path.exists():
        raise FileNotFoundError(f"OpenAlex data not found: {jsonl_path}. Run 'Resolve OpenAlex' first.")

    # Pre-load (pdf_root, pdf_pattern) for each pool in search order.
    pool_pdf_locs: list[tuple[Path, str]] = []
    if cfg.pool_search:
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

    results: list[OaFetchResult] = []
    run_id = new_run_id("pdf_fetch_oa")
    total = len(records)

    for idx, record in enumerate(records, start=1):
        citekey = str(record.get("citekey") or "").strip()
        if not citekey:
            continue

        if progress_cb:
            progress_cb({"completed": idx - 1, "total": total, "citekey": citekey})

        dest = (cfg.pdf_root / cfg.pdf_pattern.format(citekey=citekey)).resolve()

        if dest.exists() and not force:
            results.append(OaFetchResult(citekey=citekey, status="skipped", url=None, dest=str(dest), error=None))
            continue

        # Check pools (in search order) before network fetch
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
            continue

        url = _oa_pdf_url(record)
        if not url:
            if queue:
                doi = str(record.get("doi") or "").strip() or None
                paper_url = str((record.get("primary_location") or {}).get("landing_page_url") or "").strip() or None
                add_to_queue(cfg, citekey, doi=doi, url=paper_url, oa_status="no_url")
            results.append(OaFetchResult(citekey=citekey, status="no_url", url=None, dest=None, error=None))
            continue

        try:
            _download(url, dest)
            results.append(OaFetchResult(citekey=citekey, status="downloaded", url=url, dest=str(dest), error=None))
            if delay > 0:
                time.sleep(delay)
        except Exception as e:
            if queue:
                doi = str(record.get("doi") or "").strip() or None
                add_to_queue(cfg, citekey, doi=doi, url=url, oa_status="error")
            results.append(OaFetchResult(citekey=citekey, status="error", url=url, dest=None, error=str(e)))

    if progress_cb:
        progress_cb({"completed": total, "total": total, "citekey": None})

    counts = {s: sum(1 for r in results if r.status == s) for s in ("downloaded", "skipped", "no_url", "error", "pool_linked")}
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
