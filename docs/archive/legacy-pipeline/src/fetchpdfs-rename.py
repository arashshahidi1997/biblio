#!/usr/bin/env python3
"""
Copy linked PDFs from all .bib files in ./metadata/ to ./pdfs/,
renaming them like:
    auth.lower + "_" + year + "_" + TitleWord1TitleWord2
Example: jordan_2019_FromSocial.pdf

Features:
- Idempotent: re-running doesn’t duplicate or recopy unchanged files.
- Handles {{braces}}, LaTeX escapes (\dots, \textit{...}), etc.
- Logs missing PDFs to missing_pdfs.txt.
- Keeps a .pdf_manifest.json with file hashes for change detection.
"""

import bibtexparser, os, re, shutil, json, hashlib
from pathlib import Path

# ---------- paths ----------
ROOT = Path(__file__).resolve().parents[1]
METADATA_DIR = ROOT / "metadata"
PDF_DIR = ROOT / "pdfs"
PDF_DIR.mkdir(exist_ok=True)

MISSING_LOG = ROOT / "missing_pdfs.txt"
MANIFEST_FILE = ROOT / ".pdf_manifest.json"

# ---------- helpers ----------

def clean_text(s: str) -> str:
    """Remove LaTeX markup, braces, and unsafe chars."""
    if not s:
        return ""
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\\[A-Za-z]+(\s*\{[^}]*\})?", "", s)
    s = re.sub(r"[^0-9A-Za-z _\-\.]+", "", s)
    return " ".join(s.split()).strip()

def first_author_lastname(author_field: str) -> str:
    """Extract first author's last name (handles 'Last, First' and 'First Last')."""
    if not author_field:
        return "unknown"
    first_author = author_field.split(" and ")[0].strip()
    if "," in first_author:
        last = first_author.split(",")[0].strip()
    else:
        parts = first_author.split()
        last = parts[-1] if parts else "unknown"
    return clean_text(last).lower() or "unknown"

def title_pascalcase_first_n(title: str, n_words: int = 2) -> str:
    """Take first n words of title, capitalize each, concatenate."""
    t = clean_text(title)
    if not t:
        return "Xx"
    words = t.split()[:n_words]
    return "".join(w.capitalize() for w in words)

def extract_pdf_path(file_field: str) -> str | None:
    """Return the path to a .pdf file from a Better BibTeX file field."""
    parts = [p.strip() for p in file_field.split(":")]
    for p in parts:
        if p.lower().endswith(".pdf"):
            return p
    if file_field.lower().endswith(".pdf"):
        return file_field.strip()
    return None

def md5sum(path: Path) -> str:
    """Compute MD5 checksum for file contents."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# ---------- load manifest ----------
manifest = {}
if MANIFEST_FILE.exists():
    try:
        manifest = json.loads(MANIFEST_FILE.read_text())
    except json.JSONDecodeError:
        manifest = {}

# reset missing log each run
if MISSING_LOG.exists():
    MISSING_LOG.unlink()

# ---------- main ----------
for bibfile in sorted(METADATA_DIR.glob("*.bib")):
    print(f"📘 Processing {bibfile.name}...")
    with open(bibfile, encoding="utf-8") as f:
        bib = bibtexparser.load(f)

    for entry in bib.entries:
        key = entry.get("ID") or entry.get("key") or "unknown_key"
        file_field = entry.get("file")

        # -- no file field --
        if not file_field:
            print(f"  ❌ No file field for: {key}")
            with open(MISSING_LOG, "a", encoding="utf-8") as f:
                f.write(f"No file field: {key}\n")
            continue

        # -- extract actual pdf path --
        pdf_path = extract_pdf_path(file_field)
        if not pdf_path or not os.path.exists(pdf_path):
            print(f"  ❌ No PDF found for: {key}")
            with open(MISSING_LOG, "a", encoding="utf-8") as f:
                f.write(f"No PDF: {key}\t{pdf_path or 'N/A'}\n")
            continue

        # -- build clean filename --
        author_key = first_author_lastname(entry.get("author", ""))
        year = clean_text(entry.get("year", "")) or "0000"
        short_cc = title_pascalcase_first_n(entry.get("title", ""), 2)
        newname = f"{author_key}_{year}_{short_cc}.pdf"
        target = PDF_DIR / newname

        src_hash = md5sum(Path(pdf_path))

        # -- idempotent logic --
        if target.exists():
            prev_hash = manifest.get(newname)
            if prev_hash == src_hash:
                print(f"  ↩︎ Skipping (unchanged): {target.name}")
                continue
            else:
                print(f"  ⚠️ Overwriting changed file: {target.name}")
                shutil.copy(pdf_path, target)
        else:
            shutil.copy(pdf_path, target)
            print(f"  ✅ Copied: {target.name}")

        manifest[newname] = src_hash

# ---------- save manifest ----------
MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
print("\n✨ Done. PDFs copied to ./pdfs/ with citekey-like names.")
print(f"🧾 Manifest saved to {MANIFEST_FILE}")
print(f"🪶 Missing file list written to {MISSING_LOG}")
