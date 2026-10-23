"""Check every quote in a markdown file against the cited papers (journal-club R29).

A source file lists quotes one per list item::

    - F4, buzsaki_2015_HippocampalSharp, "Impact of SPW-Rs on Cortical Targets", L529: "In the prefrontal cortex ..." — exact
    - F5, same, L529: "the stronger direct projections ..." — exact
    - Q16h, Discussion, L290: "in a minority of cases ..." — exact

that is ``<id>, <citekey>, <section>, L<n>: "<quote>"`` with an optional
claimed status after a dash. ``same`` (or no citekey at all) means the
previous item's paper; the section is optional. Each quote is matched with
the wiki's :class:`~biblio.wiki.fidelity.QuoteChecker` against the paper's
docling text, project first, then the pools, and located on the line
``grep -n`` would print for it (:func:`biblio.sections.text_lines`, the same
numbering as ``biblio fulltext --grep``).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import BiblioConfig
from .sections import fulltext_path

_ITEM = re.compile(
    r"^\s*[-*]\s+(?P<prefix>.*?)\bL(?P<line>\d+)(?:\s*\([^)]*\))?\s*:\s*[\"“](?P<quote>.+?)[\"”]"
    r"(?=\s*(?:[—–]|$))\s*(?:[—–]+\s*(?P<claimed>[\w-]+))?")
# a quoted list item that claims a check ("..." — exact) but gives no L<n>
_QUOTED_ITEM = re.compile(r"^\s*[-*]\s+.*[\"“].{20,}?[\"”]\s*[—–]+\s*(?:exact|approximate)\b")
_KEYLIKE = re.compile(r"^@?[A-Za-z][\w:+.-]*\d[\w:+.-]*$")   # no spaces, has a digit: smith_2020_Title
_PROSE_KEY = re.compile(r"(?<![\w/.-])@?([a-z][a-z-]*_\d{4}[a-z]?_[A-Za-z]\w*)\b")   # biblio's convention


@dataclass
class QuoteItem:
    id: str
    citekey: str
    section: str
    line: int             # the L<n> written in the file
    quote: str
    claimed: str          # the status the file claims, "" if none
    file_line: int        # where the item is in the source file


@dataclass
class QuoteResult:
    id: str
    citekey: str
    section: str
    status: str           # exact | approximate | changed | missing | no-text | no-citekey
    diff: str
    line: int | None      # the line in <key>.md, as grep -n and `biblio fulltext --grep` count
    written_line: int
    heading: str
    where: str            # "project", "pool:<pool root>", or ""
    text: str             # the full text checked against
    file_line: int
    claimed: str
    raw: str = ""          # the exact characters of <key>.md the quote matches (grep -F finds them)
    sentence: str = ""     # the whole sentence around the quote, in the cleaned text
    version: str = ""      # the held version it matched, e.g. "published" (<key>@published); "" = default

    @property
    def line_ok(self) -> bool:
        return self.line is None or self.line == self.written_line


def parse_quotes(text: str) -> tuple[list[QuoteItem], list[int]]:
    """The quote items of a source file, and the lines of quoted list items without ``L<n>``.

    The citekey is the first comma field after the id that looks like a key
    (no spaces, a digit); ``same``, or no key at all, means the paper of the
    previous item, or one named in the prose since (``Physiology
    (oliva_2016_RoleHippocampal, ...):``). Fields after the key are the section.
    """
    items: list[QuoteItem] = []
    unchecked: list[int] = []
    prev = ""
    for no, raw in enumerate(text.split("\n"), 1):
        m = _ITEM.match(raw)
        if not m:
            if _QUOTED_ITEM.match(raw):
                unchecked.append(no)
            elif not re.match(r"^\s*[-*]\s", raw):
                named = _PROSE_KEY.findall(raw)
                if named:
                    prev = named[-1]
            continue
        fields = [f.strip() for f in m.group("prefix").strip().rstrip(",").split(",")]
        ident, rest = fields[0], fields[1:]
        key, section = prev, rest
        for i, f in enumerate(rest):
            if f.lower() == "same":
                key, section = prev, rest[i + 1:]
                break
            if _KEYLIKE.match(f):
                key, section = f.lstrip("@"), rest[i + 1:]
                break
        prev = key or prev
        items.append(QuoteItem(id=ident, citekey=key, section=", ".join(section).strip().strip('"“”'),
                               line=int(m.group("line")), quote=m.group("quote"),
                               claimed=(m.group("claimed") or "").lower(), file_line=no))
    return items, unchecked


def _where(cfg: BiblioConfig, path: Path) -> str:
    try:
        path.relative_to(cfg.out_root)
        return "project"
    except ValueError:
        pass
    # <pool>/bib/derivatives/docling/<key>/<key>.md -> the pool's root
    parts = path.parts
    if "derivatives" in parts:
        i = len(parts) - 1 - parts[::-1].index("derivatives")
        root = Path(*parts[:i])
        return f"pool:{root.parent if root.name == 'bib' else root}"
    return f"pool:{path.parent.parent}"


def check_quotes(cfg: BiblioConfig, items: list[QuoteItem]) -> list[QuoteResult]:
    from .wiki.fidelity import QuoteChecker

    paths: dict[str, Path | None] = {}

    def path_for(key: str) -> Path:
        if key not in paths:
            paths[key] = fulltext_path(cfg, key)
        return paths[key] or Path("/nonexistent") / key

    qc = QuoteChecker(path_for)
    out: list[QuoteResult] = []
    for it in items:
        if not it.citekey:
            out.append(QuoteResult(it.id, "", it.section, "no-citekey", "", None, it.line, "", "", "",
                                   it.file_line, it.claimed))
            continue
        m = qc.match(it.citekey, it.quote)
        loc = qc.locate(it.citekey, it.quote) if m.status in ("exact", "approximate", "changed") else None
        if loc and loc[0] != it.line and qc.occurs_at(it.citekey, it.quote, it.line):
            loc = (it.line, qc.heading_at(it.citekey, it.line))   # the passage occurs twice; the written one stands
        p = paths.get(it.citekey)
        sp = qc.spans(it.citekey, it.quote) if loc else None
        out.append(QuoteResult(
            id=it.id, citekey=it.citekey, section=it.section, status=m.status, diff=m.diff,
            line=loc[0] if loc else None, written_line=it.line, heading=loc[1] if loc else "",
            where=_where(cfg, p) if p else "", text=str(p) if p else "",
            file_line=it.file_line, claimed=it.claimed,
            raw=(sp or {}).get("raw") or "", sentence=(sp or {}).get("sentence") or "",
            version=(sp or {}).get("version") or m.version or ""))
    return out


def check_file(cfg: BiblioConfig, path: Path) -> tuple[list[QuoteResult], list[int]]:
    """Results for every quote item, and the lines of quoted items without ``L<n>`` (not checked)."""
    items, unchecked = parse_quotes(path.read_text(encoding="utf-8"))
    return check_quotes(cfg, items), unchecked


def fix_lines(path: Path, results: list[QuoteResult]) -> int:
    """Rewrite each wrong ``L<n>`` in place with the located line; returns how many changed."""
    lines = path.read_text(encoding="utf-8").split("\n")
    changed = 0
    for r in results:
        if r.line is None or r.line == r.written_line:
            continue
        i = r.file_line - 1
        new, n = re.subn(rf"\bL{r.written_line}(\s*:)", rf"L{r.line}\1", lines[i], count=1)
        if n:
            lines[i] = new
            changed += 1
    if changed:
        path.write_text("\n".join(lines), encoding="utf-8")
    return changed


def as_json(results: list[QuoteResult]) -> list[dict]:
    return [{**asdict(r), "line_ok": r.line_ok} for r in results]
