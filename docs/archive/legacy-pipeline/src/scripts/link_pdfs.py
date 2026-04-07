"""Symlink internalized PDFs to citekey filenames."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Symlink PDFs to citekey-based filenames")
    parser.add_argument("--pdf-map", type=Path, required=True)
    parser.add_argument("--objects-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for item in out_dir.iterdir():
            if item.is_symlink() or item.is_file():
                item.unlink()

    linked = 0
    missing = 0
    report = {}
    pdf_map = json.loads(args.pdf_map.read_text(encoding="utf-8"))
    for citekey, filename in sorted(pdf_map.items()):
        pdf_path = args.objects_dir / filename
        if not pdf_path.exists():
            missing += 1
            report[citekey] = None
            continue
        link_path = out_dir / "{0}.pdf".format(citekey)
        if link_path.exists():
            report[citekey] = str(link_path)
            continue
        rel_target = Path(os.path.relpath(pdf_path, start=out_dir))
        if args.dry_run:
            print("link {0} -> {1}".format(link_path, rel_target))
            linked += 1
            report[citekey] = str(link_path)
            continue
        link_path.symlink_to(rel_target)
        linked += 1
        report[citekey] = str(link_path)

    print("linked: {0}, missing: {1}".format(linked, missing))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("report: {0}".format(args.report))


if __name__ == "__main__":
    main()
