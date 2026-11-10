"""Where a paper's own article sits in its docling text (lit-studio R69).

A journal reprint can carry the end of the previous article and the start of
the next one (Science reprints: cash_2009_HumanK has a cover page, the tail of
a dopamine paper with its references, Cash et al., then "Crystal Structure of
the Nuclear Export Receptor CRM1 ..."). Docling converts all of it, so quote
checks and digests can match text that is not the paper's.

``article_span`` finds the article by its title heading and ends it at the
first article-like heading after its references. Nothing is trimmed: the
span flags the text (``biblio fulltext --survey``) and ``biblio quotes
check`` warns about a quote found outside it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_REFS = re.compile(r"^(references?(\s+and\s+notes)?|bibliography|literature\s+cited|works\s+cited|"
                   r"references\s+cited)\s*:?$", re.I)
_BACK = re.compile(
    r"^(supporting\s+online\s+material|supplementary|supplemental|supporting\s+information|acknowledge?ments?|"
    r"materials?\s+and\s+methods|methods|online\s+methods|author\s+contributions?|competing\s+interests?|"
    r"conflicts?\s+of\s+interest|data\s+(and\s+code\s+)?availability|code\s+availability|funding|appendix|"
    r"abbreviations|notes?|footnotes?|figure|fig\.|table|extended\s+data|additional\s+information|"
    r"author\s+information|declarations?|ethics|correspondence|reporting\s+summary|source\s+data)\b", re.I)


_SUPPL = re.compile(r"^(supplement(al|ary)?(\s+(information|materials?|data))?|supporting\s+information|"
                    r"supporting\s+online\s+material)\b", re.I)


def _sig(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text.lower() if ch.isascii() and ch.isalnum())


def title_signature(title: str, words: int = 6) -> str:
    tokens = re.findall(r"[^\W_]+", re.sub(r"(\w)-\s*(\w)", r"\1\2", re.sub(r"[{}\\]", "", title or "")))
    return _sig("".join(tokens[:words]))


def _is_title(heading: str, want: str) -> bool:
    got = _sig(heading)
    return bool(want) and len(got) >= 12 and (got.startswith(want) or want.startswith(got))


def _article_like(heading: str) -> bool:
    """A heading that reads like another article's title, not a section of this one.

    Methods subsections after the references (Nature, Cell STAR Methods) are
    sentence case or all caps; journal titles are Title Case and longer, e.g.
    "Crystal Structure of the Nuclear Export Receptor CRM1 in Complex with ...".
    """
    h = re.sub(r"^[\d.\s]+", "", heading).strip()
    words = h.split()
    if len(words) < 6 or _REFS.match(h) or _BACK.match(h) or h.endswith((":", ".")) or "," in h:
        return False
    if h.upper() == h or sum(len(w) == 1 for w in words) > len(words) / 3:   # all caps, s p a c e d
        return False
    long = [w for w in words if len(w) > 3 and w[0].isalpha()]
    return bool(long) and sum(w[0].isupper() for w in long) / len(long) >= 0.75


def _author_line(line: str) -> bool:
    """"Thomas Monecke, 1 * Thomas Güttler, 2 * Piotr Neumann, 1 ...": two or more names, little else."""
    text = re.sub(r"[\d*†‡§¶#]+", ",", line)
    parts = [p.strip() for p in re.split(r",|;|\band\b|&", text) if p.strip()]
    names = [p for p in parts if 2 <= len(p.split()) <= 4
             and all(w[0].isupper() for w in p.split() if w[0].isalpha())]
    return len(names) >= 2 and len(names) >= 0.6 * len(parts)


def _followed_by_authors(lines: list[str], no: int, look: int = 3) -> bool:
    """Is one of the first ``look`` text lines after line ``no`` (1-based) an author list?"""
    seen = 0
    for line in lines[no:no + 12]:
        if not line.strip() or line.lstrip().startswith("!["):
            continue
        if _HEADING.match(line) or seen >= look:
            return False
        if _author_line(line):
            return True
        seen += 1
    return False


@dataclass
class ArticleSpan:
    lines: int                       # lines in the text
    start: int | None = None         # 1-based, inclusive; None when the title heading was not found
    end: int | None = None
    title_headings: list[int] = field(default_factory=list)
    reference_headings: list[int] = field(default_factory=list)
    previous_references: int | None = None   # a reference list before the title: the previous article's
    next_article: tuple[int, str] | None = None
    outside_words: int = 0

    @property
    def mixed(self) -> bool:
        """The text holds the tail of the previous article or the start of the next one."""
        return self.previous_references is not None or self.next_article is not None

    def contains(self, line: int) -> bool:
        return self.start is None or (self.start <= line <= (self.end or self.lines))

    def reasons(self) -> list[str]:
        out = []
        if self.previous_references is not None:
            out.append(f"a reference list at line {self.previous_references}, before the title (line {self.start}): "
                       "the end of the previous article")
        if self.next_article:
            out.append(f"another article at line {self.next_article[0]}: {self.next_article[1][:70]}")
        if self.start is not None and self.outside_words:
            out.append(f"{self.outside_words} words outside lines {self.start}-{self.end}")
        if self.start is None:
            out.append("title heading not found")
        return out


def article_span(lines: list[str], title: str | None) -> ArticleSpan:
    """The paper's own lines in a docling text (``lines`` as ``text_lines`` splits them)."""
    span = ArticleSpan(lines=len(lines))
    want = title_signature(title or "")
    headings = [(no, m.group(1)) for no, line in enumerate(lines, 1) if (m := _HEADING.match(line))]
    span.reference_headings = [no for no, h in headings if _REFS.match(h.strip())]
    span.title_headings = [no for no, h in headings if _is_title(h, want)]
    if not span.title_headings:
        return span

    def words(a: int, b: int) -> int:
        return sum(len(line.split()) for line in lines[a - 1:b])

    def body_end(start: int) -> int:
        nxt = next((r for r in span.reference_headings if r > start), None)
        return (nxt - 1) if nxt else len(lines)

    # a cover page repeats the title; the article is the copy with the most text before its references
    start = max(span.title_headings, key=lambda t: (words(t, body_end(t)), t))
    refs = next((r for r in span.reference_headings if r > start), None)
    end = len(lines)
    if refs is not None:
        def own_supplement(i: int) -> bool:
            # "Supplemental Information" / the title again (split over two headings) just before it
            if i == 0:
                return False
            h = headings[i - 1][1]
            return bool(_SUPPL.match(h.strip())) or _is_title(h, want)

        nxt = next(((no, h) for i, (no, h) in enumerate(headings)
                    if no > refs and _article_like(h) and not _is_title(h, want)
                    and _followed_by_authors(lines, no) and not own_supplement(i)), None)
        if nxt is not None:
            span.next_article = nxt
            end = nxt[0] - 1
    span.start, span.end = start, end
    span.previous_references = next((r for r in reversed(span.reference_headings) if r < start), None)
    span.outside_words = words(1, start - 1) + words(end + 1, len(lines))
    return span


