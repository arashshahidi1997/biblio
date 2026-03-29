from __future__ import annotations

from pathlib import Path

from ._pybtex_utils import parse_bibtex_file, require_pybtex


def export_bibtex(
    citekeys: list[str],
    repo_root: str | Path,
) -> str:
    """Return formatted .bib content for the requested citekeys.

    Reads entries from the merged BibTeX file (bib/main.bib) and returns
    only the entries matching *citekeys*.

    Raises:
        FileNotFoundError: If the merged bib file does not exist.
        KeyError: If none of the requested citekeys are found.
    """
    require_pybtex("BibTeX export")
    from pybtex.database import BibliographyData
    from pybtex.database.output.bibtex import Writer

    repo_root = Path(repo_root).expanduser().resolve()
    bib_path = repo_root / "bib" / "main.bib"
    if not bib_path.exists():
        raise FileNotFoundError(
            f"Merged bib file not found: {bib_path}. Run 'biblio bibtex merge' first."
        )

    db = parse_bibtex_file(bib_path)

    out = BibliographyData()
    missing: list[str] = []
    for key in citekeys:
        clean = key.lstrip("@").strip()
        if clean in db.entries:
            out.entries[clean] = db.entries[clean]
        else:
            missing.append(clean)

    if not out.entries:
        raise KeyError(
            f"None of the requested citekeys found in {bib_path}: {missing}"
        )

    writer = Writer()
    return writer.to_string(out)
