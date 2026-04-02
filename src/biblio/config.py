from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from .bibtex_config import load_bibtex_merge_config
from .bibtex import BibtexMergeConfig, default_bibtex_merge_config
from .ledger import LedgerPaths, default_ledger_paths
from .openalex import OpenAlexConfig
from .openalex_config import load_openalex_config
from .pdf_fetch_config import load_pdf_fetch_config
from .pdf_fetch import PdfFetchConfig
from .openalex.openalex_client import OpenAlexClientConfig, openalex_config_from_mapping
from .openalex.openalex_cache import OpenAlexCache


DEFAULT_CONFIG_REL = Path(".projio/biblio/biblio.yml")
LEGACY_CONFIG_REL = Path("bib/config/biblio.yml")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge override into base, recursing into nested dicts. Override wins on conflict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


DEFAULT_CASCADE_SOURCES = ("pool", "openalex", "unpaywall", "ezproxy")


@dataclass(frozen=True)
class PdfFetchCascadeConfig:
    unpaywall_email: str | None
    ezproxy_base: str | None
    ezproxy_mode: str          # "prefix" or "suffix"
    ezproxy_cookie: str | None  # session cookie for authenticated access
    sources: tuple[str, ...]   # cascade order
    delay: float               # seconds between API calls


@dataclass(frozen=True)
class GrobidConfig:
    url: str
    installation_path: Path | None
    timeout_seconds: int
    consolidate_header: bool
    consolidate_citations: bool


@dataclass(frozen=True)
class BiblioConfig:
    repo_root: Path
    citekeys_path: Path
    pdf_root: Path
    pdf_pattern: str
    out_root: Path
    docling_cmd: Sequence[str]
    docling_to: tuple[str, ...]
    docling_image_export_mode: str
    bibtex_merge: BibtexMergeConfig
    pdf_fetch: PdfFetchConfig
    openalex: OpenAlexConfig
    ledger: LedgerPaths
    openalex_client: OpenAlexClientConfig
    openalex_cache: OpenAlexCache
    grobid: GrobidConfig
    rag_python: str | None
    rag_persist_dir: Path
    common_pool_path: Path | None
    pool_search: tuple[Path, ...]
    fetch_queue_path: Path
    pdf_fetch_cascade: PdfFetchCascadeConfig


def _as_cmd(value: Any) -> list[str]:
    if value is None:
        return ["docling"]
    if isinstance(value, str):
        import shlex

        parts = shlex.split(value)
        if not parts:
            return ["docling"]
        return parts
    if isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value):
        return list(value)
    raise TypeError("docling_cmd must be a string or list[str]")


