"""Citekey construction — pure functions over metadata, no I/O.

Two modes:

- lenient (``strict=False``): always returns a string, using fallbacks
  (``anon``, ``nd``, ``Record``, DOI-tail). Used by fresh ingest where
  *some* key must be produced even for incomplete records.
- strict (``strict=True``): returns ``None`` if any required component
  (author, year, short title) is missing or would fall back. Used by
  the normalize path to refuse renames when metadata is incomplete.

Metadata resolution (enrichment) is a separate concern — see ``enrich.py``
and ``ingest.enrich_and_cache``. Callers that want "fix everything"
should enrich first, then normalize.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .ingest import IngestRecord

_STOPWORDS = {
    "a", "an", "and", "for", "from", "in", "of", "on", "the", "to", "with",
}


class SkipReason:
    MISSING_AUTHOR = "missing_author"
    MISSING_YEAR = "missing_year"
    MISSING_TITLE = "missing_title"


@dataclass(frozen=True)
class CitekeyResult:
    """Result of a strict citekey build: either a key or a skip reason."""
    key: str | None
    reason: str | None  # one of SkipReason.* when key is None


def _transliterate(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _author_token(authors: Iterable[str], *, strict: bool) -> str | None:
    first = next(iter(authors), None)
    if not first or not str(first).strip():
        return None if strict else "anon"
    if "," in first:
        family = first.split(",", 1)[0].strip()
    else:
        family = first.split()[-1]
    ascii_approx = _transliterate(family)
    token = re.sub(r"[^A-Za-z0-9]+", "", ascii_approx).lower()
    if not token:
        return None if strict else "anon"
    return token


def _year_token(year: str | None, *, strict: bool) -> str | None:
    if not year:
        return None if strict else "nd"
    m = re.search(r"\d{4}", str(year))
    if m:
        return m.group(0)
    return None if strict else "nd"


def _title_token(title: str | None, doi: str | None, *, strict: bool, n_words: int = 2) -> str | None:
    if title:
        ascii_title = _transliterate(title)
        words: list[str] = []
        for raw in re.split(r"[^A-Za-z0-9]+", ascii_title):
            if raw and raw.lower() not in _STOPWORDS and len(words) < n_words:
                words.append(raw.capitalize())
        if words:
            return "".join(words)
    if strict:
        return None
    # lenient fallback: DOI tail, then "Record"
    if doi:
        tail = doi.rstrip("/").split("/")[-1]
        token = re.sub(r"[^A-Za-z0-9]+", "", tail)
        if token:
            return token[:20].capitalize()
    return "Record"


def canonical_citekey(record: "IngestRecord", *, strict: bool = True) -> CitekeyResult:
    """Build the ``author_year_Title`` key for a record.

    In strict mode, returns ``CitekeyResult(key=None, reason=...)`` when any
    component is missing. In lenient mode, always returns a key (with
    fallbacks) and ``reason=None``.
    """
    author = _author_token(record.authors, strict=strict)
    if author is None:
        return CitekeyResult(key=None, reason=SkipReason.MISSING_AUTHOR)
    year = _year_token(record.year, strict=strict)
    if year is None:
        return CitekeyResult(key=None, reason=SkipReason.MISSING_YEAR)
    title = _title_token(record.title, record.doi, strict=strict)
    if title is None:
        return CitekeyResult(key=None, reason=SkipReason.MISSING_TITLE)
    return CitekeyResult(key=f"{author}_{year}_{title}", reason=None)


def canonical_citekey_str(record: "IngestRecord") -> str:
    """Lenient shim used by fresh ingest — always returns a string."""
    result = canonical_citekey(record, strict=False)
    assert result.key is not None  # lenient never returns None
    return result.key


def dedup_citekeys(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Apply numeric suffixes to collisions in a list of (old, proposed_new) pairs.

    Deterministic: iterates in order, so earlier pairs keep the base name
    and later collisions get ``base2``, ``base3``, etc. If the same ``old``
    appears again with the same proposed key, the existing assignment is
    reused (idempotent for duplicate inputs).
    """
    seen: dict[str, str] = {}  # new_key -> old_key
    out: list[tuple[str, str]] = []
    for old, proposed in pairs:
        base = proposed
        new = base
        idx = 2
        while new in seen and seen[new] != old:
            new = f"{base}{idx}"
            idx += 1
        seen[new] = old
        out.append((old, new))
    return out


STANDARD_KEY_RE = re.compile(r"^[a-z]+_\d{4}_[A-Za-z]")


def looks_standard(citekey: str) -> bool:
    """Return True if ``citekey`` already matches the canonical ``author_year_Title`` shape."""
    return bool(STANDARD_KEY_RE.match(citekey))
