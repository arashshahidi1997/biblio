from __future__ import annotations

import json
from pathlib import Path

from biblio.cli import main as biblio_main
from biblio.config import load_biblio_config
from biblio.scaffold import init_bib_scaffold
from biblio.site import BiblioSiteOptions, build_biblio_site, clean_biblio_site, doctor_biblio_site


def _write_srcbib(root: Path, citekey: str = "paper2024") -> None:
    src_dir = root / "bib" / "srcbib"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "library.bib").write_text(
        f"@article{{{citekey}, title={{Paper Title}}, year={{2024}}, doi={{10.1000/example}}, author={{Doe, Jane and Roe, Richard}}}}\n",
        encoding="utf-8",
    )


def test_build_biblio_site_minimal(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _write_srcbib(tmp_path)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    result = build_biblio_site(cfg)

    assert result.out_dir == (tmp_path / "bib" / "site").resolve()
    assert (result.out_dir / "index.html").exists()
    assert (result.out_dir / "papers" / "index.html").exists()
    assert (result.out_dir / "papers" / "paper2024.html").exists()
    assert (result.out_dir / "_data" / "papers.json").exists()

    status = json.loads((result.out_dir / "_data" / "status.json").read_text(encoding="utf-8"))
    assert status["papers_total"] == 1
    assert status["missing_pdf"] == ["paper2024"]
    assert status["missing_docling"] == ["paper2024"]
    assert status["missing_openalex"] == ["paper2024"]


def test_build_biblio_site_with_docling_openalex_and_graph(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "library.bib").write_text(
        (
            "@article{paper2024, title={Paper Title}, year={2024}, doi={10.1000/example}, author={Doe, Jane}}\n"
            "@article{paper2025, title={Paper Followup}, year={2025}, doi={10.1000/example2}, author={Roe, Richard}}\n"
        ),
        encoding="utf-8",
    )
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    paper_dir = cfg.out_root / "paper2024"
    paper_dir.mkdir(parents=True)
    (paper_dir / "paper2024.md").write_text("# Paper Title\n\n- finding one\n", encoding="utf-8")
    (paper_dir / "paper2024.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    (paper_dir / "_biblio.json").write_text("{\"ok\": true}\n", encoding="utf-8")
    (paper_dir / "paper2024_summary.md").write_text("summary\n", encoding="utf-8")
    (paper_dir / "paper2024_notes.md").write_text("notes\n", encoding="utf-8")

    cfg.openalex.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    cfg.openalex.out_jsonl.write_text(
        (
            json.dumps(
                {
                    "citekey": "paper2024",
                    "display_name": "Paper Title",
                    "openalex_id": "W1",
                    "openalex_url": "https://openalex.org/W1",
                    "publication_year": 2024,
                },
                sort_keys=True,
            )
            + "\n"
            + json.dumps(
                {
                    "citekey": "paper2025",
                    "display_name": "Paper Followup",
                    "openalex_id": "W2",
                    "openalex_url": "https://openalex.org/W2",
                    "publication_year": 2025,
                },
                sort_keys=True,
            )
            + "\n"
        ),
        encoding="utf-8",
    )
    (cfg.openalex.out_jsonl.parent / "graph_candidates.json").write_text(
        json.dumps(
            [
                {
                    "seed_openalex_id": "W1",
                    "openalex_id": "W2",
                    "openalex_url": "https://openalex.org/W2",
                },
                {
                    "seed_openalex_id": "W2",
                    "openalex_id": "W1",
                    "openalex_url": "https://openalex.org/W1",
                },
                {
                    "seed_openalex_id": "W2",
                    "openalex_id": "W3",
                    "openalex_url": "https://openalex.org/W3",
                }
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = build_biblio_site(cfg)
    paper_html = (result.out_dir / "papers" / "paper2024.html").read_text(encoding="utf-8")
    assert "Docling content" in paper_html
    assert "Graph neighborhood" in paper_html
    assert "paper2024_summary.md" in paper_html
    assert "paper2024_notes.md" in paper_html
    graph_html = (result.out_dir / "graph.html").read_text(encoding="utf-8")
    assert 'id="graph-canvas"' in graph_html
    assert "Related local papers" in graph_html

    graph_payload = json.loads((result.out_dir / "_data" / "graph.json").read_text(encoding="utf-8"))
    assert len(graph_payload["edges"]) == 3
    assert graph_payload["edges"][0]["kind"] == "references"
    graph_papers = {item["citekey"]: item for item in graph_payload["papers"]}
    assert graph_papers["paper2024"]["related_local"][0]["citekey"] == "paper2025"


def test_biblio_site_doctor_cli_and_clean(tmp_path: Path, capsys) -> None:
    init_bib_scaffold(tmp_path, force=False)
    _write_srcbib(tmp_path, citekey="paper2024")
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    report = doctor_biblio_site(cfg, options=BiblioSiteOptions(out_dir=tmp_path / "bib" / "site"))
    assert report.papers_total == 1
    assert report.missing_docling == 1

    biblio_main(["site", "doctor", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "papers=1" in out
    assert "missing_docling=1" in out

    build_biblio_site(cfg, force=False)
    cleaned = clean_biblio_site(tmp_path)
    assert cleaned == (tmp_path / "bib" / "site").resolve()
    assert not cleaned.exists()
