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


def find_item(zot: Any, ref: str) -> dict[str, Any]:
    """One top-level Zotero item for an item key, a DOI, or a citekey."""
    ref = ref.strip().lstrip("@")
    m = _ITEM_KEY.match(ref)
    if m:
        item = zot.item(m.group(1))
        if item.get("data", {}).get("itemType") in _SKIP_TYPES:
            parent = item["data"].get("parentItem")
            if not parent:
                raise ZoteroLookupError(f"{ref} is a standalone {item['data']['itemType']}, not a paper")
            item = zot.item(parent)
        return item

    doi = normalize_doi(ref)
    if doi.startswith("10."):
        hits = [it for it in _top_level(zot.items(q=doi, qmode="everything", limit=25))
                if normalize_doi(it["data"].get("DOI") or _extra_doi(it["data"])) == doi]
        return _one(hits, ref)

    for term in _search_terms(ref):
        found = _top_level(zot.items(q=term, limit=100))
        hits = [it for it in found if item_citekey(it["data"]) == ref]
        if not hits:  # biblio's own convention, e.g. a key copied from a pool
            hits = [it for it in found if canonical_citekey_str(record_from_item(it)) == ref]
        if hits:
            return _one(hits, ref)
    raise ZoteroLookupError(f"no Zotero item found for {ref!r}")


def _one(hits: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    if not hits:
        raise ZoteroLookupError(f"no Zotero item found for {ref!r}")
    keys = {it["data"]["key"] for it in hits}
    if len(keys) > 1:
        listing = ", ".join(f"{it['data']['key']} ({(it['data'].get('title') or '')[:50]})" for it in hits)
        raise ZoteroLookupError(f"{ref!r} matches {len(keys)} items, pass an item key: {listing}")
    return hits[0]


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


def fetch_pdf(zot: Any, item_key: str, dest: Path) -> str:
    try:
        attachments = _pdf_attachments(zot.children(item_key))
    except Exception:  # noqa: BLE001
        return "failed"
    if not attachments:
        return "none"
    for att in attachments:
        try:
            content = zot.file(att["data"]["key"])
        except Exception:  # noqa: BLE001
            continue
        if isinstance(content, (bytes, bytearray)) and content[:5] == b"%PDF-":
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            return "copied"
        if content:
            return "not-pdf"
    return "failed"


def add_from_zotero(
    cfg: BiblioConfig,
    zotero_cfg: ZoteroConfig,
    ref: str,
    *,
    dry_run: bool = False,
    client: ZoteroClient | None = None,
) -> AddResult:
    client = client or ZoteroClient(zotero_cfg)
    zot = client._zot
    item = find_item(zot, ref)
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
                       existing=existing is not None)
    own = item_citekey(data)
    if own and own != result.citekey:
        result.notes.append(f"Zotero calls it {own}; biblio uses {result.citekey}")

    pdf_path = cfg.pdf_root / cfg.pdf_pattern.format(citekey=result.citekey)
    result.pdf_path = pdf_path
    if dry_run:
        result.action = "dry-run"
        result.pdf_status = "present" if pdf_path.is_file() else "dry-run"
        return result

    if result.existing:
        result.action = "found"
    else:
        result.action = "refreshed" if own_key else "added"
        result.bib_path = zotero_bib
        upsert_entry(result.bib_path, citekey, entry_for(item, citekey))
    result.pdf_status = "present" if pdf_path.is_file() else fetch_pdf(zot, data["key"], pdf_path)
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
