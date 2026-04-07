"""Reconcile Docling/GROBID outputs with alignment overrides."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from sutil.repo_root import repo_abs

SRC = Path(repo_abs("src"))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bib_pipeline.models import AlignmentOverrides


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile Silver artifacts")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--docling", type=Path, required=True)
    parser.add_argument("--grobid", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_docling(docling_path: Path) -> Dict[str, Any]:
    try:
        return json.loads(docling_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "unreadable_docling_json"}


def main() -> None:
    args = parse_args()
    overrides = AlignmentOverrides.from_path(args.overrides)
    docling_payload = load_docling(args.docling)

    work_overrides = overrides.by_work.get(args.work_id, [])
    payload = {
        "work_id": args.work_id,
        "docling_path": str(args.docling),
        "grobid_path": str(args.grobid),
        "override_count": len(work_overrides),
        "docling_summary": docling_payload,
        "notes": "merge logic goes here; this is a scaffold only",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
