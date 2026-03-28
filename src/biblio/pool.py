from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .citekeys import parse_citekeys_from_markdown
from .config import BiblioConfig, load_biblio_config
from .grobid import parse_tei_header, process_pdf_header
from .ingest import IngestRecord, canonical_citekey, render_bibtex, write_import_bib
from .ledger import append_jsonl, new_run_id, utc_now_iso

_DEFAULT_CONFIG_REL = Path("bib/config/biblio.yml")


@dataclass
class PoolIngestResult:
    pdf_path: Path
    citekey: str | None
    status: str  # "ingested" | "duplicate" | "error" | "dry_run"
    doi: str | None
    error: str | None


def load_pool_config(pool_root: Path) -> BiblioConfig:
    """Load biblio config from a pool workspace root."""
    cfg_path = (pool_root / _DEFAULT_CONFIG_REL).resolve()
    return load_biblio_config(cfg_path, root=pool_root)


def _resolve_pool_root(cfg: BiblioConfig) -> Path | None:
    """Return common_pool_path from project config, or None."""
    return cfg.common_pool_path


def _oa_work_to_ingest_record(work: dict[str, Any], *, source_ref: str) -> IngestRecord:
    """Convert an OpenAlex work dict to an IngestRecord."""
    authors: list[str] = []
    for item in (work.get("authorships") or []):
        author = item.get("author") if isinstance(item, dict) else None
        if isinstance(author, dict):
            name = str(author.get("display_name") or "").strip()
            if name:
                authors.append(name)

    year_raw = work.get("publication_year")
    year = str(year_raw) if year_raw else None

    doi_raw = str(work.get("doi") or "").strip()
    doi = doi_raw.removeprefix("https://doi.org/").strip() or None

    title = str(work.get("display_name") or "").strip() or None

    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    journal = str(source.get("display_name") or "").strip() or None

    entry_type_map = {
        "journal-article": "article",
        "proceedings-article": "inproceedings",
        "book-chapter": "incollection",
        "book": "book",
        "dissertation": "phdthesis",
        "preprint": "misc",
    }
    raw_type = str(work.get("type") or "").strip()
    entry_type = entry_type_map.get(raw_type, "article")

    return IngestRecord(
        source_type="pool_ingest",
        source_ref=source_ref,
        entry_type=entry_type,
        title=title,
        authors=tuple(authors),
        year=year,
        doi=doi,
        url=f"https://doi.org/{doi}" if doi else None,
        journal=journal if entry_type == "article" else None,
        booktitle=journal if entry_type == "inproceedings" else None,
        raw_id=doi,
        file=None,
    )


def _build_record_from_grobid_meta(meta: dict[str, Any], *, source_ref: str) -> IngestRecord:
    return IngestRecord(
        source_type="pool_ingest",
        source_ref=source_ref,
        entry_type="article",
        title=meta.get("title"),
        authors=tuple(meta.get("authors") or []),
        year=meta.get("year"),
        doi=meta.get("doi"),
        url=f"https://doi.org/{meta['doi']}" if meta.get("doi") else None,
        journal=None,
        booktitle=None,
        raw_id=meta.get("doi"),
        file=None,
    )


def _build_record_from_filename(pdf_path: Path) -> IngestRecord:
    stem = pdf_path.stem.replace("_", " ").replace("-", " ")
    return IngestRecord(
        source_type="pool_ingest",
        source_ref=str(pdf_path),
        entry_type="article",
        title=stem or None,
        authors=(),
        year=None,
        doi=None,
        url=None,
        journal=None,
        booktitle=None,
        raw_id=None,
        file=None,
    )


def _enrich_with_openalex(record: IngestRecord, pool_cfg: BiblioConfig) -> IngestRecord:
    """Try to enrich record via OpenAlex DOI lookup. Returns original on failure."""
    if not record.doi:
        return record
    try:
        from .openalex.openalex_client import OpenAlexClient
        client = OpenAlexClient(pool_cfg.openalex_client)
        work = client.get_work_by_doi(record.doi)
        return _oa_work_to_ingest_record(work, source_ref=record.source_ref)
    except Exception:
        return record


