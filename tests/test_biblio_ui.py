from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from biblio.config import load_biblio_config
from biblio.rag_support import load_raw_rag_config
from biblio.scaffold import init_bib_scaffold
from biblio.ui import create_ui_app, find_available_port


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
    assert "/static/app.js" in index.text

    payload = client.get("/api/model")
    assert payload.status_code == 200
    data = payload.json()
    assert data["status"]["papers_total"] == 1
    assert data["papers"][0]["citekey"] == "paper2024"

    setup = client.get("/api/setup")
    assert setup.status_code == 200
    setup_data = setup.json()
    assert "docling" in setup_data
    assert "rag" in setup_data
    assert setup_data["rag"]["config_path"].endswith(".projio/biblio/rag.yaml")


def test_ui_can_serve_pdf_for_paper(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "library.bib").write_text(
        "@article{paper2024, title={Paper Title}, year={2024}, author={Doe, Jane}}\n",
        encoding="utf-8",
    )
    pdf_dir = tmp_path / "bib" / "articles" / "paper2024"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / "paper2024.pdf").write_bytes(b"%PDF-1.4\n% demo\n")
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    client = TestClient(create_ui_app(cfg))
    resp = client.get("/api/files/pdf/paper2024")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "inline" in resp.headers.get("content-disposition", "").lower()


def test_ui_serves_docling_artifact_via_symlink(tmp_path: Path) -> None:
    """Symlinked files (git-annex style) must be served, not rejected with 403."""
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    # Simulate an annex-style symlink: real file lives outside out_root
    annex_store = tmp_path / "annex" / "objects"
    annex_store.mkdir(parents=True)
    real_file = annex_store / "image_000000.png"
    real_file.write_bytes(b"\x89PNG\r\n")

    artifact_dir = cfg.out_root / "paper2024" / "paper2024_artifacts"
    artifact_dir.mkdir(parents=True)
    symlink = artifact_dir / "image_000000.png"
    symlink.symlink_to(real_file)

    client = TestClient(create_ui_app(cfg))
    resp = client.get("/api/files/docling/paper2024/paper2024_artifacts/image_000000.png")
    assert resp.status_code == 200


def test_ui_docling_artifact_rejects_path_traversal(tmp_path: Path) -> None:
    """Path traversal attempts must not return 200 (file not served)."""
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    # Write a sensitive file one level above out_root
    secret = cfg.out_root.parent / "secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("secret", encoding="utf-8")

    client = TestClient(create_ui_app(cfg))
    # Framework normalizes ../ before the handler, so the file is never served
    resp = client.get("/api/files/docling/paper2024/../../secret.txt")
    assert resp.status_code != 200


def test_ui_action_endpoint_for_docling_validates_payload(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/actions/docling-run", json={})
    assert resp.status_code == 400
    assert "Missing citekey" in resp.json()["detail"]


def test_ui_docling_action_returns_clear_subprocess_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    import biblio.ui as ui_mod

    def _boom(*args, **kwargs):
        raise subprocess.CalledProcessError(
            127,
            ["conda", "run", "-n", "rag", "docling", "--help"],
        )

    monkeypatch.setattr(ui_mod, "run_docling_for_key", _boom)
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/actions/docling-run", json={"citekey": "paper2024"})
    assert resp.status_code == 200
    assert resp.json()["async"] is True

    deadline = time.time() + 2.0
    status = None
    while time.time() < deadline:
        status = client.get("/api/actions/docling-run/status")
        assert status.status_code == 200
        data = status.json()
        if not data["running"]:
            break
        time.sleep(0.05)

    assert status is not None
    data = status.json()
    assert data["running"] is False
    assert "exit code 127" in data["error"]
    assert "conda run -n rag docling" in data["error"]


def test_find_available_port_skips_busy_port() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        busy_port = sock.getsockname()[1]
        port = find_available_port("127.0.0.1", busy_port, max_tries=4)
        assert port != busy_port


def test_ui_openalex_action_exposes_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    src_dir = tmp_path / "bib" / "srcbib"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "library.bib").write_text(
        "@article{paper2024, title={Paper Title}, year={2024}, author={Doe, Jane}, doi={10.1234/ABC}}\n",
        encoding="utf-8",
    )
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)

    import biblio.ui as ui_mod

    def _fake_resolve(**kwargs):
        progress_cb = kwargs["progress_cb"]
        progress_cb({"phase": "start", "completed": 0, "total": 1, "citekey": None, "resolved": 0, "unresolved": 0, "errors": 0})
        progress_cb({"phase": "resolve", "completed": 1, "total": 1, "citekey": "paper2024", "resolved": 1, "unresolved": 0, "errors": 0})
        return {"total": 1, "resolved": 1, "unresolved": 0, "errors": 0}

    monkeypatch.setattr(ui_mod, "resolve_srcbib_to_openalex", _fake_resolve)
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/actions/openalex-resolve")
    assert resp.status_code == 200
    assert resp.json()["async"] is True

    deadline = time.time() + 2.0
    status = None
    while time.time() < deadline:
        status = client.get("/api/actions/openalex-resolve/status")
        assert status.status_code == 200
        data = status.json()
        if not data["running"]:
            break
        time.sleep(0.05)

    assert status is not None
    data = status.json()
    assert data["running"] is False
    assert data["counts"]["resolved"] == 1
    assert "Resolved OpenAlex metadata" in data["message"]


