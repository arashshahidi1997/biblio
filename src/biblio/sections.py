"""Read a paper by section (backlog D01).

Digests and wiki ingest work on sections, never on a truncated whole paper.
The primary source is docling's markdown: it is the text the wiki's quote
check compares against, so a quote copied from a section verifies exactly.
GROBID's TEI is the fallback when there is no docling output. Reference lists
and administrative sections (acknowledgements, funding, contributions) are
dropped.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .config import BiblioConfig

# matched against the title with spaces and digits removed: docling splits words ("Author contr ibutions")
_DROP = re.compile(r"^(references?|bibliography|literaturecited|acknowledge?ments?|funding|authorcontributions?|"
                   r"competinginterests?|conflictsofinterest|conflictofinterest|declarationofinterests?|"
                   r"disclosurestatement|supplementary(material|information)|additionalinformation|"
                   r"preprintrepositor)", re.I)


def _dropped(title: str) -> bool:
    return bool(_DROP.match(re.sub(r"[\s\d.)]+", "", title)))


def _clean_title(title: str) -> str:
    from .wiki.embeds import clean_caption
    return clean_caption(title)[0]
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_NOISE = re.compile(r"^\s*(?:<!--\s*image\s*-->|!\[[^\]]*\]\([^)]*\))\s*$")


@dataclass
class Section:
    id: str              # S1, S2, ... in reading order
    title: str
    text: str
    line: int            # 1-based line of the heading in the source file (0 without a heading)
    words: int


def read_fulltext(path: Path, *, clean: bool = False) -> str:
    """A full text as stored: newlines untranslated, so a stray carriage return is no line break.

    ``clean`` repairs docling's artefacts line for line (:mod:`biblio.textclean`):
    the same lines, readable glyphs and spacing.
    """
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if not clean:
        return raw
    from .textclean import clean_text_cached
    return clean_text_cached(str(path), raw)


def text_lines(text: str) -> list[str]:
    """Lines as ``grep -n`` counts them: split at "\\n" only.

    The one line numbering for full texts (R29). ``str.splitlines`` and
    universal-newline reading also break at "\\r", form feeds and U+2028,
    which docling writes now and then (21 stray "\\r" in buzsaki_2015 put
    every line after them 21 off).
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def fulltext_path(cfg: BiblioConfig, citekey: str) -> Path | None:
    """The paper's docling markdown: the project's copy, else a pool's."""
    key = citekey.lstrip("@")
    local = cfg.out_root / key / f"{key}.md"
    if local.is_file():
        return local
    from .pool import resolve_pool_derivative
    pooled = resolve_pool_derivative(cfg, key, "docling")
    if pooled is not None:
        for name in (f"{pooled.name}.md", f"{key}.md"):
            if (pooled / name).is_file():
                return pooled / name
    return None


def split_markdown(text: str) -> list[Section]:
    """Sections of a docling markdown file, split at headings; dropped sections removed."""
    sections: list[Section] = []
    title, start, body, dropping = "Front matter", 0, [], False

    def flush() -> None:
        content = "\n".join(line for line in body if not _NOISE.match(line)).strip()
        if content and not dropping:
            sections.append(Section("", title, content, start, len(content.split())))

    for no, line in enumerate(text_lines(text), 1):
        m = _HEADING.match(line)
        if m:
            flush()
            title, start, body = _clean_title(m.group(2).strip()), no, []
            dropping = _dropped(title)
            continue
        body.append(line)
    flush()
    for i, s in enumerate(sections, 1):
        s.id = f"S{i}"
    return sections


def split_tei(tei_xml: str) -> list[Section]:
    """Sections of a GROBID TEI body (``<div><head>...</head><p>...</p></div>``)."""
    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    root = ET.fromstring(tei_xml)
    out: list[Section] = []
    abstract = root.find(".//tei:profileDesc/tei:abstract", ns)
    if abstract is not None:
        text = " ".join(" ".join(p.itertext()).strip() for p in abstract.iter(f"{{{ns['tei']}}}p")).strip()
        if text:
            out.append(Section("", "Abstract", text, 0, len(text.split())))
    for div in root.findall(".//tei:body/tei:div", ns):
        head = div.find("tei:head", ns)
        title = _clean_title(" ".join(head.itertext()).strip()) if head is not None else "Untitled"
        if _dropped(title):
            continue
        paras = [" ".join(" ".join(p.itertext()).split()) for p in div.findall("tei:p", ns)]
        text = "\n\n".join(p for p in paras if p)
        if text:
            out.append(Section("", title, text, 0, len(text.split())))
    for i, s in enumerate(out, 1):
        s.id = f"S{i}"
    return out


def read_sections(cfg: BiblioConfig, citekey: str) -> tuple[list[Section], Path, str]:
    """(sections, source file, "docling" | "grobid") for a held paper."""
    key = citekey.lstrip("@")
    md = fulltext_path(cfg, key)
    if md is not None:
        return split_markdown(read_fulltext(md, clean=True)), md, "docling"
    from .grobid import grobid_out_root
    from .pool import resolve_pool_derivative
    for d in (grobid_out_root(cfg) / key, resolve_pool_derivative(cfg, key, "grobid")):
        tei = (d / f"{key}.tei.xml") if d else None
        if tei is not None and tei.is_file():
            return split_tei(tei.read_text(encoding="utf-8", errors="replace")), tei, "grobid"
    raise FileNotFoundError(f"no full text for {key}: run `biblio docling run --key {key}` "
                            f"(or GROBID) first")
