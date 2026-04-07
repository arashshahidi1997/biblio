from __future__ import annotations

import json
from pathlib import Path

import yaml

from biblio.scaffold import init_bib_scaffold
from biblio.tag_vocab import (
    extract_bibtex_keywords,
    keywords_to_tags,
    known_tags,
    lint_library_tags,
    load_tag_vocab,
    map_keyword_to_tag,
    normalize_tag,
    validate_tag,
)


def _make_vocab(tmp_path: Path) -> Path:
    """Write a small test vocabulary and return its path."""
    vocab = {
        "namespaces": {
            "domain": {
                "description": "Research domain",
                "values": ["nlp", "cv", "ml"],
            },
            "method": {
                "description": "Method",
                "values": ["transformer", "cnn"],
            },
            "task": {
                "description": "Task",
                "values": ["classification", "generation"],
            },
        },
        "aliases": {
            "natural language processing": "domain:nlp",
            "computer vision": "domain:cv",
            "deep learning": "domain:ml",
            "attention": "method:transformer",
        },
    }
    path = tmp_path / "tag_vocab.yml"
    path.write_text(yaml.safe_dump(vocab), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def test_normalize_tag_lowercases_and_strips():
    assert normalize_tag("  NLP ") == "nlp"
    assert normalize_tag("Deep Learning") == "deep-learning"
    assert normalize_tag("domain:NLP") == "domain:nlp"


# ---------------------------------------------------------------------------
# Load vocab
# ---------------------------------------------------------------------------


def test_load_missing_vocab(tmp_path: Path):
    vocab = load_tag_vocab(tmp_path / "nonexistent.yml")
    assert vocab == {"namespaces": {}, "aliases": {}}


def test_load_vocab(tmp_path: Path):
    path = _make_vocab(tmp_path)
    vocab = load_tag_vocab(path)
    assert "domain" in vocab["namespaces"]
    assert "nlp" in vocab["namespaces"]["domain"]["values"]


# ---------------------------------------------------------------------------
# Known tags
# ---------------------------------------------------------------------------


def test_known_tags(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    kt = known_tags(vocab)
    assert "domain:nlp" in kt
    assert "method:transformer" in kt
    assert "task:classification" in kt
    assert len(kt) == 7  # 3 + 2 + 2


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def test_validate_known_tag(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    result = validate_tag("domain:nlp", vocab)
    assert result["valid"] is True
    assert result["namespace"] == "domain"


def test_validate_unknown_tag_suggests(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    result = validate_tag("domain:npl", vocab)
    assert result["valid"] is False
    assert result["suggestion"] == "domain:nlp"


def test_validate_unnamespaced_tag(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    result = validate_tag("nlp", vocab)
    assert result["valid"] is False
    # "nlp" is too short for difflib to confidently match "domain:nlp",
    # but that's OK — unnamespaced tags are allowed, just not validated.
    assert result["namespace"] is None


# ---------------------------------------------------------------------------
# Keyword mapping
# ---------------------------------------------------------------------------


def test_map_keyword_via_alias(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    assert map_keyword_to_tag("Natural Language Processing", vocab) == "domain:nlp"
    assert map_keyword_to_tag("deep learning", vocab) == "domain:ml"


def test_map_keyword_direct_match(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    assert map_keyword_to_tag("domain:cv", vocab) == "domain:cv"


def test_map_keyword_namespace_value_match(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    # "transformer" matches method:transformer
    assert map_keyword_to_tag("transformer", vocab) == "method:transformer"


def test_map_keyword_unknown(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    assert map_keyword_to_tag("some unknown keyword", vocab) == "some-unknown-keyword"


# ---------------------------------------------------------------------------
# BibTeX keyword extraction
# ---------------------------------------------------------------------------


def test_extract_keywords_comma_separated():
    fields = {"keywords": "NLP, Deep Learning, Transformers"}
    kws = extract_bibtex_keywords(fields)
    assert kws == ["NLP", "Deep Learning", "Transformers"]


def test_extract_keywords_semicolon_separated():
    fields = {"keywords": "NLP; Deep Learning; Transformers"}
    kws = extract_bibtex_keywords(fields)
    assert kws == ["NLP", "Deep Learning", "Transformers"]


def test_extract_keywords_single():
    fields = {"keywords": "NLP"}
    kws = extract_bibtex_keywords(fields)
    assert kws == ["NLP"]


def test_extract_keywords_empty():
    assert extract_bibtex_keywords({}) == []
    assert extract_bibtex_keywords({"keywords": ""}) == []


def test_extract_keywords_keyword_field():
    """Some BibTeX entries use 'keyword' (singular) instead of 'keywords'."""
    fields = {"keyword": "NLP, ML"}
    kws = extract_bibtex_keywords(fields)
    assert kws == ["NLP", "ML"]


# ---------------------------------------------------------------------------
# keywords_to_tags pipeline
# ---------------------------------------------------------------------------


def test_keywords_to_tags(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    keywords = ["Natural Language Processing", "Deep Learning", "some random thing"]
    tags = keywords_to_tags(keywords, vocab)
    assert "domain:nlp" in tags
    assert "domain:ml" in tags
    assert "some-random-thing" in tags
    # No duplicates
    assert len(tags) == len(set(tags))


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------


def test_lint_clean_library(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    library = {
        "paper1": {"tags": ["domain:nlp", "method:transformer"]},
        "paper2": {"tags": ["domain:cv"]},
    }
    report = lint_library_tags(library, vocab)
    assert report["non_vocab"] == []
    assert report["suggestions"] == []


def test_lint_non_vocab_tag(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    library = {
        "paper1": {"tags": ["domain:nlp", "domain:unknown"]},
    }
    report = lint_library_tags(library, vocab)
    assert len(report["non_vocab"]) == 1
    assert report["non_vocab"][0]["tag"] == "domain:unknown"
    assert report["non_vocab"][0]["citekey"] == "paper1"


def test_lint_duplicate_tags(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    library = {
        "paper1": {"tags": ["domain:nlp", "Domain:NLP"]},
    }
    report = lint_library_tags(library, vocab)
    assert len(report["duplicates"]) >= 1


def test_lint_suggestion(tmp_path: Path):
    vocab = load_tag_vocab(_make_vocab(tmp_path))
    library = {
        "paper1": {"tags": ["domain:npl"]},
    }
    report = lint_library_tags(library, vocab)
    assert len(report["suggestions"]) == 1
    assert report["suggestions"][0]["suggestion"] == "domain:nlp"


# ---------------------------------------------------------------------------
# CLI lint command
# ---------------------------------------------------------------------------


def test_cli_library_lint(tmp_path: Path):
    """Test the CLI lint subcommand runs without error."""
    from biblio.cli import main as biblio_main

    init_bib_scaffold(tmp_path, force=True)
    # Write a library.yml with one valid and one non-vocab tag
    lib_path = tmp_path / ".projio" / "biblio" / "library.yml"
    lib_path.write_text(
        yaml.safe_dump(
            {"papers": {"paper1": {"status": "unread", "tags": ["domain:nlp", "domain:unknown"]}}}
        ),
        encoding="utf-8",
    )
    try:
        biblio_main(["library", "lint", "--root", str(tmp_path)])
    except SystemExit:
        pass  # lint may exit normally


def test_cli_library_lint_json(tmp_path: Path, capsys):
    """Test the CLI lint --json subcommand."""
    from biblio.cli import main as biblio_main

    init_bib_scaffold(tmp_path, force=True)
    lib_path = tmp_path / ".projio" / "biblio" / "library.yml"
    lib_path.write_text(
        yaml.safe_dump(
            {"papers": {"paper1": {"status": "unread", "tags": ["domain:nlp"]}}}
        ),
        encoding="utf-8",
    )
    try:
        biblio_main(["library", "lint", "--json", "--root", str(tmp_path)])
    except SystemExit:
        pass
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "non_vocab" in data
    assert "duplicates" in data


# ---------------------------------------------------------------------------
# Scaffold includes tag_vocab.yml
# ---------------------------------------------------------------------------


def test_scaffold_creates_tag_vocab(tmp_path: Path):
    init_bib_scaffold(tmp_path, force=True)
    vocab_path = tmp_path / ".projio" / "biblio" / "tag_vocab.yml"
    assert vocab_path.exists()
    vocab = yaml.safe_load(vocab_path.read_text(encoding="utf-8"))
    assert "namespaces" in vocab
    assert "domain" in vocab["namespaces"]
