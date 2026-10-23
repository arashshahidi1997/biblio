"""Clean docling text artefacts, line for line (journal-club R32).

Docling leaves PDF glyph names and lost spacing in its markdown:

- ligatures as glyph names with stray spaces: ``signi /uniFB01 cant``,
  ``the /uniFB01 rst`` (a word list decides whether the space before the
  ligature is real);
- symbol-font glyphs: ``( /C24 5 ms)`` for "(~5 ms)", ``/C0 0.64`` for
  "−0.64"; only codes whose meaning is clear from ~820 papers are mapped,
  the others are reported and left alone;
- accents written before their letter: ``Buzs /C19 aki`` for "Buzsáki";
- HTML entities: ``p &gt; 0.05``;
- words run together: ``Sharp-waveripples(SPW-Rs)inthehippocampusare``,
  split with the paper's own vocabulary, only where the run contains
  function words (or two frequent words), so real compounds stay whole.

Every change stays on its line, so line numbers are those of the docling
file (``grep -n``). :func:`clean_text` returns the text and the list of
substitutions.
"""
from __future__ import annotations

import html
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LIGATURES = {"FB00": "ff", "FB01": "fi", "FB02": "fl", "FB03": "ffi", "FB04": "ffl"}

# /Cnn glyphs of publisher symbol fonts, mapped where every sampled context agreed
SYMBOLS = {"0": "−", "2": "×", "3": "*", "6": "±", "14": "°", "176": "°", "21": "≥", "24": "~"}
# accents placed before their letter ("Buzs /C19 aki"); /C20 before a digit is "≤"
ACCENTS = {"19": "́", "20": "̌"}

FUNCTION_WORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has have he her his i if in into is it "
    "its may might more most no not of on or our she should so such than that the their them then there these they "
    "this those to was we were what when where which while who will with would".split())


@dataclass
class Sub:
    line: int
    rule: str            # ligature | symbol | accent | entity | spacing | unknown-glyph
    before: str
    after: str


@lru_cache(maxsize=1)
def ligature_words() -> frozenset[str]:
    path = Path(__file__).parent / "data" / "ligature_words.txt"
    words = path.read_text(encoding="utf-8").split("\n")
    return frozenset(w.strip() for w in words if w.strip() and not w.startswith("#"))


@lru_cache(maxsize=1)
def common_words() -> dict[str, int]:
    """Word -> number of papers it occurs in, from ~1300 docling texts (words in 40+ papers)."""
    out: dict[str, int] = {}
    for line in (Path(__file__).parent / "data" / "common_words.txt").read_text(encoding="utf-8").split("\n"):
        if line and not line.startswith("#"):
            w, _, n = line.partition(" ")
            out[w] = int(n or 1)
    return out


# ---------------------------------------------------------------------------
# Ligatures
# ---------------------------------------------------------------------------

_LIG = re.compile(r"(?P<pre>[A-Za-z]*)(?P<sp1> ?)/uni(?P<code>FB0[0-4])(?P<sp2> ?)(?P<post>[a-z]*)")


def _join_ligature(m: re.Match, vocab: Counter) -> str:
    pre, lig, post = m.group("pre"), LIGATURES[m.group("code")], m.group("post")
    if not m.group("sp1"):                  # glued on the left: part of the same word
        return pre + lig + post
    words = ligature_words()
    joined = (pre + lig + post).lower()
    right = (lig + post).lower()
    if pre.lower() in FUNCTION_WORDS and pre.lower() != "in":    # "the /uniFB01 rst", "a /uniFB02 ow"
        return f"{pre} {lig}{post}"
    common = common_words()
    if joined in words or joined in common or vocab[joined] >= 2:
        return pre + lig + post
    if right in words or right in common or vocab[right] >= 2:
        return f"{pre} {lig}{post}"
    # unknown either way: join unless the part before stands alone elsewhere in the paper
    return f"{pre} {lig}{post}" if vocab[pre.lower()] >= 3 else pre + lig + post


