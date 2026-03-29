from __future__ import annotations

import json
import re
import shutil
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .ledger import append_jsonl, new_run_id, utc_now_iso


@dataclass(frozen=True)
class IngestRecord:
    source_type: str
    source_ref: str
    entry_type: str
    title: str | None
    authors: tuple[str, ...]
    year: str | None
    doi: str | None
    url: str | None
    journal: str | None
    booktitle: str | None
    raw_id: str | None
    file: str | None = None


@dataclass(frozen=True)
class IngestResult:
    source_type: str
    input_path: Path
    output_path: Path
    parsed: int
    emitted: int
    dry_run: bool
    citekeys: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...] = ()  # (doi, existing_citekey) pairs


_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def default_import_bib_path(repo_root: str | Path) -> Path:
    return Path(repo_root).expanduser().resolve() / "bib" / "srcbib" / "imported.bib"


def default_import_log_path(repo_root: str | Path) -> Path:
    return Path(repo_root).expanduser().resolve() / "bib" / "logs" / "imports.jsonl"


def find_existing_dois(repo_root: str | Path) -> dict[str, str]:
    """Scan all srcbib/*.bib files and return a mapping of normalized DOI → citekey.

    This allows duplicate detection before making any network calls during ingestion.
    """
    repo_root = Path(repo_root).expanduser().resolve()
    src_dir = repo_root / "bib" / "srcbib"
    if not src_dir.exists():
        return {}

    doi_map: dict[str, str] = {}
    for bib_path in sorted(src_dir.glob("*.bib")):
        if not bib_path.is_file():
            continue
        try:
            from ._pybtex_utils import parse_bibtex_file

            db = parse_bibtex_file(bib_path)
            for key, entry in db.entries.items():
                doi_val = entry.fields.get("doi")
                if doi_val:
                    norm = _normalize_doi(str(doi_val))
                    if norm:
                        doi_map[norm.lower()] = key
        except Exception:
            continue
    return doi_map


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def _normalize_doi(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    text = text.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    text = text.strip().strip("{}")
    return text or None


def _slug_token(value: str | None, *, fallback: str) -> str:
    if not value:
        return fallback
    token = re.sub(r"[^A-Za-z0-9]+", "", value).lower()
    return token or fallback


def _title_token(title: str | None, doi: str | None) -> str:
    if title:
        for raw in re.split(r"[^A-Za-z0-9]+", title.lower()):
            if raw and raw not in _STOPWORDS:
                return raw[:20]
    if doi:
        tail = doi.rstrip("/").split("/")[-1]
        token = re.sub(r"[^A-Za-z0-9]+", "", tail).lower()
        if token:
            return token[:20]
    return "record"


def _title_camel_token(title: str | None, doi: str | None, n_words: int = 2) -> str:
    """Return first N significant words of title, each capitalized, concatenated."""
    if title:
        words = []
        for raw in re.split(r"[^A-Za-z0-9]+", title):
            if raw and raw.lower() not in _STOPWORDS and len(words) < n_words:
                words.append(raw.capitalize())
        if words:
            return "".join(words)
    if doi:
        tail = doi.rstrip("/").split("/")[-1]
        token = re.sub(r"[^A-Za-z0-9]+", "", tail)
        if token:
            return token[:20].capitalize()
    return "Record"


def _first_author_token(authors: Iterable[str]) -> str:
    first = next(iter(authors), None)
    if not first:
        return "anon"
    if "," in first:
        family = first.split(",", 1)[0].strip()
    else:
        family = first.split()[-1]
    return _slug_token(family, fallback="anon")


def _year_token(year: str | None) -> str:
    if not year:
        return "nd"
    m = re.search(r"\d{4}", year)
    return m.group(0) if m else _slug_token(year, fallback="nd")


def assign_citekeys(records: Iterable[IngestRecord]) -> list[tuple[str, IngestRecord]]:
    seen: dict[str, int] = {}
    assigned: list[tuple[str, IngestRecord]] = []
    for record in records:
        author = _first_author_token(record.authors)
        year = _year_token(record.year)
        title = _title_camel_token(record.title, record.doi)
        base = f"{author}_{year}_{title}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        citekey = base if count == 0 else f"{base}{count + 1}"
        assigned.append((citekey, record))
    return assigned


def canonical_citekey(record: IngestRecord) -> str:
    """Return the canonical author_year_Title citekey for a record (no dedup suffix)."""
    return f"{_first_author_token(record.authors)}_{_year_token(record.year)}_{_title_camel_token(record.title, record.doi)}"


def parse_doi_file(path: str | Path) -> list[IngestRecord]:
    file_path = Path(path).expanduser().resolve()
    records: list[IngestRecord] = []
    for lineno, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        doi = _normalize_doi(raw)
        if not doi:
            continue
        records.append(
            IngestRecord(
                source_type="doi_list",
                source_ref=f"{file_path}:{lineno}",
                entry_type="misc",
                title=None,
                authors=(),
                year=None,
                doi=doi,
                url=f"https://doi.org/{doi}",
                journal=None,
                booktitle=None,
                raw_id=doi,
                file=None,
            )
        )
    return records


def enrich_doi_records_with_openalex(
    records: list[IngestRecord],
    *,
    api_base: str = "https://api.openalex.org",
    mailto: str | None = None,
    fetch_json: Any | None = None,
) -> list[IngestRecord]:
    if fetch_json is None:
        def fetch_json(url: str) -> Any:
            with urllib.request.urlopen(url) as resp:  # nosec B310
                return json.load(resp)

    enriched: list[IngestRecord] = []
    for record in records:
        if not record.doi:
            enriched.append(record)
            continue
        doi_encoded = urllib.parse.quote(record.doi, safe="")
        url = f"{api_base.rstrip('/')}/works/doi:{doi_encoded}"
        if mailto:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}mailto={urllib.parse.quote(mailto, safe='@')}"
        try:
            payload = fetch_json(url)
        except Exception:
            enriched.append(record)
            continue
        if not isinstance(payload, Mapping):
            enriched.append(record)
            continue
        authors: list[str] = []
        authorships = payload.get("authorships")
        if isinstance(authorships, list):
            for item in authorships:
                if not isinstance(item, Mapping):
                    continue
                author = item.get("author")
                if isinstance(author, Mapping):
                    name = _clean_text(author.get("display_name"))
                    if name:
                        authors.append(name)
        enriched.append(
            IngestRecord(
                source_type=record.source_type,
                source_ref=record.source_ref,
                entry_type="article",
                title=_clean_text(payload.get("display_name")) or record.title,
                authors=tuple(authors) or record.authors,
                year=_clean_text(payload.get("publication_year")) or record.year,
                doi=record.doi,
                url=_clean_text((payload.get("ids") or {}).get("openalex")) or record.url,
                journal=record.journal,
                booktitle=record.booktitle,
                raw_id=record.raw_id,
                file=record.file,
            )
        )
    return enriched


