"""One paper from Zotero into the project (backlog I04).

``biblio add zotero REF`` finds one item (Zotero item key, a citekey from
Better BibTeX or biblio's convention, or a DOI), writes its entry to
``bib/srcbib/zotero.bib`` under biblio's citekey, and copies its PDF to
``pdf_root``. Through the local API (Zotero 7+ on the same machine, no key)
or the web API (``zotero.library_id`` and an API key in biblio.yml).

A paper already in the project (same DOI or citekey) keeps its key; only a
missing PDF is filled in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .citekey import canonical_citekey_str
from .config import BiblioConfig
from .ingest import IngestRecord
from .ledger import append_jsonl, new_run_id, utc_now_iso
from .refs import _bib_records, _project_bibs, normalize_doi
from .zotero import (ZoteroClient, ZoteroConfig, _extract_year, _zotero_type_to_bibtex, authors_and_editors,
                     item_to_bibtex)

_ITEM_KEY = re.compile(r"^(?:\d+:)?([A-Z0-9]{8})$")
_SKIP_TYPES = {"attachment", "note", "annotation"}


class ZoteroLookupError(LookupError):
    pass


@dataclass
class AddResult:
    citekey: str
    zotero_key: str
    title: str
    existing: bool = False
    action: str = ""  # "added", "refreshed" (entry in zotero.bib rewritten), "found" (kept), "dry-run"
    bib_path: Path | None = None
    pdf_path: Path | None = None
    pdf_status: str = ""  # "copied", "present", "none", "not-pdf", "failed"
    notes: list[str] = field(default_factory=list)
    library: str = "user"


# ---------------------------------------------------------------------------
# Finding the item
# ---------------------------------------------------------------------------

def item_citekey(data: dict[str, Any]) -> str:
    """The item's own citekey: Zotero 7's field, else Better BibTeX's line in Extra."""
    if data.get("citationKey"):
        return str(data["citationKey"])
    m = re.search(r"^Citation Key:\s*(\S+)", data.get("extra") or "", re.M | re.I)
    return m.group(1) if m else ""


def record_from_item(item: dict[str, Any]) -> IngestRecord:
    data = item.get("data", item)
    authors, editors = authors_and_editors(data)
    return IngestRecord(
        source_type="zotero",
        source_ref=str(data.get("key") or ""),
        entry_type=_zotero_type_to_bibtex(data.get("itemType", "")),
        title=data.get("title") or None,
        authors=tuple(authors or editors),
        year=_extract_year(data),
        doi=normalize_doi(data.get("DOI") or _extra_doi(data)) or None,
        url=data.get("url") or None,
        journal=data.get("publicationTitle") or None,
        booktitle=data.get("proceedingsTitle") or data.get("bookTitle") or None,
        raw_id=str(data.get("key") or ""),
    )


def _extra_doi(data: dict[str, Any]) -> str:
    m = re.search(r"^DOI:\s*(\S+)", data.get("extra") or "", re.M | re.I)
    return m.group(1) if m else ""


