"""Reference triage for one paper: which of its references can we read now?

Each reference of a held paper (its GROBID ``references.json``, optionally
completed by the paper's OpenAlex ``referenced_works``) gets a status:

- ``fulltext``: docling output exists in the project or a pool
- ``pdf``: a PDF exists (project, pool, or the optional Zotero library)
- ``metadata``: a bibliography entry exists, no PDF
- ``absent``: found nowhere

Matching, in order: DOI; normalized title with the year within one; a DOI
recovered from the paper's OpenAlex ``referenced_works`` (``--openalex``),
which helps when GROBID found no DOI (most pool references, unless
``grobid.consolidate_citations`` is on).
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .config import BiblioConfig

STATUSES = ("fulltext", "pdf", "metadata", "absent")
_RANK = {s: i for i, s in enumerate(STATUSES)}
_TITLE_RATIO = 0.92
_MIN_PREFIX = 30


def normalize_doi(doi: str | None) -> str:
    """Lowercase bare DOI; drops URL prefixes and the trailing junk GROBID sometimes attaches
    ("10.1152/physrev.00032.2012.-over" -> "10.1152/physrev.00032.2012")."""
    d = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    m = re.search(r"10\.\d{4,9}/\S+", d)
    if m:
        d = m.group(0)
    d = re.split(r"\.-|\s", d, maxsplit=1)[0]
    return d.strip().rstrip(".,;:)]>\"'")


def normalize_title(title: str | None) -> str:
    t = re.sub(r"[{}\\]", "", (title or "").lower())
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _year(value: Any) -> int | None:
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(value or ""))
    return int(m.group(1)) if m else None


@dataclass
class Holding:
    """One copy of a paper somewhere we can read from."""
    where: str  # "project", "pool:<name>", "zotero"
    key: str
    doi: str = ""
    title: str = ""
    year: int | None = None
    pdf: bool = False
    fulltext: bool = False
    author: str = ""    # first author's family name, lower case
    library: str = ""   # Zotero library name ("My Library", a group's name)

    @property
    def status(self) -> str:
        return "fulltext" if self.fulltext else "pdf" if self.pdf else "metadata"


@dataclass
class HoldingIndex:
    holdings: list[Holding] = field(default_factory=list)
    by_doi: dict[str, list[Holding]] = field(default_factory=dict)
    by_title: dict[str, list[Holding]] = field(default_factory=dict)

    def add(self, h: Holding) -> None:
        self.holdings.append(h)
        if h.doi:
            self.by_doi.setdefault(h.doi, []).append(h)
        nt = normalize_title(h.title)
        if nt:
            self.by_title.setdefault(nt, []).append(h)

    def match_doi(self, doi: str) -> list[Holding]:
        return list(self.by_doi.get(normalize_doi(doi), [])) if doi else []

    def match_title(self, title: str, year: int | None) -> list[Holding]:
        nt = normalize_title(title)
        if len(nt) < 12:
            return []
        hits = [h for h in self.by_title.get(nt, []) if _year_ok(year, h.year)]
        if hits:
            return hits
        matcher = difflib.SequenceMatcher(None, autojunk=False)
        matcher.set_seq2(nt)  # seq2 is the side difflib caches
        for other, hs in self.by_title.items():
            hs = [h for h in hs if _year_ok(year, h.year)]
            if hs and _titles_close(nt, other, matcher):
                hits.extend(hs)
        return hits


def _year_ok(a: int | None, b: int | None) -> bool:
    return a is None or b is None or abs(a - b) <= 1


def _titles_close(a: str, b: str, matcher: difflib.SequenceMatcher | None = None) -> bool:
    """Same title up to OCR and typesetting noise. ``matcher``, if given, has ``a`` as seq2."""
    short, long_ = sorted((a, b), key=len)
    if len(short) >= _MIN_PREFIX and long_.startswith(short):
        return True  # GROBID often glues the venue onto the title
    if abs(len(a) - len(b)) > 0.15 * max(len(a), len(b)):
        return False  # ratio >= 0.92 is impossible past this length gap
    if matcher is None:
        matcher = difflib.SequenceMatcher(None, autojunk=False)
        matcher.set_seq2(a)
    matcher.set_seq1(b)
    return (matcher.real_quick_ratio() >= _TITLE_RATIO and matcher.quick_ratio() >= _TITLE_RATIO
            and matcher.ratio() >= _TITLE_RATIO)


# ---------------------------------------------------------------------------
# Where papers are held
# ---------------------------------------------------------------------------

def _bib_records(path: Path) -> Iterable[dict[str, Any]]:
    from ._pybtex_utils import parse_bibtex_file
    try:
        db = parse_bibtex_file(path)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for key, entry in db.entries.items():
        f = entry.fields
        out.append({
            "key": key,
            "doi": normalize_doi(f.get("doi")),
            "title": str(f.get("title") or ""),
            "year": _year(f.get("year") or f.get("date")),
            "file": str(f.get("file") or ""),
            "author": _first_family(entry),
        })
    return out


def family_key(name: str) -> str:
    """A family name for matching: lower case, no accents, spaces or hyphens ("Buzsáki" -> "buzsaki")."""
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFKD", name or "") if not unicodedata.combining(c))
    return normalize_title(folded).replace(" ", "")


def _first_family(entry: Any) -> str:
    people = entry.persons.get("author") or entry.persons.get("editor") or []
    if not people:
        return ""
    return family_key(" ".join(people[0].last_names) or " ".join(people[0].first_names))


def pool_name(pool_root: Path) -> str:
    """'sirocampus' for /storage/share/sirocampus/bib/articles."""
    if pool_root.name == "articles" and pool_root.parent.name == "bib":
        return pool_root.parent.parent.name
    return pool_root.name


def _project_bibs(cfg: BiblioConfig) -> list[Path]:
    root = cfg.repo_root
    paths = [root / rel for rel in (".projio/render/compiled.bib", ".projio/biblio/merged.bib", "bib/main.bib")]
    src = cfg.bibtex_merge.src_dir
    if src.is_dir():
        paths.extend(sorted(src.glob(cfg.bibtex_merge.src_glob)))
    return [p for p in paths if p.is_file()]


def _docling_done(out_dir: Path, key: str) -> bool:
    d = out_dir / key
    return d.is_dir() and any(d.glob("*.md"))


def add_project(index: HoldingIndex, cfg: BiblioConfig) -> None:
    seen: set[str] = set()
    for bib in _project_bibs(cfg):
        for r in _bib_records(bib):
            if r["key"] in seen:
                continue
            seen.add(r["key"])
            pdf = (cfg.pdf_root / cfg.pdf_pattern.format(citekey=r["key"])).is_file()
            index.add(Holding("project", r["key"], r["doi"], r["title"], r["year"],
                              pdf=pdf, fulltext=_docling_done(cfg.out_root, r["key"]), author=r["author"]))


def _pool_derivatives(pool_root: Path) -> Path | None:
    for base in (pool_root, pool_root.parent):
        if (base / "derivatives").is_dir():
            return base / "derivatives"
    return None


def add_pool(index: HoldingIndex, pool_root: Path) -> None:
    from .pool import _find_pool_bib
    bib = _find_pool_bib(pool_root)
    if bib is None:
        return
    deriv = _pool_derivatives(pool_root)
    name = f"pool:{pool_name(pool_root)}"
    for r in _bib_records(bib):
        key = r["key"]
        pdf = (pool_root / key / f"{key}.pdf").is_file() or (pool_root / f"{key}.pdf").is_file()
        fulltext = deriv is not None and _docling_done(deriv / "docling", key)
        index.add(Holding(name, key, r["doi"], r["title"], r["year"], pdf=pdf, fulltext=fulltext,
                          author=r["author"]))


def add_zotero(index: HoldingIndex, path: Path) -> int:
    """A Zotero library: ``zotero.sqlite`` (read-only) or a BibTeX export."""
    if path.suffix == ".sqlite":
        return _add_zotero_sqlite(index, path)
    n = 0
    for r in _bib_records(path):
        index.add(Holding("zotero", r["key"], r["doi"], r["title"], r["year"],
                          pdf=".pdf" in r["file"].lower(), author=r["author"]))
        n += 1
    return n


_ZOTERO_SQL = """
SELECT i.itemID, i.libraryID, i.key, f.fieldName, v.value
FROM items i
JOIN itemData d ON d.itemID = i.itemID
JOIN fields f ON f.fieldID = d.fieldID
JOIN itemDataValues v ON v.valueID = d.valueID
WHERE f.fieldName IN ('title', 'DOI', 'date', 'extra')
  AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
