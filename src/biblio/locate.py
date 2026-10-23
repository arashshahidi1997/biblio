"""Where is each paper of a list? (journal-club R30)

``biblio locate`` takes DOIs or "Author Year Title" lines and says, per item,
what can be read now: full text or PDF in the project, in a pool, in Zotero
(library, item key, PDF or not, duplicates), or nothing, with a doi.org link
(from OpenAlex when the line has no DOI). Matching reuses the reference
triage's index (:mod:`biblio.refs`): DOI, then the title with the year within
one, then first author and year with every title word given.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import BiblioConfig
from .refs import Holding, HoldingIndex, build_index, family_key, normalize_doi, normalize_title

_STOP = frozenset("a an and are as at by for from in into is of on or the to with".split())


@dataclass
class Item:
    raw: str
    doi: str = ""
    author: str = ""
    year: int | None = None
    title: str = ""


@dataclass
class Located:
    item: Item
    holdings: list[dict[str, Any]] = field(default_factory=list)   # where, key, status, library
    status: str = "not held"
    doi: str = ""
    title: str = ""                 # the matched or OpenAlex title
    via: str = ""                   # doi | title | author-year | openalex
    note: str = ""

    @property
    def link(self) -> str:
        return f"https://doi.org/{self.doi}" if self.doi else ""


def parse_item(line: str) -> Item:
    """A DOI (or doi.org link), or "Author [& Author | et al.] Year Title"."""
    raw = line.strip()
    doi = normalize_doi(raw) if re.search(r"10\.\d{4,9}/", raw) else ""
    if doi:
        return Item(raw, doi=doi)
    m = re.search(r"\b(1[89]\d\d|20\d\d)[a-z]?\b", raw)
    if not m:
        return Item(raw, title=raw)
    before, after = raw[:m.start()], raw[m.end():]
    words = re.findall(r"[^\W\d_][\w'-]*", before, re.UNICODE)
    author = family_key(words[0]) if words else ""
    title = after.strip(" ,.;:()-—–\"“”")
    return Item(raw, author=author, year=int(m.group(1)), title=title)


def _title_words(title: str) -> list[str]:
    return [w for w in normalize_title(title).split() if len(w) >= 3 and w not in _STOP]


def match(index: HoldingIndex, it: Item) -> tuple[list[Holding], str]:
    if it.doi:
        hits = index.match_doi(it.doi)
        return hits, "doi" if hits else ""
    if it.title:
        hits = index.match_title(it.title, it.year)
        if hits:
            return hits, "title"
    if it.author and it.year:
        want = _title_words(it.title)
        hits = [h for h in index.holdings
                if h.year == it.year and h.author and (h.author == it.author or h.author.startswith(it.author))
                and all(w in normalize_title(h.title).split() for w in want)]
        if hits:
            return hits, "author-year"
    return [], ""


def _openalex(cfg: BiblioConfig, it: Item) -> dict[str, Any] | None:
    """The work for an item: by DOI, else a title search checked against year and first author."""
    from .openalex.openalex_client import OpenAlexClient
    client = OpenAlexClient(cfg.openalex_client)
    try:
        if it.doi:
            return client.get_work_by_doi(it.doi)
        query = it.title or it.raw
        for w in client.search_works(query, per_page=10) or []:
            if it.year and w.get("publication_year") and abs(int(w["publication_year"]) - it.year) > 1:
                continue
            authors = [family_key((a.get("author") or {}).get("display_name") or "")
                       for a in w.get("authorships") or []]
            if it.author and authors and it.author not in authors[0]:
                continue
            want = _title_words(it.title)
            if want and not all(x in normalize_title(w.get("title") or "").split() for x in want[:6]):
                continue
            return w
    except Exception:  # noqa: BLE001  offline, rate limit
        return None
    return None


def _rank(h: dict[str, Any]) -> tuple[int, int]:
    where = h["where"]
    place = 0 if where == "project" else 1 if where.startswith("pool:") else 2
    return ({"fulltext": 0, "pdf": 1, "metadata": 2}.get(h["status"], 3), place)


def _status(holdings: list[dict[str, Any]]) -> str:
    if not holdings:
        return "not held"
    best = min(holdings, key=_rank)
    what = {"fulltext": "full text", "pdf": "PDF only", "metadata": "entry only"}[best["status"]]
    where = best["where"] if best["where"] != "zotero" else f"zotero ({best.get('library') or 'library'})"
    return f"{where}: {what}"


def _zotero_live(libs: list, it: Item, title: str) -> list[dict[str, Any]]:
    from .zotero_add import _best_pdf_rank, find_items
    ref = it.doi or title or it.title
    if not ref:
        return []
    out = []
    for lib in libs:
        try:
            items = find_items(lib.zot, ref)
        except Exception:  # noqa: BLE001
            continue
        for zi in items:
            pdf = _best_pdf_rank(lib.zot, zi["data"]["key"]) != (9,)
            out.append({"where": "zotero", "key": zi["data"]["key"], "status": "pdf" if pdf else "metadata",
                        "library": lib.label})
    return out


def locate(
    cfg: BiblioConfig,
    lines: list[str],
    *,
    zotero: Path | None = None,
    zotero_libraries: list | None = None,
    openalex: bool = False,
) -> list[Located]:
    """Status per item; ``zotero`` is a ``zotero.sqlite``/export, ``zotero_libraries`` the live API."""
    index = build_index(cfg, zotero=zotero)
    out: list[Located] = []
    for line in lines:
        it = parse_item(line)
        hits, via = match(index, it)
        loc = Located(it, via=via, doi=it.doi)
        if hits:
            loc.doi = loc.doi or next((h.doi for h in hits if h.doi), "")
            loc.title = next((h.title for h in hits if h.title), "")
        if openalex and (not hits or not loc.doi):
            work = _openalex(cfg, it)
            if work:
                loc.doi = loc.doi or normalize_doi(work.get("doi"))
                loc.title = loc.title or (work.get("title") or "")
                if not hits and loc.doi:        # held under another title? try its DOI
                    hits = index.match_doi(loc.doi)
                    loc.via = "openalex" if hits else ""
        loc.holdings = [{"where": h.where, "key": h.key, "status": h.status, "library": h.library}
                        for h in hits]
        if zotero_libraries:
            loc.holdings += _zotero_live(zotero_libraries, Item(it.raw, doi=loc.doi, title=it.title),
                                         loc.title or it.title)
        zot = [h for h in loc.holdings if h["where"] == "zotero"]
        if len(zot) > 1:
            loc.note = f"{len(zot)} Zotero items"
        loc.status = _status(loc.holdings)
        out.append(loc)
    return out


def to_markdown(rows: list[Located]) -> str:
    lines = ["| # | paper | status | held | link |", "|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        held = "; ".join(
            (f"{h['where']}" if h["where"] != "zotero" else f"zotero {h.get('library') or ''}".strip())
            + f" `{h['key']}` {({'fulltext': 'full text', 'pdf': 'PDF', 'metadata': 'no PDF'})[h['status']]}"
            for h in sorted(r.holdings, key=_rank))
        if r.note:
            held += f" ({r.note})"
        paper = r.item.raw.replace("|", "/")
        if r.title and normalize_title(r.title) not in normalize_title(r.item.raw):
            paper += f"<br>*{r.title.replace('|', '/')}*"
        lines.append(f"| {i} | {paper} | {r.status} | {held} | {r.link} |")
    counts: dict[str, int] = {}
    for r in rows:
        k = "not held" if r.status == "not held" else r.status.split(": ", 1)[1]
        counts[k] = counts.get(k, 0) + 1
    summary = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
    return "\n".join(lines) + f"\n\n{len(rows)} papers: {summary}.\n"


def as_json(rows: list[Located]) -> list[dict[str, Any]]:
    return [{"item": r.item.raw, "doi": r.doi, "link": r.link, "title": r.title, "status": r.status,
             "via": r.via, "note": r.note, "holdings": r.holdings} for r in rows]
