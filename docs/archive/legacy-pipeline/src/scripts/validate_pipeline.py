"""Validate Silver artifacts and record results in the manifest."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sutil.repo_root import repo_abs

SRC = Path(repo_abs("src"))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bib_pipeline.models import AlignmentOverrides


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Silver artifacts before Gold indexing")
    parser.add_argument("--silver-root", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-alignment-coverage", type=float, default=0.8)
    parser.add_argument("--max-unresolved-rate", type=float, default=0.2)
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_error": "invalid_json"}


def compute_metrics(silver_files: List[Path], overrides: AlignmentOverrides) -> Dict[str, Any]:
    total = len(silver_files)
    with_overrides = 0
    unresolved_count = 0
    schema_errors: List[str] = []

    for silver_path in silver_files:
        payload = load_json(silver_path)
        required_keys = {"work_id", "docling_path", "grobid_path", "override_count"}
        missing = required_keys - payload.keys()
        if missing:
            schema_errors.append(f"{silver_path.name}: missing {sorted(missing)}")

        work_id = payload.get("work_id")
        if work_id and overrides.by_work.get(work_id):
            with_overrides += 1

        unresolved = payload.get("unresolved_citations")
        if isinstance(unresolved, list):
            unresolved_count += len(unresolved)

    alignment_coverage = (with_overrides / total) if total else 0.0
    unresolved_rate = (unresolved_count / total) if total else 0.0

    return {
        "total_silver": total,
        "alignment_coverage": alignment_coverage,
        "unresolved_rate": unresolved_rate,
        "schema_errors": schema_errors,
    }


def main() -> None:
    args = parse_args()
    silver_files = sorted(args.silver_root.glob("*.json"))
    overrides = AlignmentOverrides.from_path(args.overrides)

    metrics = compute_metrics(silver_files, overrides)
    status = "success"
    failures = []

    if metrics["alignment_coverage"] < args.min_alignment_coverage:
        status = "failed"
        failures.append("alignment_coverage_below_threshold")
    if metrics["unresolved_rate"] > args.max_unresolved_rate:
        status = "failed"
        failures.append("unresolved_rate_above_threshold")
    if metrics["schema_errors"]:
        status = "failed"
        failures.append("schema_compliance_failed")

    result = {
        "record_type": "validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": "validation",
        "status": status,
        "failures": failures,
        "metrics": metrics,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    with args.manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