"""
_ZOTERO_FIRST_SQL = """
SELECT ic.itemID, c.lastName FROM itemCreators ic JOIN creators c ON c.creatorID = ic.creatorID
WHERE ic.orderIndex = 0
"""
_ZOTERO_PDF_SQL = """
SELECT DISTINCT parentItemID FROM itemAttachments
WHERE contentType = 'application/pdf' AND parentItemID IS NOT NULL
  AND itemID NOT IN (SELECT itemID FROM deletedItems)
"""


def _add_zotero_sqlite(index: HoldingIndex, path: Path) -> int:
    # immutable=1 reads a library Zotero holds open without taking a lock
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        items: dict[int, dict[str, Any]] = {}
        for item_id, lib, key, fname, value in con.execute(_ZOTERO_SQL):
            it = items.setdefault(item_id, {"key": f"{lib}:{key}"})
            it[fname] = value
        with_pdf = {row[0] for row in con.execute(_ZOTERO_PDF_SQL)}
        first: dict[int, str] = {}
        libraries: dict[int, str] = {1: "My Library"}
        try:
            for item_id, last in con.execute(_ZOTERO_FIRST_SQL):
                first[item_id] = family_key(last or "")
            libraries.update({lib: name for lib, name in con.execute("SELECT libraryID, name FROM groups")})
        except sqlite3.Error:
            pass
    finally:
        con.close()
    for item_id, it in items.items():
        doi = it.get("DOI") or ""
        if not doi:  # Zotero keeps DOIs of some item types in Extra
            m = re.search(r"^DOI:\s*(\S+)", it.get("extra") or "", re.M | re.I)
            doi = m.group(1) if m else ""
        lib_id = int(it["key"].split(":", 1)[0])
        index.add(Holding("zotero", it["key"], normalize_doi(doi), it.get("title") or "",
                          _year(it.get("date")), pdf=item_id in with_pdf, author=first.get(item_id, ""),
                          library=libraries.get(lib_id, f"library {lib_id}")))
    return len(items)


# ---------------------------------------------------------------------------
# The paper's references
# ---------------------------------------------------------------------------

def _grobid_dir(cfg: BiblioConfig, citekey: str) -> Path | None:
    from .grobid import grobid_out_root
    from .pool import resolve_pool_derivative
    local = grobid_out_root(cfg) / citekey
    if (local / "references.json").is_file():
        return local
    pooled = resolve_pool_derivative(cfg, citekey, "grobid")
    if pooled is not None and (pooled / "references.json").is_file():
        return pooled
    return None


def load_references(cfg: BiblioConfig, citekey: str) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """(GROBID references, GROBID header, where they came from)."""
    d = _grobid_dir(cfg, citekey)
    if d is None:
        return [], {}, ""
    refs = json.loads((d / "references.json").read_text(encoding="utf-8"))
    header: dict[str, Any] = {}
    if (d / "header.json").is_file():
        try:
            header = json.loads((d / "header.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            header = {}
    return [r for r in refs if isinstance(r, dict)], header, str(d)


def _openalex_id(value: str) -> str:
    return str(value or "").rstrip("/").split("/")[-1]


def openalex_references(cfg: BiblioConfig, doi: str, *, fetch: bool = True) -> list[dict[str, Any]] | None:
    """The paper's ``referenced_works`` as {openalex, doi, title, year}; None if the work is unknown."""
    cache = cfg.openalex_cache
    work = cache.load_json(cache.path_for_doi(doi))
    client = None
    try:
        if work is None and fetch:
            from .openalex.openalex_client import OpenAlexClient
            client = OpenAlexClient(cfg.openalex_client)
            work = client.get_work_by_doi(doi)
            cache.save_json(cache.path_for_doi(doi), work)
        if work is None:
            return None
        ids = [_openalex_id(w) for w in work.get("referenced_works") or []]
        works: dict[str, dict[str, Any]] = {}
        missing = []
        for wid in ids:
            cached = cache.load_json(cache.path_for_work_id(wid))
            if cached is not None:
                works[wid] = cached
            else:
                missing.append(wid)
        if missing and fetch:
            if client is None:
                from .openalex.openalex_client import OpenAlexClient
                client = OpenAlexClient(cfg.openalex_client)
            for i in range(0, len(missing), 50):
                batch = missing[i:i + 50]
                for w in client.filter_works(filter_expr="openalex_id:" + "|".join(batch), per_page=50):
                    wid = _openalex_id(w.get("id"))
                    cache.save_json(cache.path_for_work_id(wid), w)
                    works[wid] = w
    finally:
        if client is not None:
            client.close()
    out = []
    for wid in ids:
        w = works.get(wid, {})
        out.append({
            "openalex": wid,
            "doi": normalize_doi(w.get("doi")),
            "title": str(w.get("display_name") or w.get("title") or ""),
            "year": w.get("publication_year"),
        })
    return out


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------

