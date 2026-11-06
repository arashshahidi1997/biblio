from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from ._pybtex_utils import parse_bibtex_file, require_pybtex
from .ledger import append_jsonl, new_run_id, utc_now_iso


@dataclass(frozen=True)
class BibtexMergeConfig:
    repo_root: Path
    src_dir: Path
    src_glob: str
    out_bib: Path
    file_field_mode: str  # "keep" | "drop" | "rewrite"
    file_field_template: str
    duplicates_log: Path


class MergeResult(tuple):
    """``(n_sources, n_entries, quality_warnings)``, plus ``doi_duplicates``.

    ``doi_duplicates`` lists the DOIs held by more than one citekey in the
    merged output: ``[{"doi": ..., "entries": [{"citekey": ..., "source": ...}]}]``.
    """

    doi_duplicates: list[dict]

    def __new__(cls, n_sources: int, n_entries: int, quality_warnings: list[str], doi_duplicates: list[dict]):
        obj = super().__new__(cls, (n_sources, n_entries, quality_warnings))
        obj.doi_duplicates = doi_duplicates
        return obj


def doi_duplicates_log_path(cfg: BibtexMergeConfig) -> Path:
    return cfg.duplicates_log.parent / "duplicate_dois.txt"


def find_doi_duplicates(entries: dict, provenance: dict[str, str]) -> list[dict]:
    """Group citekeys by normalized DOI; return the groups with more than one key."""
    from .dedup import _normalize_doi

    buckets: dict[str, list[str]] = {}
    for key, entry in entries.items():
        doi = _normalize_doi(entry.fields.get("doi"))
        if doi:
            buckets.setdefault(doi, []).append(key)
    return [
        {"doi": doi, "entries": [{"citekey": k, "source": provenance.get(k, "<unknown>")} for k in sorted(keys)]}
        for doi, keys in sorted(buckets.items())
        if len(keys) > 1
    ]


def _iter_bib_files(src_dir: Path, glob: str) -> list[Path]:
    if not src_dir.exists():
        return []
    return sorted(p for p in src_dir.glob(glob) if p.is_file())


