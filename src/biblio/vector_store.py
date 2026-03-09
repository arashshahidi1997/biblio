"""Standalone ChromaDB indexer/searcher for biblio docling documents.

Designed to run under a Python environment that has chromadb installed
(e.g. the 'rag' conda env), called as a subprocess from the biblio UI server.

Usage:
    python -m biblio.vector_store build   --root /path/to/repo [--persist-dir .cache/rag/chroma_db] [--chunk-size 800]
    python -m biblio.vector_store search  --root /path/to/repo [--persist-dir .cache/rag/chroma_db] --query "..." [--n 10]

Both subcommands print a single JSON object to stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# ── chunking ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks by paragraph boundaries."""
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
            # start next chunk with overlap from end of current
            current = current[-overlap:].strip() + "\n\n" + para if overlap > 0 else para
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _iter_docling_docs(repo_root: Path) -> list[tuple[str, str]]:
    """Yield (citekey, full_text) for each docling MD."""
    docling_root = repo_root / "bib" / "derivatives" / "docling"
    results = []
    if not docling_root.exists():
        return results
    for md_path in sorted(docling_root.glob("**/*.md")):
        # skip hidden files
        if any(part.startswith("_") for part in md_path.parts):
            continue
        citekey = md_path.stem
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if text.strip():
            results.append((citekey, text))
    return results


# ── chroma helpers ─────────────────────────────────────────────────────────────

COLLECTION_NAME = "biblio_docling"


def _get_client(persist_dir: Path):
    import chromadb  # noqa: PLC0415
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def _get_collection(client, *, create: bool = False):
    import chromadb  # noqa: PLC0415
    if create:
        return client.get_or_create_collection(COLLECTION_NAME)
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


# ── build ──────────────────────────────────────────────────────────────────────

def build(repo_root: Path, persist_dir: Path, chunk_size: int = 800) -> dict:
    docs = _iter_docling_docs(repo_root)
    if not docs:
        return {"ok": False, "error": "No docling markdown files found.", "indexed": 0, "chunks": 0}

    client = _get_client(persist_dir)
    col = _get_collection(client, create=True)

    # delete existing docs for this repo so we can re-index cleanly
    try:
        existing = col.get(include=[])
        if existing["ids"]:
            col.delete(ids=existing["ids"])
    except Exception:
        pass

    all_ids: list[str] = []
    all_docs: list[str] = []
    all_meta: list[dict] = []

    total_papers = 0
    for citekey, text in docs:
        chunks = _chunk_text(text, chunk_size=chunk_size)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{citekey}__chunk_{i}"
            all_ids.append(chunk_id)
            all_docs.append(chunk)
            all_meta.append({"citekey": citekey, "chunk_index": i})
        total_papers += 1

    # upsert in batches of 100
    batch = 100
    for start in range(0, len(all_ids), batch):
        col.upsert(
            ids=all_ids[start:start + batch],
            documents=all_docs[start:start + batch],
            metadatas=all_meta[start:start + batch],
        )

    return {
        "ok": True,
        "indexed": total_papers,
        "chunks": len(all_ids),
        "collection": COLLECTION_NAME,
        "persist_dir": str(persist_dir),
    }


# ── search ─────────────────────────────────────────────────────────────────────

def search(repo_root: Path, persist_dir: Path, query: str, n_results: int = 10) -> dict:
    client = _get_client(persist_dir)
    col = _get_collection(client)
    if col is None:
        return {"ok": False, "error": "RAG index not built yet. Run 'Build RAG Index' first.", "results": []}

    try:
        n_items = col.count()
    except Exception:
        n_items = 0

    if n_items == 0:
        return {"ok": False, "error": "RAG index is empty. Run 'Build RAG Index' first.", "results": []}

    n = min(n_results, n_items)
    raw = col.query(query_texts=[query], n_results=n, include=["documents", "metadatas", "distances"])

    results = []
    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    for doc_id, text, meta, dist in zip(ids, documents, metadatas, distances):
        results.append({
            "id": doc_id,
            "citekey": meta.get("citekey", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "text": text,
            "distance": round(float(dist), 4),
        })

    return {"ok": True, "query": query, "results": results}


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="biblio vector store worker")
    sub = parser.add_subparsers(dest="cmd")

    p_build = sub.add_parser("build")
    p_build.add_argument("--root", required=True)
    p_build.add_argument("--persist-dir", default=None)
    p_build.add_argument("--chunk-size", type=int, default=800)

    p_search = sub.add_parser("search")
    p_search.add_argument("--root", required=True)
    p_search.add_argument("--persist-dir", default=None)
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--n", type=int, default=10)

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    repo_root = Path(args.root).resolve()
    raw_persist = getattr(args, "persist_dir", None)
    persist_dir = Path(raw_persist).resolve() if raw_persist else (repo_root / ".cache" / "rag" / "chroma_db")

    if args.cmd == "build":
        result = build(repo_root, persist_dir, chunk_size=args.chunk_size)
    else:
        result = search(repo_root, persist_dir, query=args.query, n_results=args.n)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
