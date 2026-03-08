from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from biblio.openalex.openalex_cache import OpenAlexCache
from biblio.openalex.openalex_client import OpenAlexClientConfig
from biblio.openalex.openalex_resolve import ResolveOptions, resolve_srcbib_to_openalex


class _FakeClient:
    def __init__(self, cfg: OpenAlexClientConfig, responses: dict[str, dict[str, Any]]):
        self.cfg = cfg
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def close(self) -> None:
        return

    def get_work_by_doi(self, doi: str) -> dict[str, Any]:
        self.calls.append(("doi", doi))
        if doi in self.responses:
            return self.responses[doi]
        raise RuntimeError("not found")

    def search_works(self, query: str, *, per_page: int | None = None) -> list[dict[str, Any]]:
        self.calls.append(("search", query))
        return []


def test_openalex_resolve_uses_cache_without_httpx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Create srcbib with a DOI.
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    (src_dir / "a.bib").write_text(
        "@article{a2020, title={A}, year={2020}, doi={10.1234/ABC}}\n",
        encoding="utf-8",
    )

    oa_cfg = OpenAlexClientConfig(
        base_url="https://api.openalex.org",
        email=None,
        api_key=None,
        timeout_s=30,
        max_retries=0,
        per_page=10,
        select=("id", "display_name"),
    )
    cache = OpenAlexCache(root=tmp_path / "cache")

    response = {
        "id": "https://openalex.org/W123",
        "display_name": "A",
        "publication_year": 2020,
        "cited_by_count": 1,
        "ids": {"openalex": "https://openalex.org/W123"},
        "authorships": [],
        "topics": [],
        "referenced_works": [],
    }

    # First run: fake client is used and cache is written.
    fake = _FakeClient(oa_cfg, responses={"10.1234/abc": response})

    import biblio.openalex.openalex_resolve as mod

    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    out = tmp_path / "resolved.jsonl"
    opts = ResolveOptions(prefer_doi=True, fallback_title_search=False, per_page=10, strict=True, force=False)
    counts = resolve_srcbib_to_openalex(
        cfg=oa_cfg,
        cache=cache,
        src_dir=src_dir,
        src_glob="*.bib",
        out_path=out,
        out_format="jsonl",
        limit=None,
        opts=opts,
    )
    assert counts["resolved"] == 1
    assert fake.calls and fake.calls[0][0] == "doi"

    # Second run: no client call if cache is hit (we swap in a client that would fail).
    fake2 = _FakeClient(oa_cfg, responses={})
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake2)
    counts2 = resolve_srcbib_to_openalex(
        cfg=oa_cfg,
        cache=cache,
        src_dir=src_dir,
        src_glob="*.bib",
        out_path=out,
        out_format="jsonl",
        limit=None,
        opts=opts,
    )
    assert counts2["resolved"] == 1
    assert fake2.calls == []


def test_openalex_missing_httpx_message(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force importlib to fail for httpx so we can assert the message.
    import biblio.openalex.openalex_client as client_mod

    real = importlib.import_module

    def _fake_import(name: str, package: str | None = None):
        if name == "httpx":
            raise ModuleNotFoundError("no httpx")
        return real(name, package=package)

    monkeypatch.setattr(client_mod.importlib, "import_module", _fake_import)
    with pytest.raises(RuntimeError) as e:
        client_mod._require_httpx()
    assert "labpy[openalex]" in str(e.value)

