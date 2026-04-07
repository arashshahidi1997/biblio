"""Reusable test harness for pipeline commands."""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path
from typing import List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pipeline test commands")
    parser.add_argument(
        "--work-id",
        action="append",
        dest="work_ids",
        default=[],
        help="Work ID to test (repeatable). Defaults to first registry entry.",
    )
    parser.add_argument("--skip-mkdocs", action="store_true")
    parser.add_argument("--skip-gold", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(cmd: List[str], dry_run: bool) -> None:
    cmd_str = " ".join(shlex.quote(part) for part in cmd)
    print(f"$ {cmd_str}")
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def resolve_default_work_id() -> str:
    registry = Path("data/01_bronze/registry.json")
    if not registry.exists():
        raise FileNotFoundError("Missing data/01_bronze/registry.json; run ingest_bronze first.")
    import json

    payload = json.loads(registry.read_text(encoding="utf-8"))
    works = payload.get("works", [])
    if not works:
        raise ValueError("Registry has no works.")
    return works[0]["work_id"]


def main() -> None:
    args = parse_args()
    work_ids = args.work_ids or [resolve_default_work_id()]
    work_ids_arg = f'["{work_ids[0]}"]' if len(work_ids) == 1 else str(work_ids)

    run(
        [
            "snakemake",
            "-j1",
            "compile_project_bib",
            "validate_project_bib",
            "internalize_pdfs",
            "link_pdfs",
            "build_manifest",
        ],
        args.dry_run,
    )

    run(
        [
            "python",
            "src/scripts/ingest_bronze.py",
            "--bib",
            "data/01_bronze/project.bib",
            "--bronze-root",
            "data/01_bronze",
            "--pdf-map",
            "data/01_bronze/pdf_map.json",
            "--objects-dir",
            "data/01_bronze/objects",
            "--registry",
            "data/01_bronze/registry.json",
            "--manifest",
            "manifest.ingest.jsonl",
        ],
        args.dry_run,
    )

    run(
        [
            "snakemake",
            "-j1",
            "extract_docling",
            "extract_grobid",
            "--config",
            f"work_ids={work_ids_arg}",
        ],
        args.dry_run,
    )
    run(
        ["snakemake", "-j1", "reconcile_silver", "--config", f"work_ids={work_ids_arg}"],
        args.dry_run,
    )
    run(
        ["snakemake", "-j1", "validate", "--config", f"work_ids={work_ids_arg}"],
        args.dry_run,
    )

    if not args.skip_gold:
        run(
            ["snakemake", "-j1", "build_gold", "--config", f"work_ids={work_ids_arg}"],
            args.dry_run,
        )

    if not args.skip_mkdocs:
        run(["mkdocs", "build"], args.dry_run)


if __name__ == "__main__":
    main()
