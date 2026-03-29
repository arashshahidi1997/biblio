"""Tests for duplicate paper detection (biblio.dedup)."""
from __future__ import annotations

from pathlib import Path

import pytest


def _require_pybtex():
    try:
        import pybtex  # noqa: F401
    except ImportError:
        pytest.skip("pybtex not installed")


def _write_bib(bib_dir: Path, filename: str, entries: str) -> Path:
    bib_dir.mkdir(parents=True, exist_ok=True)
    path = bib_dir / filename
    path.write_text(entries, encoding="utf-8")
    return path


def _setup_repo(tmp_path: Path, bib_content: str) -> Path:
    """Create a minimal repo with bib/main.bib."""
    repo = tmp_path / "repo"
    repo.mkdir()
    main_bib = repo / "bib" / "main.bib"
    main_bib.parent.mkdir(parents=True, exist_ok=True)
    main_bib.write_text(bib_content, encoding="utf-8")
    return repo


# ---------------------------------------------------------------------------
# DOI duplicate detection
# ---------------------------------------------------------------------------


def test_doi_duplicates(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    bib = """\
@article{smith2020,
  title = {A Great Paper},
  doi = {10.1234/abc},
  author = {Smith, J.},
  year = {2020},
}

@article{smith2020a,
  title = {A Great Paper (copy)},
  doi = {10.1234/abc},
  author = {Smith, J.},
  year = {2020},
}

@article{jones2021,
  title = {Another Paper},
  doi = {10.5678/xyz},
  author = {Jones, A.},
  year = {2021},
}
"""
    repo = _setup_repo(tmp_path, bib)
    groups = find_duplicates(repo)
    assert len(groups) == 1
    g = groups[0]
    assert g["reason"] == "doi"
    assert set(g["citekeys"]) == {"smith2020", "smith2020a"}
    assert g["confidence"] == 1.0
    assert g["suggested_keep"] in g["citekeys"]


def test_doi_normalization(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    bib = """\
@article{a,
  title = {Paper A},
  doi = {https://doi.org/10.1234/test},
  author = {A, B.},
  year = {2020},
}

@article{b,
  title = {Paper B Different Title},
  doi = {10.1234/TEST},
  author = {B, C.},
  year = {2020},
}
"""
    repo = _setup_repo(tmp_path, bib)
    groups = find_duplicates(repo)
    assert len(groups) == 1
    assert groups[0]["reason"] == "doi"


# ---------------------------------------------------------------------------
# Title similarity detection
# ---------------------------------------------------------------------------


def test_title_duplicates(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    bib = """\
@article{alpha,
  title = {Deep Learning for Brain-Computer Interfaces: A Review},
  author = {Alpha, A.},
  year = {2020},
}

@article{beta,
  title = {Deep Learning for Brain Computer Interfaces A Review},
  author = {Beta, B.},
  year = {2020},
}

@article{gamma,
  title = {Something Completely Different},
  author = {Gamma, G.},
  year = {2021},
}
"""
    repo = _setup_repo(tmp_path, bib)
    groups = find_duplicates(repo)
    assert len(groups) == 1
    g = groups[0]
    assert g["reason"] == "title"
    assert set(g["citekeys"]) == {"alpha", "beta"}
    assert g["confidence"] >= 0.90


def test_no_duplicates(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    bib = """\
@article{paper1,
  title = {Completely Unique First Paper},
  doi = {10.1111/aaa},
  author = {One, A.},
  year = {2020},
}

@article{paper2,
  title = {Totally Different Second Paper},
  doi = {10.2222/bbb},
  author = {Two, B.},
  year = {2021},
}
"""
    repo = _setup_repo(tmp_path, bib)
    groups = find_duplicates(repo)
    assert groups == []


# ---------------------------------------------------------------------------
# Title threshold
# ---------------------------------------------------------------------------


def test_title_threshold(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    bib = """\
@article{x,
  title = {Attention Is All You Need},
  author = {X, Y.},
  year = {2017},
}

@article{y,
  title = {Attention Is All We Need},
  author = {Y, Z.},
  year = {2018},
}
"""
    repo = _setup_repo(tmp_path, bib)
    # With high threshold, should not match
    groups_strict = find_duplicates(repo, title_threshold=0.99)
    # With lower threshold, should match
    groups_loose = find_duplicates(repo, title_threshold=0.80)
    assert len(groups_strict) == 0
    assert len(groups_loose) == 1


# ---------------------------------------------------------------------------
# suggested_keep picks citekey with more metadata
# ---------------------------------------------------------------------------


def test_suggested_keep_prefers_richer_entry(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    bib = """\
@article{bare,
  title = {My Paper},
  doi = {10.9999/dup},
  author = {A, B.},
  year = {2020},
}

@article{rich,
  title = {My Paper},
  doi = {10.9999/dup},
  author = {A, B.},
  year = {2020},
}
"""
    repo = _setup_repo(tmp_path, bib)

    # Create derivatives for "rich" so it gets a higher score
    docling_dir = repo / "bib" / "derivatives" / "docling" / "rich"
    docling_dir.mkdir(parents=True, exist_ok=True)
    (docling_dir / "rich.md").write_text("# Full text", encoding="utf-8")
    notes_path = repo / "bib" / "notes" / "rich.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text("Notes on rich", encoding="utf-8")

    groups = find_duplicates(repo)
    assert len(groups) == 1
    assert groups[0]["suggested_keep"] == "rich"


# ---------------------------------------------------------------------------
# Empty / missing bib
# ---------------------------------------------------------------------------


def test_missing_main_bib(tmp_path: Path):
    _require_pybtex()
    from biblio.dedup import find_duplicates

    repo = tmp_path / "empty_repo"
    repo.mkdir()
    groups = find_duplicates(repo)
    assert groups == []


# ---------------------------------------------------------------------------
# OpenAlex duplicate detection
# ---------------------------------------------------------------------------


def test_openalex_duplicates(tmp_path: Path):
    """OpenAlex ID duplicates detected when JSONL resolve output exists."""
    _require_pybtex()
    import json

    from biblio.dedup import find_duplicates

    bib = """\
@article{oa1,
  title = {First OpenAlex Paper},
  author = {One, A.},
  year = {2020},
}

@article{oa2,
  title = {Second Completely Different Title},
  author = {Two, B.},
  year = {2021},
}
"""
    repo = _setup_repo(tmp_path, bib)

    # Create a mock config that points to a JSONL with matching OpenAlex IDs
    oa_dir = repo / "bib" / "derivatives" / "openalex"
    oa_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = oa_dir / "resolve.jsonl"
    records = [
        {"citekey": "oa1", "openalex_id": "W1234567890", "doi": None, "title": "First"},
        {"citekey": "oa2", "openalex_id": "W1234567890", "doi": None, "title": "Second"},
    ]
    jsonl_path.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n",
        encoding="utf-8",
    )

    # We need a config object with openalex.out_jsonl pointing to the file
    from unittest.mock import MagicMock

    mock_cfg = MagicMock()
    mock_cfg.repo_root = repo
    mock_cfg.openalex.out_jsonl = jsonl_path

    groups = find_duplicates(repo, cfg=mock_cfg)
    assert len(groups) == 1
    assert groups[0]["reason"] == "openalex"
    assert set(groups[0]["citekeys"]) == {"oa1", "oa2"}


# ---------------------------------------------------------------------------
# Normalize helpers
# ---------------------------------------------------------------------------


def test_normalize_title():
    from biblio.dedup import _normalize_title

    assert _normalize_title("Hello, World!") == "hello world"
    assert _normalize_title("  A  B  C  ") == "a b c"
    assert _normalize_title("Café & Résumé") == "cafe resume"


def test_normalize_doi():
    from biblio.dedup import _normalize_doi

    assert _normalize_doi("https://doi.org/10.1234/abc") == "10.1234/abc"
    assert _normalize_doi("10.1234/ABC") == "10.1234/abc"
    assert _normalize_doi(None) is None
    assert _normalize_doi("") is None
