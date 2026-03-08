from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import quote


def _require_httpx():
    try:
        return importlib.import_module("httpx")
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            'OpenAlex features require `httpx` (install with `pip install "labpy[openalex]"`).'
        ) from e


def _require_tenacity():
    try:
        return importlib.import_module("tenacity")
    except Exception:  # pragma: no cover
        return None


@dataclass(frozen=True)
class OpenAlexClientConfig:
    base_url: str
    email: str | None
    api_key: str | None
    timeout_s: float
    max_retries: int
    per_page: int
    select: tuple[str, ...]


DEFAULT_SELECT: tuple[str, ...] = (
    "id",
    "doi",
    "display_name",
    "publication_year",
    "cited_by_count",
    "authorships",
    "topics",
    "referenced_works",
    "ids",
)


class OpenAlexClient:
    def __init__(self, cfg: OpenAlexClientConfig):
        self.cfg = cfg
        httpx = _require_httpx()
        self._httpx = httpx
        self._client = httpx.Client(timeout=cfg.timeout_s, follow_redirects=True)

        tenacity = _require_tenacity()
        self._tenacity = tenacity

    def close(self) -> None:
        self._client.close()

    def _params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.cfg.email:
            params["mailto"] = self.cfg.email
        if self.cfg.api_key:
            params["api_key"] = self.cfg.api_key
        if self.cfg.select:
            params["select"] = ",".join(self.cfg.select)
        return params

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.cfg.base_url.rstrip("/") + "/" + path.lstrip("/")
        merged = self._params()
        if params:
            for k, v in params.items():
                if v is None:
                    continue
                merged[k] = str(v)

        def _do() -> dict[str, Any]:
            r = self._client.get(url, params=merged)
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, dict):
                raise TypeError(f"Expected JSON object from {url}, got {type(payload).__name__}")
            return payload

        if self._tenacity is None:
            last: Exception | None = None
            for attempt in range(self.cfg.max_retries + 1):
                try:
                    return _do()
                except Exception as e:
                    last = e
                    if attempt >= self.cfg.max_retries:
                        raise
                    time.sleep(0.5 * (2**attempt))
            assert last is not None
            raise last

        tenacity = self._tenacity
        retry = tenacity.retry(
            reraise=True,
            stop=tenacity.stop_after_attempt(self.cfg.max_retries + 1),
            wait=tenacity.wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=tenacity.retry_if_exception_type(Exception),
        )
        return retry(_do)()

    def get_work_by_doi(self, doi: str) -> dict[str, Any]:
        doi_norm = (doi or "").strip()
        if doi_norm.lower().startswith("https://doi.org/"):
            doi_norm = doi_norm[len("https://doi.org/") :]
        if doi_norm.lower().startswith("doi:"):
            doi_norm = doi_norm[len("doi:") :]
        doi_norm = doi_norm.strip()
        if not doi_norm:
            raise ValueError("Empty DOI")
        # OpenAlex uses /works/doi:<doi>
        return self._get_json(f"works/doi:{quote(doi_norm, safe='')}")

    def get_work(self, work_id: str) -> dict[str, Any]:
        work_id = (work_id or "").strip()
        if not work_id:
            raise ValueError("Empty work_id")
        if work_id.startswith("http"):
            # Accept OpenAlex IDs like https://openalex.org/W...
            work_id = work_id.rstrip("/").split("/")[-1]
        return self._get_json(f"works/{quote(work_id, safe='')}")

    def search_works(self, query: str, *, per_page: int | None = None) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        payload = self._get_json(
            "works",
            params={
                "search": q,
                "per-page": per_page or self.cfg.per_page,
            },
        )
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        out: list[dict[str, Any]] = []
        for item in results:
            if isinstance(item, dict):
                out.append(item)
        return out


def openalex_config_from_mapping(mapping: dict[str, Any] | None) -> OpenAlexClientConfig:
    m = mapping or {}
    base_url = str(m.get("base_url") or "https://api.openalex.org").rstrip("/")
    email = m.get("email")
    email = str(email).strip() if isinstance(email, str) and email.strip() else None
    api_key = m.get("api_key")
    api_key = str(api_key).strip() if isinstance(api_key, str) and api_key.strip() else None
    timeout_s = float(m.get("timeout_s") or 30)
    max_retries = int(m.get("max_retries") or 3)
    per_page = int(m.get("per_page") or 25)

    select_raw = m.get("select")
    if select_raw is None:
        select = DEFAULT_SELECT
    elif isinstance(select_raw, str):
        select = tuple(s.strip() for s in select_raw.split(",") if s.strip())
    elif isinstance(select_raw, list) and all(isinstance(x, str) for x in select_raw):
        select = tuple(select_raw)
    else:
        select = DEFAULT_SELECT

    return OpenAlexClientConfig(
        base_url=base_url,
        email=email,
        api_key=api_key,
        timeout_s=timeout_s,
        max_retries=max_retries,
        per_page=per_page,
        select=select,
    )

