from __future__ import annotations

import json
from pathlib import Path

from biblio.graph import add_openalex_work_to_bib, expand_openalex_reference_graph, load_openalex_seed_records
from biblio.openalex.openalex_cache import OpenAlexCache
from biblio.openalex.openalex_client import OpenAlexClientConfig


class _FakeGraphClient:
    def __init__(self, cfg: OpenAlexClientConfig, works: dict[str, dict]):
        self.cfg = cfg
        self.works = works
        self.calls: list[str] = []
        self.filter_calls: list[str] = []

    def close(self) -> None:
        return

    def get_work(self, work_id: str) -> dict:
        self.calls.append(work_id)
        return self.works[work_id]

    def get_work_by_doi(self, doi: str) -> dict:
        self.calls.append(f"doi:{doi}")
        return self.works["W9"]

    def filter_works(self, *, filter_expr: str, per_page: int | None = None) -> list[dict]:
        self.filter_calls.append(filter_expr)
        if filter_expr == "cites:W1":
            return [self.works["W5"]]
        return []


def test_load_openalex_seed_records_reads_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "resolved.jsonl"
    path.write_text(
        '{"openalex_id":"https://openalex.org/W1"}\n{"openalex_id":"W2"}\n',
        encoding="utf-8",
    )
    records = load_openalex_seed_records(path)
    assert [record["openalex_id"] for record in records] == ["https://openalex.org/W1", "W2"]


def test_expand_openalex_reference_graph_writes_candidates(monkeypatch, tmp_path: Path) -> None:
    cfg = OpenAlexClientConfig(
        base_url="https://api.openalex.org",
        email=None,
        api_key=None,
        timeout_s=30,
        max_retries=0,
        per_page=10,
        select=("id", "referenced_works"),
    )
    cache = OpenAlexCache(root=tmp_path / "cache")
    works = {
        "W1": {
            "id": "https://openalex.org/W1",
            "referenced_works": [
                "https://openalex.org/W2",
                "https://openalex.org/W3",
            ],
        },
        "W3": {
            "id": "https://openalex.org/W3",
            "referenced_works": ["https://openalex.org/W4"],
        },
        "W2": {"id": "https://openalex.org/W2", "display_name": "Two", "publication_year": 2002, "ids": {"doi": "https://doi.org/10.1/2"}},
        "W4": {"id": "https://openalex.org/W4", "display_name": "Four", "publication_year": 2004, "ids": {"doi": "https://doi.org/10.1/4"}},
        "W5": {"id": "https://openalex.org/W5", "display_name": "Five", "publication_year": 2005, "ids": {"doi": "https://doi.org/10.1/5"}},
    }

    import biblio.graph as mod

    fake = _FakeGraphClient(cfg, works=works)
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    out_path = tmp_path / "graph_candidates.json"
    result = expand_openalex_reference_graph(
        cfg=cfg,
        cache=cache,
        records=[
            {"openalex_id": "https://openalex.org/W1"},
            {"openalex_id": "W3"},
        ],
        out_path=out_path,
        direction="both",
    )
    assert result.seeds_with_openalex == 2
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert [item["openalex_id"] for item in payload] == ["W5", "W2", "W4"]
    assert payload[0]["direction"] == "citing"
    assert payload[1]["direction"] == "references"
    assert fake.calls == ["W1", "W2", "W3", "W4"]
    assert fake.filter_calls == ["cites:W1", "cites:W3"]


def test_add_openalex_work_to_bib_by_doi(monkeypatch, tmp_path: Path) -> None:
    cfg = OpenAlexClientConfig(
        base_url="https://api.openalex.org",
        email=None,
        api_key=None,
        timeout_s=30,
        max_retries=0,
        per_page=10,
        select=("id", "display_name", "publication_year", "authorships", "ids"),
    )
    cache = OpenAlexCache(root=tmp_path / "cache")
    works = {
        "W9": {
            "id": "https://openalex.org/W9",
            "display_name": "Added Paper",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "Doe, Jane"}}],
            "ids": {"doi": "https://doi.org/10.1000/test"},
        }
    }

    import biblio.graph as mod

    fake = _FakeGraphClient(cfg, works=works)
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)
    (tmp_path / "bib" / "config").mkdir(parents=True)
    result = add_openalex_work_to_bib(
        cfg=cfg,
        cache=cache,
        repo_root=tmp_path,
        doi="10.1000/test",
    )
    assert result.citekey.startswith("doe_2024_")
    assert result.output_path.exists()
    assert result.citekeys_path.exists()
    text = result.output_path.read_text(encoding="utf-8")
    assert "Added Paper" in text