def span_for_file(path: Path, title: str | None) -> ArticleSpan:
    from .sections import read_fulltext, text_lines
    return article_span(text_lines(read_fulltext(path)), title)


def bib_titles(cfg) -> dict[str, str]:
    """citekey -> title from the project's bibliographies and its pools' (first wins)."""
    from .pool import _find_pool_bib
    from .refs import _bib_records, _project_bibs

    titles: dict[str, str] = {}
    bibs = list(_project_bibs(cfg))
    for root in getattr(cfg, "pool_search", ()) or ():
        bib = _find_pool_bib(root)
        if bib is not None:
            bibs.append(bib)
    for bib in bibs:
        for r in _bib_records(bib):
            if r["title"]:
                titles.setdefault(r["key"], r["title"])
    from .aliases import load_aliases
    for alias, canon in load_aliases(cfg.repo_root).canonical_of.items():
        if canon in titles or alias in titles:
            titles.setdefault(alias, titles.get(canon, ""))
            titles.setdefault(canon, titles[alias])
    return titles


def survey(cfg, roots: list[Path]) -> list[tuple[str, Path, ArticleSpan]]:
    """Every ``<root>/<key>/<key>.md`` whose text is mixed, with its span."""
    titles = bib_titles(cfg)
    out = []
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            md = d / f"{d.name}.md"
            if not md.is_file():
                continue
            title = titles.get(d.name)
            span = span_for_file(md, title)
            if span.mixed:
                out.append((d.name, md, span))
    return out
