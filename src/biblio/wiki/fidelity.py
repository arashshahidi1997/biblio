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

from ..sections import read_fulltext, text_lines

SHINGLE = 3
MIN_COVERAGE = 0.8      # share of the quote's words found in order in one passage
MIN_WORDS = 4           # shorter quotes must match exactly

# words whose change can flip a claim: never "approximately" right
MUST_MATCH = re.compile(
    r"^(?:\d[\d.]*|not|no|never|none|nor|neither|without|cannot|cant|nt|only|all|both|either|"
    r"less|more|most|least|fewer|greater|smaller|larger|higher|lower|bigger|shorter|longer|"
    r"increas\w*|decreas\w*|rais\w*|ris\w*|rose|fell|fall\w*|reduc\w*|enhanc\w*|elevat\w*|"
    r"suppress\w*|abolish\w*|block\w*|before|after|above|below|deeper|shallower|earlier|later|"
    r"preced\w*|follow\w*|lead\w*|led|lag\w*|precede|prior|subsequent\w*|"
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
        self.raw_lines = text_lines(raw)
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


_ABBREV = frozenset("al fig figs eq eqs ref refs e.g i.e vs approx ca cf resp".split())


_PIECE = re.compile(r"&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);|.", re.S)


def _alnum(text: str) -> tuple[str, list[tuple[int, int]]]:
    """The letters and digits of ``text`` (entities decoded, NFKC, lower case), each with its raw span.

    Spaces, punctuation and line breaks drop out, so words docling ran
    together or split still line up with the quote.
    """
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    for m in _PIECE.finditer(text):
        piece = unicodedata.normalize("NFKC", html.unescape(m.group(0))).lower()
        for ch in piece:
            if ch.isalnum():
                chars.append(ch)
                spans.append((m.start(), m.end()))
    return "".join(chars), spans


def _span_in(window: str, quote: str) -> tuple[int, int] | None:
    """(start, end) of the passage of ``window`` the quote aligns with, in ``window``'s own characters."""
    q, _ = _alnum(quote)
    r, spans = _alnum(window)
    if len(q) < 8 or not r:
        return None
    sm = difflib.SequenceMatcher(None, q, r, autojunk=False)
    anchor = sm.find_longest_match(0, len(q), 0, len(r))
    if anchor.size < min(12, len(q)):
        return None
    lo = max(0, anchor.b - anchor.a - 24)
    hi = min(len(r), anchor.b + (len(q) - anchor.a) + 24)
    sub = difflib.SequenceMatcher(None, q, r[lo:hi], autojunk=False)
    if sum(b.size for b in sub.get_matching_blocks()) < 0.75 * len(q):
        return None
    ops = [op for op in sub.get_opcodes() if not (op[0] == "insert" and op[1] in (0, len(q)))]
    js = next(j1 for tag, i1, i2, j1, j2 in ops if i2 > 0)
    je = next(j2 for tag, i1, i2, j1, j2 in reversed(ops) if i1 < len(q))
    if je <= js:
        return None
    start, end = spans[lo + js][0], spans[lo + je - 1][1]
    qs = quote.strip()
    lead = re.match(r"^[^\w]*", qs).group(0)
    trail = re.search(r"[^\w]*$", qs).group(0)
    if lead and window[max(0, start - len(lead)):start].strip() == lead.strip():
        start -= len(lead)                                          # an opening "(" the quote has too
    if trail and window[end:end + len(trail)].strip() == trail.strip():
        end += len(trail)
    return start, end


def _sentence_around(window: str, start: int, end: int, max_words: int = 120) -> str | None:
    """The sentence (or sentences) of ``window`` that contain [start, end)."""
    def boundary(i: int) -> bool:                                   # window[i] ends a sentence
        if window[i] not in ".!?":
            return False
        nxt = window[i + 1:i + 3]
        if nxt and not (nxt[0].isspace() or nxt[0] in "\"')]"):
            return False
        after = window[i + 1:].lstrip(" \"')]")
        if after and not (after[0] == "\n" or after[0].isupper() or after[0] in "([\"'"):
            return False                                            # "str. oriens", "et al. found"
        word = re.search(r"([\w.]+)$", window[:i])
        w = word.group(1).lower().rstrip(".") if word else ""
        return not (w in _ABBREV or (len(w) == 1 and w.isalpha()))
    line_start = window.rfind("\n", 0, start) + 1
    s = start
    while s > line_start and not boundary(s - 1):
        s -= 1
    while s < start and window[s].isspace():
        s += 1
    line_end = window.find("\n", end)
    line_end = len(window) if line_end == -1 else line_end
    e = end
    while e < line_end and not boundary(e):
        e += 1
    e = min(line_end, e + 1)
    sentence = window[s:e].strip()
    return sentence if sentence and len(sentence.split()) <= max_words else None


class QuoteChecker:
    """Caches normalized full texts; ``path_for`` maps a citekey to its markdown file.

    Each paper is checked against its cleaned text (:mod:`biblio.textclean`:
    "fibers", "~5 ms", "Buzsáki") and, where that differs, docling's raw text,
    so a quote copied from either verifies. Both have the same lines.
    """

    _RANK = {"exact": 0, "approximate": 1, "changed": 2, "missing": 3}

    def __init__(self, path_for: Callable[[str], Path]):
        self.path_for = path_for
        self._texts: dict[str, list[_Text] | None] = {}

    def _variants(self, citekey: str) -> list[_Text] | None:
        if citekey not in self._texts:
            path = self.path_for(citekey)
            if not path.is_file():
                self._texts[citekey] = None
            else:
                raw = read_fulltext(path)
                clean = read_fulltext(path, clean=True)
                self._texts[citekey] = [_Text(clean)] + ([_Text(raw)] if clean != raw else [])
        return self._texts[citekey]

    def _text(self, citekey: str) -> _Text | None:
        variants = self._variants(citekey)
        return variants[0] if variants else None

    def has_text(self, citekey: str) -> bool:
        return self._variants(citekey) is not None

    def match(self, citekey: str, quote: str) -> Match:
        variants = self._variants(citekey)
        if variants is None:
            return Match("no-text")
        q = normalize(quote)
        if not q:
            return Match("missing")
        if any(q in t.norm for t in variants):
            return Match("exact")
        best = None
        for t in variants:
            m = align(q.split(), t)
            if best is None or self._RANK[m.status] < self._RANK[best.status]:
                best = m
        return best

    @staticmethod
    def _joined(text: _Text) -> tuple[str, list[int]]:
        if not hasattr(text, "_lines_joined"):
            norms = [normalize(line) for line in text.raw_lines]
            starts, pos = [], 0
            for n in norms:
                starts.append(pos)
                pos += len(n) + 1
            text._lines_joined, text._line_starts = " ".join(norms), starts
        return text._lines_joined, text._line_starts

    def locate(self, citekey: str, quote: str) -> tuple[int, str] | None:
        """(1-based line in the full text, nearest heading above it) for a quote, or None."""
        import bisect
        variants = self._variants(citekey)
        if variants is None:
            return None
        m = self.match(citekey, quote)
        words = (m.passage or normalize(quote)).split()
        if not words:
            return None
        whole = " " + " ".join(words) + " "
        for text in variants:                                 # where the whole quote is, if it is there
            joined, starts = self._joined(text)
            hit = (" " + joined + " ").find(whole)
            if hit >= 0:
                idx = bisect.bisect_right(starts, hit) - 1
                return idx + 1, self.heading_at(citekey, idx + 1)
        for text in variants:
            joined, starts = self._joined(text)
            for i in range(0, max(1, len(words) - 4), 2):     # anchors along the quote (line breaks split words)
                hit = (" " + joined + " ").find(" " + " ".join(words[i:i + 5]) + " ")
                if hit >= 0:
                    idx = bisect.bisect_right(starts, hit) - 1
                    return idx + 1, self.heading_at(citekey, idx + 1)
        return None

    def spans(self, citekey: str, quote: str) -> dict | None:
        """Where a quote is: its line, the exact characters of ``<key>.md`` it matches, and its sentence.

        ``raw`` is a plain substring of the docling file (double spaces, ``&lt;``,
        ``/C24`` and all), so it can be found with ``grep -F``; ``sentence`` is
        the whole sentence around the quote in the cleaned text (None when it
        is very long). Journal-club R39.
        """
        variants = self._variants(citekey)
        loc = self.locate(citekey, quote) if variants else None
        if not loc:
            return None
        line = loc[0]

        def window(text: _Text) -> tuple[str, int]:
            lo = max(0, line - 2)
            return "\n".join(text.raw_lines[lo:line + 4]), lo

        raw_text, clean_text = variants[-1], variants[0]
        out: dict = {"line": line, "raw": None, "sentence": None}
        win, lo = window(raw_text)
        sp = _span_in(win, quote)
        if sp:
            out["raw"] = win[sp[0]:sp[1]]
            out["line"] = lo + 1 + win.count("\n", 0, sp[0])
        cwin, _ = window(clean_text)
        csp = _span_in(cwin, quote)
        if csp:
            out["sentence"] = _sentence_around(cwin, *csp)
        return out

    def occurs_at(self, citekey: str, quote: str, line: int) -> bool:
        """Whether the quote starts on ``line`` (1-based; it may run on to the next lines)."""
        words = normalize(quote).split()
        for text in self._variants(citekey) or []:
            if words and 1 <= line <= len(text.raw_lines):
                here = normalize("\n".join(text.raw_lines[line - 1:line + 3]))
                if f" {' '.join(words[:5])} " in f" {here} ":
                    return True
        return False

    def heading_at(self, citekey: str, line: int) -> str:
        text = self._text(citekey)
        if text is None:
            return ""
        return next((ln.lstrip("#").strip() for ln in reversed(text.raw_lines[:line])
                     if re.match(r"^#{1,6}\s", ln)), "")

    def number_in(self, citekey: str, number: str) -> bool | None:
        """Whether a number (as written on the page) occurs in the full text; None without a text."""
        variants = self._variants(citekey)
        if variants is None:
            return None
        return any(f" {normalize(number)} " in f" {t.norm} " for t in variants)

    def check(self, citekey: str, quote: str) -> str:
        """The status alone: 'exact', 'approximate', 'changed', 'missing' or 'no-text'."""
        return self.match(citekey, quote).status
