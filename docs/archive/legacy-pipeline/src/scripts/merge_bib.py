"""Lax merge of .bib files using bibtexparser with deduplication."""

from __future__ import annotations

import argparse

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lax merge of .bib files")
    parser.add_argument("--inputs", nargs="+", required=True, help="Input .bib files")
    parser.add_argument("--output", required=True, help="Output merged .bib file")
    return parser.parse_args()


def merge_bibs_lax(input_files: list[str], output_file: str) -> int:
    merged_entries = []
    keys_seen: set[str] = set()
    total_entries = 0
    duplicates_dropped = 0

    print("Lax Merge: Processing {0} files...".format(len(input_files)))

    for file_path in sorted(input_files):
        try:
            with open(file_path, "r", encoding="utf-8") as bibtex_file:
                parser = BibTexParser()
                parser.ignore_nonstandard_types = True
                parser.homogenise_fields = False
                parser.common_strings = False
                parser.customization = convert_to_unicode
                db = bibtexparser.load(bibtex_file, parser=parser)
        except Exception as exc:
            print("Warning: Issue reading {0}: {1}".format(file_path, exc))
            continue

        for entry in db.entries:
            raw_key = entry.get("ID")
            if not raw_key:
                continue
            norm_key = raw_key.lower()
            if norm_key in keys_seen:
                duplicates_dropped += 1
                continue
            keys_seen.add(norm_key)
            merged_entries.append(entry)
            total_entries += 1

    out_db = bibtexparser.bibdatabase.BibDatabase()
    out_db.entries = merged_entries

    print("Writing {0}...".format(output_file))
    with open(output_file, "w", encoding="utf-8") as out_file:
        bibtexparser.dump(out_db, out_file)

    print("Merged {0} unique entries to {1}".format(total_entries, output_file))
    print("Dropped {0} duplicates during merge.".format(duplicates_dropped))
    return 0


def main() -> None:
    args = parse_args()
    raise SystemExit(merge_bibs_lax(args.inputs, args.output))


if __name__ == "__main__":
    main()
