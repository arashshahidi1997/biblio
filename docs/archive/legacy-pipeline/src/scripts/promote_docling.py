#!/usr/bin/env python3
"""Promote raw Docling output into a minimal Silver artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote Docling output to Silver.")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--docling", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    docling_payload = json.loads(args.docling.read_text(encoding="utf-8"))

    silver = {
        "id": args.work_id,
        "metadata": {
            "title": "TODO: Parsed from Docling",
            "authors": [],
        },
        "content": docling_payload,
        "bibliography": [],
        "provenance": {
            "docling_source": str(args.docling),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(silver, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
