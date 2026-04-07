"""Ingest Bronze inputs into a registry and manifest ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from pybtex.database import parse_file


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_pdf_path(bronze_root: Path, entry_fields: Dict[str, str], citekey: str) -> Optional[Path]:
    file_field = entry_fields.get("file")
    if file_field:
        pdf_path = Path(file_field)
        if pdf_path.is_absolute():
            return pdf_path if pdf_path.exists() else None
        if pdf_path.parts and pdf_path.parts[0] == "bib":
            pdf_path = Path(*pdf_path.parts[1:])
        candidate = bronze_root / pdf_path
        if candidate.exists():
            return candidate
    fallback = bronze_root / "pdfs" / f"{citekey}.pdf"
    if fallback.exists():
        return fallback
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Bronze registry and manifest entries")
    parser.add_argument("--bib", type=Path, required=True)
    parser.add_argument("--bronze-root", type=Path, required=True)
    parser.add_argument("--pdf-map", type=Path, default=None)
    parser.add_argument("--objects-dir", type=Path, default=None)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bib_path = args.bib
    bronze_root = args.bronze_root
    pdf_map_path = args.pdf_map
    objects_dir = args.objects_dir
    registry_path = args.registry
    manifest_path = args.manifest
    log_path = args.log
    log_lines = []

    bib_db = parse_file(str(bib_path))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pdf_map = {}
    if pdf_map_path and pdf_map_path.exists():
        try:
            pdf_map = json.loads(pdf_map_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pdf_map = {}

    registry = {
        "run_id": run_id,
        "source_bib": bib_path.name,
        "works": [],
    }
    log_lines.append("run_id: {0}".format(run_id))
    log_lines.append("bib: {0}".format(bib_path))

    manifest_entries = []
    manifest_entries.append(
        {
            "record_type": "run",
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": "ingestion",
            "status": "started",
            "source_bib": str(bib_path),
        }
    )

    for citekey, entry in bib_db.entries.items():
        work_id = citekey
        pdf_path = None
        if pdf_map:
            filename = pdf_map.get(citekey)
            if filename and objects_dir:
                candidate = objects_dir / filename
                if candidate.exists():
                    pdf_path = candidate
        if not pdf_path:
            pdf_path = resolve_pdf_path(bronze_root, entry.fields, citekey)
        artifact_id = file_hash(pdf_path) if pdf_path else None
        status = "success" if pdf_path else "failed"
        failure_reason = None if pdf_path else "pdf_not_found"

        registry["works"].append(
            {
                "work_id": work_id,
                "citekey": citekey,
                "artifact_id": artifact_id,
                "pdf_path": str(pdf_path) if pdf_path else None,
            }
        )
        log_lines.append("work_id: {0} status={1}".format(work_id, status))

        manifest_entries.append(
            {
                "record_type": "work",
                "run_id": run_id,
                "work_id": work_id,
                "artifact_id": artifact_id,
                "stage": "ingestion",
                "status": status,
                "failure_reason": failure_reason,
            }
        )

    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    log_lines.append("wrote registry: {0}".format(registry_path))

    with manifest_path.open("a", encoding="utf-8") as f:
        for entry in manifest_entries:
            f.write(json.dumps(entry) + "\n")
    log_lines.append("appended manifest: {0}".format(manifest_path))

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        print("Log written to: {0}".format(log_path))
    else:
        print("\n".join(log_lines))


if __name__ == "__main__":
    main()