def _top_level(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [it for it in items if it.get("data", {}).get("itemType") not in _SKIP_TYPES]


def _search_terms(citekey: str) -> list[str]:
    """Quick-search terms likely to find a citekey's item: family name, then title words."""
    parts = citekey.split("_")
    terms = [parts[0].replace("-", " ")] if parts and parts[0] else []
    if len(parts) >= 3:
        words = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+", parts[2])
        if words:
            terms.append(" ".join(words))
    return terms


def _norm_title(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def find_items(zot: Any, ref: str) -> list[dict[str, Any]]:
    """Every top-level item one library has for an item key, a DOI, a citekey or a title."""
    ref = ref.strip().lstrip("@")
    m = _ITEM_KEY.match(ref)
    if m:
        try:
            item = zot.item(m.group(1))
        except Exception:  # noqa: BLE001  404 in this library
            return []
        if item.get("data", {}).get("itemType") in _SKIP_TYPES:
            parent = item["data"].get("parentItem")
            if not parent:
                raise ZoteroLookupError(f"{ref} is a standalone {item['data']['itemType']}, not a paper")
            item = zot.item(parent)
        return [item]

    doi = normalize_doi(ref)
    if doi.startswith("10."):
        return [it for it in _top_level(zot.items(q=doi, qmode="everything", limit=25))
                if normalize_doi(it["data"].get("DOI") or _extra_doi(it["data"])) == doi]

    if " " in ref:  # a title (or most of one)
        want = _norm_title(ref)
        words = [w for w in want.split() if len(w) > 3][:6] or want.split()[:6]
        found = _top_level(zot.items(q=" ".join(words), limit=50))
        return [it for it in found if want and (_norm_title(it["data"].get("title") or "").startswith(want)
                                                or _norm_title(it["data"].get("title") or "") == want)]

    for term in _search_terms(ref):
        found = _top_level(zot.items(q=term, limit=100))
        hits = [it for it in found if item_citekey(it["data"]) == ref]
        if not hits:  # biblio's own convention, e.g. a key copied from a pool
            hits = [it for it in found if canonical_citekey_str(record_from_item(it)) == ref]
        if hits:
            return hits
    return []


def find_item(zot: Any, ref: str) -> dict[str, Any]:
    """One top-level Zotero item for an item key, a DOI, a citekey or a title."""
    return _one(find_items(zot, ref), ref)


def _one(hits: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    if not hits:
        raise ZoteroLookupError(f"no Zotero item found for {ref!r}")
    keys = {it["data"]["key"] for it in hits}
    if len(keys) > 1:
        listing = ", ".join(f"{it['data']['key']} ({(it['data'].get('title') or '')[:50]})" for it in hits)
        raise ZoteroLookupError(f"{ref!r} matches {len(keys)} items, pass an item key: {listing}")
    return hits[0]


@dataclass
class Library:
    label: str          # "user" or "group:<id> (<name>)"
    zot: Any


def open_libraries(zotero_cfg: ZoteroConfig, which: str = "all", client_cls: Any = None) -> list[Library]:
    """The libraries to search: ``user``, ``group:<id>`` or ``all`` (the user's, then every group).

    The local API serves group libraries too (Zotero 7); a group that cannot
    be opened is skipped.
    """
    import dataclasses
    client_cls = client_cls or ZoteroClient
    base = client_cls(zotero_cfg)
    own = "user" if zotero_cfg.library_type == "user" else f"group:{zotero_cfg.library_id}"
    which = (which or "all").strip()
    if which.startswith("group:"):
        gid = which.split(":", 1)[1]
        cfg = dataclasses.replace(zotero_cfg, library_id=gid, library_type="group")
        return [Library(f"group:{gid}", client_cls(cfg)._zot)]
    libs = [Library(own, base._zot)]
    if which == "all" and zotero_cfg.library_type == "user":
        try:
            groups = base._zot.groups() or []
        except Exception:  # noqa: BLE001  no group access
            groups = []
        for g in groups:
            gid = str(g.get("id") or g.get("data", {}).get("id") or "")
            if not gid:
                continue
            name = (g.get("data") or {}).get("name") or ""
            cfg = dataclasses.replace(zotero_cfg, library_id=gid, library_type="group")
            libs.append(Library(f"group:{gid}" + (f" ({name})" if name else ""), client_cls(cfg)._zot))
    return libs


def _paper_id(item: dict[str, Any]) -> str:
    d = item.get("data", item)
    return normalize_doi(d.get("DOI") or _extra_doi(d)) or _norm_title(d.get("title") or "")


def _best_pdf_rank(zot: Any, item_key: str, local: bool = False) -> tuple:
    try:
        atts = _pdf_attachments(zot.children(item_key))
    except Exception:  # noqa: BLE001
        return (9,)
    if not atts:
        return (9,)
    if local:  # a PDF on disk in Zotero's storage beats one Zotero only knows about (R52)
        return min((not _on_disk(a["data"]["key"]), *_pdf_rank(a)) for a in atts)
    return _pdf_rank(atts[0])


def local_sqlite_keys_for_doi(doi: str) -> list[str]:
    """Item keys holding ``doi`` in the Zotero app's own database on this machine (read-only).

    The fallback when the local API's quick search does not find a DOI (R52).
    """
    from .refs import HoldingIndex, _add_zotero_sqlite

    keys: list[str] = []
    for storage in zotero_storage_dirs():
        db = storage.parent / "zotero.sqlite"
        if not db.is_file():
            continue
        index = HoldingIndex()
        try:
            _add_zotero_sqlite(index, db)
        except Exception:  # noqa: BLE001  locked or another schema: the API result stands
            continue
        keys += [h.key.split(":", 1)[-1] for h in index.match_doi(doi) if h.key.split(":", 1)[-1] not in keys]
    return keys


def resolve_item(libs: list[Library], ref: str, *, local: bool = False) -> tuple[dict[str, Any], Library, list[str]]:
    """The item for ``ref`` across libraries, and notes on the duplicates passed over (R27).

    Items for the same paper (DOI, else title) are duplicates: the one with a
    stored PDF wins (with ``local``, a PDF on disk; the user's library first on
    a tie). Different papers are an error that lists them. With ``local`` a DOI
    the API search misses is looked up in ``zotero.sqlite``.
    """
    hits: list[tuple[dict[str, Any], Library]] = []

    def collect(r: str) -> None:
        for lib in libs:
            try:
                hits.extend((it, lib) for it in find_items(lib.zot, r)
                            if it["data"]["key"] not in {h["data"]["key"] for h, _ in hits})
            except ZoteroLookupError:
                raise
            except Exception:  # noqa: BLE001  one library unreachable: try the others
                continue

    collect(ref)
    doi = normalize_doi(ref.strip().lstrip("@"))
    if not hits and local and doi.startswith("10."):
        for key in local_sqlite_keys_for_doi(doi):
            collect(key)
    if not hits:
        where = ", ".join(lib.label for lib in libs)
        raise ZoteroLookupError(f"no Zotero item found for {ref!r} (searched {where})")
    if len({_paper_id(it) for it, _ in hits}) > 1:
        listing = ", ".join(f"{lib.label} {it['data']['key']} ({(it['data'].get('title') or '')[:50]})"
                            for it, lib in hits)
        raise ZoteroLookupError(f"{ref!r} matches {len(hits)} different papers, pass an item key: {listing}")
    if len(hits) == 1:
        return hits[0][0], hits[0][1], []
    ranked = sorted(((_best_pdf_rank(lib.zot, it["data"]["key"], local), i, it, lib)
                     for i, (it, lib) in enumerate(hits)),
                    key=lambda r: (r[0], r[1]))
    _, _, item, lib = ranked[0]
    def pdf_word(rank: tuple) -> str:
        if rank == (9,):
            return "no PDF"
        return "PDF not on disk" if local and rank[0] else "PDF"

    others = [f"duplicate {o_lib.label} {o_it['data']['key']} ({pdf_word(rank)}) not used"
              for rank, _, o_it, o_lib in ranked[1:]]
    return item, lib, others


# ---------------------------------------------------------------------------
# Writing it into the project
# ---------------------------------------------------------------------------

def _existing_key(cfg: BiblioConfig, citekey: str, doi: str | None) -> str | None:
    for bib in _project_bibs(cfg):
        for r in _bib_records(bib):
            if r["key"] == citekey or (doi and r["doi"] == doi):
                return r["key"]
    return None


def entry_for(item: dict[str, Any], citekey: str) -> str:
    bib = item_to_bibtex(item)
    if bib is None:
        raise ZoteroLookupError("item has no bibliographic data")
    head, _, rest = bib.partition(",\n")
    head = re.sub(r"\{[^,]*$", "{" + citekey, head)
    zkey = item.get("data", {}).get("key", "")
    return f"{head},\n  zotero = {{{zkey}}},\n{rest}"


def upsert_entry(bib_path: Path, citekey: str, entry: str) -> None:
    """Add or replace one entry in a .bib file, keeping the others byte for byte."""
    bib_path.parent.mkdir(parents=True, exist_ok=True)
    text = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
    blocks = [b.strip() for b in re.split(r"\n(?=@)", text) if b.strip()]
    pat = re.compile(r"@\w+\{\s*" + re.escape(citekey) + r"\s*,")
    blocks = [b for b in blocks if not pat.match(b)] + [entry.strip()]
    bib_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


_SUPPLEMENT = re.compile(r"\b(supp|supplement(ary)?|appendix|extended data|SI)\b", re.I)
_NOT_FINAL = re.compile(r"\b(accepted|submitted|author)\b.*\bversion\b|\bpre-?print\b|\bmanuscript\b", re.I)


def _pdf_rank(att: dict[str, Any]) -> tuple[int, int, int]:
    """Lower is better: a stored file, the main text, the published version."""
    d = att["data"]
    title = f"{d.get('title') or ''} {d.get('filename') or ''}"
    return (d.get("linkMode") != "imported_file", bool(_SUPPLEMENT.search(title)), bool(_NOT_FINAL.search(title)))


def _pdf_attachments(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pdfs = [c for c in children if c.get("data", {}).get("itemType") == "attachment"
            and c["data"].get("contentType") == "application/pdf"]
    return sorted(pdfs, key=_pdf_rank)  # stable: Zotero's order breaks ties


def zotero_storage_dirs() -> list[Path]:
    """Where the Zotero app keeps attachment files on this machine (``storage/<attachment key>/``)."""
    import os
    homes = [os.environ.get("ZOTERO_DATA_DIR", ""), "~/Zotero", "~/snap/zotero-snap/common/Zotero",
             "~/.zotero/zotero"]
    return [Path(h).expanduser() / "storage" for h in homes if h and (Path(h).expanduser() / "storage").is_dir()]


def _storage_pdf(att_key: str) -> bytes | None:
    for root in zotero_storage_dirs():
        for pdf in sorted((root / att_key).glob("*.pdf")):
            data = pdf.read_bytes()
            if data[:5] == b"%PDF-":
                return data
    return None


def _on_disk(att_key: str) -> bool:
    return any(any((root / att_key).glob("*.pdf")) for root in zotero_storage_dirs())


def _from_storage(att_key: str, dest: Path) -> bool:
    data = _storage_pdf(att_key)
    if data is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def _signature(text: str) -> str:
    """Letters and digits only, lower case, accents dropped: hyphenation and line breaks vanish."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text.lower() if ch.isascii() and ch.isalnum())


def first_page_text(pdf: bytes) -> str | None:
    """Text of page 1 via poppler's pdftotext; None when it is not installed or fails."""
    import shutil
    import subprocess
    import tempfile
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf)
        tmp.flush()
        try:
            out = subprocess.run([exe, "-q", "-f", "1", "-l", "1", tmp.name, "-"], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


def title_on_first_page(pdf: bytes, title: str, *, words: int = 6) -> bool | None:
    """Do the title's first ``words`` words appear on the PDF's first page? None when it cannot tell.

    lit-studio's rule (R52): the opening six words, letters and digits only,
    hyphenation joined, separated eight papers cleanly where a looser
    "most title words on pages 1-2" did not.
    """
    tokens = re.findall(r"[^\W_]+", re.sub(r"(\w)-\s*(\w)", r"\1\2", title or ""))
    want = _signature("".join(tokens[:words]))
    if len(want) < 8:
        return None                       # too short to tell papers apart
    text = first_page_text(pdf)
    if text is None:
        return None
    return want in _signature(text)


def fetch_pdf_checked(zot: Any, item_key: str, dest: Path, *, local: bool = False,
                      title: str | None = None) -> tuple[str, str | None]:
    """Copy the item's best PDF to ``dest``; returns (status, note).

    With ``local`` the Zotero storage folder is the fallback. With ``title``
    each candidate's first page must show the title's opening words: the first
    that does is written; when none does, the best candidate is written and
    the note says so (book chapters often lack the title on page 1).
    """
    try:
        attachments = _pdf_attachments(zot.children(item_key))
    except Exception:  # noqa: BLE001
        return "failed", None
    if not attachments:
        return "none", None
    if local:
        attachments = sorted(attachments, key=lambda a: not _on_disk(a["data"]["key"]))  # stable
    status = "failed"
    fallback: tuple[str, bytes] | None = None
    checked = 0
    for att in attachments:
        key = att["data"]["key"]
        try:
            content = zot.file(key)
        except Exception:  # noqa: BLE001
            content = None
        if not (isinstance(content, (bytes, bytearray)) and content[:5] == b"%PDF-"):
            if content:
                status = "not-pdf"
            # Both imported modes keep a copy in storage/<attachment key>/ (imported_url:
            # saved from a web page by the Connector); linked files and URLs do not.
            content = _storage_pdf(key) if local and att["data"].get("linkMode") in (
                "imported_file", "imported_url") else None
        if content is None:
            continue
        verdict = title_on_first_page(bytes(content), title) if title else None
        if verdict is False:
            checked += 1
            fallback = fallback or (key, bytes(content))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return "copied", None
    if fallback is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fallback[1])
        which = "the PDF" if checked == 1 else f"any of {checked} PDFs"
        return "copied", (f"title not found on the first page of {which} (attachment {fallback[0]} written): "
                          "check it is this paper; book chapters often fail this check")
    return status, None


def fetch_pdf(zot: Any, item_key: str, dest: Path, *, local: bool = False, title: str | None = None) -> str:
    """Copy the item's best PDF to ``dest``; with ``local`` the Zotero storage folder is the fallback."""
    return fetch_pdf_checked(zot, item_key, dest, local=local, title=title)[0]


def add_from_zotero(
    cfg: BiblioConfig,
    zotero_cfg: ZoteroConfig,
    ref: str,
    *,
    dry_run: bool = False,
    client: ZoteroClient | None = None,
    libraries: list[Library] | None = None,
    version: str | None = None,
) -> AddResult:
    if libraries is None:
        client = client or ZoteroClient(zotero_cfg)
        libraries = [Library("user" if zotero_cfg.library_type == "user" else f"group:{zotero_cfg.library_id}",
                             client._zot)]
    item, lib, duplicates = resolve_item(libraries, ref, local=zotero_cfg.local)
    zot = lib.zot
    data = item["data"]
    record = record_from_item(item)
    citekey = canonical_citekey_str(record)
    zotero_bib = cfg.bibtex_merge.src_dir / "zotero.bib"
    own_key = next((r["key"] for r in (_bib_records(zotero_bib) if zotero_bib.is_file() else [])
                    if r["key"] == citekey or (record.doi and r["doi"] == record.doi)), None)
    # an entry this command (or `zotero pull`) wrote is refreshed under its key; one from elsewhere is kept
    if own_key:
        citekey = own_key
    existing = None if own_key else _existing_key(cfg, citekey, record.doi)
    result = AddResult(citekey=existing or citekey, zotero_key=data["key"], title=data.get("title") or "",
                       existing=existing is not None, library=lib.label)
    result.notes.extend(duplicates)
    own = item_citekey(data)
    if own and own != result.citekey:
        result.notes.append(f"Zotero calls it {own}; biblio uses {result.citekey}")

    if version:
        # a second text of a paper already held (R38): its PDF under <key>@<version>, the entry untouched
        if not result.existing and not own_key:
            raise ZoteroLookupError(f"{ref!r} is not in the project yet; add it first, then its other version")
        version = re.sub(r"[^\w.-]+", "-", version.strip()).strip("-") or "v2"
        result.citekey = f"{result.citekey}@{version}"
    pdf_path = cfg.pdf_root / cfg.pdf_pattern.format(citekey=result.citekey)
    result.pdf_path = pdf_path
    if dry_run:
        result.action = "dry-run"
        result.pdf_status = "present" if pdf_path.is_file() else "dry-run"
        return result

    if version:
        result.action = "version"
    elif result.existing:
        result.action = "found"
    else:
        result.action = "refreshed" if own_key else "added"
        result.bib_path = zotero_bib
        upsert_entry(result.bib_path, citekey, entry_for(item, citekey))
    if pdf_path.is_file():
        result.pdf_status = "present"
    else:
        result.pdf_status, title_note = fetch_pdf_checked(zot, data["key"], pdf_path, local=zotero_cfg.local,
                                                          title=data.get("title") or "")
        if title_note:
            result.notes.append(title_note)
    if result.pdf_status in ("none", "failed", "not-pdf"):
        result.notes.append({
            "none": "no PDF attached in Zotero",
            "failed": "PDF could not be downloaded (web API: is the file synced to zotero.org?)",
            "not-pdf": "attachment is not a PDF",
        }[result.pdf_status])

    append_jsonl(cfg.repo_root / ".projio" / "biblio" / "logs" / "runs" / "zotero_sync.jsonl", {
        "run_id": new_run_id("zotero_add"),
        "timestamp": utc_now_iso(),
        "stage": "zotero_add",
        "status": "success",
        "zotero_key": result.zotero_key,
        "library": result.library,
        "citekey": result.citekey,
        "action": result.action,
        "pdf": result.pdf_status,
        "local": zotero_cfg.local,
    })
    return result


def local_config(zotero_cfg: ZoteroConfig | None, repo_root: Path) -> ZoteroConfig:
    """The local API's view of the personal library (user id 0), or the configured group."""
    if zotero_cfg is not None:
        library_id = zotero_cfg.library_id if zotero_cfg.library_type == "group" else "0"
        return ZoteroConfig(library_id=library_id, library_type=zotero_cfg.library_type, api_key=None,
                            local=True, collection=None, tags_filter=None,
                            citekey_mode=zotero_cfg.citekey_mode, sync_state_path=zotero_cfg.sync_state_path)
    return ZoteroConfig(library_id="0", library_type="user", api_key=None, local=True, collection=None,
                        tags_filter=None, citekey_mode="biblio",
                        sync_state_path=repo_root / ".projio" / "biblio" / "zotero_sync.yml")