def _get(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = mapping
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_biblio_config(path: str | Path, *, root: str | Path | None = None) -> BiblioConfig:
    path = Path(path)
    repo_root = Path(root) if root is not None else Path.cwd()
    abs_path = (repo_root / path).resolve() if not path.is_absolute() else path

    from .profile import load_user_config
    payload: dict[str, Any] = load_user_config()

    if abs_path.exists():
        project_raw = yaml.safe_load(abs_path.read_text(encoding="utf-8")) or {}
        if not isinstance(project_raw, dict):
            raise TypeError(f"Expected mapping in {abs_path}, got {type(project_raw).__name__}")
        payload = _deep_merge(payload, project_raw)

    citekeys = Path(_get(payload, "citekeys", default=".projio/biblio/citekeys.md"))
    pdf_root = Path(_get(payload, "pdf_root", default="bib/articles"))
    pdf_pattern = str(_get(payload, "pdf_pattern", default="{citekey}/{citekey}.pdf"))
    out_root = Path(_get(payload, "out_root", default="bib/derivatives/docling"))

    docling_cmd = _as_cmd(_get(payload, "docling", "cmd", default="docling"))
    docling_to_raw = _get(payload, "docling", "to", default=["md", "json"])
    if isinstance(docling_to_raw, str):
        docling_to = (docling_to_raw,)
    elif isinstance(docling_to_raw, list) and all(isinstance(x, str) for x in docling_to_raw):
        docling_to = tuple(docling_to_raw)
    else:
        raise TypeError("docling.to must be a string or list[str]")
    image_export_mode = str(_get(payload, "docling", "image_export_mode", default="referenced"))

    def _abs(p: Path) -> Path:
        return (repo_root / p).resolve() if not p.is_absolute() else p

    bibtex_merge = load_bibtex_merge_config(payload, repo_root)
    pdf_fetch = load_pdf_fetch_config(payload, repo_root, dest_root=_abs(pdf_root), dest_pattern=pdf_pattern)
    openalex = load_openalex_config(payload, repo_root)

    openalex_mapping = payload.get("openalex") if isinstance(payload, dict) else None
    openalex_cfg = openalex_config_from_mapping(openalex_mapping if isinstance(openalex_mapping, dict) else None)
    cache_dir = Path((openalex_mapping or {}).get("cache_dir") or "bib/derivatives/openalex/cache")
    openalex_cache = OpenAlexCache(root=_abs(cache_dir))

    grobid_mapping = payload.get("grobid") if isinstance(payload, dict) else None
    if not isinstance(grobid_mapping, dict):
        grobid_mapping = {}
    raw_inst_path = grobid_mapping.get("installation_path")
    grobid = GrobidConfig(
        url=str(grobid_mapping.get("url") or "http://127.0.0.1:8070"),
        installation_path=_abs(Path(raw_inst_path)) if raw_inst_path else None,
        timeout_seconds=int(grobid_mapping.get("timeout_seconds") or 30),
        consolidate_header=bool(grobid_mapping.get("consolidate_header", True)),
        consolidate_citations=bool(grobid_mapping.get("consolidate_citations", False)),
    )

    rag_mapping = payload.get("rag") if isinstance(payload, dict) else None
    if not isinstance(rag_mapping, dict):
        rag_mapping = {}
    raw_rag_python = rag_mapping.get("python") or None
    raw_rag_persist = rag_mapping.get("persist_dir") or ".cache/rag/chroma_db"
    rag_persist_dir = _abs(Path(raw_rag_persist))

    pool_mapping = payload.get("pool") if isinstance(payload, dict) else None
    if not isinstance(pool_mapping, dict):
        pool_mapping = {}
    raw_pool = pool_mapping.get("path") or None
    common_pool_path = Path(os.path.expanduser(str(raw_pool))).resolve() if raw_pool else None

    raw_search = pool_mapping.get("search") or None
    if raw_search:
        if isinstance(raw_search, str):
            raw_search = [raw_search]
        pool_search: tuple[Path, ...] = tuple(
            Path(os.path.expanduser(str(p))).resolve() for p in raw_search
        )
    else:
        pool_search = (common_pool_path,) if common_pool_path else ()

    fetch_queue_path = _abs(Path(_get(payload, "fetch_queue", default=".projio/biblio/fetch_queue.yml")))

    pf_mapping = payload.get("pdf_fetch") if isinstance(payload, dict) else None
    if not isinstance(pf_mapping, dict):
        pf_mapping = {}
    raw_sources = pf_mapping.get("sources")
    if isinstance(raw_sources, list) and all(isinstance(s, str) for s in raw_sources):
        cascade_sources = tuple(raw_sources)
    else:
        cascade_sources = DEFAULT_CASCADE_SOURCES
    pdf_fetch_cascade = PdfFetchCascadeConfig(
        unpaywall_email=str(pf_mapping["unpaywall_email"]) if pf_mapping.get("unpaywall_email") else None,
        ezproxy_base=str(pf_mapping["ezproxy_base"]).rstrip("/") if pf_mapping.get("ezproxy_base") else None,
        ezproxy_mode=str(pf_mapping.get("ezproxy_mode") or "prefix"),
        ezproxy_cookie=str(pf_mapping["ezproxy_cookie"]) if pf_mapping.get("ezproxy_cookie") else None,
        sources=cascade_sources,
        delay=float(pf_mapping.get("delay") or 1.0),
    )

    return BiblioConfig(
        repo_root=repo_root.resolve(),
        citekeys_path=_abs(citekeys),
        pdf_root=_abs(pdf_root),
        pdf_pattern=pdf_pattern,
        out_root=_abs(out_root),
        docling_cmd=tuple(docling_cmd),
        docling_to=tuple(docling_to),
        docling_image_export_mode=image_export_mode,
        bibtex_merge=bibtex_merge,
        pdf_fetch=pdf_fetch,
        openalex=openalex,
        ledger=default_ledger_paths(repo_root),
        openalex_client=openalex_cfg,
        openalex_cache=openalex_cache,
        grobid=grobid,
        rag_python=str(raw_rag_python) if raw_rag_python else None,
        rag_persist_dir=rag_persist_dir,
        common_pool_path=common_pool_path,
        pool_search=pool_search,
        fetch_queue_path=fetch_queue_path,
        pdf_fetch_cascade=pdf_fetch_cascade,
    )


def default_config_path(*, root: str | Path | None = None) -> Path:
    repo_root = Path(root) if root is not None else Path.cwd()
    new_path = (repo_root / DEFAULT_CONFIG_REL).resolve()
    if new_path.exists():
        return new_path
    # Fall back to legacy location for backward compat
    legacy_path = (repo_root / LEGACY_CONFIG_REL).resolve()
    if legacy_path.exists():
        return legacy_path
    # Return new path as the write target even if neither exists
    return new_path
