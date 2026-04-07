"""Validate BibTeX syntax using pybtex."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pybtex.database.input.bibtex import Parser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate BibTeX syntax")
    parser.add_argument("input", type=Path, help="Input .bib file")
    return parser.parse_args()


def validate(path: Path) -> int:
    parser = Parser()
    try:
        parser.parse_file(str(path))
        print("OK: {0} is valid.".format(path))
        return 0
    except Exception as exc:  # pragma: no cover - error details vary by parser
        print("ERROR: Syntax error in {0}".format(path))
        print("DETAIL: {0}".format(exc))
        return 1


def main() -> None:
    args = parse_args()
    sys.exit(validate(args.input))


if __name__ == "__main__":
    main()
