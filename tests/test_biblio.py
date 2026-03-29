from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from biblio.citekeys import add_citekeys_md, load_citekeys_md, parse_citekeys_from_markdown, remove_citekeys_md
from biblio.bibtex import BibtexMergeConfig, merge_srcbib
from biblio.bibtex_export import export_bibtex
from biblio.config import load_biblio_config
from biblio.docling import outputs_for_key
from biblio.openalex import resolve_openalex
from biblio.paths import find_repo_root
from biblio.pdf_fetch import PdfFetchConfig, fetch_pdfs
from biblio.scaffold import init_bib_scaffold
from biblio.cli import _build_screen_bash_command


def test_parse_citekeys_from_markdown_order_unique() -> None:
    text = """
    # Heading with @not_a_key should be ignored
    # Example: @key

    - @a_2020_Test
    - @b_2021_Test  extra words ignored
    - @a_2020_Test

    ```text
    - @in_code_block_should_be_ignored
    ```
    """
    assert parse_citekeys_from_markdown(text) == ["a_2020_Test", "b_2021_Test"]


def test_citekeys_add_remove_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "citekeys.md"
    add_citekeys_md(path, ["@a", "b"])
    assert load_citekeys_md(path) == ["a", "b"]
    add_citekeys_md(path, ["@a", "c"])
    assert load_citekeys_md(path) == ["a", "b", "c"]
    remove_citekeys_md(path, ["b"])
    assert load_citekeys_md(path) == ["a", "c"]


def test_init_bib_scaffold(tmp_path: Path) -> None:
    res = init_bib_scaffold(tmp_path, force=False)
    assert (tmp_path / "bib" / "Makefile").exists()
    assert (tmp_path / "bib" / "config" / "biblio.yml").exists()
    assert (tmp_path / "bib" / "config" / "citekeys.md").exists()
    assert (tmp_path / "bib" / "config" / "rag.yaml").exists()
    assert (tmp_path / "bib" / ".gitignore").exists()
    assert res.root == tmp_path.resolve()

def test_find_repo_root_prefers_biblio_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "bib" / "config").mkdir(parents=True)
    (tmp_path / "bib" / "config" / "biblio.yml").write_text("{}", encoding="utf-8")

    deep = tmp_path / "docs" / "tutorials" / "deeplabcut"
    deep.mkdir(parents=True)
    assert find_repo_root(deep) == tmp_path.resolve()


