from __future__ import annotations

import io
import json
import re
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BiblioConfig, GrobidConfig

_TEI = "http://www.tei-c.org/ns/1.0"
_T = f"{{{_TEI}}}"


# ── output paths ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GrobidOutputs:
    outdir: Path
    tei_path: Path
    header_path: Path
    references_path: Path
    meta_path: Path


def grobid_out_root(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / "bib" / "derivatives" / "grobid").resolve()


def grobid_outputs_for_key(cfg: BiblioConfig, citekey: str) -> GrobidOutputs:
    key = citekey.lstrip("@")
    outdir = grobid_out_root(cfg) / key
    return GrobidOutputs(
        outdir=outdir,
        tei_path=outdir / f"{key}.tei.xml",
        header_path=outdir / "header.json",
        references_path=outdir / "references.json",
        meta_path=outdir / "_biblio.json",
    )


def resolve_grobid_outputs(
    cfg: BiblioConfig, citekey: str, doi: str | None = None,
) -> tuple[GrobidOutputs, str]:
    """Resolve grobid outputs, checking pool first then local.

    Returns ``(outputs, source)`` where source is "pool", "local", or "missing".
    Uses DOI for matching when citekeys differ between project and pool.
    """
    key = citekey.lstrip("@")

    # Check pool first (by citekey, then by DOI)
    try:
        from .pool import resolve_pool_derivative
        pool_dir = resolve_pool_derivative(cfg, key, "grobid", doi=doi)
        if pool_dir is not None:
            # The pool citekey may differ — find files by extension
            tei_files = list(pool_dir.glob("*.tei.xml"))
            tei = tei_files[0] if tei_files else pool_dir / f"{key}.tei.xml"
            if tei.exists():
                return GrobidOutputs(
                    outdir=pool_dir,
                    tei_path=tei,
                    header_path=pool_dir / "header.json",
                    references_path=pool_dir / "references.json",
                    meta_path=pool_dir / "_biblio.json",
                ), "pool"
    except Exception:
        pass

    # Fall back to local
    local = grobid_outputs_for_key(cfg, key)
    if local.tei_path.exists():
        return local, "local"
    return local, "missing"


def find_pending_grobid(cfg: BiblioConfig) -> list[str]:
    """Find citekeys that have PDFs but no GROBID output yet.

    Papers with valid outputs in the shared pool are treated as already done.
    """
    from .citekeys import load_citekeys_md
    from .docling import pdf_path_for_key

    all_keys = load_citekeys_md(cfg.citekeys_path)
    pending = []
    for key in all_keys:
        pdf = pdf_path_for_key(cfg, key)
        if not pdf.exists():
            continue
        _, source = resolve_grobid_outputs(cfg, key)
        if source == "missing":
            pending.append(key)
    return pending


# ── server check ─────────────────────────────────────────────────────────────

@dataclass
class GrobidCheckResult:
    ok: bool
    url: str
    message: str
    version: str | None
    latency_ms: int | None


def check_grobid_server(cfg: GrobidConfig) -> GrobidCheckResult:
    """Ping GROBID /api/isalive and return status."""
    base = cfg.url.rstrip("/")
    alive_url = f"{base}/api/isalive"
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(alive_url, method="GET")
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            latency_ms = int((time.monotonic() - t0) * 1000)
            body = resp.read().decode("utf-8", errors="replace").strip()
            ok = body.lower() in ("true", "ok", "1", "")
            return GrobidCheckResult(
                ok=ok,
                url=cfg.url,
                message=f"GROBID reachable at {cfg.url} ({latency_ms}ms)." if ok else f"Unexpected response from GROBID: {body!r}",
                version=None,
                latency_ms=latency_ms,
            )
    except urllib.error.HTTPError as e:
        return GrobidCheckResult(ok=False, url=cfg.url, message=f"GROBID HTTP {e.code} at {alive_url}", version=None, latency_ms=None)
    except Exception as e:
        return GrobidCheckResult(ok=False, url=cfg.url, message=f"GROBID not reachable at {cfg.url}: {e}", version=None, latency_ms=None)


def check_grobid_server_as_dict(cfg: GrobidConfig) -> dict[str, Any]:
    result = check_grobid_server(cfg)
    return {"ok": result.ok, "url": result.url, "message": result.message, "version": result.version, "latency_ms": result.latency_ms}


# ── HTTP submission ───────────────────────────────────────────────────────────

