from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .rag_support import OwnedSourcesSyncResult, sync_owned_sources


BIBLIO_DOCLING_SOURCE_ID = "biblio_docling"
BIBLIO_OWNED_SOURCE_IDS = (BIBLIO_DOCLING_SOURCE_ID,)
BIBLIO_RAG_CONFIG_REL = Path("bib/config/rag.yaml")


@dataclass(frozen=True)
class BiblioRagSyncResult:
    config_path: Path
    created: bool
    initialized: bool
    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    follow_up_cmd: str


def default_rag_config_path(repo_root: str | Path) -> Path:
    repo_root = Path(repo_root).expanduser().resolve()
    return (repo_root / BIBLIO_RAG_CONFIG_REL).resolve()


def default_biblio_rag_template() -> str:
    return """# Bibliography-owned RAG config
#
# This file is owned by `biblio`. It can be used directly in standalone
# projects, or included from a larger project-level RAG config.

embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
chunk_size_chars: 1000
chunk_overlap_chars: 200

default_store: local

stores:
  local:
    persist_directory: .cache/rag/chroma_db
    read_only: false
    description: "Per-clone writable Chroma cache for bibliography indexing"

sources:
  - id: "biblio_docling"
    corpus: "bib"
    glob: "bib/derivatives/docling/**/*.md"
    exclude: ["**/_*"]
"""


def owned_biblio_sources() -> list[dict[str, object]]:
    return [
        {
            "id": BIBLIO_DOCLING_SOURCE_ID,
            "corpus": "bib",
            "glob": "bib/derivatives/docling/**/*.md",
            "exclude": ["**/_*"],
        }
    ]


def sync_biblio_rag_config(
    repo_root: str | Path,
    *,
    config_path: str | Path | None = None,
    force_init: bool = False,
) -> BiblioRagSyncResult:
    repo_root = Path(repo_root).expanduser().resolve()
    target = default_rag_config_path(repo_root) if config_path is None else (
        (repo_root / config_path).resolve() if not Path(config_path).is_absolute() else Path(config_path).resolve()
    )
    result: OwnedSourcesSyncResult = sync_owned_sources(
        target,
        owned_source_ids=BIBLIO_OWNED_SOURCE_IDS,
        sources=owned_biblio_sources(),
        force_init=force_init,
        template=default_biblio_rag_template(),
    )
    rel_config = str(result.config_path.relative_to(repo_root))
    follow_up_cmd = f"rag build --config {rel_config} --sources {','.join(BIBLIO_OWNED_SOURCE_IDS)}"
    return BiblioRagSyncResult(
        config_path=result.config_path,
        created=result.created,
        initialized=result.initialized,
        added=result.added,
        updated=result.updated,
        removed=result.removed,
        follow_up_cmd=follow_up_cmd,
    )
