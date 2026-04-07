"""Extraction wrapper that enforces CAS output layout and caching."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Optional


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def safe_file_hash(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return "missing"
    return file_hash(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CAS-aware extraction wrapper")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--tool-name", required=True)
    parser.add_argument("--tool-version", required=True)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--link-path", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_path = args.pdf
    config_path = args.config

    artifact_id = file_hash(pdf_path)
    config_hash = safe_file_hash(config_path)
    extraction_id = f"{artifact_id}__{args.tool_name}__{args.tool_version}__{config_hash}"

    output_dir = args.output_dir
    output_file = args.output_file
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = output_dir / "metadata.json"
    if output_file.exists():
        print(f"Cached output exists at {output_file}; skipping extraction.")
        if args.link_path:
            args.link_path.parent.mkdir(parents=True, exist_ok=True)
            if not args.link_path.exists():
                args.link_path.symlink_to(output_file)
        return

    metadata = {
        "extraction_id": extraction_id,
        "artifact_id": artifact_id,
        "tool_name": args.tool_name,
        "tool_version": args.tool_version,
        "config_hash": config_hash,
        "source_pdf": str(pdf_path),
        "config_path": str(config_path) if config_path else None,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Placeholder output for scaffold; replace with actual tool invocation.
    if output_file.suffix.lower() == ".xml":
        output_file.write_text(
            f'<extraction status="placeholder" extraction_id="{extraction_id}"/>',
            encoding="utf-8",
        )
    else:
        output_file.write_text(
            json.dumps(
                {"status": "placeholder extraction", "extraction_id": extraction_id},
                indent=2,
            ),
            encoding="utf-8",
        )
    if args.link_path:
        args.link_path.parent.mkdir(parents=True, exist_ok=True)
        if args.link_path.exists():
            args.link_path.unlink()
        args.link_path.symlink_to(output_file)
        print(f"Linked output at {args.link_path} -> {output_file}")
    else:
        print(f"Wrote placeholder output to {output_file}")


if __name__ == "__main__":
    main()
