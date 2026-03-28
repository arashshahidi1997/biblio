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
