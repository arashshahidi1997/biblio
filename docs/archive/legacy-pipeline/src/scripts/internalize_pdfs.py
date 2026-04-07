#!/usr/bin/env python3
"""Internalize PDFs from .bib files into a content-addressable store."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import bibtexparser
from sutil.repo_root import repo_abs


DEFAULT_OBJECTS_DIR = repo_abs("data/01_bronze/objects")
DEFAULT_MAP_FILE = repo_abs("data/01_bronze/pdf_map.json")


def sha256sum(path: Path) -> str:
    """Compute SHA-256 checksum for file contents."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_pdf_path(file_field: str) -> Path | None:
    """Parse Better BibTeX file field and return a PDF path."""
    if not file_field:
        return None
    for part in file_field.split(";"):
        cleaned = part.strip()
        if not cleaned:
            continue
        subparts = cleaned.split(":")
        for candidate in subparts:
            if candidate.lower().endswith(".pdf") and Path(candidate).exists():
                return Path(candidate)
        if cleaned.lower().endswith(".pdf") and Path(cleaned).exists():
            return Path(cleaned)
    return None


def internalize_pdfs(bib_paths: list[Path], objects_dir: Path, map_output: Path) -> int:
    objects_dir.mkdir(parents=True, exist_ok=True)

    pdf_map: dict[str, str] = {}
    missing_log: list[str] = []
    stats = {"new": 0, "skipped": 0, "missing": 0}

    for bib_path in bib_paths:
        try:
            with bib_path.open("r", encoding="utf-8") as f:
                db = bibtexparser.load(f)
        except Exception as exc:
            print("error: failed to read {0}: {1}".format(bib_path, exc))
            continue

        for entry in db.entries:
            work_id = entry.get("ID")
            file_field = entry.get("file")
            if not work_id:
                continue

            source_path = extract_pdf_path(file_field)
            if not source_path or not source_path.exists():
                stats["missing"] += 1
                missing_log.append(work_id)
                continue

            try:
                file_hash = sha256sum(source_path)
            except OSError:
                stats["missing"] += 1
                continue

            target_filename = "{0}.pdf".format(file_hash)
            target_path = objects_dir / target_filename
            pdf_map[work_id] = target_filename

            if target_path.exists():
                stats["skipped"] += 1
                continue

            shutil.copy2(source_path, target_path)
            stats["new"] += 1

    map_output.parent.mkdir(parents=True, exist_ok=True)
    with map_output.open("w", encoding="utf-8") as f:
        json.dump(pdf_map, f, indent=2)

    if missing_log:
        print("warning: {0} papers missing PDFs".format(len(missing_log)))

    print(
        "internalize complete: new={0} cached={1} missing={2}".format(
            stats["new"], stats["skipped"], stats["missing"]
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Internalize PDFs into CAS storage.")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--objects-dir", default=str(DEFAULT_OBJECTS_DIR))
    parser.add_argument("--map-output", default=str(DEFAULT_MAP_FILE))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bib_paths = [Path(path) for path in args.inputs]
    objects_dir = Path(args.objects_dir)
    map_output = Path(args.map_output)
    sys.exit(internalize_pdfs(bib_paths, objects_dir, map_output))


if __name__ == "__main__":
    main()
