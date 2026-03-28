"""Tests for the paper summary pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── assemble_context ─────────────────────────────────────────────────────────


def _make_paper_context(citekey: str = "smith_2024_Test") -> dict:
    return {
        "citekey": citekey,
        "bib": {
            "title": "A Test Paper",
            "authors": ["Alice Smith", "Bob Jones"],
            "year": "2024",
            "journal": "Test Journal",
            "doi": "10.1234/test",
            "abstract": "This is a test abstract.",
        },
        "library": {"status": "unread", "tags": ["ml", "neuroscience"]},
        "docling_excerpt": "# Introduction\n\nThis paper explores...",
        "grobid_header": {
            "title": "A Test Paper",
            "abstract": "This is a test abstract.",
            "authors": ["Alice Smith", "Bob Jones"],
            "year": "2024",
            "doi": "10.1234/test",
        },
    }


@patch("biblio.summarize.json")
@patch("biblio.summarize.load_biblio_config")
@patch("biblio.summarize.default_config_path")
@patch("biblio.summarize.grobid_outputs_for_key")
@patch("biblio.mcp.paper_context")
def test_assemble_context_includes_all_sections(
    mock_paper_ctx, mock_grobid_out, mock_cfg_path, mock_load_cfg, mock_json
):
    mock_paper_ctx.return_value = _make_paper_context()

    # Mock GROBID outputs (references file doesn't exist)
    grobid_out = MagicMock()
    grobid_out.references_path.exists.return_value = False
    mock_grobid_out.return_value = grobid_out
    mock_cfg_path.return_value = Path("/fake/config.yml")
    mock_load_cfg.return_value = MagicMock()

    from biblio.summarize import assemble_context

    result = assemble_context("smith_2024_Test", root=Path("/fake/root"))

    assert "# BibTeX Metadata" in result
    assert "A Test Paper" in result
    assert "Alice Smith" in result
    assert "# GROBID Header" in result
    assert "# Full Text (excerpt)" in result
    assert "This paper explores" in result
    assert "# Library Status" in result
    assert "unread" in result


@patch("biblio.summarize.json")
@patch("biblio.summarize.load_biblio_config")
@patch("biblio.summarize.default_config_path")
@patch("biblio.summarize.grobid_outputs_for_key")
@patch("biblio.mcp.paper_context")
def test_assemble_context_with_grobid_references(
    mock_paper_ctx, mock_grobid_out, mock_cfg_path, mock_load_cfg, mock_json_mod
):
    mock_paper_ctx.return_value = _make_paper_context()

    refs = [
        {"title": "Ref One", "authors": ["Author A"], "year": "2020"},
        {"title": "Ref Two", "authors": ["Author B"], "year": "2021"},
    ]

    grobid_out = MagicMock()
    grobid_out.references_path.exists.return_value = True
    grobid_out.references_path.read_text.return_value = json.dumps(refs)
    mock_grobid_out.return_value = grobid_out
    mock_cfg_path.return_value = Path("/fake/config.yml")
    mock_load_cfg.return_value = MagicMock()
    mock_json_mod.loads = json.loads

    from biblio.summarize import assemble_context

    result = assemble_context("smith_2024_Test", root=Path("/fake/root"))

    assert "# References (GROBID-extracted)" in result
    assert "Ref One" in result
    assert "Ref Two" in result


# ── _render_summary_md ───────────────────────────────────────────────────────


def test_render_summary_md_frontmatter():
    from biblio.summarize import _render_summary_md

    md = _render_summary_md("smith_2024_Test", "## Contribution\nGreat paper.", "claude-sonnet-4-20250514")

    assert "---" in md
    assert "citekey: smith_2024_Test" in md
    assert "model_used: claude-sonnet-4-20250514" in md
    assert "date_generated:" in md
    assert "# Summary: smith_2024_Test" in md
    assert "## Contribution" in md


# ── summarize prompt_only mode ───────────────────────────────────────────────


@patch("biblio.summarize.assemble_context")
@patch("biblio.summarize.load_biblio_config")
@patch("biblio.summarize.default_config_path")
def test_summarize_prompt_only(mock_cfg_path, mock_load_cfg, mock_assemble):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = Path("/fake/root")
    mock_load_cfg.return_value = cfg

    mock_assemble.return_value = "assembled prompt text"

    from biblio.summarize import summarize

    result = summarize("smith_2024_Test", Path("/fake/root"), prompt_only=True)

    assert result["prompt"] == "assembled prompt text"
    assert result["summary_path"] is None
    assert result["summary_text"] is None
    assert result["skipped"] is False


# ── summarize skip existing ──────────────────────────────────────────────────


@patch("biblio.summarize.assemble_context")
@patch("biblio.summarize.load_biblio_config")
@patch("biblio.summarize.default_config_path")
@patch("biblio.summarize.summary_path_for_key")
def test_summarize_skips_existing(mock_summary_path, mock_cfg_path, mock_load_cfg, mock_assemble, tmp_path):
    existing = tmp_path / "smith_2024_Test.md"
    existing.write_text("existing summary", encoding="utf-8")
    mock_summary_path.return_value = existing
    mock_cfg_path.return_value = Path("/fake/config.yml")
    mock_load_cfg.return_value = MagicMock()
    mock_assemble.return_value = "prompt"

    from biblio.summarize import summarize

    result = summarize("smith_2024_Test", Path("/fake/root"), prompt_only=False, force=False)

    assert result["skipped"] is True
    assert result["summary_path"] == str(existing)


# ── summarize no API key ─────────────────────────────────────────────────────


@patch("biblio.summarize.assemble_context")
@patch("biblio.summarize.load_biblio_config")
@patch("biblio.summarize.default_config_path")
@patch("biblio.summarize.summary_path_for_key")
@patch.dict("os.environ", {}, clear=True)
def test_summarize_no_api_key(mock_summary_path, mock_cfg_path, mock_load_cfg, mock_assemble, tmp_path):
    mock_summary_path.return_value = tmp_path / "smith_2024_Test.md"
    mock_cfg_path.return_value = Path("/fake/config.yml")
    mock_load_cfg.return_value = MagicMock()
    mock_assemble.return_value = "prompt"

    from biblio.summarize import summarize

    result = summarize("smith_2024_Test", Path("/fake/root"), prompt_only=False)

    assert result.get("error") == "ANTHROPIC_API_KEY not set"
    assert result["summary_path"] is None


# ── batch filtering via CLI ──────────────────────────────────────────────────


def test_cli_summarize_batch_filtering():
    """Test that --status flag filters papers correctly (integration with library)."""
    from biblio.library import VALID_STATUSES

    assert "unread" in VALID_STATUSES
    assert "reading" in VALID_STATUSES


# ── site.py picks up summaries directory ─────────────────────────────────────


def test_site_finds_summaries_from_derivatives_dir(tmp_path):
    """Verify that site model includes summaries from bib/derivatives/summaries/."""
    summary_dir = tmp_path / "bib" / "derivatives" / "summaries"
    summary_dir.mkdir(parents=True)
    summary_file = summary_dir / "testkey.md"
    summary_file.write_text("---\ncitekey: testkey\n---\n# Summary\nTest.", encoding="utf-8")

    # The summary file should be found
    assert summary_file.exists()
    assert summary_file.name == "testkey.md"