# ---------------------------------------------------------------------------
# Words run together
# ---------------------------------------------------------------------------

_PREFIXES = frozenset("inter intra sub super non pre post multi anti over under cross extra hyper hypo micro "
                      "macro semi trans neuro electro thalamo cortico temporo fronto parieto septo peri para supra infra re de "
                      "un co".split())


def _freq(word: str, vocab: Counter) -> int:
    """How common a word is: its count in this paper plus the number of held papers using it."""
    return vocab.get(word, 0) + common_words().get(word, 0)


def _known(word: str, vocab: Counter) -> bool:
    if word in FUNCTION_WORDS:
        return True
    if len(word) < 3:
        return False
    return word in common_words() or vocab.get(word, 0) >= 2


def _segment(run: str, vocab: Counter, total: int, pairs: frozenset = frozenset()) -> list[str] | None:
    """Split a lower-case letter run into words, or None if it should stay whole.

    Parts are known words (:func:`_known`); one part of 5+ letters may be
    unknown, at a high cost. Three or more parts need a function word among
    them; two parts need both to be common (or one to be a function word) and
    the first not to be a prefix ("inter neuronal").
    """
    n = len(run)
    inf = math.inf
    # state (position, unknown parts used) -> (cost, previous position, previous unknown count)
    best: dict[tuple[int, int], tuple[float, int, int]] = {(0, 0): (0.0, -1, 0)}
    for end in range(1, n + 1):
        for start in range(max(0, end - 24), end):
            w = run[start:end]
            known = _known(w, vocab)
            for u in (0, 1):
                if (start, u) not in best:
                    continue
                prev = best[(start, u)][0]
                if known:
                    cost, nu = prev - math.log((_freq(w, vocab) + 1) / total) + 2.0, u
                elif u == 0 and len(w) >= 5:
                    cost, nu = prev - math.log(1 / total) + 12.0, 1
                else:
                    continue
                if cost < best.get((end, nu), (inf,))[0]:
                    best[(end, nu)] = (cost, start, u)
    ends = [k for k in ((n, 0), (n, 1)) if k in best]
    if not ends:
        return None
    state = min(ends, key=lambda k: best[k][0])
    parts: list[str] = []
    while state[0] > 0:
        _, start, pu = best[state]
        parts.append(run[start:state[0]])
        state = (start, pu)
    parts.reverse()
    if len(parts) < 2 or parts[0] in _PREFIXES:
        return None
    # evidence from the paper itself: adjacent parts that it also writes apart ("lower amplitude", "in the")
    seen = sum((a, b) in pairs for a, b in zip(parts, parts[1:]))
    if len(parts) == 2:     # "lower amplitude", "composed of"; never "in validating"
        return parts if seen and n >= 7 and len(parts[0]) >= 3 else None
    if not any(p in FUNCTION_WORDS for p in parts) or 2 * seen < len(parts) - 1:
        return None
    return parts


_CHUNK = re.compile(r"\S{10,}")
_PIECES = re.compile(r"[A-Z]{2,}(?=[a-z])|[A-Z][a-z]+|[A-Z]+|[a-z]+|\d+(?:\.\d+)?|[^A-Za-z\d]")


def _paren_len(out: list[str], close: int) -> int:
    """Characters between out[close] == ")" and its "(" (large if there is none)."""
    depth, n = 0, 0
    for j in range(close - 1, -1, -1):
        if out[j] == ")":
            depth += 1
        elif out[j] == "(":
            if depth == 0:
                return n
            depth -= 1
        n += len(out[j])
    return 99


