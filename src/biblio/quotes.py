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
from typing import Any

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
    outside: str = ""      # set when the text holds other articles and the quote lies outside this one (R69)
    quote: str = ""        # the quote as written (``--text`` mode, where items carry no id)

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
    spans: dict[Path, Any] = {}
    titles: dict[str, str] | None = None

    def outside(key: str, path: Path | None, line: int | None) -> str:
        nonlocal titles
        from .article_span import bib_titles, span_for_file
        if path is None or line is None or not path.is_file():
            return ""
        if path not in spans:
            if titles is None:
                titles = bib_titles(cfg)
            base = key.split("@", 1)[0]
            spans[path] = span_for_file(path, titles.get(base))
        span = spans[path]
        if not span.mixed or span.contains(line):
            return ""
        return f"L{line} is outside the article (lines {span.start}-{span.end}): " + "; ".join(span.reasons())
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
            version=(sp or {}).get("version") or m.version or "",
            outside=outside(it.citekey, p, loc[0] if loc else None)))
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


# ── any quoted string, against named texts (``quotes check --text``) ───────────────────────────
# A page that is not a list of ``L<n>`` items (an answer, a claims digest, slide notes): every
# "..." on one line, 12 characters or more, outside the YAML frontmatter, is checked against the
# texts named on the command line. "…" inside a quote splits it into parts, each checked.
_ANY_QUOTE = re.compile(r"[\"“]([^\"“”\n]{12,}?)[\"”]")
MIN_QUOTE = 12


def free_quotes(text: str) -> list[tuple[int, str]]:
    """(line number in the file, quote) for every quoted string outside the frontmatter."""
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                start = i + 1
                break
    return [(n, q.strip()) for n, line in enumerate(lines[start:], start + 1)
            for q in _ANY_QUOTE.findall(line) if len(q.strip()) >= MIN_QUOTE]


def resolve_text(cfg: BiblioConfig | None, source: str, tmpdir: Path) -> tuple[str, Path | None]:
    """A ``--text`` source as (label, markdown path): a file (.md, .txt; .pdf via pdftotext) or a
    citekey held in the project or a pool."""
    p = Path(source).expanduser()
    if p.is_file():
        if p.suffix.lower() == ".pdf":
            import subprocess
            out = tmpdir / f"{p.stem}.md"
            try:
                txt = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True,
                                     text=True, check=True).stdout
            except (OSError, subprocess.CalledProcessError) as exc:
                raise SystemExit(f"[ERROR] cannot read {p} (needs poppler's pdftotext): {exc}") from None
            out.write_text(txt, encoding="utf-8")
            return str(p), out
        return str(p), p.resolve()
    if p.suffix.lower() in (".md", ".txt", ".pdf") or "/" in source:
        return source, None
    return source, (fulltext_path(cfg, source) if cfg is not None else None)


def check_against(cfg: BiblioConfig | None, path: Path, sources: list[str]) -> list[QuoteResult]:
    """Every quoted string in ``path`` checked against ``sources`` (paths or citekeys)."""
    import tempfile
    from .wiki.fidelity import QuoteChecker

    with tempfile.TemporaryDirectory() as tmp:
        texts = [resolve_text(cfg, s, Path(tmp)) for s in sources]
        missing = [label for label, p in texts if p is None]
        if missing:
            raise SystemExit("[ERROR] no text for: " + ", ".join(missing)
                             + " (a .md/.txt/.pdf path, or a citekey held in the project or a pool)")
        by_label = {label: p for label, p in texts}
        qc = QuoteChecker(lambda label: by_label[label])
        rank = QuoteChecker._RANK
        out: list[QuoteResult] = []
        for i, (file_line, quote) in enumerate(free_quotes(path.read_text(encoding="utf-8")), 1):
            parts = [q.strip(" .,;") for q in re.split(r"…|\.\.\.", quote) if q.strip(" .,;")]
            worst, best_src, diffs, first_loc = "exact", "", [], None
            for part in parts:
                best = None
                for label, _ in texts:
                    m = qc.match(label, part)
                    if best is None or rank[m.status] < rank[best[1].status]:
                        best = (label, m)
                label, m = best
                if rank[m.status] > rank[worst]:
                    worst = m.status
                if m.diff:
                    diffs.append(m.diff)
                if not best_src:
                    best_src = label
                if first_loc is None and m.status != "missing":
                    first_loc = (label, qc.locate(label, part))
            loc_label, loc = first_loc if first_loc else (best_src, None)
            text_path = by_label.get(loc_label)
            out.append(QuoteResult(
                id=f"q{i}", citekey=loc_label, section="", status=worst, diff="; ".join(diffs),
                line=loc[0] if loc else None, written_line=loc[0] if loc else 0,
                heading=loc[1] if loc else "", where="", text=str(text_path or ""),
                file_line=file_line, claimed="", quote=quote))
        return out
