from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(record), sort_keys=True) + "\n")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class LedgerPaths:
    root: Path
    docling_runs: Path
    bibtex_fetch_runs: Path
    bibtex_merge_runs: Path
    openalex_resolve_runs: Path


def default_ledger_paths(repo_root: str | Path) -> LedgerPaths:
    repo_root = Path(repo_root).expanduser().resolve()
    root = repo_root / ".projio" / "biblio" / "logs" / "runs"
    return LedgerPaths(
        root=root,
        docling_runs=root / "docling.jsonl",
        bibtex_fetch_runs=root / "bibtex_fetch.jsonl",
        bibtex_merge_runs=root / "bibtex_merge.jsonl",
        openalex_resolve_runs=root / "openalex_resolve.jsonl",
    )
