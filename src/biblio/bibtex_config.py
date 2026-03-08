from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .bibtex import BibtexMergeConfig, default_bibtex_merge_config


def _get(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = mapping
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_bibtex_merge_config(payload: Mapping[str, Any], repo_root: str | Path) -> BibtexMergeConfig:
    """
    Read a `bibtex.merge` section from biblio.yml.

    If the section is missing, returns defaults.
    """
    repo_root = Path(repo_root).expanduser().resolve()
    defaults = default_bibtex_merge_config(repo_root)

    src_dir = Path(_get(payload, "bibtex", "merge", "src_dir", default=str(defaults.src_dir)))
    src_glob = str(_get(payload, "bibtex", "merge", "src_glob", default=defaults.src_glob))
    out_bib = Path(_get(payload, "bibtex", "merge", "out_bib", default=str(defaults.out_bib)))
    file_mode = str(_get(payload, "bibtex", "merge", "file_field_mode", default=defaults.file_field_mode))
    file_template = str(_get(payload, "bibtex", "merge", "file_field_template", default=defaults.file_field_template))
    dup_log = Path(_get(payload, "bibtex", "merge", "duplicates_log", default=str(defaults.duplicates_log)))

    def _abs(p: Path) -> Path:
        return (repo_root / p).resolve() if not p.is_absolute() else p

    return BibtexMergeConfig(
        repo_root=repo_root,
        src_dir=_abs(src_dir),
        src_glob=src_glob,
        out_bib=_abs(out_bib),
        file_field_mode=file_mode,
        file_field_template=file_template,
        duplicates_log=_abs(dup_log),
    )