def enrich_record(
    record: IngestRecord,
    *,
    pdf_path: Path | None = None,
    grobid_cfg: Any | None = None,
    openalex_base: str = "https://api.openalex.org",
    mailto: str | None = None,
    crossref_min_similarity: float = 0.85,
    fetch_json: Any | None = None,
) -> IngestRecord:
    """Cascade-enrich a record that may be missing author/year/title metadata.

    Tries in order:
    1. DOI → OpenAlex  (fast, reliable)
    2. PDF → GROBID header extraction  (needs running GROBID)
    3. Title → CrossRef title search → get DOI → OpenAlex

    Returns an enriched copy, or the original if nothing helps.
    """
    def _needs_authors(rec: IngestRecord) -> bool:
        return not rec.authors

    if not _needs_authors(record):
        return record

    # ── Tier 1: DOI → OpenAlex ──────────────────────────────────────────────
    if record.doi:
        enriched = enrich_doi_records_with_openalex(
            [record], api_base=openalex_base, mailto=mailto, fetch_json=fetch_json,
        )
        if enriched and not _needs_authors(enriched[0]):
            return enriched[0]

    # ── Tier 2: PDF → GROBID header ─────────────────────────────────────────
    if pdf_path and pdf_path.exists() and grobid_cfg is not None:
        try:
            from .grobid import process_pdf_header, parse_tei_header

            tei_xml = process_pdf_header(grobid_cfg, pdf_path)
            header = parse_tei_header(tei_xml)
            authors = tuple(header.get("authors") or [])
            if authors:
                return IngestRecord(
                    source_type=record.source_type,
                    source_ref=record.source_ref,
                    entry_type=record.entry_type,
                    title=header.get("title") or record.title,
                    authors=authors,
                    year=header.get("year") or record.year,
                    doi=header.get("doi") or record.doi,
                    url=record.url,
                    journal=record.journal,
                    booktitle=record.booktitle,
                    raw_id=record.raw_id,
                    file=record.file,
                )
        except Exception:
            pass  # GROBID unavailable or failed — fall through

    # ── Tier 3: Title → CrossRef → DOI → OpenAlex ───────────────────────────
    if record.title:
        try:
            from .crossref import resolve_doi_by_title

            result = resolve_doi_by_title(record.title)
            sim = result.get("similarity", 0)
            matched = (result.get("matched_title") or "").lower()
            query = record.title.lower()
            # Accept if similarity is high enough, OR if the matched title
            # starts with the query (subtitle mismatch, e.g. "Title" vs
            # "Title: Evidence from ...").
            title_ok = sim >= crossref_min_similarity or (
                sim >= 0.7 and matched.startswith(query)
            )
            if result.get("ok") and title_ok:
                found_doi = result.get("doi")
                if found_doi:
                    rec_with_doi = IngestRecord(
                        source_type=record.source_type,
                        source_ref=record.source_ref,
                        entry_type=record.entry_type,
                        title=record.title,
                        authors=record.authors,
                        year=record.year,
                        doi=found_doi,
                        url=record.url,
                        journal=record.journal,
                        booktitle=record.booktitle,
                        raw_id=record.raw_id,
                        file=record.file,
                    )
                    enriched = enrich_doi_records_with_openalex(
                        [rec_with_doi], api_base=openalex_base, mailto=mailto, fetch_json=fetch_json,
                    )
                    if enriched and not _needs_authors(enriched[0]):
                        return enriched[0]
        except Exception:
            pass  # CrossRef unavailable — give up

    return record