def _unglue_chunk(chunk: str, vocab: Counter, total: int, pairs: frozenset) -> str:
    if any(c in chunk for c in "/_@&<>=?\\|{}[]#$%^*+~"):     # URLs, code, formulas, font garbage
        return chunk
    if len(re.findall(r"[a-z][A-Z]", chunk)) >= 3:            # "ACknowLEdgmEnTs": mixed-case garbage
        return chunk
    out: list[str] = []
    for p in _PIECES.findall(chunk):
        low = p.lower()
        cased = p.islower() or (p[0].isupper() and p[1:].islower())     # never an acronym run: "WAKESPW"
        if cased and p.isalpha() and len(p) >= 7 and not _known(low, vocab) and low not in ligature_words():
            parts = _segment(low, vocab, total, pairs)
            if parts:
                if p[0].isupper():
                    parts[0] = parts[0].capitalize()
                out.append(" ".join(parts))
                continue
        out.append(p)
    text = ""
    for i, p in enumerate(out):
        prev = out[i - 1] if i else ""
        space = False
        if i and p[0].isalpha():
            if " " in p or " " in prev:
                space = prev[-1].isalnum() or prev in (",", ";", ")")
            elif prev.islower() and p.isupper() and _known(prev, vocab) and len(prev) >= 3:
                space = True                                  # "hippocampalCA1" (not camelCase "numberChannels")
            elif prev[-1].isdigit() and p.islower() and (len(p) >= 4 or (p in FUNCTION_WORDS and len(p) >= 3)) \
                    and _known(p, vocab):
                space = True                                  # "CA3subregions"
            elif prev in (",", ";") and len(p) >= 2:
                space = True                                  # "CA1,CA2" -> "CA1, CA2", not "9c,d,g"
            elif prev == ")" and p.islower() and _paren_len(out, i - 1) > 4 and out[i - 2] != "-":
                space = True                                  # "(SPW-Rs)in", not "(re)constructive"
            elif prev == "." and p[0].isupper() and i > 1 and out[i - 2].islower() and len(out[i - 2]) >= 3:
                space = True                                  # "experiments.However"
        elif i and p[0].isdigit() and prev in (",", ";") and i > 1 and out[i - 2][-1].isalpha():
            space = True                                      # "CA1,CA2" handled above; "and,3" rare
        elif (p == "(" and prev and prev[-1].isalpha() and prev.islower() and _known(prev.split()[-1], vocab)
              and i + 1 < len(out) and len(out[i + 1]) > 2):
            space = True                                      # "ripples(SPW-Rs)", not "author(s)"
        text += (" " if space and not text.endswith(" ") else "") + p
    return text


def _vocabulary(text: str) -> tuple[Counter, frozenset]:
    """Word counts and the word pairs the paper writes with a space or hyphen between them."""
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text) if len(w) <= 20]
    pairs = frozenset((a.lower(), b.lower()) for a, b in re.findall(r"\b([A-Za-z]+)[ -]([A-Za-z]+)\b", text))
    pairs |= frozenset((a.lower(), b.lower()) for a, b in re.findall(r"\b[A-Za-z]+[ -]([A-Za-z]+)[ -]([A-Za-z]+)\b", text))
    return Counter(words), pairs


# ---------------------------------------------------------------------------
# The whole text
# ---------------------------------------------------------------------------

_GLYPH = re.compile(r"(?P<sp1> ?)/C(?P<code>\d+)(?P<sp2> ?)(?P<next>\S?)")
_ACCENT = re.compile(r"(?:(?<=[A-Za-z]) )?(?<![\d])/C(?:(?P<code>19) ?(?P<letter>[AEIOUYaeiouyNnCcSsZz])"
                     r"|(?P<code2>20) ?(?P<letter2>[CcSsZzRrNnEeDd]))")
_ENTITY = re.compile(r"&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);")
_UNI = re.compile(r"/uni(?P<code>[0-9A-F]{4})")


