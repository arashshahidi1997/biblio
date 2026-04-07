#!/usr/bin/env python3
"""Docling extraction wrapper with CAS-aware caching."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from bib_pipeline.config import config


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_docling(input_path: Path, output_path: Path) -> None:
    source_hash = file_hash(input_path)

    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            meta = existing.get("_meta", {})
            if (
                meta.get("source_hash") == source_hash
                and meta.get("tool_version") == config.docling.version
            ):
                print(
                    "skip: {0} matches source hash and version".format(
                        input_path.name
                    )
                )
                return
        except Exception:
            pass

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = config.docling.do_ocr
    pipeline_options.do_table_structure = config.docling.do_table_structure
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    result = converter.convert(input_path)
    output_dict = result.document.export_to_dict()
    output_dict["_meta"] = {
        "source_path": str(input_path),
        "source_hash": source_hash,
        "tool": "docling",
        "tool_version": config.docling.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_dict), encoding="utf-8")
    print("saved: {0}".format(output_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Docling extraction with caching.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--map", required=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    extract_docling(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
