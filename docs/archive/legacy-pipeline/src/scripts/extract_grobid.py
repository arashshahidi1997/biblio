#!/usr/bin/env python3
"""GROBID extraction wrapper with CAS-aware caching."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import requests

from bib_pipeline.config import config


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_grobid(input_path: Path, output_xml_path: Path) -> None:
    meta_path = output_xml_path.with_suffix(".meta.json")
    source_hash = file_hash(input_path)

    if output_xml_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (
                meta.get("source_hash") == source_hash
                and meta.get("tool_version") == config.grobid.version
            ):
                print("skip: {0} up-to-date".format(input_path.name))
                return
        except Exception:
            pass

    url = "{0}/api/processFulltextDocument".format(config.grobid.service_url)
    params = {
        "consolidateHeader": config.grobid.consolidate_header,
        "consolidateCitations": config.grobid.consolidate_citations,
        "teiCoordinates": ["ref", "biblStruct", "persName", "figure", "formula", "s"],
    }

    with input_path.open("rb") as f:
        files = {"input": f}
        resp = requests.post(url, files=files, data=params, timeout=300)
    resp.raise_for_status()

    output_xml_path.parent.mkdir(parents=True, exist_ok=True)
    output_xml_path.write_bytes(resp.content)

    meta = {
        "source_path": str(input_path),
        "source_hash": source_hash,
        "tool": "grobid",
        "tool_version": config.grobid.version,
        "timestamp": time.time(),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print("saved: {0}".format(output_xml_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run GROBID extraction with caching.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extract_grobid(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
