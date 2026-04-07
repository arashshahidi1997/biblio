"""Generate a manifest that joins BibTeX entries with PDF availability."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import bibtexparser


def generate_manifest(bib_path: Path, pdf_report_path: Path, output_path: Path) -> None:
    """Merge BibTeX registry data with PDF inventory to produce a status ledger."""
    try:
        with bib_path.open("r", encoding="utf-8") as f:
            bib_db = bibtexparser.load(f)
    except Exception as exc:
        print("error: could not read project.bib: {0}".format(exc))
        sys.exit(1)

    pdf_map = {}
    if pdf_report_path and pdf_report_path.exists():
        try:
            with pdf_report_path.open("r", encoding="utf-8") as f:
                pdf_map = json.load(f)
        except json.JSONDecodeError:
            print("warning: pdf report is empty or invalid JSON; assuming no PDFs found.")

    timestamp = datetime.now(timezone.utc).isoformat()
    records = []
    stats = {"total": 0, "ready": 0, "missing_pdf": 0}

    for entry in bib_db.entries:
        work_id = entry.get("ID")
        if not work_id:
            continue
        pdf_path = pdf_map.get(work_id)
        has_pdf = bool(pdf_path) and Path(pdf_path).exists()
        status = "ready_for_extraction" if has_pdf else "missing_pdf"
        if has_pdf:
            stats["ready"] += 1
        else:
            stats["missing_pdf"] += 1

        record = {
            "work_id": work_id,
            "timestamp": timestamp,
            "stage": "bronze",
            "status": status,
            "meta": {
                "title": entry.get("title", "").strip("{}"),
                "year": entry.get("year", ""),
                "doi": entry.get("doi", ""),
                "has_pdf": has_pdf,
                "pdf_path": str(pdf_path) if pdf_path else None,
            },
        }
        records.append(record)
        stats["total"] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print("manifest generated: {0}".format(output_path))
    print(
        "total: {0}, ready: {1}, missing_pdf: {2}".format(
            stats["total"], stats["ready"], stats["missing_pdf"]
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the project manifest ledger")
    parser.add_argument("--bib", type=Path, required=True)
    parser.add_argument("--pdf-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_manifest(args.bib, args.pdf_report, args.output)


if __name__ == "__main__":
    main()
