"""Entry quality scoring and validation for biblio.

Assigns a quality tier to each BibTeX entry based on field completeness.
Used by merge (warnings), library lint (reporting), and citekey_resolve (scoring).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Fields that indicate a real scholarly entry
_IDENTITY_FIELDS = {"title", "doi"}
_AUTHORSHIP_FIELDS = {"author", "editor"}
_PUBLICATION_FIELDS = {"year", "journal", "booktitle", "publisher", "volume", "pages"}

# Known garbage citekeys / titles (case-insensitive substrings)
_NOISE_TITLES = frozenset({
    "abstract", "untitled", "no title", "title", "references",
    "bibliography", "table of contents", "uncategorized",
    "supplementary", "erratum", "corrigendum",
})

# Minimum title length for a real entry
_MIN_TITLE_LEN = 8


@dataclass(frozen=True)
class EntryQuality:
    """Quality assessment for a single BibTeX entry."""

    citekey: str
    tier: str  # "good", "sparse", "stub", "noise"
    score: int  # 0-100
    issues: tuple[str, ...]
    has_doi: bool
    has_authors: bool
    has_year: bool
    has_title: bool
    field_count: int


def score_entry(
    citekey: str,
    fields: dict[str, Any],
    authors: list[str] | None = None,
    entry_type: str = "",
) -> EntryQuality:
    """Score a BibTeX entry's quality.

    Args:
        citekey: The BibTeX citekey.
        fields: Dict of BibTeX fields (title, doi, year, journal, etc.).
        authors: List of author names (from pybtex persons).
        entry_type: BibTeX entry type (article, book, etc.).

    Returns:
        EntryQuality with tier, score, and specific issues.
    """
    issues: list[str] = []

    # Normalize field access
    title = str(fields.get("title") or "").strip()
    doi = str(fields.get("doi") or "").strip()
    year = str(fields.get("year") or "").strip()
    has_authors = bool(authors and any(a.strip() for a in authors))
    has_doi = bool(doi)
    has_year = bool(year) and year.isdigit()
    has_title = bool(title) and len(title) >= _MIN_TITLE_LEN

    # Count substantive fields (excluding file, abstract, keywords — those are metadata)
    substantive = {k for k, v in fields.items() if v and str(v).strip() and k not in ("file", "abstract", "keywords", "note", "annote")}
    field_count = len(substantive) + (1 if has_authors else 0)

    # Check for noise patterns
    title_lower = title.lower().strip("{} ")
    citekey_lower = citekey.lower()

    is_noise = False
    if title_lower in _NOISE_TITLES or citekey_lower in _NOISE_TITLES:
        issues.append(f"title matches known noise pattern: {title!r}")
        is_noise = True
    if title_lower and title_lower == citekey_lower:
        issues.append(f"title identical to citekey: {title!r}")
        is_noise = True
    if len(title) > 0 and len(title) < _MIN_TITLE_LEN:
        issues.append(f"title too short ({len(title)} chars): {title!r}")

    # Missing field checks
    if not has_title:
        issues.append("missing title")
    if not has_authors:
        issues.append("missing authors")
    if not has_year:
        issues.append("missing year")
    if not has_doi:
        issues.append("no DOI")

    # Score: 0-100
    score = 0
    if has_title:
        score += 25
    if has_authors:
        score += 25
    if has_year:
        score += 15
    if has_doi:
        score += 20
    # Bonus for publication venue
    if any(fields.get(f) for f in ("journal", "booktitle", "publisher")):
        score += 10
    # Bonus for volume/pages
    if any(fields.get(f) for f in ("volume", "pages", "number")):
        score += 5

    # Determine tier
    if is_noise:
        tier = "noise"
        score = min(score, 10)
    elif score >= 60:
        tier = "good"
    elif score >= 30:
        tier = "sparse"
    else:
        tier = "stub"

    return EntryQuality(
        citekey=citekey,
        tier=tier,
        score=score,
        issues=tuple(issues),
        has_doi=has_doi,
        has_authors=has_authors,
        has_year=has_year,
        has_title=has_title,
        field_count=field_count,
    )


def score_bib_database(bib_db) -> list[EntryQuality]:
    """Score all entries in a pybtex BibliographyData."""
    results = []
    for key, entry in bib_db.entries.items():
        fields = dict(entry.fields)
        authors = []
        for person_list in entry.persons.values():
            for person in person_list:
                parts = list(person.first_names or []) + list(person.last_names or [])
                authors.append(" ".join(parts))
        results.append(score_entry(key, fields, authors=authors, entry_type=entry.type))
    return results
