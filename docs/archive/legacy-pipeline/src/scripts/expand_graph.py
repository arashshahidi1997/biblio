#!/usr/bin/env python3
"""Expand the graph using OpenAlex and emit discovery candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pyalex import Works
from sutil.repo_root import repo_abs


def load_manifest(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def resolve_title(title: str) -> dict | None:
    if not title:
        return None
    try:
        results = Works().search(title).get()
    except Exception as exc:
        print("openalex: resolve failed for title '{0}': {1}".format(title, exc))
        return None
    if results:
        return results[0]
    return None


def expand_ancestors(work: dict) -> list[str]:
    return work.get("referenced_works", []) or []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expand OpenAlex graph from manifest seeds.")
    parser.add_argument("--manifest", type=Path, default=repo_abs("manifest.jsonl"))
    parser.add_argument("--output", type=Path, default=repo_abs("data/graph/expansion_candidates.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_manifest(args.manifest)
    existing_work_ids = {rec.get("work_id") for rec in records if rec.get("work_id")}

    candidates = []
    for record in records:
        work_id = record.get("work_id")
        meta = record.get("meta", {})
        title = meta.get("title") or work_id
        if not work_id:
            continue

        resolved = resolve_title(title)
        if not resolved:
            continue

        refs = expand_ancestors(resolved)
        for ref_url in refs:
            oa_id = ref_url.split("/")[-1]
            candidate_id = "oa_{0}".format(oa_id)
            if candidate_id in existing_work_ids:
                continue
            candidates.append(
                {
                    "work_id": candidate_id,
                    "status": "discovered",
                    "source": "openalex_expansion",
                    "parent_work": work_id,
                    "openalex_id": oa_id,
                }
            )
            existing_work_ids.add(candidate_id)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    print("openalex: wrote {0} candidates to {1}".format(len(candidates), args.output))


if __name__ == "__main__":
    main()
