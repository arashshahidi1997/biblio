"""Batch docling processing for multiple citekeys."""
from __future__ import annotations

import fnmatch
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from .citekeys import load_active_citekeys
from .config import BiblioConfig
from .docling import outputs_for_key, pdf_path_for_key, run_docling_for_key


@dataclass
class BatchProgress:
    """Snapshot of batch progress, emitted after each key."""

    total: int
    done: int
    failed: int
    skipped: int
    current_key: str
    elapsed_s: float
    eta_s: float | None


@dataclass
class BatchResult:
    """Final summary of a batch docling run."""

    total: int
    processed: int
    failed: int
    skipped: int
    elapsed_s: float
    failures: list[dict[str, str]] = field(default_factory=list)
    successes: list[str] = field(default_factory=list)


def _load_doi_map(cfg: BiblioConfig) -> dict[str, str]:
    """Load {citekey: doi} map from the merged bib file."""
    try:
        from ._pybtex_utils import parse_bibtex_file
        bib_path = cfg.bibtex_merge.out_bib
        if not bib_path.exists():
            return {}
        db = parse_bibtex_file(bib_path)
        return {
            key: entry.fields.get("doi", "").strip()
            for key, entry in db.entries.items()
            if entry.fields.get("doi", "").strip()
        }
    except Exception:
        return {}


def plan_docling_batch(
    cfg: BiblioConfig,
    *,
    keys: list[str] | None = None,
    filter_glob: str | None = None,
    force: bool = False,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Which citekeys a docling batch converts, and why the others are skipped.

    Returns ``(pending, skipped)``; ``skipped`` holds ``(citekey, reason)``
    with reason ``done``, ``done in pool``, ``no PDF`` or
    ``not in the bibliography, no PDF``. With ``keys`` only those keys are
    considered (R28: a batch in a shared copy must not convert another
    session's papers); a named key with a PDF runs even if it is not in the
    bibliography yet. Papers with valid outputs in the shared pool count as
    done; DOI is used for pool matching when citekeys differ.
    """
    from .docling import resolve_docling_outputs

    known = load_active_citekeys(cfg)
    known_set = set(known)
    candidates = [k.lstrip("@") for k in keys] if keys is not None else known
    if filter_glob:
        candidates = [k for k in candidates if fnmatch.fnmatch(k, filter_glob)]

    doi_map = _load_doi_map(cfg) if cfg.pool_search else {}

    pending: list[str] = []
    skipped: list[tuple[str, str]] = []
    for key in candidates:
        if not pdf_path_for_key(cfg, key).exists():
            skipped.append((key, "no PDF" if key in known_set else "not in the bibliography, no PDF"))
            continue
        if force:
            pending.append(key)
            continue
        _, source = resolve_docling_outputs(cfg, key, doi=doi_map.get(key))
        if source == "local":
            skipped.append((key, "done"))
        elif source == "pool":
            skipped.append((key, "done in pool"))
        else:
            pending.append(key)
    return pending, skipped


def find_pending_docling(
    cfg: BiblioConfig,
    *,
    filter_glob: str | None = None,
    force: bool = False,
    keys: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Find citekeys that have PDFs but no valid docling output yet.

    Returns ``(pending, already_done)`` — both lists contain bare citekeys.
    Keys without a PDF on disk are excluded from both lists (see
    :func:`plan_docling_batch` for the reasons).
    """
    pending, skipped = plan_docling_batch(cfg, keys=keys, filter_glob=filter_glob, force=force)
    return pending, [k for k, why in skipped if why.startswith("done")]


def _process_one_key(
    cfg: BiblioConfig,
    key: str,
    *,
    force: bool = False,
) -> tuple[str, bool, str]:
    """Run docling + ref-md for a single key. Returns ``(key, ok, error)``."""
    try:
        run_docling_for_key(cfg, key, force=force)
        # Auto-chain ref-md if GROBID TEI exists
        try:
            from .grobid import grobid_outputs_for_key
            from .ref_md import run_ref_md_for_key

            grobid_out = grobid_outputs_for_key(cfg, key)
            if grobid_out.tei_path.exists():
                run_ref_md_for_key(cfg, key, force=force)
        except Exception:
            pass
        return (key, True, "")
    except Exception as exc:
        return (key, False, str(exc))


def run_docling_batch(
    cfg: BiblioConfig,
    keys: list[str],
    *,
    concurrency: int = 1,
    force: bool = False,
    progress_cb: Callable[[BatchProgress], None] | None = None,
) -> BatchResult:
    """Run docling for a list of citekeys with optional concurrency.

    ``progress_cb`` is invoked (from a single thread) after each key finishes.
    Concurrency defaults to 1 to stay HPC-friendly — docling uses ~2.7 GB RAM
    and 300 %+ CPU per paper.
    """
    total = len(keys)
    if total == 0:
        return BatchResult(
            total=0, processed=0, failed=0, skipped=0, elapsed_s=0.0,
        )

    start = time.monotonic()
    successes: list[str] = []
    failures: list[dict[str, str]] = []
    done = 0
    lock = threading.Lock()

    def _report(key: str) -> None:
        if progress_cb is None:
            return
        elapsed = time.monotonic() - start
        eta = (elapsed / done * (total - done)) if done > 0 else None
        progress_cb(BatchProgress(
            total=total,
            done=done,
            failed=len(failures),
            skipped=0,
            current_key=key,
            elapsed_s=elapsed,
            eta_s=eta,
        ))

    if concurrency <= 1:
        # Sequential — simple loop, no threads.
        for key in keys:
            if progress_cb:
                elapsed = time.monotonic() - start
                eta = (elapsed / done * (total - done)) if done > 0 else None
                progress_cb(BatchProgress(
                    total=total, done=done, failed=len(failures),
                    skipped=0, current_key=key,
                    elapsed_s=elapsed, eta_s=eta,
                ))
            k, ok, err = _process_one_key(cfg, key, force=force)
            done += 1
            if ok:
                successes.append(k)
            else:
                failures.append({"citekey": k, "error": err})
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {
                executor.submit(_process_one_key, cfg, key, force=force): key
                for key in keys
            }
            for future in as_completed(futures):
                k, ok, err = future.result()
                with lock:
                    done += 1
                    if ok:
                        successes.append(k)
                    else:
                        failures.append({"citekey": k, "error": err})
                    _report(k)

    elapsed = time.monotonic() - start
    return BatchResult(
        total=total,
        processed=len(successes),
        failed=len(failures),
        skipped=0,
        elapsed_s=elapsed,
        failures=failures,
        successes=successes,
    )
