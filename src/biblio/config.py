from __future__ import annotations

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


DEFAULT_CONFIG_REL = Path("bib/config/biblio.yml")


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
    payload: dict[str, Any] = {}
    if abs_path.exists():
        payload = yaml.safe_load(abs_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise TypeError(f"Expected mapping in {abs_path}, got {type(payload).__name__}")

    citekeys = Path(_get(payload, "citekeys", default="bib/config/citekeys.md"))
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
    )


def default_config_path(*, root: str | Path | None = None) -> Path:
    repo_root = Path(root) if root is not None else Path.cwd()
    return (repo_root / DEFAULT_CONFIG_REL).resolve()