def _multipart_body(pdf_path: Path, *, consolidate_header: bool, consolidate_citations: bool) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()

    def _field(name: str, value: str) -> None:
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())

    _field("consolidateHeader", "1" if consolidate_header else "0")
    _field("consolidateCitations", "1" if consolidate_citations else "0")
    _field("generateIDs", "1")
    _field("includeRawCitations", "0")

    buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"input\"; filename=\"{pdf_path.name}\"\r\nContent-Type: application/pdf\r\n\r\n".encode())
    buf.write(pdf_path.read_bytes())
    buf.write(f"\r\n--{boundary}--\r\n".encode())

    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def process_pdf(cfg: GrobidConfig, pdf_path: Path) -> str:
    """Submit PDF to GROBID processFulltextDocument, return TEI XML string."""
    body, content_type = _multipart_body(pdf_path, consolidate_header=cfg.consolidate_header, consolidate_citations=cfg.consolidate_citations)
    url = cfg.url.rstrip("/") + "/api/processFulltextDocument"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GROBID HTTP {e.code}: {detail}") from e


def process_pdf_header(cfg: GrobidConfig, pdf_path: Path) -> str:
    """Submit PDF to GROBID processHeaderDocument (header-only, fast), return TEI XML string."""
    body, content_type = _multipart_body(pdf_path, consolidate_header=cfg.consolidate_header, consolidate_citations=False)
    url = cfg.url.rstrip("/") + "/api/processHeaderDocument"
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GROBID HTTP {e.code}: {detail}") from e


# ── TEI parsing ───────────────────────────────────────────────────────────────