def _first_author(ref: dict[str, Any]) -> str:
    authors = ref.get("authors") or []
    return str(authors[0]) if authors else ""


def _row(ref: dict[str, Any], index: HoldingIndex) -> dict[str, Any]:
    doi = normalize_doi(ref.get("doi"))
    year = _year(ref.get("year"))
    via = ""
    hits = index.match_doi(doi)
    if hits:
        via = "doi"
    else:
        hits = index.match_title(ref.get("title") or "", year)
        if hits:
            via = "title"
    best = min((h.status for h in hits), key=_RANK.__getitem__, default="absent")
    return {
        "n": ref.get("n"),
        "title": ref.get("title") or "",
        "first": _first_author(ref),
        "year": year,
        "doi": doi,
        "venue": ref.get("venue") or "",
        "status": best,
        "via": via,
        "held": [{"where": h.where, "key": h.key, "status": h.status} for h in hits],
    }


def _attach_openalex(rows: list[dict[str, Any]], oa_refs: list[dict[str, Any]],
                     index: HoldingIndex) -> dict[str, int]:
    """Link rows to the paper's OpenAlex references.

    Rows with a DOI get OpenAlex's title and year (``title_openalex``, ``year_openalex``; GROBID's
    stay in ``title``/``year``); DOI-less rows get a DOI by title and year; references GROBID
    missed are appended (``source: openalex``). Returns counts: improved, added, unmatched.
    """
    used: set[str] = set()
    by_doi = {o["doi"]: o for o in oa_refs if o["doi"]}
    for row in rows:
        o = by_doi.get(row["doi"]) if row["doi"] else None
        if o is not None:
            used.add(o["openalex"])
            row["openalex"] = o["openalex"]
            if o["title"]:
                row["title_openalex"] = o["title"]
            if o["year"]:
                row["year_openalex"] = o["year"]
    improved = 0
    nt_rows = [(row, normalize_title(row["title"])) for row in rows]
    for row, nt in nt_rows:
        if row["doi"] or not nt:
            continue
        for o in oa_refs:
            if o["openalex"] in used or not o["title"]:
                continue
            if _year_ok(row["year"], o["year"]) and _titles_close(nt, normalize_title(o["title"])):
                used.add(o["openalex"])
                row["openalex"] = o["openalex"]
                if o["doi"]:
                    row["doi"] = o["doi"]
                    hits = index.match_doi(o["doi"])
                    if hits and _RANK[min((h.status for h in hits), key=_RANK.__getitem__)] < _RANK[row["status"]]:
                        row["status"] = min((h.status for h in hits), key=_RANK.__getitem__)
                        row["via"] = "openalex"
                        row["held"] = [{"where": h.where, "key": h.key, "status": h.status} for h in hits]
                        improved += 1
                break
    unmatched = sum(1 for row in rows if not row.get("openalex"))
    n = len(rows)
    added = 0
    for o in oa_refs:
        if o["openalex"] in used or not (o["doi"] or o["title"]):
            continue
        n += 1
        added += 1
        extra = _row({"n": n, "title": o["title"], "year": o["year"], "doi": o["doi"]}, index)
        extra["openalex"] = o["openalex"]
        extra["source"] = "openalex"
        rows.append(extra)
    return {"improved": improved, "added": added, "unmatched": unmatched}


