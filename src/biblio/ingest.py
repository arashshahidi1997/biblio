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
) -> tuple[IngestResult, str]:
    repo_root = Path(repo_root).expanduser().resolve()
    input_file = Path(input_path).expanduser().resolve() if input_path is not None else None
    out_path = Path(output_path).expanduser().resolve() if output_path is not None else default_import_bib_path(repo_root)
    pdf_dest_root = Path(pdf_root).expanduser().resolve() if pdf_root is not None else (repo_root / "bib" / "articles").resolve()

    if source_type == "dois":
        assert input_file is not None
        records = parse_doi_file(input_file)
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
        record_source = "csljson"
    elif source_type == "ris":
        assert input_file is not None
        records = parse_ris_file(input_file)
        record_source = "ris"
    elif source_type == "pdfs":
        records = parse_pdf_inputs(list(input_paths or ([input_file] if input_file is not None else [])))
        record_source = "pdfs"
    else:
        raise ValueError(f"Unsupported ingest source type: {source_type!r}")

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
                "parsed": len(records),
                "emitted": len(assigned),
                "citekeys": list(citekeys),
            },
        )

    result = IngestResult(
        source_type=record_source,
        input_path=input_file or repo_root,
        output_path=out_path,
        parsed=len(records),
        emitted=len(assigned),
        dry_run=dry_run,
        citekeys=citekeys,
    )
    return result, bibtex_text
