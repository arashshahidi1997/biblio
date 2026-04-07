from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ._pybtex_utils import parse_bibtex_file
from .ledger import append_jsonl, new_run_id, utc_now_iso


@dataclass(frozen=True)
class PdfFetchConfig:
    repo_root: Path
    src_dir: Path
    src_glob: str
    dest_root: Path
    dest_pattern: str  # format string, e.g. "{citekey}/{citekey}.pdf"
    mode: str  # "copy" | "symlink"
    hash_mode: str  # "md5" | "none"
    manifest_path: Path
    missing_log: Path


_PDF_RE = re.compile(r"(?i)([^;]+?\.pdf)\b")


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, val in payload.items():
        if isinstance(key, str) and isinstance(val, dict):
            out[key] = {k: str(v) for k, v in val.items() if isinstance(k, str)}
    return out


def _save_manifest(path: Path, manifest: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line.rstrip() + "\n")


def _iter_bib_files(src_dir: Path, glob: str) -> list[Path]:
    if not src_dir.exists():
        return []
    return sorted(p for p in src_dir.glob(glob) if p.is_file())


def _candidate_pdf_paths(file_field: str) -> list[str]:
    """
    Extract candidate PDF paths from a BetterBibTeX/Zotero `file` field.

    Handles common formats like:
      - /abs/path/paper.pdf
      - /abs/path/paper.pdf:application/pdf
      - /abs/a.pdf:application/pdf; /abs/b.pdf:application/pdf
    """
    if not (file_field or "").strip():
        return []
    s = str(file_field).strip().strip("{}")
    parts = [p.strip() for p in s.split(";") if p.strip()]
    out: list[str] = []
    for part in parts:
        p = part.strip().strip("{}")
        if ":" in p:
            left = p.split(":", 1)[0].strip()
            if left.lower().endswith(".pdf"):
                out.append(left)
                continue
        match = _PDF_RE.search(p)
        if match:
            out.append(match.group(1).strip())
    # de-dupe preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        if p in seen:
            continue
        uniq.append(p)
        seen.add(p)
    return uniq


def _resolve_source_path(candidate: str, *, bib_dir: Path) -> Path:
    # Strip a leading file:// if present
    c = candidate
    if c.startswith("file://"):
        c = c[len("file://") :]
    # Expand ~ and env vars
    c = os.path.expandvars(os.path.expanduser(c))
    p = Path(c)
    if p.is_absolute():
        return p
    return (bib_dir / p).resolve()


def _dest_path(dest_root: Path, dest_pattern: str, citekey: str) -> Path:
    rel = Path(dest_pattern.format(citekey=citekey))
    return (dest_root / rel).resolve()


def fetch_pdfs(cfg: PdfFetchConfig, *, dry_run: bool = False, force: bool = False) -> dict[str, int]:
    """
    Copy/symlink PDFs referenced by `file` fields in `src_dir/*.bib`.

    Returns counts: {"sources": n_bib_files, "linked": n_done, "skipped": n_skipped, "missing": n_missing}
    """
    run_id = new_run_id("bibtex_fetch")
    bib_files = _iter_bib_files(cfg.src_dir, cfg.src_glob)
    if not bib_files:
        raise FileNotFoundError(f"No .bib files found under {cfg.src_dir} (glob={cfg.src_glob!r})")

    manifest = _load_manifest(cfg.manifest_path) if cfg.hash_mode != "none" else {}
    missing_lines: list[str] = []

    linked = 0
    skipped = 0
    missing = 0
    source_records: list[dict[str, Any]] = []

    for bib_path in bib_files:
        db = parse_bibtex_file(bib_path)
        bib_dir = bib_path.parent
        for citekey, entry in sorted(db.entries.items(), key=lambda kv: kv[0]):
            file_field = entry.fields.get("file")
            if not file_field:
                continue

            source_records.append({"citekey": citekey, "source_bib": str(bib_path)})

            candidates = _candidate_pdf_paths(file_field)
            if not candidates:
                missing += 1
                missing_lines.append(f"{citekey}\t(no pdf candidate in file=)\t{bib_path}")
                continue

            source_pdf: Path | None = None
            for cand in candidates:
                p = _resolve_source_path(cand, bib_dir=bib_dir)
                if p.exists():
                    source_pdf = p
                    break
            if source_pdf is None:
                missing += 1
                missing_lines.append(f"{citekey}\tmissing\t{candidates[0]}\t{bib_path}")
                continue

            dest_pdf = _dest_path(cfg.dest_root, cfg.dest_pattern, citekey)
            dest_pdf.parent.mkdir(parents=True, exist_ok=True)

            if cfg.hash_mode == "md5":
                src_hash = _md5(source_pdf)
                prev = manifest.get(citekey, {}).get("md5")
                if not force and dest_pdf.exists() and prev == src_hash:
                    skipped += 1
                    continue
            else:
                src_hash = ""
                if not force and dest_pdf.exists():
                    skipped += 1
                    continue

            if not dry_run:
                if cfg.mode == "symlink":
                    if dest_pdf.exists() or dest_pdf.is_symlink():
                        dest_pdf.unlink()
                    dest_pdf.symlink_to(source_pdf.resolve())
                elif cfg.mode == "copy":
                    shutil.copy2(source_pdf, dest_pdf)
                else:
                    raise ValueError(f"Unsupported fetch mode: {cfg.mode!r}")

            linked += 1
            if cfg.hash_mode == "md5":
                manifest[citekey] = {"md5": src_hash, "source": str(source_pdf)}

    if not dry_run:
        if cfg.hash_mode != "none":
            _save_manifest(cfg.manifest_path, manifest)
        # overwrite missing log each run for clarity
        if cfg.missing_log.exists():
            cfg.missing_log.unlink()
        if missing_lines:
            _append_lines(cfg.missing_log, missing_lines)

    append_jsonl(
        cfg.repo_root / ".projio" / "biblio" / "logs" / "runs" / "bibtex_fetch.jsonl",
        {
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "stage": "bibtex_fetch",
            "status": "dry_run" if dry_run else "success",
            "source_count": len(bib_files),
            "source_bib": sorted({record["source_bib"] for record in source_records}),
            "linked": linked,
            "skipped": skipped,
            "missing": missing,
            "mode": cfg.mode,
            "hash_mode": cfg.hash_mode,
            "manifest_path": str(cfg.manifest_path),
            "missing_log": str(cfg.missing_log),
            "sources": source_records,
        },
    )

    return {"sources": len(bib_files), "linked": linked, "skipped": skipped, "missing": missing}


def default_pdf_fetch_config(repo_root: str | Path, *, dest_root: Path, dest_pattern: str) -> PdfFetchConfig:
    repo_root = Path(repo_root).expanduser().resolve()
    bib_root = repo_root / "bib"
    return PdfFetchConfig(
        repo_root=repo_root,
        src_dir=bib_root / "srcbib",
        src_glob="*.bib",
        dest_root=dest_root,
        dest_pattern=dest_pattern,
        mode="copy",
        hash_mode="md5",
        manifest_path=bib_root / "logs" / "pdf_manifest.json",
        missing_log=bib_root / "logs" / "missing_pdfs.txt",
    )