def _mark_duplicates(rows: list[dict[str, Any]]) -> list[str]:
    """Same-DOI references (``duplicate_of``) and papers a pool holds under two keys; returns notes."""
    notes, first = [], {}
    for row in rows:
        if row["doi"] and row["doi"] in first:
            row["duplicate_of"] = first[row["doi"]]
            notes.append(f"#{row['n']} has the same DOI as #{first[row['doi']]} ({row['doi']})")
        elif row["doi"]:
            first[row["doi"]] = row["n"]
    seen = set()
    for row in rows:
        by_where: dict[str, list[str]] = {}
        for h in row["held"]:
            by_where.setdefault(h["where"], []).append(h["key"])
        for where, keys in by_where.items():
            if len(keys) > 1 and (where, tuple(sorted(keys))) not in seen:
                seen.add((where, tuple(sorted(keys))))
                notes.append(f"{where} holds one paper under {len(keys)} keys: {', '.join(sorted(keys))}")
    return notes


def build_index(cfg: BiblioConfig, *, zotero: Path | None = None) -> HoldingIndex:
    index = HoldingIndex()
    add_project(index, cfg)
    for pool_root in getattr(cfg, "pool_search", ()) or ():
        add_pool(index, Path(pool_root))
    if zotero is not None:
        add_zotero(index, zotero)
    return index


