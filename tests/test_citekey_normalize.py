"""Tests for biblio.citekey (strict) and biblio.normalize (rename plan)."""
from __future__ import annotations

from pathlib import Path

import pytest

from biblio.citekey import (
    SkipReason,
    canonical_citekey,
    canonical_citekey_str,
    dedup_citekeys,
    looks_standard,
)
from biblio.ingest import IngestRecord
from biblio.normalize import apply_normalize_plan, build_normalize_plan
from biblio.scaffold import init_bib_scaffold
from biblio.config import default_config_path, load_biblio_config


def _rec(
    *,
    authors: tuple[str, ...] = ("Doe, Jane",),
    year: str | None = "2024",
    title: str | None = "A Paper About Things",
    doi: str | None = None,
) -> IngestRecord:
    return IngestRecord(
        source_type="bibtex",
        source_ref="test.bib",
        entry_type="article",
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        url=None,
        journal=None,
        booktitle=None,
        raw_id=None,
    )


# ---------------------------------------------------------------------------
# Strict canonical_citekey
# ---------------------------------------------------------------------------


def test_strict_success_builds_author_year_title() -> None:
    result = canonical_citekey(_rec(), strict=True)
    # Stopwords drop "A"; first two surviving words are "Paper" + "About".
    assert result.key == "doe_2024_PaperAbout"
    assert result.reason is None


def test_strict_skips_missing_author() -> None:
    result = canonical_citekey(_rec(authors=()), strict=True)
    assert result.key is None
    assert result.reason == SkipReason.MISSING_AUTHOR


def test_strict_skips_empty_author_string() -> None:
    result = canonical_citekey(_rec(authors=("",)), strict=True)
    assert result.key is None
    assert result.reason == SkipReason.MISSING_AUTHOR


def test_strict_skips_missing_year() -> None:
    result = canonical_citekey(_rec(year=None), strict=True)
    assert result.key is None
    assert result.reason == SkipReason.MISSING_YEAR


def test_strict_skips_missing_title() -> None:
    result = canonical_citekey(_rec(title=None), strict=True)
    assert result.key is None
    assert result.reason == SkipReason.MISSING_TITLE


def test_strict_does_not_fall_back_to_doi_tail_for_title() -> None:
    # A DOI-only entry with no title: lenient would use DOI tail; strict refuses.
    result = canonical_citekey(
        _rec(title=None, doi="10.1234/foo.bar.baz"), strict=True,
    )
    assert result.key is None
    assert result.reason == SkipReason.MISSING_TITLE


def test_strict_year_extracts_from_messy_string() -> None:
    result = canonical_citekey(_rec(year="published 2019"), strict=True)
    assert result.key is not None
    assert "_2019_" in result.key


def test_strict_title_stopwords_are_dropped() -> None:
    result = canonical_citekey(
        _rec(title="The Theory of the Cat"), strict=True,
    )
    assert result.key == "doe_2024_TheoryCat"


# ---------------------------------------------------------------------------
# Lenient shim (used by fresh ingest)
# ---------------------------------------------------------------------------


def test_lenient_falls_back_to_anon_nd_record() -> None:
    key = canonical_citekey_str(_rec(authors=(), year=None, title=None))
    assert key == "anon_nd_Record"


# ---------------------------------------------------------------------------
# dedup_citekeys
# ---------------------------------------------------------------------------


def test_dedup_appends_numeric_suffix_on_collision() -> None:
    out = dedup_citekeys([
        ("a", "doe_2024_X"),
        ("b", "doe_2024_X"),
        ("c", "doe_2024_X"),
    ])
    assert out == [
        ("a", "doe_2024_X"),
        ("b", "doe_2024_X2"),
        ("c", "doe_2024_X3"),
    ]


def test_dedup_is_idempotent_for_same_old_key() -> None:
    out = dedup_citekeys([("a", "k"), ("a", "k")])
    assert out == [("a", "k"), ("a", "k")]


# ---------------------------------------------------------------------------
# looks_standard
# ---------------------------------------------------------------------------


def test_looks_standard_accepts_canonical_shape() -> None:
    assert looks_standard("doe_2024_PaperThings")
    assert not looks_standard("Doe2024")
    assert not looks_standard("doe-2024-x")


# ---------------------------------------------------------------------------
# build_normalize_plan + apply_normalize_plan — integration over a temp repo
# ---------------------------------------------------------------------------


