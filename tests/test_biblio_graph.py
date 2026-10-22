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
    monkeypatch.setattr(mod, "fetch_doi_csl", lambda doi: None)      # registry has no record
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


def _cfg_cache(tmp_path):
    cfg = OpenAlexClientConfig(base_url="https://api.openalex.org", email=None, api_key=None, timeout_s=30,
                               max_retries=0, per_page=10, select=("id",))
    return cfg, OpenAlexCache(root=tmp_path / "cache")


def test_add_doi_prefers_registry_metadata(monkeypatch, tmp_path: Path) -> None:
    import biblio.graph as mod
    cfg, cache = _cfg_cache(tmp_path)
    works = {"W9": {"id": "https://openalex.org/W9", "doi": "https://doi.org/10.1000/ch",
                    "display_name": "Wrong title", "publication_year": 1970,
                    "authorships": [{"author": {"display_name": "И. Лакатос"}}]}}
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: _FakeGraphClient(cfg, works=works))
    monkeypatch.setattr(mod, "fetch_doi_csl", lambda doi: {
        "type": "book-chapter", "title": "Falsification and the Methodology of Scientific Research Programmes",
        "author": [{"family": "Lakatos", "given": "I."}], "issued": {"date-parts": [[1970]]},
        "container-title": "Criticism and the Growth of Knowledge", "DOI": "10.1000/ch"})
    (tmp_path / "bib" / "config").mkdir(parents=True)
    result = add_openalex_work_to_bib(cfg=cfg, cache=cache, repo_root=tmp_path, doi="10.1000/ch")
    text = result.output_path.read_text(encoding="utf-8")
    assert result.citekey == "lakatos_1970_FalsificationMethodology"
    assert "@incollection{lakatos_1970_FalsificationMethodology" in text
    assert "booktitle = {Criticism and the Growth of Knowledge}" in text
    assert result.openalex_id == "W9"


def test_add_doi_rejects_openalex_work_with_other_doi(monkeypatch, tmp_path: Path) -> None:
    import biblio.graph as mod
    cfg, cache = _cfg_cache(tmp_path)
    works = {"W9": {"id": "https://openalex.org/W9", "doi": "https://doi.org/10.4230/other",
                    "display_name": "Some other paper", "publication_year": 2025, "authorships": []}}
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: _FakeGraphClient(cfg, works=works))
    monkeypatch.setattr(mod, "fetch_doi_csl", lambda doi: None)
    (tmp_path / "bib" / "config").mkdir(parents=True)
    import pytest
    with pytest.raises(ValueError, match="different work"):
        add_openalex_work_to_bib(cfg=cfg, cache=cache, repo_root=tmp_path, doi="10.48550/arXiv.2404.16130")


def test_expand_records_edges_between_held_papers(monkeypatch, tmp_path: Path) -> None:
    import json
    import biblio.graph as mod
    cfg, cache = _cfg_cache(tmp_path)
    works = {
        "W1": {"id": "https://openalex.org/W1", "display_name": "Held A", "referenced_works":
               ["https://openalex.org/W2", "https://openalex.org/W3"]},
        "W2": {"id": "https://openalex.org/W2", "display_name": "Held B", "referenced_works": []},
        "W3": {"id": "https://openalex.org/W3", "display_name": "External", "referenced_works": []},
    }
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: _FakeGraphClient(cfg, works=works))
    records = [{"citekey": "a_2020_A", "openalex_id": "W1"}, {"citekey": "b_2019_B", "openalex_id": "W2"}]
    out = tmp_path / "openalex" / "graph_candidates.json"
    result = expand_openalex_reference_graph(cfg=cfg, cache=cache, records=records, out_path=out,
                                             direction="references")
    candidates = json.loads(out.read_text())
    assert [c["openalex_id"] for c in candidates] == ["W3"]          # held papers are not candidates
    edges = json.loads((out.parent / "local_edges.json").read_text())
    assert edges == [{"relation": "references", "source_citekey": "a_2020_A", "source_openalex_id": "W1",
                      "target_citekey": "b_2019_B", "target_openalex_id": "W2"}]
    assert result.local_edges == 1


def test_build_local_edges_from_cache_only(tmp_path: Path) -> None:
    import json
    from biblio.graph import build_local_edges
    cfg, cache = _cfg_cache(tmp_path)
    cache.save_json(cache.path_for_work_id("W1"), {"id": "https://openalex.org/W1",
                                                   "referenced_works": ["https://openalex.org/W2"]})
    records = [{"citekey": "a_2020_A", "openalex_id": "W1"}, {"citekey": "b_2019_B", "openalex_id": "W2"},
               {"citekey": "c_2018_C", "openalex_id": "W4"}]
    edges, missing = build_local_edges(cfg=cfg, cache=cache, records=records, out_path=tmp_path / "local_edges.json")
    assert [(e["source_citekey"], e["target_citekey"]) for e in edges] == [("a_2020_A", "b_2019_B")]
    assert missing == 2                                                  # W2 and W4 not cached
    assert json.loads((tmp_path / "local_edges.json").read_text()) == edges