@dataclass(frozen=True)
class EnrichCacheResult:
    """Result of enrich_and_cache: enriched record + caching metadata."""
    record: IngestRecord
    source: str  # "openalex", "grobid", "crossref", or "" if unchanged
    cached_paths: tuple[str, ...]  # paths written during caching


def enrich_and_cache(
    record: IngestRecord,
    *,
    pdf_path: Path | None = None,
    grobid_cfg: Any | None = None,
    repo_root: Path | None = None,
    openalex_base: str = "https://api.openalex.org",
    mailto: str | None = None,
    crossref_min_similarity: float = 0.85,
    fetch_json: Any | None = None,
) -> EnrichCacheResult:
    """Wrapper around enrich_record that also persists intermediate API results.

    Caches:
    - OpenAlex work JSON to bib/derivatives/openalex/cache/doi/{doi_slug}.json
    - GROBID header JSON to bib/derivatives/grobid/{citekey}/header.json (without
      overwriting existing references.json or TEI XML from a full GROBID run)
    - CrossRef result to bib/derivatives/crossref/{doi_slug}.json
    """
    if not record.authors:
        pass  # proceed with enrichment
    else:
        return EnrichCacheResult(record=record, source="", cached_paths=())

    bib_root = repo_root / "bib" if repo_root else None
    cached_paths: list[str] = []
    source = ""

    # Build a capturing fetch_json wrapper for OpenAlex
    _openalex_payloads: list[tuple[str, Any]] = []  # (doi, payload)
    _real_fetch = fetch_json

    def _capturing_fetch(url: str) -> Any:
        fn = _real_fetch or (lambda u: json.load(urllib.request.urlopen(u)))
        return fn(url)

    # ── Tier 1: DOI → OpenAlex ──────────────────────────────────────────────
    if record.doi:
        try:
            doi_encoded = urllib.parse.quote(record.doi, safe="")
            oa_url = f"{openalex_base.rstrip('/')}/works/doi:{doi_encoded}"
            if mailto:
                sep = "&" if "?" in oa_url else "?"
                oa_url = f"{oa_url}{sep}mailto={urllib.parse.quote(mailto, safe='@')}"

            # Check OpenAlex cache first
            if bib_root:
                doi_key = record.doi.replace("/", "__")
                oa_cache_path = bib_root / "derivatives" / "openalex" / "cache" / "doi" / f"{doi_key}.json"
                if oa_cache_path.exists():
                    payload = json.loads(oa_cache_path.read_text(encoding="utf-8"))
                else:
                    payload = _capturing_fetch(oa_url)
                    if payload and isinstance(payload, dict):
                        oa_cache_path.parent.mkdir(parents=True, exist_ok=True)
                        oa_cache_path.write_text(
                            json.dumps(payload, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8",
                        )
                        cached_paths.append(str(oa_cache_path))
            else:
                payload = _capturing_fetch(oa_url)

            if isinstance(payload, dict):
                authors: list[str] = []
                authorships = payload.get("authorships")
                if isinstance(authorships, list):
                    for item in authorships:
                        if isinstance(item, Mapping):
                            author = item.get("author")
                            if isinstance(author, Mapping):
                                name = _clean_text(author.get("display_name"))
                                if name:
                                    authors.append(name)
                if authors:
                    enriched = IngestRecord(
                        source_type=record.source_type,
                        source_ref=record.source_ref,
                        entry_type="article",
                        title=_clean_text(payload.get("display_name")) or record.title,
                        authors=tuple(authors),
                        year=_clean_text(payload.get("publication_year")) or record.year,
                        doi=record.doi,
                        url=_clean_text((payload.get("ids") or {}).get("openalex")) or record.url,
                        journal=record.journal,
                        booktitle=record.booktitle,
                        raw_id=record.raw_id,
                        file=record.file,
                    )
                    return EnrichCacheResult(
                        record=enriched, source="openalex",
                        cached_paths=tuple(cached_paths),
                    )
        except Exception:
            pass

    # ── Tier 2: PDF → GROBID header ─────────────────────────────────────────
    if pdf_path and pdf_path.exists() and grobid_cfg is not None:
        try:
            from .grobid import process_pdf_header, parse_tei_header

            tei_xml = process_pdf_header(grobid_cfg, pdf_path)
            header = parse_tei_header(tei_xml)
            authors_t = tuple(header.get("authors") or [])
            if authors_t:
                # Cache header.json (only if no existing header from a full run)
                citekey = record.raw_id or "unknown"
                if bib_root:
                    grobid_dir = bib_root / "derivatives" / "grobid" / citekey
                    header_path = grobid_dir / "header.json"
                    if not header_path.exists():
                        grobid_dir.mkdir(parents=True, exist_ok=True)
                        header_path.write_text(
                            json.dumps(header, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                        cached_paths.append(str(header_path))
                enriched = IngestRecord(
                    source_type=record.source_type,
                    source_ref=record.source_ref,
                    entry_type=record.entry_type,
                    title=header.get("title") or record.title,
                    authors=authors_t,
                    year=header.get("year") or record.year,
                    doi=header.get("doi") or record.doi,
                    url=record.url,
                    journal=record.journal,
                    booktitle=record.booktitle,
                    raw_id=record.raw_id,
                    file=record.file,
                )
                return EnrichCacheResult(
                    record=enriched, source="grobid",
                    cached_paths=tuple(cached_paths),
                )
        except Exception:
            pass

    # ── Tier 3: Title → CrossRef → DOI → OpenAlex ───────────────────────────
    if record.title:
        try:
            from .crossref import resolve_doi_by_title

            result = resolve_doi_by_title(record.title)
            sim = result.get("similarity", 0)
            matched = (result.get("matched_title") or "").lower()
            query = record.title.lower()
            title_ok = sim >= crossref_min_similarity or (
                sim >= 0.7 and matched.startswith(query)
            )
            if result.get("ok") and title_ok:
                found_doi = result.get("doi")
                if found_doi:
                    # Cache CrossRef result
                    if bib_root:
                        doi_slug = found_doi.replace("/", "__")
                        cr_cache_dir = bib_root / "derivatives" / "crossref"
                        cr_cache_path = cr_cache_dir / f"{doi_slug}.json"
                        if not cr_cache_path.exists():
                            cr_cache_dir.mkdir(parents=True, exist_ok=True)
                            cr_cache_path.write_text(
                                json.dumps(result, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8",
                            )
                            cached_paths.append(str(cr_cache_path))

                    # Now resolve via OpenAlex with the found DOI
                    rec_with_doi = IngestRecord(
                        source_type=record.source_type,
                        source_ref=record.source_ref,
                        entry_type=record.entry_type,
                        title=record.title,
                        authors=record.authors,
                        year=record.year,
                        doi=found_doi,
                        url=record.url,
                        journal=record.journal,
                        booktitle=record.booktitle,
                        raw_id=record.raw_id,
                        file=record.file,
                    )
                    # Cache OpenAlex result for the CrossRef-resolved DOI too
                    try:
                        doi_encoded = urllib.parse.quote(found_doi, safe="")
                        oa_url = f"{openalex_base.rstrip('/')}/works/doi:{doi_encoded}"
                        if mailto:
                            sep = "&" if "?" in oa_url else "?"
                            oa_url = f"{oa_url}{sep}mailto={urllib.parse.quote(mailto, safe='@')}"

                        if bib_root:
                            doi_key = found_doi.replace("/", "__")
                            oa_cache_path = bib_root / "derivatives" / "openalex" / "cache" / "doi" / f"{doi_key}.json"
                            if oa_cache_path.exists():
                                payload = json.loads(oa_cache_path.read_text(encoding="utf-8"))
                            else:
                                payload = _capturing_fetch(oa_url)
                                if payload and isinstance(payload, dict):
                                    oa_cache_path.parent.mkdir(parents=True, exist_ok=True)
                                    oa_cache_path.write_text(
                                        json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                        encoding="utf-8",
                                    )
                                    cached_paths.append(str(oa_cache_path))
                        else:
                            payload = _capturing_fetch(oa_url)

                        if isinstance(payload, dict):
                            authors_list: list[str] = []
                            authorships = payload.get("authorships")
                            if isinstance(authorships, list):
                                for item in authorships:
                                    if isinstance(item, Mapping):
                                        author = item.get("author")
                                        if isinstance(author, Mapping):
                                            name = _clean_text(author.get("display_name"))
                                            if name:
                                                authors_list.append(name)
                            if authors_list:
                                enriched = IngestRecord(
                                    source_type=rec_with_doi.source_type,
                                    source_ref=rec_with_doi.source_ref,
                                    entry_type="article",
                                    title=_clean_text(payload.get("display_name")) or rec_with_doi.title,
                                    authors=tuple(authors_list),
                                    year=_clean_text(payload.get("publication_year")) or rec_with_doi.year,
                                    doi=found_doi,
                                    url=_clean_text((payload.get("ids") or {}).get("openalex")) or rec_with_doi.url,
                                    journal=rec_with_doi.journal,
                                    booktitle=rec_with_doi.booktitle,
                                    raw_id=rec_with_doi.raw_id,
                                    file=rec_with_doi.file,
                                )
                                return EnrichCacheResult(
                                    record=enriched, source="crossref",
                                    cached_paths=tuple(cached_paths),
                                )
                    except Exception:
                        pass
        except Exception:
            pass

    return EnrichCacheResult(record=record, source="", cached_paths=tuple(cached_paths))


def _csl_authors(item: Mapping[str, Any]) -> tuple[str, ...]:
    out: list[str] = []
    authors = item.get("author")
    if isinstance(authors, list):
        for author in authors:
            if not isinstance(author, Mapping):
                continue
            family = _clean_text(author.get("family"))
            given = _clean_text(author.get("given"))
            literal = _clean_text(author.get("literal"))
            if family and given:
                out.append(f"{family}, {given}")
            elif family:
                out.append(family)
            elif literal:
                out.append(literal)
    return tuple(out)


def _csl_year(item: Mapping[str, Any]) -> str | None:
    issued = item.get("issued")
    if not isinstance(issued, Mapping):
        return None
    parts = issued.get("date-parts")
    if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
        return _clean_text(parts[0][0])
    return None


def parse_csljson_file(path: str | Path) -> list[IngestRecord]:
    file_path = Path(path).expanduser().resolve()
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else [payload]
    records: list[IngestRecord] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            continue
        csl_type = _clean_text(item.get("type")) or "article-journal"
        entry_type = {
            "article-journal": "article",
            "paper-conference": "inproceedings",
            "chapter": "incollection",
            "book": "book",
            "report": "techreport",
            "thesis": "phdthesis",
        }.get(csl_type, "misc")
        container = item.get("container-title")
        if isinstance(container, list):
            container_text = _clean_text(container[0] if container else None)
        else:
            container_text = _clean_text(container)
        records.append(
            IngestRecord(
                source_type="csljson",
                source_ref=f"{file_path}:{idx}",
                entry_type=entry_type,
                title=_clean_text(item.get("title")),
                authors=_csl_authors(item),
                year=_csl_year(item),
                doi=_normalize_doi(item.get("DOI")),
                url=_clean_text(item.get("URL")),
                journal=container_text if entry_type == "article" else None,
                booktitle=container_text if entry_type == "inproceedings" else None,
                raw_id=_clean_text(item.get("id")),
                file=None,
            )
        )
    return records


def parse_ris_file(path: str | Path) -> list[IngestRecord]:
    file_path = Path(path).expanduser().resolve()
    lines = file_path.read_text(encoding="utf-8").splitlines()
    raw_entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    last_tag: str | None = None
    for line in lines:
        if not line.strip():
            continue
        if len(line) >= 6 and line[2:6] == "  - ":
            tag = line[:2]
            value = line[6:].strip()
            if tag == "TY":
                current = {"TY": value}
                raw_entries.append(current)
            elif tag == "ER":
                current = {}
            elif current:
                current.setdefault(tag, []).append(value)
            last_tag = tag
        elif current and last_tag:
            current.setdefault(last_tag, []).append(line.strip())

    records: list[IngestRecord] = []
    type_map = {
        "JOUR": "article",
        "CONF": "inproceedings",
        "CHAP": "incollection",
        "BOOK": "book",
        "THES": "phdthesis",
        "RPRT": "techreport",
    }
    for idx, item in enumerate(raw_entries, start=1):
        if not item:
            continue
        ris_type = _clean_text(item.get("TY")) or "GEN"
        title = _clean_text((item.get("TI") or item.get("T1") or [None])[0] if isinstance(item.get("TI") or item.get("T1"), list) else None)
        authors = tuple(_clean_text(v) or "" for v in item.get("AU", [])) if isinstance(item.get("AU"), list) else ()
        authors = tuple(a for a in authors if a)
        records.append(
            IngestRecord(
                source_type="ris",
                source_ref=f"{file_path}:{idx}",
                entry_type=type_map.get(ris_type, "misc"),
                title=title,
                authors=authors,
                year=_clean_text((item.get("PY") or item.get("Y1") or [None])[0] if isinstance(item.get("PY") or item.get("Y1"), list) else None),
                doi=_normalize_doi((item.get("DO") or [None])[0] if isinstance(item.get("DO"), list) else None),
                url=_clean_text((item.get("UR") or [None])[0] if isinstance(item.get("UR"), list) else None),
                journal=_clean_text((item.get("JO") or item.get("T2") or item.get("JF") or [None])[0] if isinstance(item.get("JO") or item.get("T2") or item.get("JF"), list) else None),
                booktitle=_clean_text((item.get("BT") or [None])[0] if isinstance(item.get("BT"), list) else None),
                raw_id=_clean_text((item.get("ID") or [None])[0] if isinstance(item.get("ID"), list) else None),
                file=None,
            )
        )
    return records


def parse_pdf_inputs(paths: Iterable[str | Path]) -> list[IngestRecord]:
    records: list[IngestRecord] = []
    for idx, raw_path in enumerate(paths, start=1):
        path = Path(raw_path).expanduser().resolve()
        if path.is_dir():
            files = sorted(p for p in path.rglob("*.pdf") if p.is_file())
        else:
            files = [path]
        for file_path in files:
            stem = file_path.stem.replace("_", " ").replace("-", " ").strip()
            records.append(
                IngestRecord(
                    source_type="pdfs",
                    source_ref=str(file_path),
                    entry_type="misc",
                    title=stem or file_path.stem,
                    authors=(),
                    year=None,
                    doi=None,
                    url=None,
                    journal=None,
                    booktitle=None,
                    raw_id=f"pdf-{idx}",
                    file=None,
                )
            )
    return records


def _bibtex_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def render_bibtex(records: Iterable[tuple[str, IngestRecord]]) -> str:
    chunks: list[str] = []
    for citekey, record in records:
        fields: list[tuple[str, str]] = []
        if record.title:
            fields.append(("title", record.title))
        if record.authors:
            fields.append(("author", " and ".join(record.authors)))
        if record.year:
            fields.append(("year", record.year))
        if record.doi:
            fields.append(("doi", record.doi))
        if record.url:
            fields.append(("url", record.url))
        if record.journal:
            fields.append(("journal", record.journal))
        if record.booktitle:
            fields.append(("booktitle", record.booktitle))
        if record.file:
            fields.append(("file", record.file))
        body = ",\n".join(f"  {key} = {{{_bibtex_escape(value)}}}" for key, value in fields)
        chunks.append(f"@{record.entry_type}{{{citekey},\n{body}\n}}")
    return "\n\n".join(chunks) + ("\n" if chunks else "")


def write_import_bib(path: str | Path, bibtex_text: str) -> Path:
    out_path = Path(path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.read_text(encoding="utf-8").strip():
        prefix = "\n" if not out_path.read_text(encoding="utf-8").endswith("\n") else ""
        with out_path.open("a", encoding="utf-8") as f:
            f.write(prefix)
            f.write(bibtex_text)
    else:
        out_path.write_text(bibtex_text, encoding="utf-8")
    return out_path


def ingest_file(
    *,
    repo_root: str | Path,
    source_type: str,
    input_path: str | Path | None = None,
    input_paths: Iterable[str | Path] | None = None,
    output_path: str | Path | None = None,
    dry_run: bool = False,
    stdout: bool = False,
    pdf_root: str | Path | None = None,
    pdf_pattern: str = "{citekey}/{citekey}.pdf",
    doi_fetch_json: Any | None = None,
    doi_api_base: str = "https://api.openalex.org",
    doi_mailto: str | None = None,
    force: bool = False,
) -> tuple[IngestResult, str]:
    repo_root = Path(repo_root).expanduser().resolve()
    input_file = Path(input_path).expanduser().resolve() if input_path is not None else None
    out_path = Path(output_path).expanduser().resolve() if output_path is not None else default_import_bib_path(repo_root)
    pdf_dest_root = Path(pdf_root).expanduser().resolve() if pdf_root is not None else (repo_root / "bib" / "articles").resolve()

    # ── Duplicate detection: build DOI→citekey map from existing srcbib ────
    skipped: list[tuple[str, str]] = []  # (doi, existing_citekey)
    existing_dois: dict[str, str] = {}
    if not force:
        try:
            existing_dois = find_existing_dois(repo_root)
        except Exception:
            pass  # if pybtex unavailable or bib corrupt, skip check

    if source_type == "dois":
        assert input_file is not None
        records = parse_doi_file(input_file)
        # Filter duplicates BEFORE network calls
        if existing_dois:
            filtered: list[IngestRecord] = []
            for rec in records:
                norm = (rec.doi or "").lower()
                if norm and norm in existing_dois:
                    skipped.append((rec.doi or "", existing_dois[norm]))
                else:
                    filtered.append(rec)
            records = filtered
        records = enrich_doi_records_with_openalex(
            records,
            api_base=doi_api_base,
            mailto=doi_mailto,
            fetch_json=doi_fetch_json,
        )
        record_source = "doi_list"
    elif source_type == "csljson":
        assert input_file is not None
        records = parse_csljson_file(input_file)
        if existing_dois:
            filtered = []
            for rec in records:
                norm = _normalize_doi(rec.doi)
                if norm and norm.lower() in existing_dois:
                    skipped.append((rec.doi or "", existing_dois[norm.lower()]))
                else:
                    filtered.append(rec)
            records = filtered
        record_source = "csljson"
    elif source_type == "ris":
        assert input_file is not None
        records = parse_ris_file(input_file)
        if existing_dois:
            filtered = []
            for rec in records:
                norm = _normalize_doi(rec.doi)
                if norm and norm.lower() in existing_dois:
                    skipped.append((rec.doi or "", existing_dois[norm.lower()]))
                else:
                    filtered.append(rec)
            records = filtered
        record_source = "ris"
    elif source_type == "pdfs":
        records = parse_pdf_inputs(list(input_paths or ([input_file] if input_file is not None else [])))
        record_source = "pdfs"
    else:
        raise ValueError(f"Unsupported ingest source type: {source_type!r}")

    parsed_count = len(records) + len(skipped)
    assigned = assign_citekeys(records)
    if source_type == "pdfs":
        updated: list[tuple[str, IngestRecord]] = []
        source_paths = [Path(record.source_ref) for _, record in assigned]
        for (citekey, record), source_path in zip(assigned, source_paths):
            rel = pdf_pattern.format(citekey=citekey)
            dest_path = (pdf_dest_root / rel).resolve()
            updated.append(
                (
                    citekey,
                    IngestRecord(
                        source_type=record.source_type,
                        source_ref=record.source_ref,
                        entry_type=record.entry_type,
                        title=record.title,
                        authors=record.authors,
                        year=record.year,
                        doi=record.doi,
                        url=record.url,
                        journal=record.journal,
                        booktitle=record.booktitle,
                        raw_id=record.raw_id,
                        file=str(dest_path.relative_to(repo_root)),
                    ),
                )
            )
            if not dry_run and not stdout:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, dest_path)
        assigned = updated
    bibtex_text = render_bibtex(assigned)
    citekeys = tuple(citekey for citekey, _ in assigned)

    if not dry_run and not stdout:
        write_import_bib(out_path, bibtex_text)
        append_jsonl(
            default_import_log_path(repo_root),
            {
                "run_id": new_run_id("ingest"),
                "timestamp": utc_now_iso(),
                "source_type": record_source,
                "input_path": str(input_file) if input_file is not None else None,
                "input_paths": [str(p) for p in (input_paths or [])] if input_paths is not None else None,
                "output_path": str(out_path),
                "parsed": parsed_count,
                "emitted": len(assigned),
                "skipped": len(skipped),
                "citekeys": list(citekeys),
            },
        )

    result = IngestResult(
        source_type=record_source,
        input_path=input_file or repo_root,
        output_path=out_path,
        parsed=parsed_count,
        emitted=len(assigned),
        dry_run=dry_run,
        citekeys=citekeys,
        skipped=tuple(skipped),
    )
    return result, bibtex_text


def sync_bibtex_keywords_to_library(
    cfg: Any,
    citekeys: Iterable[str],
    *,
    vocab_path: Path | None = None,
) -> dict[str, list[str]]:
    """Extract BibTeX keywords for *citekeys* and merge as tags into library.yml.

    Loads the merged .bib, extracts ``keywords`` fields, maps them through the
    tag vocabulary, and merges (union) with existing library tags.

    Returns ``{citekey: [tags_added]}`` for citekeys that gained new tags.
    """
    from .tag_vocab import (
        default_tag_vocab_path,
        extract_bibtex_keywords,
        keywords_to_tags,
        load_tag_vocab,
    )
    from .library import load_library, update_entry
    from ._pybtex_utils import parse_bibtex_file

    vpath = vocab_path or default_tag_vocab_path(cfg.repo_root)
    vocab = load_tag_vocab(vpath)

    bib_path = cfg.bibtex_merge.out_bib
    if not bib_path.exists():
        return {}

    bib_db = parse_bibtex_file(bib_path)
    library = load_library(cfg)
    result: dict[str, list[str]] = {}

    for ck in citekeys:
        key = ck.lstrip("@")
        if key not in bib_db.entries:
            continue
        entry = bib_db.entries[key]
        keywords = extract_bibtex_keywords(dict(entry.fields))
        if not keywords:
            continue
        new_tags = keywords_to_tags(keywords, vocab)
        if not new_tags:
            continue

        existing = list(library.get(key, {}).get("tags") or [])
        existing_set = set(existing)
        added = [t for t in new_tags if t not in existing_set]
        if added:
            merged = existing + added
            update_entry(cfg, key, tags=merged)
            result[key] = added

    return result


# ── BibTeX file/string preview & import ──────────────────────────────────────


@dataclass(frozen=True)
class BibPreviewEntry:
    """A single entry from a BibTeX preview."""
    citekey: str
    title: str | None
    authors: list[str]
    year: str | None
    doi: str | None
    entry_type: str
    already_exists: bool


def _authors_from_pybtex(persons: Any) -> list[str]:
    """Extract author name strings from a pybtex persons dict."""
    names: list[str] = []
    author_list = persons.get("author", [])
    for person in author_list:
        parts = []
        for part in person.first_names:
            parts.append(str(part))
        for part in person.last_names:
            parts.append(str(part))
        if parts:
            names.append(" ".join(parts))
    return names


def preview_bibtex(
    bibtex_text: str,
    repo_root: str | Path,
) -> list[BibPreviewEntry]:
    """Parse BibTeX text and return preview entries with duplicate detection."""
    from ._pybtex_utils import parse_bibtex_string

    db = parse_bibtex_string(bibtex_text)

    # Build sets of existing citekeys and DOIs for duplicate detection
    repo_root = Path(repo_root).expanduser().resolve()
    existing_dois = find_existing_dois(repo_root)
    existing_citekeys: set[str] = set()
    src_dir = repo_root / "bib" / "srcbib"
    if src_dir.exists():
        from ._pybtex_utils import parse_bibtex_file
        for bib_path in sorted(src_dir.glob("*.bib")):
            if bib_path.is_file():
                try:
                    existing_db = parse_bibtex_file(bib_path)
                    existing_citekeys.update(existing_db.entries.keys())
                except Exception:
                    continue
    # Also check citekeys.md
    ck_path = repo_root / "bib" / "citekeys.md"
    if ck_path.exists():
        from .citekeys import load_citekeys_md
        existing_citekeys.update(load_citekeys_md(ck_path))

    entries: list[BibPreviewEntry] = []
    for key, entry in db.entries.items():
        fields = entry.fields
        doi = _normalize_doi(fields.get("doi"))
        authors = _authors_from_pybtex(entry.persons)
        already_exists = (
            key in existing_citekeys
            or (doi is not None and doi.lower() in existing_dois)
        )
        entries.append(BibPreviewEntry(
            citekey=key,
            title=_clean_text(fields.get("title")),
            authors=authors,
            year=_clean_text(fields.get("year")),
            doi=doi,
            entry_type=entry.type,
            already_exists=already_exists,
        ))
    return entries


def import_bibtex_entries(
    bibtex_text: str,
    selected_citekeys: list[str],
    repo_root: str | Path,
    output_path: str | Path | None = None,
) -> tuple[int, list[str]]:
    """Import selected entries from parsed BibTeX text into srcbib.

    Returns (imported_count, list_of_citekeys_added).
    """
    from ._pybtex_utils import parse_bibtex_string

    db = parse_bibtex_string(bibtex_text)
    repo_root = Path(repo_root).expanduser().resolve()
    out_path = Path(output_path).expanduser().resolve() if output_path else default_import_bib_path(repo_root)
    selected_set = set(selected_citekeys)

    # Filter to selected entries that exist in the parsed BibTeX
    to_import: list[tuple[str, IngestRecord]] = []
    for key in selected_citekeys:
        if key not in db.entries:
            continue
        entry = db.entries[key]
        fields = entry.fields
        authors = _authors_from_pybtex(entry.persons)
        record = IngestRecord(
            source_type="bibtex_import",
            source_ref="uploaded .bib",
            entry_type=entry.type,
            title=_clean_text(fields.get("title")),
            authors=tuple(authors),
            year=_clean_text(fields.get("year")),
            doi=_normalize_doi(fields.get("doi")),
            url=_clean_text(fields.get("url")),
            journal=_clean_text(fields.get("journal")),
            booktitle=_clean_text(fields.get("booktitle")),
            raw_id=key,
            file=_clean_text(fields.get("file")),
        )
        to_import.append((key, record))

    if not to_import:
        return 0, []

    # Write the selected entries preserving their original citekeys
    bibtex_out = render_bibtex(to_import)
    write_import_bib(out_path, bibtex_out)

    # Register in citekeys.md
    ck_path = repo_root / "bib" / "citekeys.md"
    from .citekeys import add_citekeys_md
    added_keys = [k for k, _ in to_import]
    add_citekeys_md(ck_path, added_keys)

    # Log the import
    append_jsonl(
        default_import_log_path(repo_root),
        {
            "run_id": new_run_id("ingest"),
            "timestamp": utc_now_iso(),
            "source_type": "bibtex_import",
            "output_path": str(out_path),
            "parsed": len(selected_citekeys),
            "emitted": len(to_import),
            "citekeys": added_keys,
        },
    )

    return len(to_import), added_keys
