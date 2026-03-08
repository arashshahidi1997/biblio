from __future__ import annotations

import csv
import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..ledger import append_jsonl, new_run_id, utc_now_iso


@dataclass(frozen=True)
class OpenAlexConfig:
    repo_root: Path
    src_dir: Path
    src_glob: str
    cache_root: Path
    out_jsonl: Path
    out_csv: Path | None
    mailto: str | None
    api_base: str


def _require_pybtex():
    try:
        from pybtex.database import parse_file  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            'biblio OpenAlex resolution requires `pybtex` (install with `pip install "labpy[biblio]"`).'
        ) from e


def _iter_bib_files(src_dir: Path, glob: str) -> list[Path]:
    if not src_dir.exists():
        return []
    return sorted(p for p in src_dir.glob(glob) if p.is_file())


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip().strip("{}").strip()
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    doi = doi.strip().lower()
    return doi or None


def _normalize_title(value: str | None) -> str:
    return " ".join((value or "").replace("{", "").replace("}", "").split()).strip()


def _title_cache_key(title: str) -> str:
    return hashlib.sha256(title.encode("utf-8")).hexdigest()


def _cache_paths(cfg: OpenAlexConfig, *, doi: str | None, title: str) -> tuple[Path | None, Path]:
    doi_path = None
    if doi:
        doi_key = doi.replace("/", "__")
        doi_path = cfg.cache_root / "doi" / f"{doi_key}.json"
    title_path = cfg.cache_root / "title" / f"{_title_cache_key(title)}.json"
    return doi_path, title_path


def _load_cached_json(path: Path | None) -> Any | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_cache(path: Path | None, payload: Any) -> Path | None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _default_fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url) as resp:  # nosec B310
        return json.load(resp)


def _works_url(cfg: OpenAlexConfig, *, doi: str | None = None, title: str | None = None) -> str:
    if doi:
        encoded = urllib.parse.quote(doi, safe="")
        url = f"{cfg.api_base}/works/https://doi.org/{encoded}"
    else:
        params = {"search": title or "", "per-page": "5"}
        url = f"{cfg.api_base}/works?{urllib.parse.urlencode(params)}"
    if cfg.mailto:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}mailto={urllib.parse.quote(cfg.mailto, safe='@')}"
    return url


def _extract_work_id(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    work_id = payload.get("id")
    if isinstance(work_id, str) and work_id:
        return work_id
    return None


def _resolve_entry(
    cfg: OpenAlexConfig,
    *,
    citekey: str,
    source_bib: Path,
    title: str,
    doi: str | None,
    fetch_json: Callable[[str], Any],
) -> dict[str, Any]:
    doi_cache_path, title_cache_path = _cache_paths(cfg, doi=doi, title=title)

    payload: Any | None = None
    resolution_method = ""
    cache_path: Path | None = None

    if doi:
        payload = _load_cached_json(doi_cache_path)
        if payload is None:
            try:
                payload = fetch_json(_works_url(cfg, doi=doi))
            except Exception:
                payload = None
            if payload is not None:
                _write_cache(doi_cache_path, payload)
        if isinstance(payload, dict) and _extract_work_id(payload):
            resolution_method = "doi"
            cache_path = doi_cache_path

    if not resolution_method:
        search_payload = _load_cached_json(title_cache_path)
        if search_payload is None:
            try:
                search_payload = fetch_json(_works_url(cfg, title=title))
            except Exception:
                search_payload = None
            if search_payload is not None:
                _write_cache(title_cache_path, search_payload)
        cache_path = title_cache_path
        payload = None
        if isinstance(search_payload, dict):
            results = search_payload.get("results")
            if isinstance(results, list):
                if len(results) == 1 and isinstance(results[0], dict):
                    payload = results[0]
                    resolution_method = "title"
                elif len(results) > 1 and isinstance(results[0], dict):
                    payload = results[0]
                    resolution_method = "title"

    work_id = _extract_work_id(payload if isinstance(payload, dict) else None)
    status = "resolved" if work_id else "unresolved"

    return {
        "citekey": citekey,
        "source_bib": str(source_bib),
        "title": title,
        "doi": doi,
        "openalex_id": work_id,
        "resolution_method": resolution_method or ("doi" if doi else "title"),
        "status": status,
        "provenance": {
            "cache_path": str(cache_path) if cache_path is not None else None,
        },
    }


def resolve_openalex(
    cfg: OpenAlexConfig,
    *,
    fetch_json: Callable[[str], Any] | None = None,
) -> dict[str, int]:
    _require_pybtex()
    from pybtex.database import parse_file

    fetch_json = fetch_json or _default_fetch_json
    run_id = new_run_id("openalex_resolve")
    bib_files = _iter_bib_files(cfg.src_dir, cfg.src_glob)
    if not bib_files:
        raise FileNotFoundError(f"No .bib files found under {cfg.src_dir} (glob={cfg.src_glob!r})")

    rows: list[dict[str, Any]] = []
    for bib_path in bib_files:
        db = parse_file(str(bib_path))
        for citekey, entry in sorted(db.entries.items(), key=lambda kv: kv[0]):
            title = _normalize_title(entry.fields.get("title"))
            doi = _normalize_doi(entry.fields.get("doi"))
            rows.append(
                _resolve_entry(
                    cfg,
                    citekey=citekey,
                    source_bib=bib_path,
                    title=title,
                    doi=doi,
                    fetch_json=fetch_json,
                )
            )

    rows.sort(key=lambda row: (row["citekey"], row["source_bib"]))

    cfg.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with cfg.out_jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    if cfg.out_csv is not None:
        cfg.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with cfg.out_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "citekey",
                    "source_bib",
                    "title",
                    "doi",
                    "openalex_id",
                    "resolution_method",
                    "status",
                    "cache_path",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "citekey": row["citekey"],
                        "source_bib": row["source_bib"],
                        "title": row["title"],
                        "doi": row["doi"],
                        "openalex_id": row["openalex_id"],
                        "resolution_method": row["resolution_method"],
                        "status": row["status"],
                        "cache_path": row["provenance"]["cache_path"],
                    }
                )

    summary = {
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "stage": "openalex_resolve",
        "status": "success",
        "source_count": len(bib_files),
        "entry_count": len(rows),
        "resolved": sum(1 for row in rows if row["status"] == "resolved"),
        "unresolved": sum(1 for row in rows if row["status"] == "unresolved"),
        "out_jsonl": str(cfg.out_jsonl),
        "out_csv": str(cfg.out_csv) if cfg.out_csv is not None else None,
        "cache_root": str(cfg.cache_root),
    }
    append_jsonl(cfg.repo_root / "bib" / "logs" / "runs" / "openalex_resolve.jsonl", summary)

    return {
        "sources": len(bib_files),
        "entries": len(rows),
        "resolved": sum(1 for row in rows if row["status"] == "resolved"),
        "unresolved": sum(1 for row in rows if row["status"] == "unresolved"),
    }


def default_openalex_config(repo_root: str | Path) -> OpenAlexConfig:
    repo_root = Path(repo_root).expanduser().resolve()
    bib_root = repo_root / "bib"
    return OpenAlexConfig(
        repo_root=repo_root,
        src_dir=bib_root / "srcbib",
        src_glob="*.bib",
        cache_root=bib_root / "derivatives" / "openalex" / "cache",
        out_jsonl=bib_root / "derivatives" / "openalex" / "resolved.jsonl",
        out_csv=bib_root / "derivatives" / "openalex" / "resolved.csv",
        mailto=None,
        api_base="https://api.openalex.org",
    )
