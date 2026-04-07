"""Normalize BibTeX file fields using extracted PDF paths."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bibtexparser
from sutil.repo_root import repo_abs

SRC = Path(repo_abs("src"))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fetch import extract_pdf_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rewrite BibTeX file fields to local PDF paths")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix", default="bib/pdfs", help="Prefix for normalized file paths")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input
    output_path = args.output
    if not input_path.is_absolute():
        input_path = Path(repo_abs(str(input_path)))
    if not output_path.is_absolute():
        output_path = Path(repo_abs(str(output_path)))

    with input_path.open(encoding="utf-8") as f:
        bib = bibtexparser.load(f)

    for entry in bib.entries:
        pdf_path = extract_pdf_path(entry.get("file", ""))
        if pdf_path:
            entry["file"] = "{0}/{1}".format(args.prefix, Path(pdf_path).name)
        else:
            entry.pop("file", None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        bibtexparser.dump(bib, f)


if __name__ == "__main__":
    main()
