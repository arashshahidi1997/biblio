"""Zotero integration — pull and push-back with incremental sync.

Depends on pyzotero (optional). Import guarded so the rest of biblio works without it.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .ledger import append_jsonl, new_run_id, utc_now_iso

try:
    from pyzotero import zotero as pyzotero_client

    HAS_PYZOTERO = True
except ImportError:  # pragma: no cover
    pyzotero_client = None  # type: ignore[assignment]
    HAS_PYZOTERO = False


def _require_pyzotero() -> None:
    if not HAS_PYZOTERO:
        raise ImportError(
            "pyzotero is required for Zotero integration. "
            "Install with: pip install 'biblio-tools[zotero]'"
        )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ZoteroConfig:
    """Zotero section of biblio.yml."""

    library_id: str
    library_type: str  # "user" or "group"
    api_key: str | None
    local: bool
    collection: str | None
    tags_filter: list[str] | None
    citekey_mode: str  # "zotero" or "biblio"
    sync_state_path: Path


def load_zotero_config(
    payload: dict[str, Any],
    repo_root: Path,
) -> ZoteroConfig | None:
    """Extract the ``zotero`` section from the merged biblio config payload.

    Returns *None* if the section is absent or has no ``library_id``.
    """
    raw = payload.get("zotero")
    if not isinstance(raw, dict):
        return None
    library_id = raw.get("library_id")
    if not library_id:
        return None

    api_key = raw.get("api_key") or os.environ.get("BIBLIO_ZOTERO_API_KEY")
    sync_rel = raw.get("sync_state", ".projio/biblio/zotero_sync.yml")
    sync_path = (repo_root / sync_rel).resolve()

    return ZoteroConfig(
        library_id=str(library_id),
        library_type=str(raw.get("library_type", "user")),
        api_key=api_key,
        local=bool(raw.get("local", False)),
        collection=raw.get("collection") or None,
        tags_filter=raw.get("tags_filter") or None,
        citekey_mode=str(raw.get("citekey_mode", "zotero")),
        sync_state_path=sync_path,
    )


# ---------------------------------------------------------------------------
# Sync state
# ---------------------------------------------------------------------------

@dataclass
class SyncState:
    """Persistent sync state stored in zotero_sync.yml."""

    last_version: int = 0
    last_sync: str = ""
    library_id: str = ""
    library_type: str = "user"
    collection: str | None = None
    item_map: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> SyncState:
        if not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            last_version=int(raw.get("last_version", 0)),
            last_sync=str(raw.get("last_sync", "")),
            library_id=str(raw.get("library_id", "")),
            library_type=str(raw.get("library_type", "user")),
            collection=raw.get("collection"),
            item_map=raw.get("item_map") or {},
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_version": self.last_version,
            "last_sync": self.last_sync,
            "library_id": self.library_id,
            "library_type": self.library_type,
            "collection": self.collection,
            "item_map": self.item_map,
        }
        path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Zotero client wrapper
# ---------------------------------------------------------------------------

class ZoteroClient:
    """Thin wrapper around pyzotero.Zotero for biblio integration."""

    def __init__(self, cfg: ZoteroConfig) -> None:
        _require_pyzotero()
        self.cfg = cfg
        if cfg.local:
            # Zotero 7 local API — no API key needed
            self._zot = pyzotero_client.Zotero(
                cfg.library_id, cfg.library_type,
            )
        else:
            if not cfg.api_key:
                raise ValueError(
                    "Zotero API key required. Set BIBLIO_ZOTERO_API_KEY env var "
                    "or zotero.api_key in biblio.yml."
                )
            self._zot = pyzotero_client.Zotero(
                cfg.library_id, cfg.library_type, cfg.api_key,
            )

    def item_versions(self, since: int = 0) -> dict[str, int]:
        """Return {item_key: version} for items changed since *since*."""
        if self.cfg.collection:
            # Zotero filters collections via URL path, not query param;
            # /items?collection=KEY is silently ignored. Use the path form.
            return self._zot.collection_items(
                self.cfg.collection, format="versions", since=since,
            )
        return self._zot.item_versions(since=since)

    def fetch_items(self, keys: list[str]) -> list[dict[str, Any]]:
        """Fetch full JSON items for the given keys."""
        if not keys:
            return []
        # pyzotero has a 50-key limit per request
        items: list[dict[str, Any]] = []
        for i in range(0, len(keys), 50):
            batch = keys[i : i + 50]
            items.extend(self._zot.items(itemKey=",".join(batch)))
        return items

    def fetch_bibtex(self) -> str:
        """Fetch the entire library (or collection) as BibTeX."""
        if self.cfg.collection:
            return self._zot.collection_items(
                self.cfg.collection, format="bibtex",
            )
        return self._zot.items(format="bibtex")

    def deleted_since(self, since: int) -> list[str]:
        """Return item keys deleted since version *since*."""
        result = self._zot.deleted(since=since)
        if isinstance(result, dict):
            return result.get("items", [])
        return []

    def fetch_attachment(self, attachment_key: str) -> bytes | None:
        """Download the binary content of an attachment."""
        try:
            return self._zot.file(attachment_key)
        except Exception:
            return None

    def children(self, item_key: str) -> list[dict[str, Any]]:
        """Return child items (attachments, notes) for an item."""
        return self._zot.children(item_key)

    def update_item(self, item: dict[str, Any]) -> bool:
        """Update an existing Zotero item. Returns True on success."""
        try:
            self._zot.update_item(item)
            return True
        except Exception:
            return False

    def create_note(
        self, parent_key: str, html_content: str, tags: list[dict[str, str]] | None = None,
    ) -> str | None:
        """Create a child note item under *parent_key*. Returns the new note key."""
        note_template = self._zot.item_template("note")
        note_template["note"] = html_content
        note_template["parentItem"] = parent_key
        if tags:
            note_template["tags"] = tags
        try:
            resp = self._zot.create_items([note_template])
            # pyzotero returns {"successful": {"0": {...}}, ...}
            successful = resp.get("successful", {}) if isinstance(resp, dict) else {}
            if successful:
                first = next(iter(successful.values()))
                return first.get("key") if isinstance(first, dict) else None
            return None
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZOTERO_TO_BIBTEX_TYPE: dict[str, str] = {
    "journalArticle": "article",
    "book": "book",
    "bookSection": "incollection",
    "conferencePaper": "inproceedings",
    "thesis": "phdthesis",
    "report": "techreport",
    "webpage": "misc",
    "preprint": "article",
    "manuscript": "unpublished",
    "presentation": "misc",
    "patent": "misc",
    "letter": "misc",
    "document": "misc",
}


def _zotero_type_to_bibtex(item_type: str) -> str:
    return _ZOTERO_TO_BIBTEX_TYPE.get(item_type, "misc")


def _extract_creators(item_data: dict[str, Any]) -> list[str]:
    """Extract author names from Zotero JSON item data."""
    creators = item_data.get("creators", [])
    names: list[str] = []
    for c in creators:
        if c.get("creatorType") not in ("author", "editor"):
            continue
        first = c.get("firstName", "")
        last = c.get("lastName", "")
        name = c.get("name", "")  # single-field name
        if name:
            names.append(name)
        elif last:
            names.append(f"{last}, {first}".strip(", "))
    return names


def _extract_year(item_data: dict[str, Any]) -> str | None:
    date_str = item_data.get("date", "")
    if not date_str:
        return None
    match = re.search(r"\b(\d{4})\b", date_str)
    return match.group(1) if match else None


def _bibtex_escape(value: str) -> str:
    """Minimal BibTeX escaping."""
    return value.replace("{", r"\{").replace("}", r"\}")


def _make_citekey_from_bibtex(bibtex_block: str) -> str | None:
    """Extract the citekey from a single @type{key, block."""
    match = re.match(r"@\w+\{([^,]+),", bibtex_block.strip())
    return match.group(1).strip() if match else None


def item_to_bibtex(item: dict[str, Any]) -> str | None:
    """Convert a Zotero JSON item to a BibTeX entry string.

    Used as fallback when BibTeX export from Zotero fails.
    """
    data = item.get("data", item)
    item_type = data.get("itemType", "")
    if item_type in ("attachment", "note", "annotation"):
        return None

    bib_type = _zotero_type_to_bibtex(item_type)
    authors = _extract_creators(data)
    year = _extract_year(data)
    title = data.get("title", "")
    doi = data.get("DOI", "")
    url = data.get("url", "")
    journal = data.get("publicationTitle", "")
    booktitle = data.get("proceedingsTitle", "") or data.get("bookTitle", "")
    volume = data.get("volume", "")
    issue = data.get("issue", "")
    pages = data.get("pages", "")
    publisher = data.get("publisher", "")
    abstract_text = data.get("abstractNote", "")

    # Build citekey: first_author_year_TitleWord
    first_author = ""
    if authors:
        parts = authors[0].split(",")
        first_author = parts[0].strip().split()[-1] if parts else "Unknown"
    else:
        first_author = "Unknown"
    year_str = year or "XXXX"
    title_word = ""
    if title:
        words = re.findall(r"[A-Za-z]+", title)
        stop = {"a", "an", "the", "of", "in", "on", "for", "and", "to", "with", "from"}
        significant = [w for w in words if w.lower() not in stop]
        if significant:
            title_word = significant[0].capitalize()
        elif words:
            title_word = words[0].capitalize()
    citekey = f"{first_author}_{year_str}_{title_word}"

    fields: list[str] = []
    if title:
        fields.append(f"  title = {{{_bibtex_escape(title)}}}")
    if authors:
        fields.append(f"  author = {{{' and '.join(authors)}}}")
    if year:
        fields.append(f"  year = {{{year}}}")
    if doi:
        fields.append(f"  doi = {{{doi}}}")
    if url:
        fields.append(f"  url = {{{url}}}")
    if journal:
        fields.append(f"  journal = {{{_bibtex_escape(journal)}}}")
    if booktitle:
        fields.append(f"  booktitle = {{{_bibtex_escape(booktitle)}}}")
    if volume:
        fields.append(f"  volume = {{{volume}}}")
    if issue:
        fields.append(f"  number = {{{issue}}}")
    if pages:
        fields.append(f"  pages = {{{pages}}}")
    if publisher:
        fields.append(f"  publisher = {{{_bibtex_escape(publisher)}}}")
    if abstract_text:
        fields.append(f"  abstract = {{{_bibtex_escape(abstract_text)}}}")

    body = ",\n".join(fields)
    return f"@{bib_type}{{{citekey},\n{body}\n}}"


# ---------------------------------------------------------------------------
# Pull result
# ---------------------------------------------------------------------------

@dataclass
class ZoteroPullResult:
    """Result of a zotero pull operation."""

    pulled: int = 0
    skipped: int = 0
    deleted: int = 0
    pdfs_downloaded: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    citekeys: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pull orchestrator
# ---------------------------------------------------------------------------

def pull(
    *,
    repo_root: Path,
    zotero_cfg: ZoteroConfig,
    collection: str | None = None,
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> ZoteroPullResult:
    """Pull items and PDFs from Zotero into the biblio workspace.

    Steps:
    1. Read sync state
    2. Fetch changed item versions
    3. Fetch full items for changed keys
    4. Write BibTeX to bib/srcbib/zotero.bib
    5. Download PDFs for items with attachments
    6. Update sync state
    7. Log the operation
    """
    _require_pyzotero()
    result = ZoteroPullResult(dry_run=dry_run)

    # Override collection from argument if provided
    if collection:
        zotero_cfg = ZoteroConfig(
            library_id=zotero_cfg.library_id,
            library_type=zotero_cfg.library_type,
            api_key=zotero_cfg.api_key,
            local=zotero_cfg.local,
            collection=collection,
            tags_filter=tags or zotero_cfg.tags_filter,
            citekey_mode=zotero_cfg.citekey_mode,
            sync_state_path=zotero_cfg.sync_state_path,
        )

    client = ZoteroClient(zotero_cfg)
    state = SyncState.load(zotero_cfg.sync_state_path)

    # 1. Fetch changed item versions
    changed_versions = client.item_versions(since=state.last_version)
    if not changed_versions and state.last_version > 0:
        # Check for deletions even when no changes
        deleted_keys = client.deleted_since(state.last_version)
        if deleted_keys and not dry_run:
            _handle_deletions(deleted_keys, state, repo_root)
            result.deleted = len(deleted_keys)
            state.last_sync = utc_now_iso()
            state.save(zotero_cfg.sync_state_path)
        return result

    # 2. Compute new library version (max of all returned versions)
    new_version = max(changed_versions.values()) if changed_versions else state.last_version

    # 3. Fetch full items
    changed_keys = list(changed_versions.keys())
    items = client.fetch_items(changed_keys)

    # Filter to top-level items (skip attachments, notes, annotations)
    top_items = [
        it for it in items
        if it.get("data", {}).get("itemType") not in ("attachment", "note", "annotation")
    ]

    # 4. Apply tags filter if configured
    if zotero_cfg.tags_filter:
        tag_set = set(zotero_cfg.tags_filter)
        filtered = []
        for it in top_items:
            item_tags = {t.get("tag", "") for t in it.get("data", {}).get("tags", [])}
            if item_tags & tag_set:
                filtered.append(it)
        top_items = filtered

    # 5. Generate BibTeX
    bib_entries: list[str] = []
    item_citekey_map: dict[str, str] = {}  # zotero_key -> citekey

    for it in top_items:
        data = it.get("data", {})
        zotero_key = data.get("key", it.get("key", ""))

        # Try to generate BibTeX from item data
        bib_str = item_to_bibtex(it)
        if not bib_str:
            result.skipped += 1
            continue

        citekey = _make_citekey_from_bibtex(bib_str)
        if not citekey:
            result.skipped += 1
            continue

        bib_entries.append(bib_str)
        item_citekey_map[zotero_key] = citekey
        result.citekeys.append(citekey)
        result.pulled += 1

    if dry_run:
        return result

    # 6. Write BibTeX to bib/srcbib/zotero.bib
    if bib_entries:
        _write_zotero_bib(repo_root, bib_entries, state, item_citekey_map)

    # 7. Download PDFs
    pdf_root = repo_root / "bib" / "articles"
    for it in top_items:
        data = it.get("data", {})
        zotero_key = data.get("key", it.get("key", ""))
        citekey = item_citekey_map.get(zotero_key)
        if not citekey:
            continue

        pdf_dir = pdf_root / citekey
        pdf_path = pdf_dir / f"{citekey}.pdf"
        if pdf_path.exists():
            continue

        # Fetch child attachments to find PDFs
        try:
            children = client.children(zotero_key)
        except Exception:
            continue

        for child in children:
            child_data = child.get("data", {})
            if child_data.get("contentType") != "application/pdf":
                continue
            child_key = child_data.get("key", child.get("key", ""))
            content = client.fetch_attachment(child_key)
            if content:
                pdf_dir.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(content)
                result.pdfs_downloaded += 1
                break

    # 8. Handle deletions
    if state.last_version > 0:
        deleted_keys = client.deleted_since(state.last_version)
        if deleted_keys:
            _handle_deletions(deleted_keys, state, repo_root)
            result.deleted = len(deleted_keys)

    # 9. Update sync state
    for zkey, ckey in item_citekey_map.items():
        state.item_map[zkey] = {
            "version": changed_versions.get(zkey, new_version),
            "citekey": ckey,
            "has_pdf": (pdf_root / ckey / f"{ckey}.pdf").exists(),
        }
    state.last_version = new_version
    state.last_sync = utc_now_iso()
    state.library_id = zotero_cfg.library_id
    state.library_type = zotero_cfg.library_type
    state.collection = zotero_cfg.collection
    state.save(zotero_cfg.sync_state_path)

    # 10. Log
    log_path = repo_root / ".projio" / "biblio" / "logs" / "runs" / "zotero_sync.jsonl"
    append_jsonl(log_path, {
        "run_id": new_run_id("zotero_pull"),
        "timestamp": utc_now_iso(),
        "stage": "zotero_pull",
        "status": "success",
        "pulled": result.pulled,
        "skipped": result.skipped,
        "deleted": result.deleted,
        "pdfs_downloaded": result.pdfs_downloaded,
        "errors": result.errors,
    })

    return result


def _write_zotero_bib(
    repo_root: Path,
    bib_entries: list[str],
    state: SyncState,
    new_map: dict[str, str],
) -> None:
    """Write (full replace) bib/srcbib/zotero.bib with all known entries.

    On incremental sync we merge new entries with existing ones from state.
    Zotero is authoritative for this file — full replace on each sync.
    """
    bib_path = repo_root / "bib" / "srcbib" / "zotero.bib"
    bib_path.parent.mkdir(parents=True, exist_ok=True)

    # For incremental: if there's an existing file and we only pulled a subset,
    # we need to merge. But spec says "full replace" — the new_entries represent
    # all changed items plus the unchanged ones remain from previous state.
    # On first sync, we write everything. On incremental, we read existing and
    # replace/add changed entries.
    existing_entries: dict[str, str] = {}
    if bib_path.exists():
        existing_text = bib_path.read_text(encoding="utf-8")
        # Parse existing entries by citekey
        for block in re.split(r"\n(?=@)", existing_text):
            block = block.strip()
            if not block:
                continue
            ck = _make_citekey_from_bibtex(block)
            if ck:
                existing_entries[ck] = block

    # Add/update new entries
    for entry in bib_entries:
        ck = _make_citekey_from_bibtex(entry)
        if ck:
            existing_entries[ck] = entry

    # Write all entries
    content = "\n\n".join(existing_entries.values())
    if content and not content.endswith("\n"):
        content += "\n"
    bib_path.write_text(content, encoding="utf-8")


def _handle_deletions(
    deleted_keys: list[str],
    state: SyncState,
    repo_root: Path,
) -> None:
    """Remove deleted items from zotero.bib and sync state."""
    # Find citekeys for deleted Zotero keys
    citekeys_to_remove: set[str] = set()
    for dkey in deleted_keys:
        entry = state.item_map.pop(dkey, None)
        if entry and "citekey" in entry:
            citekeys_to_remove.add(entry["citekey"])

    if not citekeys_to_remove:
        return

    # Remove from zotero.bib
    bib_path = repo_root / "bib" / "srcbib" / "zotero.bib"
    if not bib_path.exists():
        return

    text = bib_path.read_text(encoding="utf-8")
    remaining: list[str] = []
    for block in re.split(r"\n(?=@)", text):
        block = block.strip()
        if not block:
            continue
        ck = _make_citekey_from_bibtex(block)
        if ck and ck not in citekeys_to_remove:
            remaining.append(block)

    content = "\n\n".join(remaining)
    if content and not content.endswith("\n"):
        content += "\n"
    bib_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def status(*, zotero_cfg: ZoteroConfig) -> dict[str, Any]:
    """Return current sync state as a dict for display."""
    state = SyncState.load(zotero_cfg.sync_state_path)
    total_items = len(state.item_map)
    with_pdf = sum(1 for v in state.item_map.values() if v.get("has_pdf"))

    return {
        "library_id": state.library_id or zotero_cfg.library_id,
        "library_type": state.library_type or zotero_cfg.library_type,
        "collection": state.collection,
        "last_version": state.last_version,
        "last_sync": state.last_sync or "never",
        "total_items": total_items,
        "items_with_pdf": with_pdf,
        "sync_state_path": str(zotero_cfg.sync_state_path),
    }


# ---------------------------------------------------------------------------
# Push result
# ---------------------------------------------------------------------------

@dataclass
class ZoteroPushResult:
    """Result of a zotero push operation."""

    updated: int = 0
    created: int = 0
    skipped: int = 0
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Push helpers
# ---------------------------------------------------------------------------

_TAG_PREFIX = "biblio:"


def _collect_enrichment_tags(
    citekey: str,
    cfg: "BiblioConfig",
    library_entry: dict[str, Any],
) -> list[str]:
    """Collect all biblio-generated tags to push for a citekey.

    Sources: library.yml tags + status, autotag cache, concept cache.
    All prefixed with ``biblio:`` namespace.
    """
    from .autotag import load_cache as load_autotag_cache
    from .concepts import load_concepts

    tags: list[str] = []

    # Library status → biblio:status/<status>
    lib_status = library_entry.get("status")
    if lib_status:
        tags.append(f"{_TAG_PREFIX}status/{lib_status}")

    # Library tags → biblio:tag/<tag>
    lib_tags = library_entry.get("tags")
    if isinstance(lib_tags, list):
        for t in lib_tags:
            if isinstance(t, str) and t:
                tags.append(f"{_TAG_PREFIX}tag/{t}")

    # Autotag results → biblio:topic/<tag>
    at_cache = load_autotag_cache(cfg, citekey)
    if at_cache:
        for entry in at_cache.get("tags", []):
            tag_val = entry.get("tag", "") if isinstance(entry, dict) else str(entry)
            if tag_val:
                tags.append(f"{_TAG_PREFIX}topic/{tag_val}")

    # Concept categories → biblio:concept/<value>
    concepts = load_concepts(cfg, citekey)
    if concepts:
        for _cat, vals in concepts.items():
            for v in vals:
                if v:
                    tags.append(f"{_TAG_PREFIX}concept/{v}")

    return sorted(set(tags))


def _collect_extra_fields(
    citekey: str,
    cfg: "BiblioConfig",
    bib_entry: dict[str, Any] | None,
) -> dict[str, str]:
    """Collect DOI and OpenAlex ID to write to Zotero extra field."""
    fields: dict[str, str] = {}
    if bib_entry:
        doi = bib_entry.get("doi") or bib_entry.get("DOI")
        if doi:
            fields["DOI"] = str(doi)
        openalex_id = bib_entry.get("openalex") or bib_entry.get("openalex_id")
        if openalex_id:
            fields["OpenAlex"] = str(openalex_id)
    return fields


def _load_summary_html(citekey: str, cfg: "BiblioConfig") -> str | None:
    """Load a rendered summary as HTML for pushing as a Zotero note."""
    from .summarize import summary_path_for_key

    md_path = summary_path_for_key(cfg, citekey)
    if not md_path.exists():
        return None
    md_text = md_path.read_text(encoding="utf-8").strip()
    if not md_text:
        return None
    # Convert markdown to simple HTML (basic conversion)
    lines = md_text.split("\n")
    html_parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            html_parts.append(f"<h1>{stripped[2:]}</h1>")
        elif stripped.startswith("## "):
            html_parts.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("### "):
            html_parts.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("- "):
            html_parts.append(f"<li>{stripped[2:]}</li>")
        elif stripped:
            html_parts.append(f"<p>{stripped}</p>")
    return "\n".join(html_parts) if html_parts else None


def _has_biblio_note(children: list[dict[str, Any]], summary_html: str) -> bool:
    """Check if a child note with the same biblio summary already exists."""
    for child in children:
        data = child.get("data", {})
        if data.get("itemType") != "note":
            continue
        note_text = data.get("note", "")
        # Check if note starts with our marker
        if "[biblio summary]" in note_text:
            return True
    return False


def _update_extra_field(existing_extra: str, key: str, value: str) -> str:
    """Add or skip a key: value line in the Zotero extra field."""
    lines = existing_extra.split("\n") if existing_extra else []
    # Check if key already present
    prefix = f"{key}:"
    for line in lines:
        if line.strip().startswith(prefix):
            return existing_extra  # already present, don't overwrite
    # Append
    new_line = f"{key}: {value}"
    if existing_extra and not existing_extra.endswith("\n"):
        return existing_extra + "\n" + new_line
    return (existing_extra or "") + new_line


# ---------------------------------------------------------------------------
# Push orchestrator
# ---------------------------------------------------------------------------

def push(
    *,
    repo_root: Path,
    zotero_cfg: ZoteroConfig,
    citekeys: list[str] | None = None,
    push_tags: bool = True,
    push_notes: bool = False,
    push_ids: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> ZoteroPushResult:
    """Push biblio enrichments back to Zotero items.

    Steps:
    1. Load sync state to get citekey → Zotero item key mapping.
    2. Load enrichments (tags, summaries, DOI/OpenAlex IDs).
    3. Fetch current Zotero items for version checking.
    4. Apply enrichments with optimistic concurrency.
    5. Log the operation.
    """
    from .config import default_config_path, load_biblio_config

    _require_pyzotero()
    result = ZoteroPushResult(dry_run=dry_run)

    state = SyncState.load(zotero_cfg.sync_state_path)
    if not state.item_map:
        result.errors.append("No items in sync state. Run 'biblio zotero pull' first.")
        return result

    # Build citekey → zotero_key reverse map
    ck_to_zkey: dict[str, str] = {}
    for zkey, info in state.item_map.items():
        ck = info.get("citekey")
        if ck:
            ck_to_zkey[ck] = zkey

    # Determine which citekeys to process
    if citekeys:
        target_citekeys = [ck for ck in citekeys if ck in ck_to_zkey]
        missing = [ck for ck in citekeys if ck not in ck_to_zkey]
        if missing:
            result.errors.append(
                f"No Zotero mapping for: {', '.join(missing)}. "
                "These items may not have been pulled from Zotero."
            )
    else:
        target_citekeys = list(ck_to_zkey.keys())

    if not target_citekeys:
        return result

    # Load biblio config for enrichment access
    config_path = default_config_path(root=repo_root)
    cfg = load_biblio_config(config_path, root=repo_root)

    # Load bib database for DOI/OpenAlex lookups
    bib_db: dict[str, dict[str, Any]] = {}
    if push_ids:
        try:
            from ._pybtex_utils import parse_bibtex_file
            bib_path = cfg.bibtex_merge.out_bib
            if bib_path.exists():
                db = parse_bibtex_file(bib_path)
                for ck, entry in db.entries.items():
                    fields = dict(entry.fields)
                    bib_db[ck] = {k: str(v) for k, v in fields.items()}
        except Exception:
            pass

    # Load library for status/tags
    from .library import load_library
    library = load_library(cfg)

    client = ZoteroClient(zotero_cfg)

    # Fetch current items in batches for version checking
    zkeys_to_push = [ck_to_zkey[ck] for ck in target_citekeys]
    current_items: dict[str, dict[str, Any]] = {}
    for item in client.fetch_items(zkeys_to_push):
        key = item.get("data", {}).get("key") or item.get("key", "")
        if key:
            current_items[key] = item

    for ck in target_citekeys:
        zkey = ck_to_zkey[ck]
        item = current_items.get(zkey)
        if not item:
            result.errors.append(f"{ck}: item {zkey} not found in Zotero")
            continue

        item_data = item.get("data", {})
        stored_version = state.item_map.get(zkey, {}).get("version", 0)
        current_version = item_data.get("version", 0)

        # Conflict detection: skip if item was modified in Zotero since last sync
        if not force and current_version > stored_version:
            result.conflicts.append(
                f"{ck}: Zotero version {current_version} > synced {stored_version}"
            )
            continue

        if dry_run:
            result.updated += 1
            continue

        modified = False

        # --- Push tags ---
        if push_tags:
            new_tags = _collect_enrichment_tags(ck, cfg, library.get(ck, {}))
            if new_tags:
                existing_tags = {
                    t.get("tag", "") for t in item_data.get("tags", [])
                }
                tags_to_add = [t for t in new_tags if t not in existing_tags]
                if tags_to_add:
                    current_tag_list = list(item_data.get("tags", []))
                    for t in tags_to_add:
                        current_tag_list.append({"tag": t})
                    item_data["tags"] = current_tag_list
                    modified = True

        # --- Push IDs (DOI, OpenAlex) ---
        if push_ids:
            extra_fields = _collect_extra_fields(ck, cfg, bib_db.get(ck))
            if extra_fields:
                extra = item_data.get("extra", "") or ""
                new_extra = extra
                for k, v in extra_fields.items():
                    if k == "DOI" and not item_data.get("DOI"):
                        item_data["DOI"] = v
                        modified = True
                    else:
                        updated = _update_extra_field(new_extra, k, v)
                        if updated != new_extra:
                            new_extra = updated
                            modified = True
                if new_extra != (item_data.get("extra", "") or ""):
                    item_data["extra"] = new_extra

        # Apply item update if modified
        if modified:
            success = client.update_item(item)
            if success:
                result.updated += 1
                # Update stored version
                new_version = item_data.get("version", current_version)
                if zkey in state.item_map:
                    state.item_map[zkey]["version"] = new_version
            else:
                # Retry once on potential conflict
                if not force:
                    result.conflicts.append(f"{ck}: update failed (possible conflict)")
                else:
                    result.errors.append(f"{ck}: update failed")
                continue

        # --- Push notes (child items, separate from item update) ---
        if push_notes:
            summary_html = _load_summary_html(ck, cfg)
            if summary_html:
                children = client.children(zkey)
                if not _has_biblio_note(children, summary_html):
                    tagged_html = f"<p><strong>[biblio summary]</strong></p>\n{summary_html}"
                    note_key = client.create_note(zkey, tagged_html)
                    if note_key:
                        result.created += 1
                    else:
                        result.errors.append(f"{ck}: failed to create summary note")
                else:
                    result.skipped += 1

        if not modified and not push_notes:
            result.skipped += 1

    # Save updated sync state
    if not dry_run:
        state.save(zotero_cfg.sync_state_path)

    # Log
    log_path = repo_root / ".projio" / "biblio" / "logs" / "runs" / "zotero_sync.jsonl"
    append_jsonl(log_path, {
        "run_id": new_run_id("zotero_push"),
        "timestamp": utc_now_iso(),
        "stage": "zotero_push",
        "status": "success",
        "updated": result.updated,
        "created": result.created,
        "skipped": result.skipped,
        "conflicts": result.conflicts,
        "errors": result.errors,
        "dry_run": dry_run,
    })

    return result