def merge_srcbib(cfg: BibtexMergeConfig, *, dry_run: bool = False) -> MergeResult:
    """
    Merge many .bib files into one.

    Entries with the same citekey collapse (last wins, logged to
    ``duplicates_log``). Different citekeys with the same DOI are kept, since
    documents may cite either, but are reported: ``result.doi_duplicates`` and
    ``duplicate_dois.txt`` beside ``duplicates_log``.

    Returns: ``MergeResult`` (n_sources, n_entries_written, quality_warnings)
    """
    require_pybtex("BibTeX features")
    from pybtex.database import BibliographyData, Entry
    from pybtex.database.output.bibtex import Writer

    run_id = new_run_id("bibtex_merge")
    bib_files = _iter_bib_files(cfg.src_dir, cfg.src_glob)
    if not bib_files:
        raise FileNotFoundError(f"No .bib files found under {cfg.src_dir} (glob={cfg.src_glob!r})")

    merged: dict[str, Entry] = {}
    duplicates: list[tuple[str, str, str]] = []  # (key, prev_source, new_source)
    provenance: dict[str, str] = {}

    for bib_path in bib_files:
        db = parse_bibtex_file(bib_path)
        for key, entry in sorted(db.entries.items(), key=lambda kv: kv[0]):
            entry = copy.deepcopy(entry)

            if cfg.file_field_mode == "drop":
                entry.fields.pop("file", None)
            elif cfg.file_field_mode == "rewrite":
                entry.fields["file"] = cfg.file_field_template.format(citekey=key)
            elif cfg.file_field_mode == "keep":
                pass
            else:
                raise ValueError(f"Unsupported file_field_mode: {cfg.file_field_mode!r}")

            if key in merged:
                duplicates.append((key, provenance.get(key, "<unknown>"), str(bib_path)))
            merged[key] = entry
            provenance[key] = str(bib_path)

    out_db = BibliographyData()
    # We already resolved duplicates with explicit last-wins semantics above.
    # Assign entries directly so pybtex does not re-raise on source duplicates
    # that have already been collapsed in `merged`.
    out_db.entries = dict(sorted(merged.items(), key=lambda kv: kv[0]))

    # Quality check: warn about noise/stub entries
    quality_warnings: list[str] = []
    try:
        from .quality import score_bib_database
        for q in score_bib_database(out_db):
            if q.tier in ("noise", "stub"):
                quality_warnings.append(
                    f"{q.citekey} [{q.tier}, score={q.score}]: {', '.join(q.issues)}"
                )
    except Exception:
        pass  # quality check is optional, don't block merge

    if quality_warnings and not dry_run:
        warnings_path = cfg.duplicates_log.parent / "low_quality_entries.txt"
        warnings_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "Low-quality BibTeX entries detected during merge:",
            f"({len(quality_warnings)} entries with tier 'noise' or 'stub')",
            "",
        ]
        lines.extend(quality_warnings)
        warnings_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    if duplicates and not dry_run:
        cfg.duplicates_log.parent.mkdir(parents=True, exist_ok=True)
        lines = ["Duplicate BibTeX IDs encountered (resolved by last-wins):", ""]
        for key, prev, new in duplicates:
            lines.append(f"{key}")
            lines.append(f"  previous: {prev}")
            lines.append(f"  kept:     {new}")
            lines.append("")
        cfg.duplicates_log.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    elif not duplicates and not dry_run and cfg.duplicates_log.exists():
        cfg.duplicates_log.unlink()

    doi_duplicates = find_doi_duplicates(out_db.entries, provenance)
    doi_log = doi_duplicates_log_path(cfg)
    if doi_duplicates and not dry_run:
        doi_log.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "DOIs held by more than one citekey (one paper, several keys; all kept):",
            f"({len(doi_duplicates)} DOIs)",
            "",
        ]
        for group in doi_duplicates:
            lines.append(group["doi"])
            for e in group["entries"]:
                lines.append(f"  {e['citekey']}  ({e['source']})")
            lines.append("")
        doi_log.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    elif not doi_duplicates and not dry_run and doi_log.exists():
        doi_log.unlink()

    if not dry_run:
        cfg.out_bib.parent.mkdir(parents=True, exist_ok=True)
        writer = Writer()
        cfg.out_bib.write_text(writer.to_string(out_db), encoding="utf-8")

    append_jsonl(
        cfg.repo_root / ".projio" / "biblio" / "logs" / "runs" / "bibtex_merge.jsonl",
        {
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "stage": "bibtex_merge",
            "status": "dry_run" if dry_run else "success",
            "source_bib": [str(p) for p in bib_files],
            "sources": [str(p) for p in bib_files],
            "source_count": len(bib_files),
            "entry_count": len(out_db.entries),
            "duplicate_count": len(duplicates),
            "doi_duplicate_count": len(doi_duplicates),
            "out_bib": str(cfg.out_bib),
            "file_field_mode": cfg.file_field_mode,
        },
    )

    return MergeResult(len(bib_files), len(out_db.entries), quality_warnings, doi_duplicates)


def default_bibtex_merge_config(repo_root: str | Path) -> BibtexMergeConfig:
    repo_root = Path(repo_root).expanduser().resolve()
    projio_biblio = repo_root / ".projio" / "biblio"
    return BibtexMergeConfig(
        repo_root=repo_root,
        src_dir=repo_root / "bib" / "srcbib",
        src_glob="*.bib",
        out_bib=projio_biblio / "merged.bib",
        file_field_mode="drop",
        file_field_template="bib/articles/{citekey}/{citekey}.pdf",
        duplicates_log=projio_biblio / "logs" / "duplicate_bib_ids.txt",
    )


def compile_bib(
    sources: list[Path],
    output: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Merge multiple .bib intermediates into a single compiled output.

    Reads each source .bib file, merges entries with last-wins semantics
    for duplicate keys across sources, and writes the combined output.
    Missing source files are skipped gracefully.

    Returns (n_sources_read, n_entries).
    """
    require_pybtex("BibTeX features")
    from pybtex.database import BibliographyData, Entry
    from pybtex.database.output.bibtex import Writer

    merged: dict[str, Entry] = {}
    sources_read = 0

    for src in sources:
        if not src.exists():
            continue
        db = parse_bibtex_file(src)
        for key, entry in sorted(db.entries.items(), key=lambda kv: kv[0]):
            merged[key] = copy.deepcopy(entry)
        sources_read += 1

    if not dry_run:
        out_db = BibliographyData()
        out_db.entries = dict(sorted(merged.items(), key=lambda kv: kv[0]))
        output.parent.mkdir(parents=True, exist_ok=True)
        writer = Writer()
        output.write_text(writer.to_string(out_db), encoding="utf-8")

    return (sources_read, len(merged))
