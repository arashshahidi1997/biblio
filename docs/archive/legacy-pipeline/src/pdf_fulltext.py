#!/usr/bin/env python
import sys
from pathlib import Path
from pybtex.database import parse_file
from pdfminer.high_level import extract_text

PROJECT = Path(__file__).resolve().parents[1]
BIB = PROJECT / "pixecog.bib"
bib_db = parse_file(str(BIB))

def pdf_for_key(key):
    entry = bib_db.entries[key]
    file_field = entry.fields.get("file")
    if not file_field:
        raise RuntimeError(f"No file= field for {key}")
    pdf_rel = Path(file_field)
    if pdf_rel.parts[0] == "bib":
        pdf_rel = Path(*pdf_rel.parts[1:])
    return PROJECT / pdf_rel

def main():
    key, outdir = sys.argv[1], Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    pdf_path = pdf_for_key(key)
    text = extract_text(str(pdf_path))

    txt_out = outdir / "full.txt"
    txt_out.write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