def test_ui_graph_action_exposes_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    cfg.openalex.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    cfg.openalex.out_jsonl.write_text('{"openalex_id":"W1","citekey":"paper2024"}\n', encoding="utf-8")

    import biblio.ui as ui_mod

    def _fake_expand(**kwargs):
        progress_cb = kwargs["progress_cb"]
        progress_cb({"phase": "start", "completed": 0, "total": 1, "seed_openalex_id": None, "candidates": 0})
        progress_cb({"phase": "expand", "completed": 1, "total": 1, "seed_openalex_id": "W1", "candidates": 2})
        class _R:
            total_inputs = 1
            candidates = 2
            output_path = tmp_path / "graph_candidates.json"
        return _R()

    monkeypatch.setattr(ui_mod, "expand_openalex_reference_graph", _fake_expand)
    monkeypatch.setattr(ui_mod, "load_openalex_seed_records", lambda path: [{"openalex_id": "W1", "citekey": "paper2024"}])
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/actions/graph-expand")
    assert resp.status_code == 200
    assert resp.json()["async"] is True

    deadline = time.time() + 2.0
    status = None
    while time.time() < deadline:
        status = client.get("/api/actions/graph-expand/status")
        assert status.status_code == 200
        data = status.json()
        if not data["running"]:
            break
        time.sleep(0.05)

    assert status is not None
    data = status.json()
    assert data["running"] is False
    assert data["candidates"] == 2
    assert "2 total candidates" in data["message"]


def test_ui_setup_can_update_docling_command(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/setup/docling-command", json={"mode": "conda", "env_name": "docling"})
    assert resp.status_code == 200
    payload = resp.json()
    assert "conda env docling" in payload["message"]

    updated = (tmp_path / "bib" / "config" / "biblio.yml").read_text(encoding="utf-8")
    assert 'cmd:' in updated
    assert '- conda' in updated
    assert '- docling' in updated


def test_ui_setup_can_install_docling_uv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    import biblio.ui as ui_mod

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ui_mod.subprocess, "run", _fake_run)

    resp = client.post("/api/setup/install-docling-uv", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "Installed Docling into" in data["message"]
    assert any(cmd[:2] == ["/usr/bin/uv", "venv"] for cmd in calls)
    assert any(cmd[:3] == ["/usr/bin/uv", "pip", "install"] for cmd in calls)


def test_ui_can_add_paper_by_doi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    import biblio.ui as ui_mod

    class _Result:
        citekey = "doe2024added"
        openalex_id = "W9"
        doi = "10.1000/test"

    monkeypatch.setattr(ui_mod, "add_openalex_work_to_bib", lambda **kwargs: _Result())

    resp = client.post("/api/actions/add-paper", json={"doi": "10.1000/test"})
    assert resp.status_code == 200
    assert "Added paper as doe2024added" in resp.json()["message"]


def test_ui_setup_can_save_rag_config(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    resp = client.post(
        "/api/setup/rag-config",
        json={
            "embedding_model": "sentence-transformers/test-model",
            "chunk_size_chars": "777",
            "chunk_overlap_chars": "111",
            "default_store": "local",
            "local_persist_directory": ".cache/custom-rag",
        },
    )
    assert resp.status_code == 200
    payload = load_raw_rag_config(tmp_path / "bib" / "config" / "rag.yaml")
    assert payload["embedding_model"] == "sentence-transformers/test-model"
    assert payload["chunk_size_chars"] == 777
    assert payload["chunk_overlap_chars"] == 111
    assert payload["stores"]["local"]["persist_directory"] == ".cache/custom-rag"


def test_ui_setup_can_sync_rag_config(tmp_path: Path) -> None:
    init_bib_scaffold(tmp_path, force=False)
    cfg = load_biblio_config(tmp_path / "bib" / "config" / "biblio.yml", root=tmp_path)
    client = TestClient(create_ui_app(cfg))

    resp = client.post("/api/setup/rag-sync", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "Synchronized bibliography-owned RAG sources" in data["message"]
    payload = load_raw_rag_config(tmp_path / "bib" / "config" / "rag.yaml")
    assert any(item["id"] == "biblio_docling" for item in payload["sources"])