def clean_line(line: str, no: int, vocab: Counter, total: int, subs: list[Sub], pairs: frozenset = frozenset()) -> str:
    original = line
    if "&" in line:
        line = _ENTITY.sub(lambda m: html.unescape(m.group(0)), line)
        if line != original:
            subs.append(Sub(no, "entity", original, line))
    if "/uni" in line:
        before = line
        line = _LIG.sub(lambda m: _join_ligature(m, vocab), line)
        line = _UNI.sub(lambda m: chr(int(m.group("code"), 16)) if m.group("code") not in LIGATURES else m.group(0),
                        line)
        if line != before:
            subs.append(Sub(no, "ligature", before, line))
    if "/C" in line:
        before = line
        def accent(m: re.Match) -> str:
            start = m.start()
            word = re.search(r"\S*$", line[:start]).group(0)
            if any(ch.isdigit() for ch in word):               # "8ms /C20 t" is "8 ms ≤ t"
                return m.group(0)
            letter, code = (m.group("letter"), "19") if m.group("code") else (m.group("letter2"), "20")
            return unicodedata.normalize("NFC", letter + ACCENTS[code])

        line = _ACCENT.sub(accent, line)
        if line != before:
            subs.append(Sub(no, "accent", before, line))
        before = line

        def glyph(m: re.Match) -> str:
            code, nxt = m.group("code"), m.group("next")
            sym = SYMBOLS.get(code) or ("≤" if code == "20" and nxt[:1].isdigit() else None)
            if sym is None:
                subs.append(Sub(no, "unknown-glyph", f"/C{code}", ""))
                return m.group(0)
            if sym in "−~" and nxt[:1].isdigit():     # "/C0 0.64" -> "−0.64", "( /C24 5 ms)" -> "(~5 ms)"
                return f"{m.group('sp1')}{sym}{nxt}"
            if sym == "°":                            # "62.9 /C14 ±" -> "62.9° ±"
                return f"{sym}{m.group('sp2')}{nxt}"
            return f"{m.group('sp1')}{sym}{m.group('sp2')}{nxt}"

        line = _GLYPH.sub(glyph, line)
        line = re.sub(r"\( (?=[~−±≤≥])", "(", line)
        if line != before:
            subs.append(Sub(no, "symbol", before, line))
    if _CHUNK.search(line):
        before = line
        line = _CHUNK.sub(lambda m: _unglue_chunk(m.group(0), vocab, total, pairs), line)
        if line != before:
            subs.append(Sub(no, "spacing", before, line))
    return line


def clean_text(text: str) -> tuple[str, list[Sub]]:
    """The cleaned text (same lines, split at "\\n" only) and the substitutions made."""
    if not any(marker in text for marker in ("/uni", "/C", "&")) and not _CHUNK.search(text):
        return text, []
    vocab, pairs = _vocabulary(_LIG.sub(lambda m: m.group("pre") + LIGATURES[m.group("code")] + m.group("post"), text))
    total = sum(vocab.values()) or 1
    subs: list[Sub] = []
    lines = text.split("\n")
    out = [clean_line(line, no, vocab, total, subs, pairs) for no, line in enumerate(lines, 1)]
    return "\n".join(out), subs


_CACHE: dict[str, tuple[int, str]] = {}


def clean_text_cached(key: str, raw: str) -> str:
    """:func:`clean_text` memoized per file for this process (the wiki lint reads a paper many times)."""
    h = hash(raw)
    hit = _CACHE.get(key)
    if hit and hit[0] == h:
        return hit[1]
    text = clean_text(raw)[0]
    if len(_CACHE) > 256:
        _CACHE.clear()
    _CACHE[key] = (h, text)
    return text


def describe(sub: Sub) -> str:
    """The changed words of a substitution: "'a /uniFB01 b' -> 'afib'; ..." (or the unknown glyph)."""
    import difflib
    if sub.rule == "unknown-glyph":
        return f"{sub.before} left as is"
    a, b = sub.before.split(" "), sub.after.split(" ")
    parts = [f"{' '.join(a[i1:i2])!r} -> {' '.join(b[j1:j2])!r}"
             for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
             if tag != "equal"]
    return "; ".join(parts)
