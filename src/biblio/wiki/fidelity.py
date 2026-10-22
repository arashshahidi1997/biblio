"""Check that quoted text appears in the cited paper's full text.

Matching tolerates whitespace, punctuation, hyphenation at line breaks and
Unicode variants. A quote matches exactly when its normalized text is a
substring of the normalized paper; it matches approximately when at least
``FUZZY_MIN`` of its 3-word shingles occur in the paper (one or two words
changed). Paraphrases do not match.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Callable

SHINGLE = 3
FUZZY_MIN = 0.8


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"-\s*\n\s*", "", text)          # hyphenation at line breaks
    text = re.sub(r"[^\w\s]|_", " ", text)          # punctuation and markdown markup
    return re.sub(r"\s+", " ", text).strip().lower()


def shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + SHINGLE]) for i in range(max(1, len(words) - SHINGLE + 1))}


class QuoteChecker:
    """Caches normalized full texts; ``path_for`` maps a citekey to its markdown file."""

    def __init__(self, path_for: Callable[[str], Path]):
        self.path_for = path_for
        self._texts: dict[str, tuple[str, set] | None] = {}

    def _text(self, citekey: str):
        if citekey not in self._texts:
            path = self.path_for(citekey)
            if path.is_file():
                norm = normalize(path.read_text(encoding="utf-8", errors="replace"))
                self._texts[citekey] = (norm, shingles(norm.split()))
            else:
                self._texts[citekey] = None
        return self._texts[citekey]

    def has_text(self, citekey: str) -> bool:
        return self._text(citekey) is not None

    def check(self, citekey: str, quote: str) -> str:
        """Return 'exact', 'fuzzy', 'missing' or 'no-text'."""
        entry = self._text(citekey)
        if entry is None:
            return "no-text"
        text, text_shingles = entry
        q = normalize(quote)
        if not q:
            return "missing"
        if q in text:
            return "exact"
        q_shingles = shingles(q.split())
        hit = len(q_shingles & text_shingles) / len(q_shingles)
        return "fuzzy" if hit >= FUZZY_MIN else "missing"
