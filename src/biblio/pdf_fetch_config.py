from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .pdf_fetch import PdfFetchConfig, default_pdf_fetch_config


def _get(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = mapping
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_pdf_fetch_config(
    payload: Mapping[str, Any],
    repo_root: str | Path,
    *,
    dest_root: Path,
    dest_pattern: str,
) -> PdfFetchConfig:
    """
    Read `bibtex.fetch` section from biblio.yml, defaulting to dest_root/dest_pattern.
    """
    repo_root = Path(repo_root).expanduser().resolve()
    defaults = default_pdf_fetch_config(repo_root, dest_root=dest_root, dest_pattern=dest_pattern)

    src_dir = Path(_get(payload, "bibtex", "fetch", "src_dir", default=str(defaults.src_dir)))
    src_glob = str(_get(payload, "bibtex", "fetch", "src_glob", default=defaults.src_glob))
    mode = str(_get(payload, "bibtex", "fetch", "mode", default=defaults.mode))
    hash_mode = str(_get(payload, "bibtex", "fetch", "hash", default=defaults.hash_mode))
    manifest_path = Path(_get(payload, "bibtex", "fetch", "manifest", default=str(defaults.manifest_path)))
    missing_log = Path(_get(payload, "bibtex", "fetch", "missing_log", default=str(defaults.missing_log)))

    # Allow overriding destination separately if desired.
    dest_root_cfg = Path(_get(payload, "bibtex", "fetch", "dest_root", default=str(dest_root)))
    dest_pattern_cfg = str(_get(payload, "bibtex", "fetch", "dest_pattern", default=dest_pattern))

    def _abs(p: Path) -> Path:
        return (repo_root / p).resolve() if not p.is_absolute() else p

    return PdfFetchConfig(
        repo_root=repo_root,
        src_dir=_abs(src_dir),
        src_glob=src_glob,
        dest_root=_abs(dest_root_cfg),
        dest_pattern=dest_pattern_cfg,
        mode=mode,
        hash_mode=hash_mode,
        manifest_path=_abs(manifest_path),
        missing_log=_abs(missing_log),
    )
