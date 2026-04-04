from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip()
    d = d.removeprefix("doi:").removeprefix("DOI:")
    if d.lower().startswith("https://doi.org/"):
        d = d[len("https://doi.org/") :]
    d = d.strip().lower()
    return d or None


@dataclass(frozen=True)
class OpenAlexCache:
    root: Path

    def path_for_doi(self, doi: str) -> Path:
        key = normalize_doi(doi) or doi
        h = _sha1(key)
        return self.root / "doi" / h[:2] / f"{h}.json"

    def path_for_work_id(self, work_id: str) -> Path:
        wid = (work_id or "").strip()
        if wid.startswith("http"):
            wid = wid.rstrip("/").split("/")[-1]
        h = _sha1(wid)
        return self.root / "work" / h[:2] / f"{h}.json"

    def path_for_author(self, author_id: str) -> Path:
        aid = (author_id or "").strip()
        if aid.startswith("http"):
            aid = aid.rstrip("/").split("/")[-1]
        h = _sha1(aid)
        return self.root / "author" / h[:2] / f"{h}.json"

    def path_for_institution(self, institution_id: str) -> Path:
        iid = (institution_id or "").strip()
        if iid.startswith("http"):
            iid = iid.rstrip("/").split("/")[-1]
        h = _sha1(iid)
        return self.root / "institution" / h[:2] / f"{h}.json"

    def path_for_search(self, query: str) -> Path:
        h = _sha1(query.strip().lower())
        return self.root / "search" / h[:2] / f"{h}.json"

    def load_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def save_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)

