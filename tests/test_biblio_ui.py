from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from biblio.config import load_biblio_config
from biblio.scaffold import init_bib_scaffold
from biblio.ui import create_ui_app


def test_ui_api_exposes_model_and_index(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "library.bib").write_text(
        "@article{paper2024, title={Paper Title}, year={2024}, author={Doe, Jane}}\n",
        encoding="utf-8",
    )
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    cfg.openalex.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    cfg.openalex.out_jsonl.write_text(
        json.dumps(
            {
                "citekey": "paper2024",
                "display_name": "Paper Title",
                "openalex_id": "W1",
                "openalex_url": "https://openalex.org/W1",
                "publication_year": 2024,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    client = TestClient(create_ui_app(cfg))
    index = client.get("/")
    assert index.status_code == 200
    assert "cytoscape" in index.text.lower()

    payload = client.get("/api/model")
    assert payload.status_code == 200
    data = payload.json()
    assert data["status"]["papers_total"] == 1
    assert data["papers"][0]["citekey"] == "paper2024"


def test_ui_action_endpoint_for_docling_validates_payload(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/actions/docling-run", json={})
    assert resp.status_code == 400
    assert "Missing citekey" in resp.json()["detail"]