BIB_CONTENT = """\
@article{OldKeyOne,
  author = {Doe, Jane and Smith, Bob},
  year = {2024},
  title = {A Paper About Things},
  doi = {10.1/foo},
}

@article{another_bad_KEY,
  author = {Roe, Alice},
  year = {2019},
  title = {Machine Learning Methods},
}

@article{anon_entry,
  title = {No Author Here},
  year = {2020},
}

@article{doe_2024_PaperAbout,
  author = {Doe, Jane and Smith, Bob},
  year = {2024},
  title = {A Paper About Things},
}
"""


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    init_bib_scaffold(tmp_path, force=False)
    srcbib = tmp_path / "bib" / "srcbib"
    srcbib.mkdir(parents=True, exist_ok=True)
    (srcbib / "sample.bib").write_text(BIB_CONTENT, encoding="utf-8")
    return tmp_path


def _load_cfg(root: Path):
    return load_biblio_config(default_config_path(root=root), root=root)


def test_build_plan_classifies_entries(sample_repo: Path) -> None:
    cfg = _load_cfg(sample_repo)
    plan = build_normalize_plan(cfg, enrich=False)

    rename_olds = {r.old for r in plan.renames}
    skipped_olds = {s.citekey for s in plan.skipped}

    # Both non-canonical entries with good metadata should be renamed
    assert "OldKeyOne" in rename_olds
    assert "another_bad_KEY" in rename_olds

    # The entry missing author metadata should be skipped, not renamed
    assert "anon_entry" in skipped_olds
    skip_reasons = {s.citekey: s.reason for s in plan.skipped}
    assert skip_reasons["anon_entry"] == SkipReason.MISSING_AUTHOR

    # Already-canonical entry should land in already_standard
    assert "doe_2024_PaperAbout" in plan.already_standard


def test_build_plan_new_keys_are_canonical(sample_repo: Path) -> None:
    cfg = _load_cfg(sample_repo)
    plan = build_normalize_plan(cfg, enrich=False)
    new_by_old = {r.old: r.new for r in plan.renames}
    # OldKeyOne collides with the existing doe_2024_PaperAbout, so it
    # must get a suffix rather than overwrite.
    assert new_by_old["OldKeyOne"] == "doe_2024_PaperAbout2"
    assert new_by_old["another_bad_KEY"] == "roe_2019_MachineLearning"


def test_apply_plan_rewrites_bib_and_leaves_skipped_untouched(sample_repo: Path) -> None:
    cfg = _load_cfg(sample_repo)
    plan = build_normalize_plan(cfg, enrich=False)
    apply_normalize_plan(cfg, plan)

    bib_text = (sample_repo / "bib" / "srcbib" / "sample.bib").read_text(encoding="utf-8")

    # Renamed entries are present under new keys
    assert "roe_2019_MachineLearning" in bib_text
    assert "doe_2024_PaperAbout2" in bib_text

    # Old non-canonical keys are gone
    assert "another_bad_KEY" not in bib_text
    assert "OldKeyOne" not in bib_text

    # Skipped entry keeps its original (bad) key — never renamed
    assert "anon_entry" in bib_text
    assert "anon_nd_Record" not in bib_text


def test_apply_creates_backup_and_ledger(sample_repo: Path) -> None:
    cfg = _load_cfg(sample_repo)
    plan = build_normalize_plan(cfg, enrich=False)
    result = apply_normalize_plan(cfg, plan)

    assert result.run_id.startswith("normalize_")
    backup_dir = Path(result.backup_dir)
    assert backup_dir.exists()
    assert (backup_dir / "sample.bib").exists()

    ledger = cfg.ledger.root / "normalize.jsonl"
    assert ledger.exists()
    assert result.run_id in ledger.read_text(encoding="utf-8")


def test_apply_is_noop_when_no_renames(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    srcbib = tmp_path / "bib" / "srcbib"
    srcbib.mkdir(parents=True, exist_ok=True)
    (srcbib / "sample.bib").write_text(
        "@article{doe_2024_Paper,\n  author = {Doe, Jane},\n  year = {2024},\n  title = {Paper},\n}\n",
        encoding="utf-8",
    )
    cfg = _load_cfg(tmp_path)
    plan = build_normalize_plan(cfg, enrich=False)
    assert plan.renames == []
    result = apply_normalize_plan(cfg, plan)
    assert result.renames == []
    assert result.run_id == ""