def triage(
    cfg: BiblioConfig,
    citekey: str,
    *,
    zotero: Path | None = None,
    use_openalex: bool = False,
    fetch: bool = True,
    index: HoldingIndex | None = None,
) -> dict[str, Any]:
    """Triage the references of ``citekey``. See the module docstring."""
    citekey = citekey.lstrip("@")
    refs, header, refs_from = load_references(cfg, citekey)
    index = index or build_index(cfg, zotero=zotero)
    rows = []
    for i, ref in enumerate(refs, 1):
        row = _row({**ref, "n": i}, index)
        row["source"] = "grobid"
        rows.append(row)

    notes: list[str] = []
    if not refs:
        notes.append("no GROBID references.json in the project or a pool (run `biblio grobid run`)")
    doi = normalize_doi(header.get("doi")) or _bib_doi(index, citekey)
    if use_openalex:
        if not doi:
            notes.append("OpenAlex skipped: no DOI for the paper")
        else:
            oa_refs = openalex_references(cfg, doi, fetch=fetch)
            if oa_refs is None:
                notes.append("OpenAlex: work not cached (fetch disabled)")
            else:
                st = _attach_openalex(rows, oa_refs, index)
                notes.append(f"OpenAlex: {len(oa_refs)} referenced works; {st['improved']} references improved; "
                             f"{st['added']} works GROBID missed (added, marked OpenAlex only); "
                             f"{st['unmatched']} GROBID references not among them")

    notes.extend(_mark_duplicates(rows))
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {
        "citekey": citekey,
        "doi": doi,
        "references_from": refs_from,
        "searched": sorted({h.where for h in index.holdings}),
        "counts": counts,
        "without_doi": sum(1 for r in rows if not r["doi"]),
        "notes": notes,
        "references": rows,
    }


def _bib_doi(index: HoldingIndex, citekey: str) -> str:
    for h in index.holdings:
        if h.key == citekey and h.doi:
            return h.doi
    return ""


_STATUS_TITLES = {
    "fulltext": "Full text (docling)",
    "pdf": "PDF, not converted",
    "metadata": "Metadata only",
    "absent": "Absent",
}


def to_markdown(result: dict[str, Any]) -> str:
    c = result["counts"]
    lines = [
        f"# Reference triage: {result['citekey']}",
        "",
        f"{len(result['references'])} references: "
        + ", ".join(f"{c[s]} {s}" for s in STATUSES)
        + f". {result['without_doi']} without a DOI.",
        "",
        "Searched: " + ", ".join(result["searched"]) + ".",
    ]
    for note in result["notes"]:
        lines += ["", f"- {note}"]
    for status in STATUSES:
        rows = [r for r in result["references"] if r["status"] == status]
        if not rows:
            continue
        lines += ["", f"## {_STATUS_TITLES[status]} ({len(rows)})", "",
                  "| # | First author | Year | Title | DOI | Held |", "|---|---|---|---|---|---|"]
        for r in rows:
            held = ", ".join(f"{h['where']}:{h['key']}" for h in r["held"])
            title = (r.get("title_openalex") or r["title"]).replace("|", "\\|")
            if r.get("source") == "openalex":
                title += " *(OpenAlex only)*"
            if r.get("duplicate_of"):
                title += f" *(same DOI as #{r['duplicate_of']})*"
            year = r.get("year_openalex") or r["year"] or ""
            lines.append(f"| {r['n']} | {r['first']} | {year} | {title} | {r['doi']} | {held} |")
    return "\n".join(lines) + "\n"


def write_outputs(cfg: BiblioConfig, result: dict[str, Any], out_dir: Path | None = None) -> tuple[Path, Path]:
    out_dir = out_dir or (cfg.repo_root / "bib" / "derivatives" / "refs" / result["citekey"])
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "triage.json", out_dir / "triage.md"
    jp.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mp.write_text(to_markdown(result), encoding="utf-8")
    return jp, mp