def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def parse_tei_header(tei_xml: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return {}

    header = root.find(f".//{_T}teiHeader")
    if header is None:
        return {}

    # Title
    title = ""
    for t in header.findall(f".//{_T}titleStmt/{_T}title"):
        level = t.get("level", "")
        typ = t.get("type", "")
        if level == "a" or typ == "main":
            title = _text(t)
            break
    if not title:
        t_el = header.find(f".//{_T}titleStmt/{_T}title")
        title = _text(t_el) if t_el is not None else ""

    # Authors (from analytic or fileDesc)
    authors: list[str] = []
    for author_el in header.findall(f".//{_T}analytic/{_T}author"):
        persname = author_el.find(f"{_T}persName")
        if persname is None:
            continue
        forenames = " ".join(_text(f) for f in persname.findall(f"{_T}forename")).strip()
        surname = _text(persname.find(f"{_T}surname"))
        full = f"{forenames} {surname}".strip() if forenames else surname
        if full:
            authors.append(full)

    # Abstract
    abstract_el = header.find(f".//{_T}abstract")
    abstract = " ".join("".join(p.itertext()).strip() for p in (abstract_el.findall(f".//{_T}p") if abstract_el is not None else []))
    if not abstract and abstract_el is not None:
        abstract = _text(abstract_el)

    # Year
    year = None
    for date_el in header.findall(f".//{_T}date"):
        when = date_el.get("when") or date_el.get("year")
        if when:
            year = when[:4]
            break

    # DOI
    doi = None
    for idno in header.findall(f".//{_T}idno"):
        if idno.get("type", "").upper() == "DOI":
            doi = _text(idno) or None
            break

    return {
        "title": title or None,
        "authors": authors,
        "abstract": abstract or None,
        "year": year,
        "doi": doi,
    }


_parse_tei_header = parse_tei_header  # backwards-compat alias


def _parse_tei_references(tei_xml: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return []

    refs: list[dict[str, Any]] = []
    for bib in root.findall(f".//{_T}listBibl/{_T}biblStruct"):
        # Title: analytic (article) or monogr (book/proceedings)
        title = None
        for container in (f"{_T}analytic", f"{_T}monogr"):
            t_el = bib.find(f"{container}/{_T}title")
            if t_el is not None:
                title = _text(t_el) or None
                break

        # Authors
        authors: list[str] = []
        for author_el in bib.findall(f".//{_T}author"):
            persname = author_el.find(f"{_T}persName")
            if persname is None:
                continue
            forenames = " ".join(_text(f) for f in persname.findall(f"{_T}forename")).strip()
            surname = _text(persname.find(f"{_T}surname"))
            full = f"{forenames} {surname}".strip() if forenames else surname
            if full:
                authors.append(full)

        # Year
        year = None
        for date_el in bib.findall(f".//{_T}date"):
            when = date_el.get("when") or date_el.get("year")
            if when:
                year = when[:4]
                break

        # DOI
        doi = None
        for idno in bib.findall(f".//{_T}idno"):
            if idno.get("type", "").upper() == "DOI":
                doi = _text(idno) or None
                break

        # Venue (monogr title if analytic title differs)
        venue = None
        monogr_title_el = bib.find(f"{_T}monogr/{_T}title")
        if monogr_title_el is not None:
            monogr_title = _text(monogr_title_el)
            if monogr_title and monogr_title != title:
                venue = monogr_title

        refs.append({"title": title, "authors": authors, "year": year, "doi": doi, "venue": venue})

    return refs


# ── run for key ───────────────────────────────────────────────────────────────

def run_grobid_for_key(cfg: BiblioConfig, citekey: str, *, force: bool = False) -> GrobidOutputs:
    """Submit PDF to GROBID and write derivatives under bib/derivatives/grobid/<citekey>/."""
    from .docling import pdf_path_for_key

    key = citekey.lstrip("@")
    pdf_path = pdf_path_for_key(cfg, key)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found for {key}: {pdf_path}")

    out = grobid_outputs_for_key(cfg, key)

    if out.tei_path.exists() and out.header_path.exists() and not force:
        meta = json.loads(out.meta_path.read_text()) if out.meta_path.exists() else {}
        return out

    out.outdir.mkdir(parents=True, exist_ok=True)

    tei_xml = process_pdf(cfg.grobid, pdf_path)
    out.tei_path.write_text(tei_xml, encoding="utf-8")

    header = _parse_tei_header(tei_xml)
    out.header_path.write_text(json.dumps(header, indent=2, ensure_ascii=False), encoding="utf-8")

    references = _parse_tei_references(tei_xml)
    out.references_path.write_text(json.dumps(references, indent=2, ensure_ascii=False), encoding="utf-8")

    meta = {
        "citekey": key,
        "pdf_path": str(pdf_path),
        "tei_path": str(out.tei_path),
        "header_path": str(out.header_path),
        "references_path": str(out.references_path),
        "reference_count": len(references),
        "grobid_url": cfg.grobid.url,
    }
    out.meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return out


# ── install helpers ───────────────────────────────────────────────────────────

def derive_start_cmd(cfg: GrobidConfig) -> list[str] | None:
    """Return a start command derived from installation_path, or None if not applicable."""
    if cfg.installation_path is None:
        return None
    gradlew = cfg.installation_path / "gradlew"
    if gradlew.exists():
        return [str(gradlew), "--stacktrace", "run"]
    jar_dir = cfg.installation_path / "grobid-service" / "build" / "libs"
    if jar_dir.exists():
        jar_candidates = sorted(jar_dir.glob("grobid-service-*.jar"))
        if jar_candidates:
            return ["java", "-jar", str(jar_candidates[-1])]
    return None


# ── reference matching ────────────────────────────────────────────────────────

def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy matching."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def local_refs_path(cfg: BiblioConfig) -> Path:
    """Path to the GROBID local reference match output file."""
    return grobid_out_root(cfg) / "local_refs.json"


def match_grobid_references(
    cfg: BiblioConfig,
    corpus: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Match GROBID-extracted references against the local corpus.

    corpus: list of {citekey, doi, title}.
    Returns: {source_citekey: [{target_citekey, ref_title, ref_doi, match_type}]}.
    DOI match takes precedence; title match is the fallback.
    """
    doi_index: dict[str, str] = {}    # normalized_doi -> citekey
    title_index: dict[str, str] = {}  # normalized_title -> citekey
    grobid_root = grobid_out_root(cfg)

    for record in corpus:
        ck = str(record.get("citekey") or "").strip()
        if not ck:
            continue
        doi = str(record.get("doi") or "").strip().lower()
        if doi:
            doi_index.setdefault(doi, ck)
        title = str(record.get("title") or "").strip()
        if title:
            norm = _normalize_title(title)
            if norm:
                title_index.setdefault(norm, ck)
        # Enrich index from GROBID header (paper may have DOI/title not in srcbib)
        header_path = grobid_root / ck / "header.json"
        if header_path.exists():
            try:
                header = json.loads(header_path.read_text(encoding="utf-8"))
                h_doi = str(header.get("doi") or "").strip().lower()
                if h_doi:
                    doi_index.setdefault(h_doi, ck)
                h_title = str(header.get("title") or "").strip()
                if h_title:
                    norm = _normalize_title(h_title)
                    if norm:
                        title_index.setdefault(norm, ck)
            except Exception:  # noqa: BLE001
                pass

    result: dict[str, list[dict[str, Any]]] = {}
    for record in corpus:
        ck = str(record.get("citekey") or "").strip()
        if not ck:
            continue
        refs_path = grobid_root / ck / "references.json"
        if not refs_path.exists():
            continue
        try:
            refs = json.loads(refs_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        matched: list[dict[str, Any]] = []
        seen: set[str] = set()
        for ref in refs:
            target: str | None = None
            match_type: str | None = None
            ref_doi = str(ref.get("doi") or "").strip().lower()
            if ref_doi and ref_doi in doi_index:
                candidate = doi_index[ref_doi]
                if candidate != ck:
                    target, match_type = candidate, "doi"
            if target is None:
                ref_title = str(ref.get("title") or "").strip()
                if ref_title:
                    norm = _normalize_title(ref_title)
                    if norm and norm in title_index:
                        candidate = title_index[norm]
                        if candidate != ck:
                            target, match_type = candidate, "title"
            if target and target not in seen:
                seen.add(target)
                matched.append({
                    "target_citekey": target,
                    "ref_title": ref.get("title"),
                    "ref_doi": ref.get("doi"),
                    "match_type": match_type,
                })
        if matched:
            result[ck] = matched
    return result


def build_corpus_for_match(cfg: BiblioConfig) -> list[dict[str, Any]]:
    """Build a {citekey, doi, title} corpus from srcbib for reference matching."""
    from .site import _iter_srcbib_records  # lazy to avoid circular at module load
    records = _iter_srcbib_records(cfg)
    if records:
        return [
            {"citekey": r["citekey"], "doi": r.get("doi"), "title": r.get("title")}
            for r in records
        ]
    # Fallback: citekeys only — GROBID headers will fill in DOI/title via match index
    from .citekeys import load_citekeys_md
    keys = load_citekeys_md(cfg.citekeys_path) if cfg.citekeys_path.exists() else []
    return [{"citekey": k, "doi": None, "title": None} for k in keys]


def run_grobid_match(cfg: BiblioConfig) -> tuple[Path, dict[str, list[dict[str, Any]]]]:
    """Run GROBID reference matching, write local_refs.json, return (path, matches)."""
    corpus = build_corpus_for_match(cfg)
    matches = match_grobid_references(cfg, corpus)
    out_path = local_refs_path(cfg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(matches, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path, matches


def get_absent_refs(cfg: BiblioConfig, citekey: str) -> list[dict[str, Any]]:
    """Return GROBID-extracted references for citekey that have no local corpus match.

    Each entry: {title, authors, year, doi, venue}.
    """
    refs_path = grobid_out_root(cfg) / citekey / "references.json"
    if not refs_path.exists():
        return []
    try:
        refs: list[dict[str, Any]] = json.loads(refs_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []

    corpus = build_corpus_for_match(cfg)

    # Build DOI + title index for local corpus
    doi_index: set[str] = set()
    title_index: set[str] = set()
    for record in corpus:
        doi = str(record.get("doi") or "").strip().lower()
        if doi:
            doi_index.add(doi)
        title = str(record.get("title") or "").strip()
        if title:
            norm = _normalize_title(title)
            if norm:
                title_index.add(norm)
        # Also check GROBID header
        ck = str(record.get("citekey") or "")
        if ck:
            header_path = grobid_out_root(cfg) / ck / "header.json"
            if header_path.exists():
                try:
                    h = json.loads(header_path.read_text(encoding="utf-8"))
                    h_doi = str(h.get("doi") or "").strip().lower()
                    if h_doi:
                        doi_index.add(h_doi)
                    h_title = str(h.get("title") or "").strip()
                    if h_title:
                        norm = _normalize_title(h_title)
                        if norm:
                            title_index.add(norm)
                except Exception:  # noqa: BLE001
                    pass

    absent = []
    for ref in refs:
        ref_doi = str(ref.get("doi") or "").strip().lower()
        ref_title = str(ref.get("title") or "").strip()
        matched = (ref_doi and ref_doi in doi_index) or (
            ref_title and _normalize_title(ref_title) in title_index
        )
        if not matched and (ref_title or ref_doi):
            absent.append(ref)
    return absent