def ingest_inbox(
    pool_cfg: BiblioConfig,
    inbox_dir: Path,
    *,
    dry_run: bool = False,
    move: bool = False,
) -> list[PoolIngestResult]:
    """Scan inbox_dir for PDFs, extract metadata, copy to pool, write .bib entry.

    Pipeline per PDF:
      1. GROBID header → DOI + metadata
      2. OpenAlex enrichment if DOI found
      3. Filename fallback if no metadata
      4. Copy to pool pdf_root, append to bib/srcbib/inbox.bib
    """
    inbox_dir = inbox_dir.expanduser().resolve()
    if not inbox_dir.exists():
        raise FileNotFoundError(f"Inbox directory not found: {inbox_dir}")

    pdfs = sorted(p for p in inbox_dir.rglob("*.pdf") if p.is_file())
    results: list[PoolIngestResult] = []
    run_id = new_run_id("pool_ingest")
    bib_entries: list[tuple[str, IngestRecord]] = []

    for pdf_path in pdfs:
        meta: dict[str, Any] = {}
        grobid_ok = False

        # Step 1: GROBID header extraction
        try:
            tei = process_pdf_header(pool_cfg.grobid, pdf_path)
            meta = parse_tei_header(tei)
            grobid_ok = bool(meta)
        except Exception:
            pass

        # Step 2: Build initial record
        if grobid_ok and (meta.get("title") or meta.get("doi")):
            record = _build_record_from_grobid_meta(meta, source_ref=str(pdf_path))
        else:
            record = _build_record_from_filename(pdf_path)

        # Step 3: OpenAlex enrichment if we have a DOI
        if record.doi:
            record = _enrich_with_openalex(record, pool_cfg)

        citekey = canonical_citekey(record)

        # Step 4: Check for duplicate in pool
        dest = (pool_cfg.pdf_root / pool_cfg.pdf_pattern.format(citekey=citekey)).resolve()
        if dest.exists():
            results.append(PoolIngestResult(
                pdf_path=pdf_path, citekey=citekey,
                status="duplicate", doi=record.doi, error=None,
            ))
            continue

        if dry_run:
            results.append(PoolIngestResult(
                pdf_path=pdf_path, citekey=citekey,
                status="dry_run", doi=record.doi, error=None,
            ))
            continue

        # Step 5: Copy PDF + write .bib
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_path, dest)
            file_rel = str(dest)
            record_with_file = IngestRecord(
                source_type=record.source_type,
                source_ref=record.source_ref,
                entry_type=record.entry_type,
                title=record.title,
                authors=record.authors,
                year=record.year,
                doi=record.doi,
                url=record.url,
                journal=record.journal,
                booktitle=record.booktitle,
                raw_id=record.raw_id,
                file=file_rel,
            )
            bib_entries.append((citekey, record_with_file))
            if move:
                pdf_path.unlink()
            results.append(PoolIngestResult(
                pdf_path=pdf_path, citekey=citekey,
                status="ingested", doi=record.doi, error=None,
            ))
        except Exception as e:
            results.append(PoolIngestResult(
                pdf_path=pdf_path, citekey=citekey,
                status="error", doi=record.doi, error=str(e),
            ))

    # Write all new .bib entries at once
    if bib_entries:
        inbox_bib = pool_cfg.repo_root / "bib" / "srcbib" / "inbox.bib"
        bibtex_text = render_bibtex(bib_entries)
        write_import_bib(inbox_bib, bibtex_text)

    counts = {s: sum(1 for r in results if r.status == s)
              for s in ("ingested", "duplicate", "error", "dry_run")}
    append_jsonl(
        pool_cfg.repo_root / "bib" / "logs" / "runs" / "pool_ingest.jsonl",
        {
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "stage": "pool_ingest",
            "status": "dry_run" if dry_run else "success",
            "inbox_dir": str(inbox_dir),
            "move": move,
            **counts,
        },
    )

    return results


def link_project(project_cfg: BiblioConfig, pool_root: Path, *, lab_pool: Path | None = None) -> dict[str, bool]:
    """Write pool.path into project biblio.yml and add articles/ to bib/.gitignore."""
    pool_root = pool_root.expanduser().resolve()
    cfg_path = project_cfg.repo_root / "bib" / "config" / "biblio.yml"

    # Update biblio.yml
    config_updated = False
    raw: dict = {}
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}
    pool_section = raw.get("pool") or {}
    if not isinstance(pool_section, dict):
        pool_section = {}
    needs_write = pool_section.get("path") != str(pool_root)
    if lab_pool is not None:
        new_search = [str(lab_pool), str(pool_root)]
        if pool_section.get("search") != new_search:
            pool_section["search"] = new_search
            needs_write = True
    if needs_write:
        pool_section["path"] = str(pool_root)
        raw["pool"] = pool_section
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        config_updated = True

    # Update bib/.gitignore
    gitignore_path = project_cfg.repo_root / "bib" / ".gitignore"
    gitignore_updated = False
    existing = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    lines = existing.splitlines()
    if "articles/" not in lines and "articles" not in lines:
        with gitignore_path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("articles/\n")
        gitignore_updated = True

    return {"config_updated": config_updated, "gitignore_updated": gitignore_updated}


def sync_pool_symlinks(project_cfg: BiblioConfig) -> dict[str, str]:
    """Create symlinks in project bib/articles/ for all active citekeys present in pool.

    Searches pools in the order given by project_cfg.pool_search.
    Returns {citekey: "linked" | "already_exists" | "not_in_pool"}.
    """
    if not project_cfg.pool_search:
        raise ValueError("No pool configured. Run 'biblio pool link --pool <path>' first.")

    pool_locs: list[tuple[Path, str]] = []
    for pool_root in project_cfg.pool_search:
        try:
            pcfg = load_pool_config(pool_root)
            pool_locs.append((pcfg.pdf_root, pcfg.pdf_pattern))
        except Exception:
            pass

    if not pool_locs:
        raise ValueError("No reachable pool found in pool_search.")

    if not project_cfg.citekeys_path.exists():
        return {}

    keys = parse_citekeys_from_markdown(project_cfg.citekeys_path.read_text(encoding="utf-8"))
    result: dict[str, str] = {}

    for key in keys:
        local_pdf = (project_cfg.pdf_root / project_cfg.pdf_pattern.format(citekey=key)).resolve()

        if local_pdf.exists() or local_pdf.is_symlink():
            result[key] = "already_exists"
            continue

        pool_hit: Path | None = None
        for pool_pdf_root, pool_pdf_pat in pool_locs:
            candidate = (pool_pdf_root / pool_pdf_pat.format(citekey=key)).resolve()
            if candidate.exists():
                pool_hit = candidate
                break

        if pool_hit is None:
            result[key] = "not_in_pool"
            continue

        local_pdf.parent.mkdir(parents=True, exist_ok=True)
        local_pdf.symlink_to(pool_hit)
        result[key] = "linked"

    return result
