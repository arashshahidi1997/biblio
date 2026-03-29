from __future__ import annotations

import json
from pathlib import Path

from biblio.cli import main as biblio_main
from biblio.ingest import ingest_file
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
