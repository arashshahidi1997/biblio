#!/usr/bin/env python3
"""
Merge multiple .bib files into a single project bibliography.

This script intentionally avoids rewriting entry fields so it can be used
purely as a merger step in the pipeline.
"""

import argparse
import bibtexparser, os, re, shutil, json, hashlib
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Merge BibTeX files into a single project bibliography")
    parser.add_argument("--bib-dir", type=Path, required=True, help="Directory containing .bib files")
    parser.add_argument("--output", type=Path, required=True, help="Output .bib file path")
    return parser.parse_args()

def merge_bib_files(bib_files, output_file):
    """Merge multiple .bib files into one, deterministically and without side effects."""
    merged_entries = []

    # deterministic ordering → no random reordering across runs
    for bibfile in sorted(bib_files):
        with open(bibfile, encoding="utf-8") as f:
            bib = bibtexparser.load(f)

        # deterministic entry order
        for entry in sorted(bib.entries, key=lambda e: e.get("ID", "")):
            print(f"Processing entry: {entry.get('ID', 'unknown')}")

            merged_entries.append(entry.copy())

    # build new merged DB cleanly
    merged_bib = bibtexparser.bibdatabase.BibDatabase()
    merged_bib.entries = merged_entries

    # overwrite final output deterministically
    with open(output_file, "w", encoding="utf-8") as f:
        bibtexparser.dump(merged_bib, f)


def main():
    args = parse_args()
    bib_files = list(args.bib_dir.glob("*.bib"))
    merge_bib_files(bib_files, args.output)


if __name__ == "__main__":
    main()
