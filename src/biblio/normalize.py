"""Citekey normalization — rename existing bib entries to canonical form.

This module is the orchestrator. It composes three concerns that used to
be tangled inside the UI action:

1. **Scanning** bib files for non-canonical citekeys.
2. **Metadata resolution** (optional, via ``enrich_and_cache``) — fills
   missing authors/year/title from DOI → OpenAlex / PDF → GROBID /
   title → CrossRef. This is a separate step. Callers that want pure
   renaming should pass ``enrich=False``.
3. **Citekey construction** — builds the canonical key via the strict
   path in :mod:`.citekey`. Entries whose metadata is still incomplete
   after enrichment are *skipped* (never renamed to ``anon_nd_Record``).

The output is a :class:`NormalizePlan` with three buckets:

- ``renames`` — entries whose strict canonical key differs from the
  current key.
- ``already_standard`` — entries whose strict canonical key matches
  the current key (or that already look standard).
- ``skipped`` — entries that could not produce a strict canonical key,
  with a reason (missing_author / missing_year / missing_title).

Applying a plan rewrites affected .bib files, updates citekeys.md,
backs up originals under ``.projio/biblio/logs/runs/normalize_backups/``,
and logs a ledger entry that supports revert.
"""
from __future__ import annotations

import copy as _copy
import io
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .citekey import (
    CitekeyResult,
    SkipReason,
    canonical_citekey,
    dedup_citekeys,
    looks_standard,
)
from .ingest import IngestRecord, enrich_and_cache
from .ledger import append_jsonl, new_run_id, utc_now_iso


@dataclass
class RenameEntry:
    old: str
    new: str
    source_bib: str
    record: IngestRecord  # possibly enriched
    enrich_source: str = ""  # "openalex" / "grobid" / "crossref" / ""


@dataclass
class SkippedEntry:
    citekey: str
    source_bib: str
    reason: str  # SkipReason.*


@dataclass
class EnrichedEntry:
    citekey: str
    source: str
    authors: str  # preview of first few authors


@dataclass
class NormalizePlan:
    renames: list[RenameEntry] = field(default_factory=list)
    already_standard: list[str] = field(default_factory=list)
    skipped: list[SkippedEntry] = field(default_factory=list)
    enriched: list[EnrichedEntry] = field(default_factory=list)
    total_scanned: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "renames": [
                {"old": r.old, "new": r.new, "source_bib": r.source_bib,
                 "enrich_source": r.enrich_source}
                for r in self.renames
            ],
            "already_standard": list(self.already_standard),
            "skipped": [
                {"citekey": s.citekey, "source_bib": s.source_bib, "reason": s.reason}
                for s in self.skipped
            ],
            "enriched": [
                {"citekey": e.citekey, "source": e.source, "authors": e.authors}
                for e in self.enriched
            ],
            "total_scanned": self.total_scanned,
        }


ProgressCallback = Callable[[int, int, str], None]
"""Called as ``cb(done, total, current_key)`` during plan building."""


def _record_from_bib_entry(bib_path: Path, key: str, entry: Any) -> IngestRecord:
    # pybtex stores authors in ``entry.persons["author"]``, not in fields.
    # An earlier version of the normalize path read ``fields.get("author")``
    # which is always empty, so every entry was mis-detected as author-less
    # and renamed to ``anon_nd_...``. Read from persons instead.
    fields = entry.fields
    author_persons = entry.persons.get("author") or []
    authors: list[str] = []
    for person in author_persons:
        family = " ".join(person.last_names) if person.last_names else ""
        given = " ".join(person.first_names) if person.first_names else ""
        if family and given:
            authors.append(f"{family}, {given}")
        elif family:
            authors.append(family)
        elif given:
            authors.append(given)
    # Fallback: if persons is empty but a raw author field exists (rare —
    # happens with non-pybtex-parsed entries), use it.
    if not authors:
        authors_raw = str(fields.get("author") or "")
        authors = [a.strip() for a in authors_raw.split(" and ") if a.strip()]
    return IngestRecord(
        source_type="bibtex",
        source_ref=str(bib_path),
        entry_type=entry.type,
        title=str(fields.get("title") or "") or None,
        authors=tuple(authors),
        year=str(fields.get("year") or "") or None,
        doi=str(fields.get("doi") or "") or None,
        url=None,
        journal=None,
        booktitle=None,
        raw_id=key,
    )


