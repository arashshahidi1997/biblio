"""Smoke tests for biblio.mcp.graph_expand."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from biblio.mcp import graph_expand


def _minimal_biblio_yml(root: Path) -> None:
    """Write a minimal biblio.yml so _load_cfg succeeds."""
    cfg_dir = root / "bib" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (root / "biblio.yml").write_text(
        "repo_root: .\n"
        "bibtex_merge:\n"
        "  src_dirs: [bib/srcbib]\n"
        "  out_bib: bib/main.bib\n"
        "openalex:\n"
        "  cache_dir: .cache/openalex\n",
        encoding="utf-8",
    )


def test_graph_expand_error_when_no_resolved_jsonl(tmp_path: Path) -> None:
    """Returns error dict when resolved.jsonl doesn't exist."""
    _minimal_biblio_yml(tmp_path)
    result = graph_expand(root=tmp_path)
    assert "error" in result
    assert "No seed records found" in result["error"]


def test_graph_expand_calls_expand_correctly(monkeypatch, tmp_path: Path) -> None:
    """Correctly calls expand_openalex_reference_graph with the right args."""
    _minimal_biblio_yml(tmp_path)

    # Write seed records
    openalex_dir = tmp_path / "bib" / "derivatives" / "openalex"
    openalex_dir.mkdir(parents=True, exist_ok=True)
    (openalex_dir / "resolved.jsonl").write_text(
        '{"openalex_id":"W1","citekey":"smith2020"}\n'
        '{"openalex_id":"W2","citekey":"doe2021"}\n',
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    class FakeResult:
        total_inputs = 2
        seeds_with_openalex = 2
        candidates = 5
        output_path = openalex_dir / "graph_candidates.json"

    def fake_expand(**kwargs: Any) -> FakeResult:
        captured.update(kwargs)
        return FakeResult()

    import biblio.graph as graph_mod
    monkeypatch.setattr(graph_mod, "expand_openalex_reference_graph", fake_expand)

    result = graph_expand(root=tmp_path, citekeys=["smith2020"], direction="both", merge=False, force=True)

    assert result["total_inputs"] == 2
    assert result["seeds_with_openalex"] == 2
    assert result["candidates"] == 5
    assert captured["direction"] == "both"
    assert captured["merge"] is False
    assert captured["force"] is True
    assert captured["seed_citekeys"] == ["smith2020"]
    assert len(captured["records"]) == 2


# ── graph promote: seed scoping ─────────────────────────────────────────────


def _promote_fixture(root: Path) -> None:
    _minimal_biblio_yml(root)
    oa = root / "bib" / "derivatives" / "openalex"
    oa.mkdir(parents=True, exist_ok=True)
    (oa / "resolved.jsonl").write_text(
        json.dumps({"citekey": "ye_2026_BrainWide", "openalex_id": "https://openalex.org/W1"}) + "\n"
        + json.dumps({"citekey": "swanson_2025_Topography", "openalex_id": "W2"}) + "\n",
        encoding="utf-8",
    )
    cands = [
        {"seed_openalex_id": "W1", "openalex_id": "W10", "doi": "https://doi.org/10.1/ye-a", "cited_by_count": 5},
        {"seed_openalex_id": "W1", "openalex_id": "W11", "doi": "10.1/shared", "cited_by_count": 9},
        {"seed_openalex_id": "W2", "openalex_id": "W11", "doi": "10.1/shared", "cited_by_count": 9},
        {"seed_openalex_id": "W2", "openalex_id": "W20", "doi": "10.1/swanson-a", "cited_by_count": 50},
    ]
    (oa / "graph_candidates.json").write_text(json.dumps(cands), encoding="utf-8")


def test_graph_promote_scoped_to_one_seed(monkeypatch, tmp_path: Path) -> None:
    from biblio.mcp import graph_promote

    _promote_fixture(tmp_path)
    ingested: list[list[str]] = []

    def fake_ingest(dois, *, root, tags=None):
        ingested.append(list(dois))
        return {"count": len(dois), "citekeys": [f"k{i}" for i in range(len(dois))]}

    monkeypatch.setattr("biblio.mcp.ingest_dois", fake_ingest)
    res = graph_promote(root=tmp_path, seed_citekeys=["ye_2026_BrainWide"], tags=["ye"])

    assert res["promoted"] == 2
    assert sorted(ingested[0]) == ["10.1/shared", "https://doi.org/10.1/ye-a"]
    assert res["by_seed"] == {"ye_2026_BrainWide": 2}
    assert res["candidates_in_scope"] == 2
    assert res["candidates_total"] == 4
    assert "warning" not in res


def test_graph_promote_unscoped_warns_and_dedupes(tmp_path: Path) -> None:
    from biblio.mcp import graph_promote

    _promote_fixture(tmp_path)
    res = graph_promote(root=tmp_path, dry_run=True)

    assert res["dry_run"] is True
    assert res["candidates_selected"] == 3  # the shared work counted once
    assert set(res["by_seed"]) == {"ye_2026_BrainWide", "swanson_2025_Topography"}
    assert "2 seeds" in res["warning"]


def test_graph_promote_unknown_seed_is_an_error(tmp_path: Path) -> None:
    from biblio.mcp import graph_promote

    _promote_fixture(tmp_path)
    res = graph_promote(root=tmp_path, seed_citekeys=["nobody_2020_X"], dry_run=True)
    assert "nobody_2020_X" in res["error"]
