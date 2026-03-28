"""Tests for concept extraction, comparison tables, and reading list curation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ── Concept schema validation ─────────────────────────────────────────────


def test_validate_concepts_valid():
    from biblio.concepts import validate_concepts

    raw = {
        "methods": ["transformer", "attention"],
        "datasets": ["ImageNet"],
        "metrics": ["accuracy"],
        "domains": ["cv"],
        "techniques": ["dropout"],
    }
    result = validate_concepts(raw)
    assert set(result.keys()) == {"methods", "datasets", "metrics", "domains", "techniques"}
    assert result["methods"] == ["transformer", "attention"]
    assert result["datasets"] == ["ImageNet"]


def test_validate_concepts_empty_and_missing():
    from biblio.concepts import validate_concepts

    result = validate_concepts({})
    for cat in ("methods", "datasets", "metrics", "domains", "techniques"):
        assert result[cat] == []


def test_validate_concepts_strips_whitespace_and_empties():
    from biblio.concepts import validate_concepts

    raw = {
        "methods": ["  transformer  ", "", None, "attention"],
        "datasets": "not a list",
        "metrics": [123, "f1"],
        "domains": [],
        "techniques": ["  "],
    }
    result = validate_concepts(raw)
    assert result["methods"] == ["transformer", "attention"]
    assert result["datasets"] == []  # non-list becomes empty
    assert result["metrics"] == ["123", "f1"]
    assert result["techniques"] == []  # whitespace-only stripped


def test_validate_concepts_extra_keys_ignored():
    from biblio.concepts import validate_concepts

    raw = {
        "methods": ["x"],
        "datasets": [],
        "metrics": [],
        "domains": [],
        "techniques": [],
        "extra_key": ["should be ignored"],
    }
    result = validate_concepts(raw)
    assert "extra_key" not in result
    assert result["methods"] == ["x"]


# ── Concept save/load roundtrip ───────────────────────────────────────────


def test_concept_save_load_roundtrip(tmp_path):
    from biblio.concepts import CONCEPT_CATEGORIES, load_concepts, save_concepts

    cfg = MagicMock()
    cfg.repo_root = tmp_path

    concepts = {
        "methods": ["GAN", "VAE"],
        "datasets": ["CelebA"],
        "metrics": ["FID"],
        "domains": ["generative modeling"],
        "techniques": ["progressive growing"],
    }

    path = save_concepts(cfg, "smith_2024_Test", concepts)
    assert path.exists()

    loaded = load_concepts(cfg, "smith_2024_Test")
    assert loaded is not None
    for cat in CONCEPT_CATEGORIES:
        assert loaded[cat] == concepts[cat]


def test_load_concepts_missing(tmp_path):
    from biblio.concepts import load_concepts

    cfg = MagicMock()
    cfg.repo_root = tmp_path

    assert load_concepts(cfg, "nonexistent") is None


# ── Concept index building ────────────────────────────────────────────────


@patch("biblio.concepts.load_biblio_config")
@patch("biblio.concepts.default_config_path")
def test_build_concept_index(mock_cfg_path, mock_load_cfg, tmp_path):
    from biblio.concepts import CONCEPT_DIR_REL, CONCEPT_INDEX_REL, build_concept_index

    mock_cfg_path.return_value = tmp_path / "config.yml"
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg

    # Create concept files
    concepts_dir = tmp_path / CONCEPT_DIR_REL
    concepts_dir.mkdir(parents=True)

    yaml.safe_dump(
        {"citekey": "paper_a", "methods": ["transformer"], "datasets": ["ImageNet"], "metrics": [], "domains": ["cv"], "techniques": []},
        (concepts_dir / "paper_a.yml").open("w"),
    )
    yaml.safe_dump(
        {"citekey": "paper_b", "methods": ["transformer", "cnn"], "datasets": [], "metrics": ["accuracy"], "domains": ["cv"], "techniques": []},
        (concepts_dir / "paper_b.yml").open("w"),
    )

    result = build_concept_index(tmp_path)

    assert result["total_papers"] == 2
    assert result["total_concepts"] >= 3  # transformer, imagenet, cnn, accuracy, cv
    c2ck = result["concept_to_citekeys"]
    assert "transformer" in c2ck
    assert set(c2ck["transformer"]) == {"paper_a", "paper_b"}
    assert "cv" in c2ck
    assert set(c2ck["cv"]) == {"paper_a", "paper_b"}

    # Index file written
    index_path = tmp_path / CONCEPT_INDEX_REL
    assert index_path.exists()


# ── Concept search ────────────────────────────────────────────────────────


@patch("biblio.concepts.load_biblio_config")
@patch("biblio.concepts.default_config_path")
def test_search_concepts(mock_cfg_path, mock_load_cfg, tmp_path):
    from biblio.concepts import CONCEPT_INDEX_REL, search_concepts

    mock_cfg_path.return_value = tmp_path / "config.yml"
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg

    # Write an index
    index_path = tmp_path / CONCEPT_INDEX_REL
    index_path.parent.mkdir(parents=True, exist_ok=True)
    yaml.safe_dump(
        {"concept_to_citekeys": {"transformer": ["p1", "p2"], "cnn": ["p2"], "transfer learning": ["p1"]}},
        index_path.open("w"),
    )

    result = search_concepts("transform", tmp_path)
    assert result["total_matches"] == 1
    assert result["matches"][0]["concept"] == "transformer"
    assert set(result["matches"][0]["citekeys"]) == {"p1", "p2"}

    # Broader search
    result2 = search_concepts("er", tmp_path)
    assert result2["total_matches"] >= 2  # transformer, transfer learning


@patch("biblio.concepts.load_biblio_config")
@patch("biblio.concepts.default_config_path")
def test_search_concepts_no_index(mock_cfg_path, mock_load_cfg, tmp_path):
    from biblio.concepts import search_concepts

    mock_cfg_path.return_value = tmp_path / "config.yml"
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg

    result = search_concepts("anything", tmp_path)
    assert result["total_matches"] == 0
    assert "hint" in result


# ── extract_concepts prompt_only ──────────────────────────────────────────


@patch("biblio.summarize.summary_path_for_key")
@patch("biblio.concepts.load_biblio_config")
@patch("biblio.concepts.default_config_path")
@patch("biblio.mcp.paper_context")
def test_extract_concepts_prompt_only(mock_paper_ctx, mock_cfg_path, mock_load_cfg, mock_summary_path, tmp_path):
    mock_paper_ctx.return_value = {
        "citekey": "test_key",
        "bib": {"title": "Test Paper", "abstract": "An abstract."},
        "library": {},
        "docling_excerpt": None,
        "grobid_header": None,
    }
    mock_cfg_path.return_value = tmp_path / "config.yml"
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg
    mock_summary_path.return_value = tmp_path / "no_such_summary.md"

    from biblio.concepts import extract_concepts

    result = extract_concepts("test_key", tmp_path, prompt_only=True)
    assert result["citekey"] == "test_key"
    assert result["prompt"] is not None
    assert "Test Paper" in result["prompt"]
    assert result["concepts"] is None
    assert result["skipped"] is False


# ── Comparison table ──────────────────────────────────────────────────────


def test_compare_needs_two_citekeys(tmp_path):
    from biblio.compare import compare

    result = compare(["only_one"], tmp_path)
    assert "error" in result


def test_slug_from_citekeys():
    from biblio.compare import _slug_from_citekeys

    slug = _slug_from_citekeys(["b_key", "a_key"])
    assert slug == "a_key_b_key"  # sorted


def test_slug_from_citekeys_long():
    from biblio.compare import _slug_from_citekeys

    keys = [f"very_long_citekey_{i:03d}" for i in range(20)]
    slug = _slug_from_citekeys(keys)
    assert len(slug) <= 100
    assert "20papers" in slug


@patch("biblio.summarize.summary_path_for_key")
@patch("biblio.compare.load_biblio_config")
@patch("biblio.compare.default_config_path")
@patch("biblio.mcp.paper_context")
def test_compare_prompt_only(mock_paper_ctx, mock_cfg_path, mock_load_cfg, mock_summary_path, tmp_path):
    def _ctx(ck, *, root):
        return {
            "citekey": ck,
            "bib": {"title": f"Paper {ck}", "authors": ["Author"], "year": "2024", "abstract": f"Abstract {ck}"},
            "library": {},
            "docling_excerpt": None,
            "grobid_header": None,
        }

    mock_paper_ctx.side_effect = _ctx
    mock_cfg_path.return_value = tmp_path / "config.yml"
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg
    mock_summary_path.return_value = tmp_path / "no_summary.md"

    from biblio.compare import compare

    result = compare(["paper_a", "paper_b"], tmp_path, prompt_only=True)
    assert result["citekeys"] == ["paper_a", "paper_b"]
    assert result["prompt"] is not None
    assert "Paper paper_a" in result["prompt"]
    assert "Paper paper_b" in result["prompt"]
    assert result["comparison_text"] is None
    assert result["skipped"] is False


def test_render_comparison_md():
    from biblio.compare import _render_comparison_md

    md = _render_comparison_md(
        ["a", "b"],
        "## Table\n| a | b |",
        ("method", "dataset"),
        "test-model",
    )
    assert "citekeys:" in md
    assert "dimensions:" in md
    assert "model_used: test-model" in md
    assert "## Table" in md


# ── Reading list ──────────────────────────────────────────────────────────


@patch("biblio.reading_list._gather_candidates")
def test_reading_list_prompt_only(mock_gather, tmp_path):
    mock_gather.return_value = [
        {"citekey": "paper_a", "library": {"status": "unread", "tags": ["ml"]}, "title": "Paper A", "abstract": "Abstract A"},
        {"citekey": "paper_b", "library": {"status": "reading"}, "title": "Paper B"},
    ]

    from biblio.reading_list import reading_list

    result = reading_list("What is attention?", tmp_path, prompt_only=True)
    assert result["question"] == "What is attention?"
    assert result["candidates_count"] == 2
    assert result["prompt"] is not None
    assert "paper_a" in result["prompt"]
    assert "paper_b" in result["prompt"]
    assert result["recommendations"] is None


@patch("biblio.reading_list._gather_candidates")
def test_reading_list_no_candidates(mock_gather, tmp_path):
    mock_gather.return_value = []

    from biblio.reading_list import reading_list

    result = reading_list("anything", tmp_path)
    assert result["candidates_count"] == 0
    assert result["recommendations"] == []
    assert "hint" in result


# ── MCP wrappers ──────────────────────────────────────────────────────────


@patch("biblio.concepts.extract_concepts")
def test_mcp_biblio_concepts(mock_extract, tmp_path):
    mock_extract.return_value = {"citekey": "test", "concepts": {"methods": ["x"]}}
    from biblio.mcp import biblio_concepts

    result = biblio_concepts("test", root=tmp_path)
    assert result["citekey"] == "test"
    mock_extract.assert_called_once()


@patch("biblio.concepts.search_concepts")
def test_mcp_biblio_concept_search(mock_search, tmp_path):
    mock_search.return_value = {"query": "transformer", "matches": [], "total_matches": 0}
    from biblio.mcp import biblio_concept_search

    result = biblio_concept_search("transformer", root=tmp_path)
    assert result["query"] == "transformer"
    mock_search.assert_called_once()


@patch("biblio.compare.compare")
def test_mcp_biblio_compare(mock_compare, tmp_path):
    mock_compare.return_value = {"citekeys": ["a", "b"], "comparison_text": "table"}
    from biblio.mcp import biblio_compare

    result = biblio_compare(["a", "b"], root=tmp_path)
    assert result["citekeys"] == ["a", "b"]
    mock_compare.assert_called_once()


@patch("biblio.reading_list.reading_list")
def test_mcp_biblio_reading_list(mock_rl, tmp_path):
    mock_rl.return_value = {"question": "q", "recommendations": []}
    from biblio.mcp import biblio_reading_list

    result = biblio_reading_list("q", root=tmp_path)
    assert result["question"] == "q"
    mock_rl.assert_called_once()


# ── CLI parser ────────────────────────────────────────────────────────────


def test_cli_concepts_parser():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["concepts", "extract", "test_key", "--prompt-only"])
    assert args.command == "concepts"
    assert args.concepts_cmd == "extract"
    assert args.key == "test_key"
    assert args.prompt_only is True


def test_cli_concepts_search_parser():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["concepts", "search", "transformer"])
    assert args.command == "concepts"
    assert args.concepts_cmd == "search"
    assert args.query == "transformer"


def test_cli_compare_parser():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["compare", "key1", "key2", "--dimensions", "method,dataset"])
    assert args.command == "compare"
    assert args.keys == ["key1", "key2"]
    assert args.dimensions == "method,dataset"


def test_cli_reading_list_parser():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["reading-list", "What is attention?", "--count", "3"])
    assert args.command == "reading-list"
    assert args.question == "What is attention?"
    assert args.count == 3
