"""Tests for citation drafting and literature review workflow."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── cite_draft: citekey extraction ────────────────────────────────────────────


def test_extract_citekey_from_source_docling():
    from biblio.cite_draft import _extract_citekey_from_source

    assert _extract_citekey_from_source("bib/derivatives/docling/Smith_2024_Title/full.md") == "Smith_2024_Title"


def test_extract_citekey_from_source_empty():
    from biblio.cite_draft import _extract_citekey_from_source

    assert _extract_citekey_from_source("") is None
    assert _extract_citekey_from_source("some/random/path.md") is None


# ── cite_draft: prompt assembly ───────────────────────────────────────────────


def test_assemble_cite_prompt_latex():
    from biblio.cite_draft import assemble_cite_prompt

    passages = [
        {"citekey": "Smith_2024_ML", "snippet": "Deep learning has shown..."},
        {"citekey": "Jones_2023_NLP", "snippet": "Language models demonstrate..."},
    ]
    result = assemble_cite_prompt("Neural networks improve NLP tasks", passages, style="latex")

    assert "Neural networks improve NLP tasks" in result
    assert "\\cite{citekey}" in result
    assert "@Smith_2024_ML" in result
    assert "@Jones_2023_NLP" in result
    assert "Deep learning has shown" in result
    assert "Language models demonstrate" in result


def test_assemble_cite_prompt_pandoc():
    from biblio.cite_draft import assemble_cite_prompt

    passages = [{"citekey": "Smith_2024", "snippet": "Some text."}]
    result = assemble_cite_prompt("A claim", passages, style="pandoc")

    assert "[@citekey]" in result
    assert "@Smith_2024" in result


def test_cite_draft_prompt_only_no_passages():
    """cite_draft returns error when no passages found."""
    from biblio.cite_draft import cite_draft

    with patch("biblio.cite_draft._query_rag", return_value=[]):
        result = cite_draft("test claim", Path("/fake"), prompt_only=True)

    assert result.get("error")
    assert "No relevant passages" in result["error"]
    assert result["passages"] == []


def test_cite_draft_prompt_only_with_passages():
    """cite_draft returns assembled prompt in prompt_only mode."""
    from biblio.cite_draft import cite_draft

    fake_passages = [
        {"citekey": "Smith_2024_ML", "snippet": "Deep learning...", "source_path": "a"},
    ]
    with patch("biblio.cite_draft._query_rag", return_value=fake_passages):
        result = cite_draft("test claim", Path("/fake"), prompt_only=True, style="latex")

    assert result["prompt"] is not None
    assert "test claim" in result["prompt"]
    assert result["draft"] is None
    assert result["model_used"] is None
    assert len(result["passages"]) == 1


# ── cite_draft: LLM call (mocked) ────────────────────────────────────────────


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_cite_draft_llm_call():
    from biblio.cite_draft import cite_draft

    fake_passages = [
        {"citekey": "Smith_2024", "snippet": "Some text.", "source_path": "a"},
    ]

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Recent work \\cite{Smith_2024} shows...")]

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic.Anthropic.return_value = mock_client

    with patch("biblio.cite_draft._query_rag", return_value=fake_passages), \
         patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        result = cite_draft("test claim", Path("/fake"), style="latex")

    assert result["draft"] == "Recent work \\cite{Smith_2024} shows..."
    assert result["model_used"] is not None


# ── lit_review: review_query prompt assembly ──────────────────────────────────


def test_assemble_review_prompt():
    from biblio.lit_review import assemble_review_prompt

    passages = [
        {"citekey": "A_2024", "snippet": "Finding A..."},
        {"citekey": "B_2023", "snippet": "Finding B..."},
    ]
    result = assemble_review_prompt("How does X affect Y?", passages, style="latex")

    assert "How does X affect Y?" in result
    assert "@A_2024" in result
    assert "@B_2023" in result
    assert "Finding A" in result


def test_review_query_prompt_only_no_passages():
    from biblio.lit_review import review_query

    with patch("biblio.lit_review._query_rag_multi", return_value=[]):
        result = review_query("test question", Path("/fake"), prompt_only=True)

    assert result.get("error")
    assert result["passages"] == []


def test_review_query_prompt_only_with_passages():
    from biblio.lit_review import review_query

    fake_passages = [
        {"citekey": "A_2024", "snippet": "text...", "source_path": "a"},
    ]
    with patch("biblio.lit_review._query_rag_multi", return_value=fake_passages):
        result = review_query("test question", Path("/fake"), prompt_only=True)

    assert result["prompt"] is not None
    assert result["synthesis"] is None
    assert "test question" in result["prompt"]


# ── lit_review: review_plan prompt assembly ───────────────────────────────────


def test_assemble_plan_prompt():
    from biblio.lit_review import assemble_plan_prompt

    seeds = [
        {"citekey": "A_2024", "title": "Paper A", "authors": ["Author"], "year": "2024"},
        {"citekey": "B_2023", "title": "Paper B", "authors": [], "year": "2023", "tags": ["ml"]},
    ]
    result = assemble_plan_prompt("How does X work?", seeds)

    assert "How does X work?" in result
    assert "@A_2024" in result
    assert "@B_2023" in result
    assert "Paper A" in result
    assert "ml" in result


def test_review_plan_prompt_only():
    from biblio.lit_review import review_plan

    fake_ctx = {
        "citekey": "A_2024",
        "bib": {"title": "Paper A", "authors": ["Alice"], "year": "2024"},
        "library": {"tags": ["ml"]},
    }

    mock_sp = MagicMock()
    mock_sp.exists.return_value = False

    with patch("biblio.mcp.paper_context", return_value=fake_ctx), \
         patch("biblio.lit_review.load_biblio_config") as mock_cfg, \
         patch("biblio.lit_review.default_config_path") as mock_cp, \
         patch("biblio.summarize.summary_path_for_key", return_value=mock_sp):
        mock_cp.return_value = Path("/fake/config.yml")
        mock_cfg.return_value = MagicMock()

        result = review_plan(["A_2024"], "How does X work?", Path("/fake"), prompt_only=True)

    assert result["prompt"] is not None
    assert result["plan"] is None
    assert len(result["seeds"]) == 1
    assert result["seeds"][0]["citekey"] == "A_2024"


# ── lit_review: review_plan LLM call (mocked) ────────────────────────────────


@patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
def test_review_plan_llm_call():
    from biblio.lit_review import review_plan

    plan_json = {
        "scope": "Review of X",
        "themes": ["theme1", "theme2"],
        "coverage": {"theme1": ["A_2024"]},
        "gaps": ["theme2 has no papers"],
        "expansion_directions": [{"direction": "search Y", "rationale": "fills gap"}],
        "estimated_additional_papers": 3,
    }

    fake_ctx = {
        "citekey": "A_2024",
        "bib": {"title": "Paper A", "authors": ["Alice"], "year": "2024"},
        "library": {},
    }

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(plan_json))]

    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic.Anthropic.return_value = mock_client

    mock_sp = MagicMock()
    mock_sp.exists.return_value = False

    with patch("biblio.mcp.paper_context", return_value=fake_ctx), \
         patch("biblio.lit_review.load_biblio_config") as mock_cfg, \
         patch("biblio.lit_review.default_config_path") as mock_cp, \
         patch("biblio.summarize.summary_path_for_key", return_value=mock_sp), \
         patch.dict(sys.modules, {"anthropic": mock_anthropic}):
        mock_cp.return_value = Path("/fake/config.yml")
        mock_cfg.return_value = MagicMock()

        result = review_plan(["A_2024"], "How does X work?", Path("/fake"))

    assert result["plan"] is not None
    assert result["plan"]["scope"] == "Review of X"
    assert len(result["plan"]["themes"]) == 2
    assert result["model_used"] is not None


# ── MCP wrappers ──────────────────────────────────────────────────────────────


def test_mcp_cite_draft_delegates():
    from biblio.mcp import biblio_cite_draft

    with patch("biblio.cite_draft.cite_draft") as mock_cd:
        mock_cd.return_value = {"draft": "test"}
        result = biblio_cite_draft("claim", root=Path("/fake"), style="pandoc", max_refs=3)

    mock_cd.assert_called_once_with(
        "claim", Path("/fake"),
        style="pandoc", max_refs=3, prompt_only=False,
        model="claude-sonnet-4-20250514",
    )
    assert result == {"draft": "test"}


def test_mcp_review_delegates_query():
    from biblio.mcp import biblio_review

    with patch("biblio.lit_review.review_query") as mock_rq:
        mock_rq.return_value = {"synthesis": "test"}
        result = biblio_review("question", root=Path("/fake"))

    mock_rq.assert_called_once()
    assert result == {"synthesis": "test"}


def test_mcp_review_delegates_plan():
    from biblio.mcp import biblio_review

    with patch("biblio.lit_review.review_plan") as mock_rp:
        mock_rp.return_value = {"plan": "test"}
        result = biblio_review("question", root=Path("/fake"), seeds=["@A_2024"])

    mock_rp.assert_called_once()
    assert result == {"plan": "test"}


# ── lit-review note template ─────────────────────────────────────────────────


def test_lit_review_template_exists():
    """Verify the lit-review notio template has the required sections."""
    template_path = Path(__file__).parent.parent / ".projio" / "notio" / "templates" / "lit-review.md"
    assert template_path.exists(), f"Template not found at {template_path}"

    content = template_path.read_text(encoding="utf-8")
    assert "## Research Question" in content
    assert "## Scope" in content
    assert "## Synthesis" in content
    assert "## Gap Analysis" in content
    assert "## References" in content
    assert "lit-review" in content  # tag in frontmatter


# ── CLI parser ────────────────────────────────────────────────────────────────


def test_cli_cite_draft_parser():
    from biblio.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["cite-draft", "some claim", "--style", "pandoc", "--max-refs", "3"])
    assert args.command == "cite-draft"
    assert args.text == "some claim"
    assert args.style == "pandoc"
    assert args.max_refs == 3


def test_cli_review_parser():
    from biblio.cli import _build_parser

    args = _build_parser().parse_args(["review", "What is X?", "--seeds", "A,B"])
    assert args.command == "review"
    assert args.question == "What is X?"
    assert args.seeds == "A,B"


def test_cli_review_parser_no_seeds():
    from biblio.cli import _build_parser

    args = _build_parser().parse_args(["review", "What is X?"])
    assert args.command == "review"
    assert args.seeds is None
