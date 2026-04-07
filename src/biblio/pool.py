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

_DEFAULT_CONFIG_REL = Path(".projio/biblio/biblio.yml")
_LEGACY_CONFIG_REL = Path("bib/config/biblio.yml")


@dataclass
class PoolIngestResult:
    pdf_path: Path
    citekey: str | None
    status: str  # "ingested" | "duplicate" | "error" | "dry_run"
    doi: str | None
    error: str | None


_DERIVATIVE_TYPES = ("docling", "grobid", "openalex", "html")

# Module-level cache: {pool_bib_path: {normalized_doi: pool_citekey}}
_pool_doi_index_cache: dict[str, dict[str, str]] = {}


def _normalize_doi(doi: str) -> str:
    """Normalize a DOI for comparison: lowercase, strip URL prefix."""
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi


def _build_pool_doi_index(pool_bib_path: Path) -> dict[str, str]:
    """Build a {normalized_doi: citekey} map from a pool's merged bib file.

    Cached per session (module-level) to avoid re-parsing on every lookup.
    """
    cache_key = str(pool_bib_path)
    if cache_key in _pool_doi_index_cache:
        return _pool_doi_index_cache[cache_key]

    index: dict[str, str] = {}
    if not pool_bib_path.exists():
        _pool_doi_index_cache[cache_key] = index
        return index

    try:
        from ._pybtex_utils import parse_bibtex_file
        db = parse_bibtex_file(pool_bib_path)
        for key, entry in db.entries.items():
            doi = entry.fields.get("doi", "").strip()
            if doi:
                index[_normalize_doi(doi)] = key
    except Exception:
        pass

    _pool_doi_index_cache[cache_key] = index
    return index


def _find_pool_bib(pool_root: Path) -> Path | None:
    """Find the merged bib file in a pool directory."""
    for base in (pool_root, pool_root.parent):
        for name in ("main.bib", "merged.bib"):
            candidate = base / name
            if candidate.exists():
                return candidate
        # Also check .projio/biblio/merged.bib
        candidate = base.parent / ".projio" / "biblio" / "merged.bib"
        if candidate.exists():
            return candidate
    return None


def _resolve_pool_citekey(
    cfg: BiblioConfig,
    citekey: str,
    doi: str | None = None,
) -> list[tuple[Path, str]]:
    """Resolve a paper's citekey(s) in each pool.

    Returns list of ``(pool_derivatives_base, pool_citekey)`` for pools
    where either the citekey or DOI matches.

    Tries in order:
    1. Direct citekey match (fast — just stat the directory)
    2. DOI lookup in pool's bib index (handles citekey mismatches)
    """
    key = citekey.lstrip("@")
    norm_doi = _normalize_doi(doi) if doi else ""
    matches: list[tuple[Path, str]] = []

    for pool_root in cfg.pool_search:
        for base in (pool_root, pool_root.parent):
            deriv_base = base / "derivatives"
            if not deriv_base.is_dir():
                continue

            # 1. Direct citekey match
            if (deriv_base / "docling" / key).is_dir() or (deriv_base / "grobid" / key).is_dir():
                matches.append((deriv_base, key))
                break

            # 2. DOI-based lookup
            if norm_doi:
                pool_bib = _find_pool_bib(pool_root)
                if pool_bib:
                    doi_index = _build_pool_doi_index(pool_bib)
                    pool_key = doi_index.get(norm_doi)
                    if pool_key and pool_key != key:
                        if (deriv_base / "docling" / pool_key).is_dir() or (deriv_base / "grobid" / pool_key).is_dir():
                            matches.append((deriv_base, pool_key))
                            break
            break  # only check one base per pool_root

    return matches


def resolve_pool_derivative(
    cfg: BiblioConfig,
    citekey: str,
    derivative_type: str,
    doi: str | None = None,
) -> Path | None:
    """Check pool search paths for an existing derivative.

    Uses both citekey and DOI for matching — handles citekey mismatches
    between project and pool bibliographies.

    Args:
        cfg: Project biblio config (uses ``pool_search`` paths).
        citekey: BibTeX citekey (tried first).
        derivative_type: One of "docling", "grobid", "openalex", "html".
        doi: Paper DOI (optional, used as fallback when citekey doesn't match).
    """
    for deriv_base, pool_key in _resolve_pool_citekey(cfg, citekey, doi=doi):
        candidate = deriv_base / derivative_type / pool_key
        if candidate.is_dir() and any(candidate.iterdir()):
            return candidate
    return None


def resolve_pool_derivatives(
    cfg: BiblioConfig,
    citekey: str,
    doi: str | None = None,
) -> dict[str, Path | None]:
    """Check all derivative types for pool availability.

    Returns ``{"docling": Path|None, "grobid": Path|None, ...}``.
    """
    return {
        dt: resolve_pool_derivative(cfg, citekey, dt, doi=doi)
        for dt in _DERIVATIVE_TYPES
    }


