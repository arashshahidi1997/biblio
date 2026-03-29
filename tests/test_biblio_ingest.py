from __future__ import annotations

import json
from pathlib import Path

from biblio.cli import main as biblio_main
from biblio.ingest import find_existing_dois, ingest_file
from biblio.scaffold import init_bib_scaffold


def test_ingest_csljson_writes_imported_bib_and_log(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    csl = tmp_path / "sample.json"
    csl.write_text(
        json.dumps(
            [
                {
                    "id": "paper-1",
                    "type": "article-journal",
                    "title": "Paper One",
                    "DOI": "10.1000/example",
                    "URL": "https://example.com/paper",
                    "author": [{"family": "Doe", "given": "Jane"}],
                    "issued": {"date-parts": [[2024]]},
                    "container-title": "Journal of Tests",
                }
            ]
        ),
        encoding="utf-8",
    )

    result, _ = ingest_file(repo_root=tmp_path, source_type="csljson", input_path=csl)
    out_bib = tmp_path / "bib" / "srcbib" / "imported.bib"
    assert result.output_path == out_bib
    text = out_bib.read_text(encoding="utf-8")
    assert "@article{doe_2024_PaperOne" in text
    assert "journal = {Journal of Tests}" in text
    log_text = (tmp_path / "bib" / "logs" / "imports.jsonl").read_text(encoding="utf-8")
    assert '"source_type": "csljson"' in log_text


def test_ingest_ris_parses_and_dry_runs(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    ris = tmp_path / "sample.ris"
    ris.write_text(
        "TY  - JOUR\n"
        "TI  - RIS Imported Paper\n"
        "AU  - Doe, Jane\n"
        "PY  - 2023\n"
        "DO  - 10.1000/ris-example\n"
        "JO  - RIS Journal\n"
        "ER  - \n",
        encoding="utf-8",
    )

    result, bibtex_text = ingest_file(repo_root=tmp_path, source_type="ris", input_path=ris, dry_run=True)
    assert result.parsed == 1
    assert result.emitted == 1
    assert not (tmp_path / "bib" / "srcbib" / "imported.bib").exists()
    assert "@article{doe_2023_RisImported" in bibtex_text


def test_ingest_dois_cli_stdout(tmp_path: Path, capsys) -> None:
    init_bib_scaffold(tmp_path, force=False)
    dois = tmp_path / "dois.txt"
    dois.write_text("# comment\n10.1000/alpha\n10.1000/beta\n", encoding="utf-8")

    biblio_main(["ingest", "dois", str(dois), "--root", str(tmp_path), "--stdout"])
    out = capsys.readouterr().out
    assert "@misc{anon_nd_Alpha" in out
    assert "doi = {10.1000/beta}" in out


def test_ingest_dois_enriches_with_openalex_metadata(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    dois = tmp_path / "dois.txt"
    dois.write_text("10.1000/alpha\n", encoding="utf-8")

    def fake_fetch(url: str) -> dict:
        assert "10.1000%2Falpha" in url
        return {
            "display_name": "Alpha Paper",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "Jane Doe"}}],
            "ids": {"openalex": "https://openalex.org/W1"},
        }

    result, bibtex_text = ingest_file(
        repo_root=tmp_path,
        source_type="dois",
        input_path=dois,
        dry_run=True,
        doi_fetch_json=fake_fetch,
    )
    assert result.emitted == 1
    assert "@article{doe_2024_AlphaPaper" in bibtex_text
    assert "title = {Alpha Paper}" in bibtex_text
    assert "author = {Jane Doe}" in bibtex_text


