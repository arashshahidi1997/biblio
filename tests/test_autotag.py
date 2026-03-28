"""Tests for the LLM auto-tagging and reference propagation pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ── prompt construction ──────────────────────────────────────────────────────


def _sample_vocab() -> dict:
    return {
        "namespaces": {
            "domain": {
                "description": "Research domain",
                "values": ["nlp", "cv", "ml"],
            },
            "method": {
                "description": "Methodology",
                "values": ["transformer", "cnn"],
            },
        },
        "aliases": {},
    }


def test_build_llm_prompt_includes_vocab_and_paper():
    from biblio.autotag import build_llm_prompt

    system, user = build_llm_prompt(
        "A Great Paper", "We study NLP transformers.", _sample_vocab()
    )

    assert "domain:nlp" in system
    assert "method:transformer" in system
    assert "A Great Paper" in user
    assert "NLP transformers" in user


def test_build_llm_prompt_constrains_output():
    from biblio.autotag import build_llm_prompt

    system, _ = build_llm_prompt("T", "A", _sample_vocab())

    assert "JSON" in system
    assert "confidence" in system
    assert "Only use tags from this vocabulary" in system


def test_format_vocab_block():
    from biblio.autotag import _format_vocab_block

    block = _format_vocab_block(_sample_vocab())

    assert "domain:nlp" in block
    assert "domain:cv" in block
    assert "method:transformer" in block
    assert "Research domain" in block


# ── LLM tier ─────────────────────────────────────────────────────────────────


@patch("biblio.autotag.load_biblio_config")
@patch("biblio.autotag.default_config_path")
@patch("biblio.autotag._get_abstract")
@patch("biblio.autotag.load_cache", return_value=None)
@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_autotag_llm_calls_api(
    mock_load_cache, mock_abstract, mock_cfg_path, mock_load_cfg,
):
    import sys

    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = Path("/fake")
    mock_load_cfg.return_value = cfg
    mock_abstract.return_value = ("Test Paper", "We study NLP.")

    llm_response = json.dumps({
        "tags": [
            {"tag": "domain:nlp", "confidence": 0.95},
            {"tag": "method:transformer", "confidence": 0.8},
            {"tag": "domain:fake", "confidence": 0.5},  # not in vocab
        ]
    })

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=llm_response)]

    # Create a fake anthropic module if not installed
    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_message

    with patch("biblio.autotag.save_cache"):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with patch("biblio.tag_vocab.load_tag_vocab", return_value=_sample_vocab()):
                with patch("biblio.tag_vocab.default_tag_vocab_path", return_value=Path("/fake/tv.yml")):
                    from biblio.autotag import autotag_llm

                    result = autotag_llm("test_key", Path("/fake"))

    assert result["citekey"] == "test_key"
    assert result["tier"] == "llm"
    assert not result["cached"]
    # domain:fake should be filtered out (not in vocab)
    tag_names = [t["tag"] for t in result["tags"]]
    assert "domain:nlp" in tag_names
    assert "method:transformer" in tag_names
    assert "domain:fake" not in tag_names


@patch("biblio.autotag.load_biblio_config")
@patch("biblio.autotag.default_config_path")
@patch("biblio.autotag._get_abstract")
@patch("biblio.autotag.load_cache", return_value=None)
@patch.dict("os.environ", {}, clear=True)
def test_autotag_llm_no_api_key(mock_load_cache, mock_abstract, mock_cfg_path, mock_load_cfg):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = Path("/fake")
    mock_load_cfg.return_value = cfg
    mock_abstract.return_value = ("Title", "Abstract")

    with patch("biblio.tag_vocab.load_tag_vocab", return_value=_sample_vocab()):
        with patch("biblio.tag_vocab.default_tag_vocab_path", return_value=Path("/fake/tv.yml")):
            from biblio.autotag import autotag_llm

            result = autotag_llm("test_key", Path("/fake"))
    assert result.get("error") == "ANTHROPIC_API_KEY not set"


@patch("biblio.autotag.load_biblio_config")
@patch("biblio.autotag.default_config_path")
def test_autotag_llm_returns_cached(mock_cfg_path, mock_load_cfg):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = Path("/fake")
    mock_load_cfg.return_value = cfg

    cached = {
        "citekey": "test_key",
        "tiers": {
            "llm": {
                "tags": [{"tag": "domain:nlp", "confidence": 0.9}],
                "model": "claude-haiku-4-5-20251001",
            }
        },
    }

    with patch("biblio.autotag.load_cache", return_value=cached):
        from biblio.autotag import autotag_llm

        result = autotag_llm("test_key", Path("/fake"))

    assert result["cached"] is True
    assert result["tags"] == [{"tag": "domain:nlp", "confidence": 0.9}]


# ── propagation tier ─────────────────────────────────────────────────────────


@patch("biblio.autotag.load_biblio_config")
@patch("biblio.autotag.default_config_path")
@patch("biblio.autotag.load_cache", return_value=None)
def test_autotag_propagate_counts_tags(mock_load_cache, mock_cfg_path, mock_load_cfg, tmp_path):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg

    # Create local_refs.json
    grobid_dir = tmp_path / "bib" / "derivatives" / "grobid"
    grobid_dir.mkdir(parents=True)
    local_refs = {
        "paper_a": [
            {"target_citekey": "ref1", "match_type": "doi"},
            {"target_citekey": "ref2", "match_type": "doi"},
            {"target_citekey": "ref3", "match_type": "title"},
            {"target_citekey": "ref4", "match_type": "title"},
        ]
    }
    (grobid_dir / "local_refs.json").write_text(json.dumps(local_refs))

    # Library with tagged papers
    library = {
        "ref1": {"tags": ["domain:nlp", "method:transformer"]},
        "ref2": {"tags": ["domain:nlp", "task:classification"]},
        "ref3": {"tags": ["domain:nlp", "method:transformer"]},
        "ref4": {"tags": ["domain:cv"]},
    }

    with patch("biblio.autotag.save_cache"):
        with patch("biblio.library.load_library", return_value=library):
            from biblio.autotag import autotag_propagate

            result = autotag_propagate("paper_a", tmp_path, threshold=3)

    assert result["tier"] == "propagate"
    assert result["cited_count"] == 4
    # domain:nlp appears in ref1, ref2, ref3 (3 >= threshold=3)
    assert "auto:domain:nlp" in result["tags"]
    # method:transformer appears in ref1, ref3 (2 < threshold=3)
    assert "auto:method:transformer" not in result["tags"]


@patch("biblio.autotag.load_biblio_config")
@patch("biblio.autotag.default_config_path")
@patch("biblio.autotag.load_cache", return_value=None)
def test_autotag_propagate_lower_threshold(mock_load_cache, mock_cfg_path, mock_load_cfg, tmp_path):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg

    grobid_dir = tmp_path / "bib" / "derivatives" / "grobid"
    grobid_dir.mkdir(parents=True)
    local_refs = {
        "paper_a": [
            {"target_citekey": "ref1", "match_type": "doi"},
            {"target_citekey": "ref2", "match_type": "doi"},
        ]
    }
    (grobid_dir / "local_refs.json").write_text(json.dumps(local_refs))

    library = {
        "ref1": {"tags": ["domain:nlp", "method:transformer"]},
        "ref2": {"tags": ["domain:nlp"]},
    }

    with patch("biblio.autotag.save_cache"):
        with patch("biblio.library.load_library", return_value=library):
            from biblio.autotag import autotag_propagate

            result = autotag_propagate("paper_a", tmp_path, threshold=2)

    assert "auto:domain:nlp" in result["tags"]


@patch("biblio.autotag.load_biblio_config")
@patch("biblio.autotag.default_config_path")
@patch("biblio.autotag.load_cache", return_value=None)
def test_autotag_propagate_skips_auto_tags(mock_load_cache, mock_cfg_path, mock_load_cfg, tmp_path):
    """auto: prefixed tags from cited papers should not be propagated."""
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = tmp_path
    mock_load_cfg.return_value = cfg

    grobid_dir = tmp_path / "bib" / "derivatives" / "grobid"
    grobid_dir.mkdir(parents=True)
    local_refs = {
        "paper_a": [
            {"target_citekey": "ref1"},
            {"target_citekey": "ref2"},
            {"target_citekey": "ref3"},
        ]
    }
    (grobid_dir / "local_refs.json").write_text(json.dumps(local_refs))

    library = {
        "ref1": {"tags": ["auto:domain:nlp", "domain:ml"]},
        "ref2": {"tags": ["auto:domain:nlp", "domain:ml"]},
        "ref3": {"tags": ["auto:domain:nlp", "domain:ml"]},
    }

    with patch("biblio.autotag.save_cache"):
        with patch("biblio.library.load_library", return_value=library):
            from biblio.autotag import autotag_propagate

            result = autotag_propagate("paper_a", tmp_path, threshold=3)

    # auto:domain:nlp should NOT be propagated (starts with auto:)
    assert "auto:auto:domain:nlp" not in result["tags"]
    # domain:ml appears 3 times so it should be propagated
    assert "auto:domain:ml" in result["tags"]


# ── caching ──────────────────────────────────────────────────────────────────


def test_cache_roundtrip(tmp_path):
    from biblio.autotag import load_cache, save_cache

    cfg = MagicMock()
    cfg.repo_root = tmp_path

    data = {
        "citekey": "test_key",
        "tiers": {
            "llm": {
                "tags": [{"tag": "domain:nlp", "confidence": 0.9}],
                "model": "test-model",
                "timestamp": "2026-03-28T12:00:00Z",
            }
        },
    }

    path = save_cache(cfg, "test_key", data)
    assert path.exists()

    loaded = load_cache(cfg, "test_key")
    assert loaded["citekey"] == "test_key"
    assert loaded["tiers"]["llm"]["tags"] == [{"tag": "domain:nlp", "confidence": 0.9}]


def test_load_cache_missing(tmp_path):
    from biblio.autotag import load_cache

    cfg = MagicMock()
    cfg.repo_root = tmp_path

    assert load_cache(cfg, "nonexistent") is None


# ── orchestrator ─────────────────────────────────────────────────────────────


@patch("biblio.autotag.autotag_propagate")
@patch("biblio.autotag.autotag_llm")
def test_autotag_orchestrator_merges(mock_llm, mock_prop):
    mock_llm.return_value = {
        "citekey": "test",
        "tags": [{"tag": "domain:nlp", "confidence": 0.9}],
        "tier": "llm",
        "cached": False,
    }
    mock_prop.return_value = {
        "citekey": "test",
        "tags": ["auto:method:transformer"],
        "tier": "propagate",
        "cited_count": 5,
        "cached": False,
    }

    from biblio.autotag import autotag

    result = autotag("test", Path("/fake"))

    assert "auto:domain:nlp" in result["all_tags"]
    assert "auto:method:transformer" in result["all_tags"]
    assert "llm" in result["tiers"]
    assert "propagate" in result["tiers"]


@patch("biblio.autotag.autotag_llm")
def test_autotag_single_tier(mock_llm):
    mock_llm.return_value = {
        "citekey": "test",
        "tags": [{"tag": "domain:nlp", "confidence": 0.9}],
        "tier": "llm",
        "cached": False,
    }

    from biblio.autotag import autotag

    result = autotag("test", Path("/fake"), tiers=["llm"])

    assert "llm" in result["tiers"]
    assert "propagate" not in result["tiers"]


# ── MCP tool ─────────────────────────────────────────────────────────────────


@patch("biblio.autotag.autotag")
def test_mcp_biblio_autotag(mock_autotag):
    mock_autotag.return_value = {
        "citekey": "paper_a",
        "tiers": {},
        "all_tags": ["auto:domain:nlp"],
    }

    from biblio.mcp import biblio_autotag

    result = biblio_autotag(["paper_a"], root=Path("/fake"))

    assert result["count"] == 1
    assert result["results"][0]["all_tags"] == ["auto:domain:nlp"]
    mock_autotag.assert_called_once()


# ── CLI batch mode ───────────────────────────────────────────────────────────


def test_cli_autotag_parser_accepts_args():
    """Verify the autotag subcommand is registered and parses correctly."""
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["library", "autotag", "test_key", "--tier", "llm", "--force"])

    assert args.command == "library"
    assert args.library_cmd == "autotag"
    assert args.key == "test_key"
    assert args.tier == "llm"
    assert args.force is True


def test_cli_autotag_parser_batch_all():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["library", "autotag", "--all", "--threshold", "5"])

    assert args.all is True
    assert args.threshold == 5


def test_cli_autotag_parser_batch_untagged():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["library", "autotag", "--untagged", "--json"])

    assert args.untagged is True
    assert args.json is True
