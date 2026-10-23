"""Parse wiki pages: frontmatter, headings, lede, links, citations and quotes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .schema import META_FILES

WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]|#^]*)(?:#([^\[\]|]*))?(?:\|([^\[\]]*))?\]\]")
MDLINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
CITE_GROUP_RE = re.compile(r"\[([^\[\]]*@[^\[\]]*)\]")
CITEKEY_RE = re.compile(r"(?<![\w.])-?@([A-Za-z0-9_][\w:.\-]*\w)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
# from an opening quote mark to the closing one right before the citation, so quotes that contain
# quoted words ("SPW bursts are ... "released" in ...") stay whole
INLINE_QUOTE_RE = re.compile(r"[\"“]([^\[\]]{20,}?)[\"”]\s*(\[[^\[\]]*@[^\[\]]*\])")
STATUS_BLOCK_RE = re.compile(r"^\s*(\[!|\*\*(Contested|Outdated|Unverified|Disputed)\.\*\*)")

# pandoc-ext/cito intent prefixes, e.g. [@supports:key]
CITO_PREFIXES = {
    "supports", "disputes", "extends", "usesMethodIn", "usesDataFrom", "agreesWith",
    "disagreesWith", "citesAsEvidence", "citesForInformation", "confirms", "critiques",
    "discusses", "obtainsBackgroundFrom", "updates", "refutes", "usesConclusionsFrom",
}


@dataclass
class Link:
    target: str          # wikilink name or relative path, without anchor
    anchor: str | None
    line: int
    kind: str            # "wiki" | "md"
    embed: bool = False


@dataclass
class Citation:
    key: str
    line: int
    intent: str | None = None


@dataclass
class Quote:
    text: str
    keys: list[str]
    line: int


@dataclass
class Page:
    path: Path
    rel: str
    name: str
    text: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    fm_error: str | None = None
    has_frontmatter: bool = False
    body_offset: int = 0                      # line number (1-based) where the body starts
    headings: list[tuple[int, str, int]] = field(default_factory=list)   # (level, text, line)
    lede: str | None = None
    links: list[Link] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    quotes: list[Quote] = field(default_factory=list)
    words: int = 0
    body_lines: list[str] = field(default_factory=list)

    @property
    def type(self) -> str | None:
        value = self.frontmatter.get("type")
        return str(value) if value is not None else None

    @property
    def status(self) -> str | None:
        value = self.frontmatter.get("status")
        return str(value) if value is not None else None

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or self.name)

    def h2(self) -> list[tuple[str, int]]:
        return [(text, line) for level, text, line in self.headings if level == 2]

    def section_of(self, line: int) -> str | None:
        """Name of the H2 section containing ``line``."""
        current = None
        for text, hline in self.h2():
            if hline <= line:
                current = text
        return current

    def list_field(self, key: str) -> list[str]:
        value = self.frontmatter.get(key)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value if v is not None]
        return [str(value)]


def split_frontmatter(text: str) -> tuple[str | None, str, int]:
    """Return (frontmatter yaml or None, body, body start line)."""
    if not text.startswith("---"):
        return None, text, 1
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1:]), i + 2
    return None, text, 1


def _parse_citations(segment: str, line: int) -> list[Citation]:
    out = []
    for group in CITE_GROUP_RE.findall(segment):
        for raw in CITEKEY_RE.findall(group):
            intent = None
            key = raw
            if ":" in raw:
                prefix, rest = raw.split(":", 1)
                if prefix in CITO_PREFIXES:
                    intent, key = prefix, rest
            out.append(Citation(key=key, line=line, intent=intent))
    return out


def _strip_citations(text: str) -> str:
    return CITE_GROUP_RE.sub(" ", text)


_MARK_RE = re.compile(r'["“”]')


def quoted_citations(text: str) -> list[tuple[str, str]]:
    """``(quote, citation group)`` for each quote that ends right before a citation.

    The quote's closing mark is the one just before the citation; its opening mark is found by
    pairing marks, so a quote that contains quoted words ("... are "released" in ...") stays whole
    and a scare-quoted word earlier in the sentence ("delta" names. ... "the quote") is not taken
    as the start. Text between two citations belongs to the second one only.
    """
    out: list[tuple[str, str]] = []
    prev_end = 0
    for cm in CITE_GROUP_RE.finditer(text):
        seg = text[prev_end:cm.start()].rstrip()
        prev_end = cm.end()
        if not seg or seg[-1] not in '"”':
            continue
        close = len(seg) - 1
        stack: list[int] = []
        for m in _MARK_RE.finditer(seg, 0, close):
            pos, ch = m.start(), m.group()
            before = seg[pos - 1] if pos > 0 else " "
            after = seg[pos + 1] if pos + 1 < len(seg) else " "
            opening = ch == "“" or (ch == '"' and (before.isspace() or before in "([{—–-/'") and not after.isspace())
            if opening:
                stack.append(pos)
            elif stack:
                stack.pop()
        if stack:
            out.append((seg[stack[-1] + 1:close].strip(), cm.group(0)))
    return out


def _flush_blockquote(block: list[tuple[int, str]], quotes: list[Quote]) -> None:
    if not block:
        return
    first_line = block[0][0]
    joined = " ".join(t for _, t in block).strip()
    if STATUS_BLOCK_RE.match(joined):
        # a Contested/Outdated block is prose, but the quotes it attributes are checked like any other
        for text, cite in quoted_citations(joined):
            keys = [c.key for c in _parse_citations(cite, first_line)]
            if keys and len(text.split()) >= 4:
                quotes.append(Quote(text=text, keys=keys, line=first_line))
        return
    keys = [c.key for c in _parse_citations(joined, first_line)]
    if not keys:
        return
    pairs = quoted_citations(joined)
    if pairs:                     # each quote with its own citation
        for text, cite in pairs:
            own = [c.key for c in _parse_citations(cite, first_line)]
            if own and len(text.split()) >= 4:
                quotes.append(Quote(text=text, keys=own, line=first_line))
        return
    whole = re.search(r"[\"“](.{20,})[\"”]", _strip_citations(joined))   # e.g. "..." (p. 3) [@k]
    text = whole.group(1) if whole else _strip_citations(joined).strip(" \"“”—-")
    if len(text.split()) >= 4:
        quotes.append(Quote(text=text.strip(), keys=keys, line=first_line))


def parse_page(path: Path, wiki_root: Path) -> Page:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(wiki_root).as_posix() if path.is_relative_to(wiki_root) else path.as_posix()
    page = Page(path=path, rel=rel, name=path.stem, text=text)

    fm_text, body, offset = split_frontmatter(text)
    page.body_offset = offset
    if fm_text is not None:
        page.has_frontmatter = True
        try:
            data = yaml.safe_load(fm_text) or {}
            if isinstance(data, dict):
                page.frontmatter = data
            else:
                page.fm_error = "frontmatter is not a mapping"
        except yaml.YAMLError as exc:
            page.fm_error = f"invalid YAML: {str(exc).splitlines()[0]}"

    lines = body.split("\n")
    page.body_lines = lines
    in_fence = False
    block: list[tuple[int, str]] = []
    paragraph: list[str] = []
    seen_h2 = False
    words = 0
    prev_text = ""                               # the previous non-blank line, to spot figure captions

    for idx, raw in enumerate(lines):
        lineno = offset + idx
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            _flush_blockquote(block, page.quotes)
            block = []
            continue
        if in_fence:
            continue

        stripped = raw.strip()
        heading = HEADING_RE.match(raw)
        if heading:
            level = len(heading.group(1))
            page.headings.append((level, heading.group(2).strip(), lineno))
            if level == 2:
                seen_h2 = True
        if stripped.startswith(">"):
            block.append((lineno, stripped.lstrip(">").strip()))
        else:
            _flush_blockquote(block, page.quotes)
            block = []

        # lede: first plain paragraph before the first H2
        if page.lede is None and not seen_h2:
            plain = stripped and not heading and not stripped.startswith(
                (">", "-", "*", "|", "<!--", "!", "+")) and not re.match(r"^\d+\.\s", stripped)
            if plain:
                paragraph.append(stripped)
            elif paragraph:
                page.lede = " ".join(paragraph)
        elif paragraph and page.lede is None:
            page.lede = " ".join(paragraph)

        for m in WIKILINK_RE.finditer(raw):
            target = m.group(2).strip()
            if target:
                page.links.append(Link(target=target, anchor=(m.group(3) or None), line=lineno,
                                       kind="wiki", embed=bool(m.group(1))))
        for m in MDLINK_RE.finditer(raw):
            target = m.group(3)
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            path_part, _, anchor = target.partition("#")
            page.links.append(Link(target=path_part, anchor=anchor or None, line=lineno,
                                   kind="md", embed=bool(m.group(1))))
        page.citations.extend(_parse_citations(raw, lineno))
        if not stripped.startswith(">"):
            for text, cite in quoted_citations(raw):
                if len(text) >= 20:
                    keys = [c.key for c in _parse_citations(cite, lineno)]
                    page.quotes.append(Quote(text=text, keys=keys, line=lineno))
        figure = stripped.startswith("![") or prev_text.startswith("![") or bool(
            re.match(r"^\*+\s*(Figure|Fig\.)", stripped))
        quoted_evidence = stripped.startswith(">") and "[@" in stripped and re.search(r"[\"“]", stripped)
        if not heading and not figure and not quoted_evidence:   # embeds, captions and quotes are not prose
            words += len(re.findall(r"\w+", _strip_citations(raw)))
        if stripped:
            prev_text = stripped

    _flush_blockquote(block, page.quotes)
    if page.lede is None and paragraph:
        page.lede = " ".join(paragraph)
    page.words = words
    return page


def iter_page_paths(wiki_root: Path) -> list[Path]:
    """All markdown pages under the wiki root, excluding meta files and hidden folders."""
    out = []
    for path in sorted(wiki_root.rglob("*.md")):
        rel = path.relative_to(wiki_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if len(rel.parts) == 1 and (rel.name in META_FILES or rel.name.startswith("review-")):
            continue                     # review packets written next to the wiki's meta files
        out.append(path)
    return out


def load_pages(wiki_root: Path, paths: list[Path] | None = None) -> list[Page]:
    return [parse_page(p, wiki_root) for p in (paths or iter_page_paths(wiki_root))]