def test_ingest_pdfs_copies_into_articles_and_emits_file_field(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    src_pdf = tmp_path / "downloads" / "Interesting-Paper.pdf"
    src_pdf.parent.mkdir(parents=True, exist_ok=True)
    src_pdf.write_bytes(b"%PDF-1.4 fake\n")

    result, bibtex_text = ingest_file(
        repo_root=tmp_path,
        source_type="pdfs",
        input_paths=[src_pdf],
    )
    assert result.emitted == 1
    dest = tmp_path / "bib" / "articles" / "anon_nd_InterestingPaper" / "anon_nd_InterestingPaper.pdf"
    assert dest.exists()
    text = (tmp_path / "bib" / "srcbib" / "imported.bib").read_text(encoding="utf-8")
    assert "file = {bib/articles/anon_nd_InterestingPaper/anon_nd_InterestingPaper.pdf}" in text
    assert "@misc{anon_nd_InterestingPaper" in bibtex_text


def test_ingest_appends_second_batch(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps([{"title": "First Paper", "author": [{"family": "Doe"}], "issued": {"date-parts": [[2024]]}}]), encoding="utf-8")
    b.write_text(json.dumps([{"title": "Second Paper", "author": [{"family": "Roe"}], "issued": {"date-parts": [[2025]]}}]), encoding="utf-8")

    ingest_file(repo_root=tmp_path, source_type="csljson", input_path=a)
    ingest_file(repo_root=tmp_path, source_type="csljson", input_path=b)
    text = (tmp_path / "bib" / "srcbib" / "imported.bib").read_text(encoding="utf-8")
    assert "@article{doe_2024_FirstPaper" in text
    assert "@article{roe_2025_SecondPaper" in text


# ---------------------------------------------------------------------------
# Duplicate detection tests
# ---------------------------------------------------------------------------


def _seed_bib(tmp_path: Path, entries: str) -> None:
    """Write a .bib file into bib/srcbib/ for duplicate detection to find."""
    bib_dir = tmp_path / "bib" / "srcbib"
    bib_dir.mkdir(parents=True, exist_ok=True)
    (bib_dir / "seed.bib").write_text(entries, encoding="utf-8")


def test_find_existing_dois_discovers_doi_in_srcbib(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _seed_bib(tmp_path, (
        "@article{doe_2024_Alpha,\n"
        "  title = {Alpha Paper},\n"
        "  doi = {10.1000/alpha}\n"
        "}\n"
    ))
    doi_map = find_existing_dois(tmp_path)
    assert "10.1000/alpha" in doi_map
    assert doi_map["10.1000/alpha"] == "doe_2024_Alpha"


def test_find_existing_dois_empty_when_no_srcbib(tmp_path: Path) -> None:
    # No bib/srcbib directory at all
    assert find_existing_dois(tmp_path) == {}


def test_ingest_dois_skips_duplicate_doi(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _seed_bib(tmp_path, (
        "@article{doe_2024_Alpha,\n"
        "  title = {Alpha Paper},\n"
        "  doi = {10.1000/alpha}\n"
        "}\n"
    ))
    dois = tmp_path / "dois.txt"
    dois.write_text("10.1000/alpha\n10.1000/beta\n", encoding="utf-8")

    fetch_called_with: list[str] = []

    def fake_fetch(url: str) -> dict:
        fetch_called_with.append(url)
        return {
            "display_name": "Beta Paper",
            "publication_year": 2025,
            "authorships": [{"author": {"display_name": "Jane Roe"}}],
            "ids": {"openalex": "https://openalex.org/W2"},
        }

    result, bibtex_text = ingest_file(
        repo_root=tmp_path,
        source_type="dois",
        input_path=dois,
        dry_run=True,
        doi_fetch_json=fake_fetch,
    )
    # alpha was skipped, beta was ingested
    assert result.emitted == 1
    assert result.parsed == 2
    assert len(result.skipped) == 1
    assert result.skipped[0] == ("10.1000/alpha", "doe_2024_Alpha")
    assert "10.1000/beta" in bibtex_text
    assert "10.1000/alpha" not in bibtex_text
    # OpenAlex should only have been called for beta, not alpha
    assert len(fetch_called_with) == 1
    assert "10.1000%2Fbeta" in fetch_called_with[0]


def test_ingest_dois_force_reingests_duplicate(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _seed_bib(tmp_path, (
        "@article{doe_2024_Alpha,\n"
        "  title = {Alpha Paper},\n"
        "  doi = {10.1000/alpha}\n"
        "}\n"
    ))
    dois = tmp_path / "dois.txt"
    dois.write_text("10.1000/alpha\n", encoding="utf-8")

    def fake_fetch(url: str) -> dict:
        return {
            "display_name": "Alpha Paper Updated",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "Jane Doe"}}],
            "ids": {"openalex": "https://openalex.org/W1"},
        }

    result, bibtex_text = ingest_file(
        repo_root=tmp_path,
        source_type="dois",
        input_path=dois,
        dry_run=True,
        doi_fetch_json=fake_fetch,
        force=True,
    )
    assert result.emitted == 1
    assert len(result.skipped) == 0
    assert "Alpha Paper Updated" in bibtex_text


def test_ingest_csljson_skips_duplicate_doi(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _seed_bib(tmp_path, (
        "@article{doe_2024_Alpha,\n"
        "  title = {Alpha Paper},\n"
        "  doi = {10.1000/alpha}\n"
        "}\n"
    ))
    csl = tmp_path / "sample.json"
    csl.write_text(json.dumps([
        {
            "id": "paper-1",
            "type": "article-journal",
            "title": "Alpha Paper",
            "DOI": "10.1000/alpha",
            "author": [{"family": "Doe", "given": "Jane"}],
            "issued": {"date-parts": [[2024]]},
        },
        {
            "id": "paper-2",
            "type": "article-journal",
            "title": "New Paper",
            "DOI": "10.1000/new",
            "author": [{"family": "Roe", "given": "John"}],
            "issued": {"date-parts": [[2025]]},
        },
    ]), encoding="utf-8")

    result, bibtex_text = ingest_file(
        repo_root=tmp_path,
        source_type="csljson",
        input_path=csl,
        dry_run=True,
    )
    assert result.emitted == 1
    assert len(result.skipped) == 1
    assert result.skipped[0][0] == "10.1000/alpha"
    assert "New Paper" in bibtex_text
    assert "Alpha Paper" not in bibtex_text


def test_ingest_skipped_field_default_empty(tmp_path: Path) -> None:
    """IngestResult.skipped defaults to empty tuple when no duplicates."""
    init_bib_scaffold(tmp_path, force=False)
    csl = tmp_path / "sample.json"
    csl.write_text(json.dumps([
        {
            "id": "paper-1",
            "type": "article-journal",
            "title": "Unique Paper",
            "author": [{"family": "Doe"}],
            "issued": {"date-parts": [[2024]]},
        },
    ]), encoding="utf-8")

    result, _ = ingest_file(
        repo_root=tmp_path,
        source_type="csljson",
        input_path=csl,
        dry_run=True,
    )
    assert result.skipped == ()
    assert result.emitted == 1


# ---------------------------------------------------------------------------
# BibTeX preview and import tests
# ---------------------------------------------------------------------------

from biblio.ingest import preview_bibtex, import_bibtex_entries

_SAMPLE_BIB = """\
@article{doe_2024_Alpha,
  title = {Alpha Paper},
  author = {Jane Doe},
  year = {2024},
  doi = {10.1000/alpha},
}

@inproceedings{roe_2025_Beta,
  title = {Beta Paper},
  author = {John Roe},
  year = {2025},
  doi = {10.1000/beta},
}
"""


def test_preview_bibtex_parses_entries(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    entries = preview_bibtex(_SAMPLE_BIB, tmp_path)
    assert len(entries) == 2
    keys = {e.citekey for e in entries}
    assert "doe_2024_Alpha" in keys
    assert "roe_2025_Beta" in keys
    # All should be new (no existing bib)
    for e in entries:
        assert e.already_exists is False
    # Check fields parsed
    alpha = next(e for e in entries if e.citekey == "doe_2024_Alpha")
    assert alpha.title == "Alpha Paper"
    assert alpha.year == "2024"
    assert alpha.doi == "10.1000/alpha"
    assert alpha.entry_type == "article"
    assert len(alpha.authors) > 0


def test_preview_bibtex_detects_duplicates(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _seed_bib(tmp_path, (
        "@article{existing_2024_Paper,\n"
        "  title = {Existing Paper},\n"
        "  doi = {10.1000/alpha}\n"
        "}\n"
    ))
    entries = preview_bibtex(_SAMPLE_BIB, tmp_path)
    alpha = next(e for e in entries if e.citekey == "doe_2024_Alpha")
    beta = next(e for e in entries if e.citekey == "roe_2025_Beta")
    # alpha shares DOI with existing entry → duplicate
    assert alpha.already_exists is True
    # beta is new
    assert beta.already_exists is False


def test_preview_bibtex_detects_citekey_duplicate(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _seed_bib(tmp_path, (
        "@article{doe_2024_Alpha,\n"
        "  title = {Alpha Paper Original},\n"
        "}\n"
    ))
    entries = preview_bibtex(_SAMPLE_BIB, tmp_path)
    alpha = next(e for e in entries if e.citekey == "doe_2024_Alpha")
    assert alpha.already_exists is True


def test_import_bibtex_entries_writes_to_srcbib(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    count, keys = import_bibtex_entries(
        bibtex_text=_SAMPLE_BIB,
        selected_citekeys=["doe_2024_Alpha", "roe_2025_Beta"],
        repo_root=tmp_path,
    )
    assert count == 2
    assert set(keys) == {"doe_2024_Alpha", "roe_2025_Beta"}
    # Check bib file written
    bib_text = (tmp_path / "bib" / "srcbib" / "imported.bib").read_text(encoding="utf-8")
    assert "doe_2024_Alpha" in bib_text
    assert "roe_2025_Beta" in bib_text
    assert "Alpha Paper" in bib_text
    # Check citekeys.md updated
    ck_text = (tmp_path / "bib" / "citekeys.md").read_text(encoding="utf-8")
    assert "doe_2024_Alpha" in ck_text
    assert "roe_2025_Beta" in ck_text
    # Check import log
    log = (tmp_path / "bib" / "logs" / "imports.jsonl").read_text(encoding="utf-8")
    assert '"source_type": "bibtex_import"' in log


def test_import_bibtex_entries_selective(tmp_path: Path) -> None:
    """Only import selected citekeys."""
    init_bib_scaffold(tmp_path, force=False)
    count, keys = import_bibtex_entries(
        bibtex_text=_SAMPLE_BIB,
        selected_citekeys=["roe_2025_Beta"],
        repo_root=tmp_path,
    )
    assert count == 1
    assert keys == ["roe_2025_Beta"]
    bib_text = (tmp_path / "bib" / "srcbib" / "imported.bib").read_text(encoding="utf-8")
    assert "roe_2025_Beta" in bib_text
    assert "doe_2024_Alpha" not in bib_text


def test_import_bibtex_entries_empty_selection(tmp_path: Path) -> None:
    """Import with no valid citekeys returns 0."""
    init_bib_scaffold(tmp_path, force=False)
    count, keys = import_bibtex_entries(
        bibtex_text=_SAMPLE_BIB,
        selected_citekeys=["nonexistent_key"],
        repo_root=tmp_path,
    )
    assert count == 0
    assert keys == []
