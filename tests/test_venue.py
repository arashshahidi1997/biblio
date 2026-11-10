from __future__ import annotations

from pathlib import Path

from biblio.venue import backfill_venues

BIB = """@article{ye_2026_BrainWide,
  title = {Brain-wide},
  author = {Ye, A},
  year = {2026},
  doi = {10.1126/science.adx1369},
  url = {https://openalex.org/W111}
}

@article{held_2020_X,
  title = {Has journal},
  doi = {10.1/held},
  journal = {Neuron}
}

@article{oa_2021_Y,
  title = {Only OpenAlex knows},
  doi = {10.1/oa},
  url = {https://openalex.org/W222}
}

@article{wrong_2022_Z,
  title = {OpenAlex returns another work},
  doi = {10.1/wrong},
  url = {https://openalex.org/W333}
}

@article{nodoi_2019_N,
  title = {No DOI}
}

@misc{pre_2023_P,
  title = {Preprint},
  doi = {10.1/pre}
}
"""

REGISTRY = {"10.1126/science.adx1369": {"title": "Brain-wide", "container-title": "Science"}}
OPENALEX = {
    "W222": {"doi": "https://doi.org/10.1/oa", "primary_location": {"source": {"display_name": "eLife"}}},
    "W333": {"doi": "https://doi.org/10.1/other", "primary_location": {"source": {"display_name": "Wrong"}}},
}


def _run(tmp_path: Path, dry_run: bool):
    bib = tmp_path / "imported.bib"
    if not bib.exists():
        bib.write_text(BIB, encoding="utf-8")
    calls: list[str] = []

    def fetch(doi):
        calls.append(doi)
        return REGISTRY.get(doi)

    res = backfill_venues(bib, dry_run=dry_run, fetch_csl=fetch, load_openalex_work=OPENALEX.get)
    return bib, res, calls


def test_backfill_dry_run_reports_and_writes_nothing(tmp_path: Path) -> None:
    bib, res, calls = _run(tmp_path, dry_run=True)
    assert res.candidates == 3
    assert res.filled == {"ye_2026_BrainWide": "Science", "oa_2021_Y": "eLife"}
    assert res.sources == {"ye_2026_BrainWide": "registry", "oa_2021_Y": "openalex"}
    assert res.unresolved == ["wrong_2022_Z"]
    assert res.no_doi == ["nodoi_2019_N"]
    assert "10.1/held" not in calls and "10.1/pre" not in calls
    assert bib.read_text(encoding="utf-8") == BIB


def test_backfill_inserts_journal_and_is_idempotent(tmp_path: Path) -> None:
    from pybtex.database import parse_file

    bib, res, _ = _run(tmp_path, dry_run=False)
    db = parse_file(str(bib))
    assert db.entries["ye_2026_BrainWide"].fields["journal"] == "Science"
    assert db.entries["oa_2021_Y"].fields["journal"] == "eLife"
    assert "journal" not in db.entries["wrong_2022_Z"].fields
    assert db.entries["held_2020_X"].fields["journal"] == "Neuron"
    # Everything else in the file is unchanged.
    assert bib.read_text(encoding="utf-8").replace("  journal = {Science},\n", "").replace(
        "  journal = {eLife},\n", "") == BIB

    _, again, _ = _run(tmp_path, dry_run=False)
    assert again.candidates == 1 and again.filled == {}


def test_backfill_unescapes_html_entities_and_escapes_ampersand(tmp_path: Path) -> None:
    """Crossref returns "Learning &amp; Memory"; the bib gets {Learning \\& Memory} (pixecog 20261108)."""
    from pybtex.database import parse_file

    bib = tmp_path / "imported.bib"
    bib.write_text("@article{lm_2001_X,\n  title = {T},\n  doi = {10.1/lm}\n}\n", encoding="utf-8")
    res = backfill_venues(bib, dry_run=False, fetch_csl=lambda doi: {"container-title": ["Learning &amp; Memory"]})
    assert res.filled == {"lm_2001_X": "Learning & Memory"}
    text = bib.read_text(encoding="utf-8")
    assert "journal = {Learning \\& Memory}" in text
    assert "&amp;" not in text
    assert parse_file(str(bib)).entries["lm_2001_X"].fields["journal"] == "Learning \\& Memory"


def test_add_doi_record_unescapes_container_and_renders_ampersand() -> None:
    from biblio.ingest import record_from_csl, render_bibtex

    rec = record_from_csl(
        {"DOI": "10.1/lm", "type": "article-journal", "title": "A &amp; B", "container-title": "Learning &amp; Memory"},
        source_type="doi", source_ref="10.1/lm",
    )
    assert rec.journal == "Learning & Memory" and rec.title == "A & B"
    out = render_bibtex([("lm_2001_X", rec)])
    assert "journal = {Learning \\& Memory}" in out and "title = {A \\& B}" in out