def build_normalize_plan(
    cfg: Any,
    *,
    enrich: bool = False,
    progress: Optional[ProgressCallback] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> NormalizePlan:
    """Scan srcbib files and build a rename plan.

    Args:
        cfg: BiblioConfig (needs ``bibtex_merge.src_dir/src_glob``,
            ``grobid``, ``repo_root``).
        enrich: If True, attempt metadata resolution for entries missing
            authors via ``enrich_and_cache``. Requires network access.
        progress: Optional ``(done, total, current_key)`` callback.
        cancel: Optional callable returning True to abort mid-scan.
    """
    from ._pybtex_utils import parse_bibtex_file, require_pybtex
    from .docling import pdf_path_for_key

    require_pybtex("citekey normalize")

    src_dir = cfg.bibtex_merge.src_dir
    src_glob = cfg.bibtex_merge.src_glob
    bib_files = sorted(p for p in src_dir.glob(src_glob) if p.is_file())

    plan = NormalizePlan()

    all_entries: list[tuple[Path, str, Any]] = []
    for bib_path in bib_files:
        db = parse_bibtex_file(bib_path)
        for key, entry in sorted(db.entries.items()):
            all_entries.append((bib_path, key, entry))

    plan.total_scanned = len(all_entries)

    # First pass: collect proposed renames + skips, without deduplication
    proposed: list[tuple[RenameEntry, CitekeyResult]] = []
    for i, (bib_path, old_key, entry) in enumerate(all_entries):
        if cancel and cancel():
            break
        if progress:
            progress(i, len(all_entries), old_key)

        rec = _record_from_bib_entry(bib_path, old_key, entry)
        enrich_source = ""

        if enrich and not rec.authors:
            pdf = pdf_path_for_key(cfg, old_key)
            cache_result = enrich_and_cache(
                rec,
                pdf_path=pdf,
                grobid_cfg=getattr(cfg, "grobid", None),
                repo_root=getattr(cfg, "repo_root", None),
            )
            rec = cache_result.record
            enrich_source = cache_result.source
            if rec.authors and enrich_source:
                plan.enriched.append(EnrichedEntry(
                    citekey=old_key,
                    source=enrich_source,
                    authors=", ".join(rec.authors[:3]),
                ))

        result = canonical_citekey(rec, strict=True)
        if result.key is None:
            plan.skipped.append(SkippedEntry(
                citekey=old_key,
                source_bib=str(bib_path),
                reason=result.reason or SkipReason.MISSING_AUTHOR,
            ))
            continue

        if result.key == old_key:
            plan.already_standard.append(old_key)
            continue

        # Entries that already match the standard shape AND match their
        # own canonical form are "already_standard" (above). A standard-
        # looking key that differs from canonical still gets renamed.
        proposed.append((
            RenameEntry(
                old=old_key,
                new=result.key,
                source_bib=str(bib_path),
                record=rec,
                enrich_source=enrich_source,
            ),
            result,
        ))

    # Second pass: dedupe collisions against each other AND against
    # all existing keys we're not touching (already_standard + skipped keys).
    reserved: set[str] = set(plan.already_standard)
    reserved.update(s.citekey for s in plan.skipped)
    deduped = _dedup_against_reserved(
        [(r.old, r.new) for r, _ in proposed],
        reserved=reserved,
    )
    for (rename, _), (_, new_key) in zip(proposed, deduped):
        rename.new = new_key
        plan.renames.append(rename)

    if progress:
        progress(len(all_entries), len(all_entries), "")
    return plan


def _dedup_against_reserved(
    pairs: list[tuple[str, str]],
    *,
    reserved: set[str],
) -> list[tuple[str, str]]:
    """Like ``dedup_citekeys`` but also avoids any key already in ``reserved``."""
    seen: dict[str, str] = {k: "" for k in reserved}
    out: list[tuple[str, str]] = []
    for old, proposed in pairs:
        base = proposed
        new = base
        idx = 2
        while new in seen and seen[new] != old:
            new = f"{base}{idx}"
            idx += 1
        seen[new] = old
        out.append((old, new))
    return out


@dataclass
class ApplyResult:
    run_id: str
    renames: list[dict[str, str]]
    affected_bibs: list[str]
    backup_dir: str


def apply_normalize_plan(cfg: Any, plan: NormalizePlan) -> ApplyResult:
    """Apply the rename plan: rewrite bib files, update citekeys.md, log."""
    from ._pybtex_utils import parse_bibtex_file, require_pybtex
    from .citekeys import load_citekeys_md, _render_citekeys_md

    require_pybtex("citekey normalize")

    if not plan.renames:
        return ApplyResult(run_id="", renames=[], affected_bibs=[], backup_dir="")

    from pybtex.database.output.bibtex import Writer as BibWriter
    from pybtex.database import BibliographyData

    run_id = new_run_id("normalize")
    backup_dir = cfg.ledger.root / "normalize_backups" / run_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    rename_map = {r.old: r.new for r in plan.renames}
    enrich_map: dict[str, IngestRecord] = {r.old: r.record for r in plan.renames}
    affected_bibs = sorted({r.source_bib for r in plan.renames})

    backup_manifest: dict[str, str] = {}
    for bib_path_str in affected_bibs:
        bib_path = Path(bib_path_str)
        dst = backup_dir / bib_path.name
        shutil.copy2(bib_path, dst)
        backup_manifest[bib_path_str] = str(dst)
    ck_path = cfg.citekeys_path
    if ck_path and Path(ck_path).exists():
        dst = backup_dir / Path(ck_path).name
        shutil.copy2(ck_path, dst)
        backup_manifest[str(ck_path)] = str(dst)

    for bib_path_str in affected_bibs:
        bib_path = Path(bib_path_str)
        db = parse_bibtex_file(bib_path)
        new_entries = {}
        for k, e in db.entries.items():
            new_k = rename_map.get(k, k)
            new_e = _copy.deepcopy(e)
            rec = enrich_map.get(k)
            if rec:
                if rec.authors and not e.fields.get("author"):
                    new_e.fields["author"] = " and ".join(rec.authors)
                if rec.year and not e.fields.get("year"):
                    new_e.fields["year"] = str(rec.year)
                if rec.title and not e.fields.get("title"):
                    new_e.fields["title"] = rec.title
                if rec.doi and not e.fields.get("doi"):
                    new_e.fields["doi"] = rec.doi
            new_entries[new_k] = new_e
        new_db = BibliographyData(entries=new_entries)
        buf = io.StringIO()
        BibWriter().write_stream(new_db, buf)
        bib_path.write_text(buf.getvalue(), encoding="utf-8")

    if ck_path and Path(ck_path).exists():
        existing = load_citekeys_md(ck_path)
        updated = [rename_map.get(k, k) for k in existing]
        Path(ck_path).write_text(_render_citekeys_md(updated), encoding="utf-8")

    normalize_log = cfg.ledger.root / "normalize.jsonl"
    append_jsonl(normalize_log, {
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "renames": rename_map,
        "backup_dir": str(backup_dir),
        "backup_manifest": backup_manifest,
    })

    return ApplyResult(
        run_id=run_id,
        renames=[{"old": r.old, "new": r.new, "source_bib": r.source_bib} for r in plan.renames],
        affected_bibs=affected_bibs,
        backup_dir=str(backup_dir),
    )
