from __future__ import annotations

from pathlib import Path

from biblio.cli import main as biblio_main
from biblio.rag import BIBLIO_DOCLING_SOURCE_ID, sync_biblio_rag_config
from biblio.rag_support import load_raw_rag_config


def test_sync_biblio_rag_config_creates_missing_config(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    result = sync_biblio_rag_config(tmp_path)
    assert result.created is True
    assert result.config_path == (tmp_path / ".projio" / "biblio" / "rag.yaml")
    payload = load_raw_rag_config(result.config_path)
    owned = {src["id"]: src for src in payload["sources"] if src["id"] == BIBLIO_DOCLING_SOURCE_ID}
    assert list(owned) == [BIBLIO_DOCLING_SOURCE_ID]
    assert owned[BIBLIO_DOCLING_SOURCE_ID]["glob"] == "bib/derivatives/docling/**/*.md"


def test_sync_biblio_rag_config_preserves_unowned_sources(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    config_path = tmp_path / "bib" / "config" / "rag.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
default_store: local
stores:
  local:
    persist_directory: .cache/rag/chroma_db
sources:
  - id: docs_keep
    corpus: docs
    glob: docs/**/*.md
  - id: biblio_docling
    corpus: bib
    glob: old/**/*.md
""".strip(),
        encoding="utf-8",
    )
    result = sync_biblio_rag_config(tmp_path)
    assert result.created is False
    payload = load_raw_rag_config(config_path)
    ids = [src["id"] for src in payload["sources"]]
    assert ids == ["docs_keep", BIBLIO_DOCLING_SOURCE_ID]
    assert payload["sources"][1]["glob"] == "bib/derivatives/docling/**/*.md"


def test_biblio_rag_sync_cli_updates_default_config(tmp_path: Path, capsys) -> None:
    (tmp_path / ".git").mkdir()
    biblio_main(["rag", "sync", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert ".projio/biblio/rag.yaml" in out
    assert "rag build --config .projio/biblio/rag.yaml --sources biblio_docling" in out
    payload = load_raw_rag_config(tmp_path / ".projio" / "biblio" / "rag.yaml")
    assert BIBLIO_DOCLING_SOURCE_ID in {src["id"] for src in payload["sources"]}