def test_citekeys_status_lists_candidates_and_configured(tmp_path: Path, capsys) -> None:
    init_bib_scaffold(tmp_path, force=False)
    (tmp_path / "bib" / "srcbib").mkdir(parents=True, exist_ok=True)
    (tmp_path / "bib" / "srcbib" / "library.bib").write_text(
        (
            "@article{configured2024, title={Configured Paper}, year={2024}}\n"
            "@article{candidate2025, title={Candidate Paper}, year={2025}}\n"
        ),
        encoding="utf-8",
    )
    add_citekeys_md(tmp_path / "bib" / "config" / "citekeys.md", ["configured2024"])

    from biblio.cli import main as biblio_main

    biblio_main(["citekeys", "status", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "configured2024\tconfigured" in out
    assert "candidate2025\tcandidate" in out


def test_bibtex_merge_drops_file_field(tmp_path: Path) -> None:
    from pybtex.database import parse_file

    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    (src_dir / "a.bib").write_text(
        "@article{a2020, title={A}, file={/abs/path/a.pdf}}\n",
        encoding="utf-8",
    )
    (src_dir / "b.bib").write_text(
        "@article{b2021, title={B}, file={/abs/path/b.pdf}}\n",
        encoding="utf-8",
    )

    out_bib = tmp_path / "bib" / "main.bib"
    cfg = BibtexMergeConfig(
        repo_root=tmp_path,
        src_dir=src_dir,
        src_glob="*.bib",
        out_bib=out_bib,
        file_field_mode="drop",
        file_field_template="bib/articles/{citekey}/{citekey}.pdf",
        duplicates_log=tmp_path / "bib" / "logs" / "duplicate_bib_ids.txt",
    )
    n_sources, n_entries = merge_srcbib(cfg, dry_run=False)
    assert n_sources == 2
    assert n_entries == 2

    db = parse_file(str(out_bib))
    assert set(db.entries.keys()) == {"a2020", "b2021"}
    assert "file" not in db.entries["a2020"].fields
    assert "file" not in db.entries["b2021"].fields
    runs = (tmp_path / "bib" / "logs" / "runs" / "bibtex_merge.jsonl").read_text(encoding="utf-8")
    assert "bibtex_merge" in runs
    assert "source_bib" in runs


def test_bibtex_merge_tolerates_duplicate_citekeys(tmp_path: Path) -> None:
    from pybtex.database import parse_file

    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    (src_dir / "dup.bib").write_text(
        (
            "@article{dupkey, title={First}, file={/abs/path/first.pdf}}\n"
            "@article{dupkey, title={Second}, file={/abs/path/second.pdf}}\n"
        ),
        encoding="utf-8",
    )

    out_bib = tmp_path / "bib" / "main.bib"
    cfg = BibtexMergeConfig(
        repo_root=tmp_path,
        src_dir=src_dir,
        src_glob="*.bib",
        out_bib=out_bib,
        file_field_mode="drop",
        file_field_template="bib/articles/{citekey}/{citekey}.pdf",
        duplicates_log=tmp_path / "bib" / "logs" / "duplicate_bib_ids.txt",
    )

    n_sources, n_entries = merge_srcbib(cfg, dry_run=False)
    assert n_sources == 1
    assert n_entries == 1

    db = parse_file(str(out_bib))
    assert list(db.entries.keys()) == ["dupkey"]


def test_fetch_pdfs_from_file_field(tmp_path: Path) -> None:
    src_pdf = tmp_path / "Downloads" / "paper.pdf"
    src_pdf.parent.mkdir(parents=True)
    src_pdf.write_bytes(b"%PDF-1.4 fake\n")

    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    # common BetterBibTeX-style file field with mime suffix
    (src_dir / "zotero.bib").write_text(
        f"@article{{k2020, title={{K}}, file={{{src_pdf}:application/pdf}}}}\n",
        encoding="utf-8",
    )

    cfg = PdfFetchConfig(
        repo_root=tmp_path,
        src_dir=src_dir,
        src_glob="*.bib",
        dest_root=tmp_path / "bib" / "articles",
        dest_pattern="{citekey}/{citekey}.pdf",
        mode="copy",
        hash_mode="md5",
        manifest_path=tmp_path / "bib" / "logs" / "pdf_manifest.json",
        missing_log=tmp_path / "bib" / "logs" / "missing_pdfs.txt",
    )

    counts = fetch_pdfs(cfg, dry_run=False, force=False)
    assert counts["sources"] == 1
    assert counts["linked"] == 1
    dest = tmp_path / "bib" / "articles" / "k2020" / "k2020.pdf"
    assert dest.exists()
    runs = (tmp_path / "bib" / "logs" / "runs" / "bibtex_fetch.jsonl").read_text(encoding="utf-8")
    assert "k2020" in runs
    assert "zotero.bib" in runs
    assert "source_bib" in runs


def test_build_screen_bash_command_includes_root(tmp_path: Path) -> None:
    cmd = _build_screen_bash_command(
        repo_root=tmp_path,
        python_exe="/usr/bin/python3",
        docling_args=["--all", "--force"],
    )
    assert f"cd {tmp_path}" in cmd
    assert "biblio.cli" in cmd
    assert "--root" in cmd
    assert "--all" in cmd


def test_fetch_pdfs_from_plain_file_field(tmp_path: Path) -> None:
    src_pdf = tmp_path / "Downloads" / "paper.pdf"
    src_pdf.parent.mkdir(parents=True)
    src_pdf.write_bytes(b"%PDF-1.4 fake\n")

    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    # plain absolute path (no mime suffix)
    (src_dir / "zotero.bib").write_text(
        f"@article{{k2021, title={{K}}, file={{{src_pdf}}}}}\n",
        encoding="utf-8",
    )

    cfg = PdfFetchConfig(
        repo_root=tmp_path,
        src_dir=src_dir,
        src_glob="*.bib",
        dest_root=tmp_path / "bib" / "articles",
        dest_pattern="{citekey}/{citekey}.pdf",
        mode="copy",
        hash_mode="md5",
        manifest_path=tmp_path / "bib" / "logs" / "pdf_manifest.json",
        missing_log=tmp_path / "bib" / "logs" / "missing_pdfs.txt",
    )

    counts = fetch_pdfs(cfg, dry_run=False, force=False)
    assert counts["sources"] == 1
    assert counts["linked"] == 1
    dest = tmp_path / "bib" / "articles" / "k2021" / "k2021.pdf"
    assert dest.exists()


def test_fetch_pdfs_tolerates_duplicate_citekeys(tmp_path: Path) -> None:
    first_pdf = tmp_path / "Downloads" / "first.pdf"
    second_pdf = tmp_path / "Downloads" / "second.pdf"
    first_pdf.parent.mkdir(parents=True)
    first_pdf.write_bytes(b"%PDF-1.4 first\n")
    second_pdf.write_bytes(b"%PDF-1.4 second\n")

    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    (src_dir / "zotero.bib").write_text(
        (
            f"@article{{dupkey, title={{One}}, file={{{first_pdf}}}}}\n"
            f"@article{{dupkey, title={{Two}}, file={{{second_pdf}}}}}\n"
        ),
        encoding="utf-8",
    )

    cfg = PdfFetchConfig(
        repo_root=tmp_path,
        src_dir=src_dir,
        src_glob="*.bib",
        dest_root=tmp_path / "bib" / "articles",
        dest_pattern="{citekey}/{citekey}.pdf",
        mode="copy",
        hash_mode="md5",
        manifest_path=tmp_path / "bib" / "logs" / "pdf_manifest.json",
        missing_log=tmp_path / "bib" / "logs" / "missing_pdfs.txt",
    )

    counts = fetch_pdfs(cfg, dry_run=False, force=False)
    assert counts["sources"] == 1
    assert counts["linked"] == 1
    dest = tmp_path / "bib" / "articles" / "dupkey" / "dupkey.pdf"
    assert dest.exists()


def test_docling_outputs_have_provenance_sidecar(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    out = outputs_for_key(cfg, "smith2020")
    out.outdir.mkdir(parents=True)
    out.md_path.write_text("# x\n", encoding="utf-8")
    out.json_path.write_text("{\"x\": 1}\n", encoding="utf-8")

    pdf_dir = tmp_path / "bib" / "articles" / "smith2020"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "smith2020.pdf").write_bytes(b"%PDF-1.4 fake\n")

    from biblio.docling import run_docling_for_key

    run_docling_for_key(cfg, "smith2020", force=False)

    assert out.meta_path.exists()
    meta = out.meta_path.read_text(encoding="utf-8")
    assert "pdf_sha256" in meta
    assert "source_pdf" in meta
    assert "smith2020.pdf" in meta
    runs = (tmp_path / "bib" / "logs" / "runs" / "docling.jsonl").read_text(encoding="utf-8")
    assert "reused" in runs


def test_openalex_config_defaults(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    assert cfg.openalex.cache_root == (tmp_path / "bib" / "derivatives" / "openalex" / "cache").resolve()
    assert cfg.openalex.out_jsonl == (tmp_path / "bib" / "derivatives" / "openalex" / "resolved.jsonl").resolve()
    assert cfg.openalex.out_csv == (tmp_path / "bib" / "derivatives" / "openalex" / "resolved.csv").resolve()


def test_openalex_resolve_doi_and_title_fallback(tmp_path: Path) -> None:
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    (src_dir / "a.bib").write_text(
        """
@article{doi_key, title={A DOI-backed paper}, doi={10.1000/example}}
@article{title_key, title={Fallback title only}}
@article{miss_key, title={No match title}}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = load_biblio_config(tmp_path / "missing.yml", root=tmp_path)

    def fake_fetch(url: str) -> dict:
        if "/works/https://doi.org/10.1000%2Fexample" in url:
            return {"id": "https://openalex.org/W1", "display_name": "A DOI-backed paper"}
        if "search=Fallback+title+only" in url:
            return {"results": [{"id": "https://openalex.org/W2", "display_name": "Fallback title only"}]}
        if "search=No+match+title" in url:
            return {"results": []}
        raise AssertionError(url)

    counts = resolve_openalex(cfg.openalex, fetch_json=fake_fetch)
    assert counts == {"sources": 1, "entries": 3, "resolved": 2, "unresolved": 1}

    rows = [json.loads(line) for line in cfg.openalex.out_jsonl.read_text(encoding="utf-8").splitlines()]
    assert [row["citekey"] for row in rows] == ["doi_key", "miss_key", "title_key"]
    assert rows[0]["resolution_method"] == "doi"
    assert rows[0]["status"] == "resolved"
    assert rows[0]["openalex_id"] == "https://openalex.org/W1"
    assert rows[1]["status"] == "unresolved"
    assert rows[2]["resolution_method"] == "title"
    assert "source_bib" in rows[2]
    assert cfg.openalex.out_csv is not None and cfg.openalex.out_csv.exists()
    run_log = (tmp_path / "bib" / "logs" / "runs" / "openalex_resolve.jsonl").read_text(encoding="utf-8")
    assert "resolved" in run_log


def test_openalex_resolve_reuses_cache(tmp_path: Path) -> None:
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True)
    (src_dir / "a.bib").write_text(
        "@article{title_key, title={Cached title only}}\n",
        encoding="utf-8",
    )
    cfg = load_biblio_config(tmp_path / "missing.yml", root=tmp_path)
    title_cache = cfg.openalex.cache_root / "title"
    title_cache.mkdir(parents=True, exist_ok=True)
    cache_file = title_cache / f"{hashlib.sha256('Cached title only'.encode('utf-8')).hexdigest()}.json"
    cache_file.write_text(
        json.dumps({"results": [{"id": "https://openalex.org/W3", "display_name": "Cached title only"}]}),
        encoding="utf-8",
    )

    def fail_fetch(url: str) -> dict:
        raise AssertionError(url)

    counts = resolve_openalex(cfg.openalex, fetch_json=fail_fetch)
    assert counts["resolved"] == 1
    rows = [json.loads(line) for line in cfg.openalex.out_jsonl.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["openalex_id"] == "https://openalex.org/W3"


# ── bibtex export ────────────────────────────────────────────────────────


def _make_merged_bib(tmp_path: Path) -> Path:
    """Helper: create a minimal bib/main.bib with two entries."""
    bib_dir = tmp_path / "bib"
    bib_dir.mkdir(parents=True, exist_ok=True)
    main_bib = bib_dir / "main.bib"
    main_bib.write_text(
        "@article{smith_2020, title={Alpha}, author={Smith, J.}}\n"
        "@article{jones_2021, title={Beta}, author={Jones, K.}}\n"
        "@article{doe_2019, title={Gamma}, author={Doe, A.}}\n",
        encoding="utf-8",
    )
    return main_bib


def test_export_bibtex_selected_keys(tmp_path: Path) -> None:
    _make_merged_bib(tmp_path)
    result = export_bibtex(["smith_2020", "doe_2019"], repo_root=tmp_path)
    assert "smith_2020" in result
    assert "doe_2019" in result
    assert "jones_2021" not in result


def test_export_bibtex_strips_at_prefix(tmp_path: Path) -> None:
    _make_merged_bib(tmp_path)
    result = export_bibtex(["@smith_2020"], repo_root=tmp_path)
    assert "smith_2020" in result


def test_export_bibtex_missing_keys_raises(tmp_path: Path) -> None:
    _make_merged_bib(tmp_path)
    with pytest.raises(KeyError):
        export_bibtex(["nonexistent_key"], repo_root=tmp_path)


def test_export_bibtex_no_merged_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_bibtex(["smith_2020"], repo_root=tmp_path)
