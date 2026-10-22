"""Check that quoted text appears in the cited paper's full text.

Matching tolerates whitespace, punctuation, hyphenation at line breaks,
Unicode variants and docling's split ligatures ("identif ied"). A quote is

- ``exact`` when its normalized text is a substring of the normalized paper;
- ``approximate`` when it aligns with one contiguous passage except for a few
  words, none of which can change the meaning (lint warning, with the diff);
- ``changed`` when it aligns but a differing word is a negation, comparative,
  direction word or number ("less" -> "more"): an error, because the quote
  then says something the paper does not;
- ``missing`` otherwise, or ``no-text`` without a full text.

Only ``exact`` counts as verified.
"""
from __future__ import annotations

import difflib
import html
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SHINGLE = 3
MIN_COVERAGE = 0.8      # share of the quote's words found in order in one passage
MIN_WORDS = 4           # shorter quotes must match exactly

# words whose change can flip a claim: never "approximately" right
MUST_MATCH = re.compile(
    r"^(?:\d[\d.]*|not|no|never|none|nor|neither|without|cannot|cant|nt|only|all|both|either|"
    r"less|more|most|least|fewer|greater|smaller|larger|higher|lower|bigger|shorter|longer|"
    r"increas\w*|decreas\w*|rais\w*|ris\w*|rose|fell|fall\w*|reduc\w*|enhanc\w*|elevat\w*|"
    r"suppress\w*|abolish\w*|block\w*|before|after|above|below|deeper|shallower|earlier|later|"
    r"positive|negative|significant\w*|insignificant|absent|present)$")


def normalize(text: str) -> str:
    text = html.unescape(text)                      # docling writes "p &gt; 0.05" for "p > 0.05"
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"-\s*\n\s*", "", text)          # hyphenation at line breaks
    text = re.sub(r"[^\w\s]|_", " ", text)          # punctuation and markdown markup
    text = re.sub(r"\s+", " ", text).strip().lower()
    return re.sub(r"f (?=[fil])", "f", text)         # docling ligature splits: "identif ied", "dif ferent"


def shingles(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + SHINGLE]) for i in range(max(1, len(words) - SHINGLE + 1))}


@dataclass
class Match:
    status: str                 # exact | approximate | changed | missing | no-text
    diff: str = ""              # "paper words -> quote words; ..." for approximate and changed
    passage: str = ""           # the aligned passage of the paper (normalized)


class _Text:
    def __init__(self, raw: str):
        self.raw_lines = raw.splitlines()
        self.norm = normalize(raw)
        self.words = self.norm.split()
        self.index: dict[tuple[str, ...], list[int]] = {}
        for i in range(max(0, len(self.words) - SHINGLE + 1)):
            self.index.setdefault(tuple(self.words[i:i + SHINGLE]), []).append(i)


def align(quote_words: list[str], text: _Text) -> Match:
    """Best contiguous passage for a quote that is not an exact substring."""
    n = len(quote_words)
    if n < MIN_WORDS:
        return Match("missing")
    votes: Counter = Counter()
    for i in range(n - SHINGLE + 1):
        for pos in text.index.get(tuple(quote_words[i:i + SHINGLE]), ()):
            votes[pos - i] += 1
    best: tuple[int, list, list] | None = None
    for start, _ in votes.most_common(5):
        lo, hi = max(0, start - 3), min(len(text.words), start + n + 3)
        window = text.words[lo:hi]
        sm = difflib.SequenceMatcher(None, quote_words, window, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size]
        matched = sum(b.size for b in blocks)
        if blocks and (best is None or matched > best[0]):
            best = (matched, blocks, window)
    if best is None or best[0] / n < MIN_COVERAGE:
        return Match("missing")
    _, blocks, window = best
    # compare the quote with the passage spanning the first to the last matched word
    span = window[blocks[0].b: blocks[-1].b + blocks[-1].size]
    q_span = quote_words[blocks[0].a: blocks[-1].a + blocks[-1].size]
    changes, meaningful = [], False
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, q_span, span, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        q_part, p_part = q_span[i1:i2], span[j1:j2]
        meaningful |= any(MUST_MATCH.match(w) for w in q_part + p_part)
        changes.append(f"'{' '.join(p_part) or '(nothing)'}' -> '{' '.join(q_part) or '(nothing)'}'")
    # words of the quote outside the aligned span are unmatched too
    lost = quote_words[:blocks[0].a] + quote_words[blocks[-1].a + blocks[-1].size:]
    if lost:
        meaningful |= any(MUST_MATCH.match(w) for w in lost)
        changes.append(f"unmatched: '{' '.join(lost)}'")
    if not changes:
        return Match("exact", passage=" ".join(span))
    return Match("changed" if meaningful else "approximate", "; ".join(changes), " ".join(span))


class QuoteChecker:
    """Caches normalized full texts; ``path_for`` maps a citekey to its markdown file."""

    def __init__(self, path_for: Callable[[str], Path]):
        self.path_for = path_for
        self._texts: dict[str, _Text | None] = {}

    def _text(self, citekey: str) -> _Text | None:
        if citekey not in self._texts:
            path = self.path_for(citekey)
            self._texts[citekey] = _Text(path.read_text(encoding="utf-8", errors="replace")) if path.is_file() else None
        return self._texts[citekey]

    def has_text(self, citekey: str) -> bool:
        return self._text(citekey) is not None

    def match(self, citekey: str, quote: str) -> Match:
        text = self._text(citekey)
        if text is None:
            return Match("no-text")
        q = normalize(quote)
        if not q:
            return Match("missing")
        if q in text.norm:
            return Match("exact")
        return align(q.split(), text)

    def locate(self, citekey: str, quote: str) -> tuple[int, str] | None:
        """(1-based line in the full text, nearest heading above it) for a quote, or None."""
        text = self._text(citekey)
        if text is None:
            return None
        if not hasattr(text, "_lines_joined"):
            norms = [normalize(line) for line in text.raw_lines]
            starts, pos = [], 0
            for n in norms:
                starts.append(pos)
                pos += len(n) + 1
            text._lines_joined, text._line_starts = " ".join(norms), starts
        m = self.match(citekey, quote)
        words = (m.passage or normalize(quote)).split()
        if not words:
            return None
        import bisect
        for i in range(0, max(1, len(words) - 4), 2):     # try anchors along the quote (line breaks split words)
            hit = (" " + text._lines_joined + " ").find(" " + " ".join(words[i:i + 5]) + " ")
            if hit >= 0:
                idx = bisect.bisect_right(text._line_starts, hit) - 1
                heading = next((ln.lstrip("#").strip() for ln in reversed(text.raw_lines[:idx + 1])
                                if re.match(r"^#{1,6}\s", ln)), "")
                return idx + 1, heading
        return None

    def number_in(self, citekey: str, number: str) -> bool | None:
        """Whether a number (as written on the page) occurs in the full text; None without a text."""
        text = self._text(citekey)
        if text is None:
            return None
        return f" {normalize(number)} " in f" {text.norm} "

    def check(self, citekey: str, quote: str) -> str:
        """The status alone: 'exact', 'approximate', 'changed', 'missing' or 'no-text'."""
        return self.match(citekey, quote).status
