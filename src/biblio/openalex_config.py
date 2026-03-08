from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .openalex import OpenAlexConfig, default_openalex_config


def _get(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = mapping
    for key in keys:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_openalex_config(payload: Mapping[str, Any], repo_root: str | Path) -> OpenAlexConfig:
    repo_root = Path(repo_root).expanduser().resolve()
    defaults = default_openalex_config(repo_root)

    src_dir = Path(_get(payload, "openalex", "src_dir", default=str(defaults.src_dir)))
    src_glob = str(_get(payload, "openalex", "src_glob", default=defaults.src_glob))
    cache_root = Path(_get(payload, "openalex", "cache_root", default=str(defaults.cache_root)))
    out_jsonl = Path(_get(payload, "openalex", "out_jsonl", default=str(defaults.out_jsonl)))
    out_csv_raw = _get(payload, "openalex", "out_csv", default=str(defaults.out_csv) if defaults.out_csv else None)
    out_csv = Path(out_csv_raw) if out_csv_raw else None
    mailto_raw = _get(payload, "openalex", "mailto", default=defaults.mailto)
    mailto = str(mailto_raw) if mailto_raw else None
    api_base = str(_get(payload, "openalex", "api_base", default=defaults.api_base))

    def _abs(p: Path) -> Path:
        return (repo_root / p).resolve() if not p.is_absolute() else p

    return OpenAlexConfig(
        repo_root=repo_root,
        src_dir=_abs(src_dir),
        src_glob=src_glob,
        cache_root=_abs(cache_root),
        out_jsonl=_abs(out_jsonl),
        out_csv=_abs(out_csv) if out_csv is not None else None,
        mailto=mailto,
        api_base=api_base,
    )