def load_pool_config(pool_root: Path) -> BiblioConfig:
    """Load biblio config from a pool workspace root."""
    cfg_path = (pool_root / _DEFAULT_CONFIG_REL).resolve()
    if not cfg_path.exists():
        legacy = (pool_root / _LEGACY_CONFIG_REL).resolve()
        if legacy.exists():
            cfg_path = legacy
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
        pool_cfg.repo_root / ".projio" / "biblio" / "logs" / "runs" / "pool_ingest.jsonl",
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


@dataclass
class PoolPromoteResult:
    citekey: str
    status: str  # "promoted" | "already_in_pool" | "no_local_pdf" | "error" | "dry_run"
    error: str | None = None


def promote_to_pool(
    project_cfg: BiblioConfig,
    pool_root: Path,
    citekeys: list[str],
    *,
    dry_run: bool = False,
) -> list[PoolPromoteResult]:
    """Move project-local papers into a pool so other projects can access them.

    For each citekey:
    1. Copy PDF from project ``bib/articles/{ck}/`` to pool ``bib/articles/{ck}/``
    2. Copy derivatives (docling, grobid, openalex) to pool ``bib/derivatives/``
    3. Copy/merge the BibTeX entry into pool ``bib/srcbib/promoted.bib``
    4. Replace local PDF with symlink to pool copy
    """
    pool_root = pool_root.expanduser().resolve()
    pool_cfg = load_pool_config(pool_root)

    # Load project bib database for extracting BibTeX entries
    from ._pybtex_utils import parse_bibtex_file

    bib_db = None
    bib_path = project_cfg.bibtex_merge.out_bib
    if bib_path.exists():
        try:
            bib_db = parse_bibtex_file(bib_path)
        except Exception:
            pass

    results: list[PoolPromoteResult] = []
    bib_entries: list[tuple[str, str]] = []  # (citekey, raw bibtex block)

    for ck in citekeys:
        key = ck.lstrip("@")
        try:
            # Check if already in pool
            pool_pdf = (pool_cfg.pdf_root / pool_cfg.pdf_pattern.format(citekey=key)).resolve()
            if pool_pdf.exists():
                results.append(PoolPromoteResult(key, "already_in_pool"))
                continue

            # Check local PDF exists
            local_pdf = (project_cfg.pdf_root / project_cfg.pdf_pattern.format(citekey=key)).resolve()
            if not local_pdf.exists() or not local_pdf.is_file():
                # Check if it's a symlink that already points to pool
                if local_pdf.is_symlink():
                    results.append(PoolPromoteResult(key, "already_in_pool"))
                else:
                    results.append(PoolPromoteResult(key, "no_local_pdf"))
                continue

            if dry_run:
                results.append(PoolPromoteResult(key, "dry_run"))
                continue

            # 1. Copy PDF to pool
            pool_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_pdf, pool_pdf)

            # 2. Copy derivatives to pool
            project_deriv = project_cfg.repo_root / "bib" / "derivatives"
            pool_deriv = pool_root / "bib" / "derivatives"
            for dtype in _DERIVATIVE_TYPES:
                src_dir = project_deriv / dtype / key
                if src_dir.is_dir() and any(src_dir.iterdir()):
                    dst_dir = pool_deriv / dtype / key
                    if not dst_dir.exists():
                        shutil.copytree(src_dir, dst_dir)

            # 3. Collect BibTeX entry for promoted.bib
            if bib_db and key in bib_db.entries:
                from pybtex.database import BibliographyData
                single = BibliographyData(entries={key: bib_db.entries[key]})
                bib_entries.append((key, single.to_string("bibtex")))

            # 4. Replace local PDF with symlink to pool copy
            local_pdf.unlink()
            local_pdf.symlink_to(pool_pdf)

            results.append(PoolPromoteResult(key, "promoted"))
        except Exception as exc:
            results.append(PoolPromoteResult(key, "error", error=str(exc)))

    # Write collected BibTeX entries to pool's promoted.bib
    if bib_entries:
        promoted_bib = pool_root / "bib" / "srcbib" / "promoted.bib"
        promoted_bib.parent.mkdir(parents=True, exist_ok=True)
        new_text = "\n\n".join(text for _, text in bib_entries)
        if promoted_bib.exists() and promoted_bib.read_text(encoding="utf-8").strip():
            existing = promoted_bib.read_text(encoding="utf-8")
            suffix = "" if existing.endswith("\n") else "\n"
            promoted_bib.write_text(existing + suffix + "\n" + new_text + "\n", encoding="utf-8")
        else:
            promoted_bib.write_text(new_text + "\n", encoding="utf-8")

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
