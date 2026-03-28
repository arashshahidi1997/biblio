"""Tests for the presentation generation pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── template loading ─────────────────────────────────────────────────────────


def test_load_template_journal_club():
    from biblio.present import load_template

    text = load_template("journal-club")
    assert "journal club" in text.lower()
    assert "Slide 1" in text


def test_load_template_conference_talk():
    from biblio.present import load_template

    text = load_template("conference-talk")
    assert "conference" in text.lower()


def test_load_template_lab_meeting():
    from biblio.present import load_template

    text = load_template("lab-meeting")
    assert "lab meeting" in text.lower()


def test_load_template_invalid():
    from biblio.present import load_template

    with pytest.raises(ValueError, match="Unknown template"):
        load_template("nonexistent-template")


def test_valid_templates_constant():
    from biblio.present import VALID_TEMPLATES

    assert "journal-club" in VALID_TEMPLATES
    assert "conference-talk" in VALID_TEMPLATES
    assert "lab-meeting" in VALID_TEMPLATES


# ── figure extraction ────────────────────────────────────────────────────────


def test_extract_figures_no_artifacts(tmp_path):
    """When no artifacts dir exists, returns empty list."""
    from biblio.present import extract_figures

    cfg = MagicMock()
    cfg.out_root = tmp_path / "docling"
    # Create the citekey output dir but no artifacts subdir
    (cfg.out_root / "smith_2024").mkdir(parents=True)

    result = extract_figures("smith_2024", cfg)
    assert result == []


def test_extract_figures_with_images(tmp_path):
    """Extracts figure paths from artifacts directory."""
    from biblio.present import extract_figures

    cfg = MagicMock()
    cfg.out_root = tmp_path / "docling"
    key = "smith_2024"
    artifacts = cfg.out_root / key / f"{key}_artifacts"
    artifacts.mkdir(parents=True)

    # Create fake image files
    (artifacts / "image_001.png").write_bytes(b"fake png")
    (artifacts / "image_002.jpg").write_bytes(b"fake jpg")
    (artifacts / "notes.txt").write_text("not an image")

    # No docling JSON (captions will be empty)
    json_path = cfg.out_root / key / f"{key}.json"

    result = extract_figures(key, cfg)

    assert len(result) == 2
    assert result[0]["filename"] == "image_001.png"
    assert "docling/smith_2024" in result[0]["rel_path"]
    assert result[0]["rel_path"].startswith("../../derivatives/docling/")
    assert result[1]["filename"] == "image_002.jpg"


def test_extract_figures_with_captions(tmp_path):
    """Captions are extracted from docling JSON."""
    from biblio.present import extract_figures

    cfg = MagicMock()
    cfg.out_root = tmp_path / "docling"
    key = "smith_2024"
    outdir = cfg.out_root / key
    artifacts = outdir / f"{key}_artifacts"
    artifacts.mkdir(parents=True)

    (artifacts / "image_001.png").write_bytes(b"fake png")

    # Create docling JSON with picture and caption
    doc = {
        "texts": [
            {"text": "Some other text"},
            {"text": "Figure 1: Architecture overview"},
        ],
        "pictures": [
            {
                "image": {"uri": "image_001.png"},
                "captions": [{"$ref": "#/texts/1"}],
            }
        ],
    }
    (outdir / f"{key}.json").write_text(json.dumps(doc), encoding="utf-8")

    result = extract_figures(key, cfg)
    assert len(result) == 1
    assert result[0]["caption"] == "Figure 1: Architecture overview"


# ── Marp frontmatter ─────────────────────────────────────────────────────────


def test_marp_frontmatter():
    from biblio.present import _build_marp_frontmatter

    bib = {
        "title": "A Great Paper",
        "authors": ["Alice Smith", "Bob Jones"],
        "year": "2024",
    }
    fm = _build_marp_frontmatter(bib)

    assert "marp: true" in fm
    assert "theme: default" in fm
    assert "paginate: true" in fm
    assert "A Great Paper" in fm
    assert "Alice Smith, Bob Jones" in fm
    assert fm.startswith("---")
    assert fm.endswith("---")


def test_marp_frontmatter_missing_fields():
    from biblio.present import _build_marp_frontmatter

    fm = _build_marp_frontmatter({})
    assert "Untitled" in fm
    assert "Unknown" in fm


# ── prompt building ──────────────────────────────────────────────────────────


def test_build_prompt_includes_metadata():
    from biblio.present import _build_prompt

    context = {
        "bib": {
            "title": "Test Paper",
            "authors": ["Alice"],
            "year": "2024",
            "journal": "Test Journal",
        },
        "summary": "## Contribution\nGreat paper.",
        "figures": [
            {"rel_path": "../../derivatives/docling/key/key_artifacts/fig1.png", "caption": "Fig 1"},
        ],
    }
    prompt = _build_prompt(context, "Template instructions here")

    assert "Template instructions here" in prompt
    assert "Test Paper" in prompt
    assert "Alice" in prompt
    assert "2024" in prompt
    assert "# Paper Summary" in prompt
    assert "Great paper." in prompt
    assert "# Available Figures" in prompt
    assert "fig1.png" in prompt
    assert "Fig 1" in prompt


def test_build_prompt_uses_excerpt_without_summary():
    from biblio.present import _build_prompt

    context = {
        "bib": {"title": "Test"},
        "summary": None,
        "docling_excerpt": "Introduction text here...",
        "figures": [],
    }
    prompt = _build_prompt(context, "Template")

    assert "# Full Text (excerpt)" in prompt
    assert "Introduction text here" in prompt
    assert "# Paper Summary" not in prompt


# ── generate_slides prompt_only ──────────────────────────────────────────────


@patch("biblio.present.assemble_slide_context")
@patch("biblio.present.load_biblio_config")
@patch("biblio.present.default_config_path")
def test_generate_slides_prompt_only(mock_cfg_path, mock_load_cfg, mock_assemble):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = Path("/fake/root")
    mock_load_cfg.return_value = cfg

    mock_assemble.return_value = {
        "citekey": "smith_2024",
        "bib": {"title": "Test", "authors": ["Alice"]},
        "summary": "A summary",
        "figures": [],
    }

    from biblio.present import generate_slides

    result = generate_slides("smith_2024", Path("/fake/root"), prompt_only=True)

    assert result["citekey"] == "smith_2024"
    assert result["slides_path"] is None
    assert result["slides_text"] is None
    assert result["skipped"] is False
    assert result["template"] == "journal-club"
    assert "Test" in result["prompt"]


@patch("biblio.present.assemble_slide_context")
@patch("biblio.present.load_biblio_config")
@patch("biblio.present.default_config_path")
def test_generate_slides_prompt_only_conference(mock_cfg_path, mock_load_cfg, mock_assemble):
    mock_cfg_path.return_value = Path("/fake/config.yml")
    cfg = MagicMock()
    cfg.repo_root = Path("/fake/root")
    mock_load_cfg.return_value = cfg

    mock_assemble.return_value = {
        "citekey": "smith_2024",
        "bib": {"title": "Test"},
        "summary": None,
        "figures": [],
    }

    from biblio.present import generate_slides

    result = generate_slides("smith_2024", Path("/fake/root"), prompt_only=True, template="conference-talk")

    assert result["template"] == "conference-talk"
    assert "conference" in result["prompt"].lower()


# ── generate_slides skip existing ────────────────────────────────────────────


@patch("biblio.present.assemble_slide_context")
@patch("biblio.present.load_biblio_config")
@patch("biblio.present.default_config_path")
@patch("biblio.present.slides_path_for_key")
def test_generate_slides_skips_existing(mock_slides_path, mock_cfg_path, mock_load_cfg, mock_assemble, tmp_path):
    existing = tmp_path / "smith_2024.md"
    existing.write_text("existing slides", encoding="utf-8")
    mock_slides_path.return_value = existing
    mock_cfg_path.return_value = Path("/fake/config.yml")
    mock_load_cfg.return_value = MagicMock()
    mock_assemble.return_value = {
        "citekey": "smith_2024",
        "bib": {},
        "summary": None,
        "figures": [],
    }

    from biblio.present import generate_slides

    result = generate_slides("smith_2024", Path("/fake/root"), prompt_only=False, force=False)

    assert result["skipped"] is True
    assert result["slides_path"] == str(existing)


# ── generate_slides no API key ───────────────────────────────────────────────


@patch("biblio.present.assemble_slide_context")
@patch("biblio.present.load_biblio_config")
@patch("biblio.present.default_config_path")
@patch("biblio.present.slides_path_for_key")
@patch.dict("os.environ", {}, clear=True)
def test_generate_slides_no_api_key(mock_slides_path, mock_cfg_path, mock_load_cfg, mock_assemble, tmp_path):
    mock_slides_path.return_value = tmp_path / "smith_2024.md"
    mock_cfg_path.return_value = Path("/fake/config.yml")
    mock_load_cfg.return_value = MagicMock()
    mock_assemble.return_value = {
        "citekey": "smith_2024",
        "bib": {},
        "summary": None,
        "figures": [],
    }

    from biblio.present import generate_slides

    result = generate_slides("smith_2024", Path("/fake/root"), prompt_only=False)

    assert result.get("error") == "ANTHROPIC_API_KEY not set"
    assert result["slides_path"] is None


# ── MCP wrapper ──────────────────────────────────────────────────────────────


@patch("biblio.present.generate_slides")
def test_mcp_biblio_present(mock_gen):
    mock_gen.return_value = {"citekey": "smith_2024", "template": "journal-club"}

    from biblio.mcp import biblio_present

    result = biblio_present("smith_2024", root=Path("/fake/root"))

    assert result["citekey"] == "smith_2024"
    mock_gen.assert_called_once_with(
        "smith_2024", Path("/fake/root"),
        template="journal-club",
        prompt_only=False,
        force=False,
        model="claude-sonnet-4-20250514",
    )


# ── CLI parser ───────────────────────────────────────────────────────────────


def test_cli_present_parser():
    """Verify the present subcommand is registered in the CLI parser."""
    from biblio.cli import _build_parser as build_parser

    parser = build_parser()
    # Should not raise on valid args
    args = parser.parse_args(["present", "smith_2024", "--template", "lab-meeting", "--prompt-only"])
    assert args.command == "present"
    assert args.key == "smith_2024"
    assert args.template == "lab-meeting"
    assert args.prompt_only is True


def test_cli_present_parser_export():
    from biblio.cli import _build_parser as build_parser

    parser = build_parser()
    args = parser.parse_args(["present", "smith_2024", "--export", "pdf"])
    assert args.export == "pdf"
