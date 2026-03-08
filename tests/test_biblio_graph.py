from __future__ import annotations

import json
from pathlib import Path

from biblio.graph import expand_openalex_reference_graph, load_openalex_seed_records
from biblio.openalex.openalex_cache import OpenAlexCache
from biblio.openalex.openalex_client import OpenAlexClientConfig


class _FakeGraphClient:
    def __init__(self, cfg: OpenAlexClientConfig, works: dict[str, dict]):
        self.cfg = cfg
        self.works = works
        self.calls: list[str] = []

    def close(self) -> None:
        return

    def get_work(self, work_id: str) -> dict:
        self.calls.append(work_id)
        return self.works[work_id]


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
    )
    assert result.seeds_with_openalex == 2
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert [item["openalex_id"] for item in payload] == ["W2", "W4"]
    assert fake.calls == ["W1", "W3"]
