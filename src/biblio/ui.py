from __future__ import annotations

import importlib
import io
import json
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
import yaml

class _JobCancelledError(Exception):
    """Raised inside a background job when the user requests cancellation."""


from .bibtex import merge_srcbib
from .bibtex_export import export_bibtex
from .ingest import IngestRecord, enrich_record, enrich_and_cache, EnrichCacheResult
from .normalize import (
    NormalizePlan,
    RenameEntry,
    SkippedEntry,
    EnrichedEntry,
    apply_normalize_plan,
    build_normalize_plan,
)
from .config import BiblioConfig, load_biblio_config
from .docling import outputs_for_key as docling_outputs_for_key, resolve_docling_outputs, run_docling_for_key
from .graph import add_openalex_work_to_bib, expand_openalex_reference_graph, load_openalex_seed_records
from .openalex.openalex_resolve import ResolveOptions, resolve_srcbib_to_openalex
from .rag import default_biblio_rag_template, default_rag_config_path, sync_biblio_rag_config
from .rag_support import load_raw_rag_config, write_raw_rag_config
from .crossref import resolve_doi_by_title
from .grobid import check_grobid_server_as_dict, derive_start_cmd, get_absent_refs, grobid_out_root, run_grobid_for_key, run_grobid_match
from .pdf_fetch_oa import fetch_pdfs_oa
from .citekeys import load_citekeys_md
from .library import bulk_update, load_library, notes_path, update_entry
from .collections import (
    load_collections, create_collection, rename_collection, move_collection,
    delete_collection, add_papers as col_add_papers, remove_papers as col_remove_papers,
    update_query as col_update_query, convert_to_smart as col_convert_to_smart,
    list_collections_summary,
)
from .tag_vocab import load_tag_vocab_from_config, lint_library_tags
from .autotag import autotag, load_cache as autotag_load_cache
from .summarize import summary_path_for_key, summarize
from .concepts import load_concepts, extract_concepts, build_concept_index, search_concepts
from .compare import compare
from .reading_list import reading_list
from .cite_draft import cite_draft
from .lit_review import review_query, review_plan
from .present import slides_path_for_key, generate_slides
from .site import build_biblio_site
from .site import BiblioSiteOptions, _build_site_model, default_site_out_dir, classify_entry_type


def _try_import_indexio():
    try:
        import indexio  # noqa: PLC0415
        return indexio
    except ImportError:
        return None


_indexio_mod = _try_import_indexio()


def _rag_build_indexio(repo_root: Path) -> dict[str, Any]:
    """Build RAG index in-process using indexio. Auto-creates rag.yaml if needed."""
    sync_biblio_rag_config(repo_root)
    rag_cfg_path = default_rag_config_path(repo_root)
    result = _indexio_mod.build_index(
        config_path=rag_cfg_path,
        root=repo_root,
        sources_filter=["biblio_docling"],
    )
    source_stats = result.get("source_stats") or {}
    total_files = sum(s.get("files", 0) for s in source_stats.values())
    total_chunks = sum(s.get("chunks", 0) for s in source_stats.values())
    return {
        "ok": True,
        "indexed": total_files,
        "chunks": total_chunks,
        "collection": result.get("store"),
        "persist_dir": result.get("persist_directory"),
    }


def _rag_search_indexio(repo_root: Path, query: str, n_results: int) -> dict[str, Any]:
    """Search RAG index in-process using indexio."""
    rag_cfg_path = default_rag_config_path(repo_root)
    if not rag_cfg_path.exists():
        return {"ok": False, "error": "RAG config not found. Run 'Build RAG Index' first.", "results": []}
    try:
        data = _indexio_mod.query_index(
            config_path=rag_cfg_path,
            root=repo_root,
            query=query,
            k=n_results,
            corpus="bib",
        )
    except FileNotFoundError:
        return {"ok": False, "error": "RAG index not built yet. Run 'Build RAG Index' first.", "results": []}
    results = []
    for item in data.get("results") or []:
        source_path = item.get("source_path") or ""
        citekey = Path(source_path).stem if source_path else ""
        results.append({
            "id": f"{source_path}::{item.get('chunk_index', 0)}",
            "citekey": citekey,
            "chunk_index": item.get("chunk_index", 0),
            "text": item.get("snippet", ""),
            "distance": None,
        })
    return {"ok": True, "query": query, "results": results}


def _require_fastapi():
    try:
        fastapi = importlib.import_module("fastapi")
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            'UI features require `fastapi` and `uvicorn` (install with `pip install "biblio-tools[ui]"`).'
        ) from e
    responses = importlib.import_module("fastapi.responses")
    return fastapi, responses


def _require_uvicorn():
    try:
        return importlib.import_module("uvicorn")
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            'UI features require `uvicorn` (install with `pip install "biblio-tools[ui]"`).'
        ) from e


def find_available_port(host: str, start_port: int, *, max_tries: int = 25) -> int:
    for port in range(int(start_port), int(start_port) + int(max_tries)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No available port found starting at {start_port} on host {host}")


def _paper_citekeys_from_bib(cfg: BiblioConfig) -> set[str]:
    """Return citekeys that are classified as papers (not books, theses, etc.).

    Uses the merged bib file for entry type info. Falls back to treating
    all entries as papers if the bib file is unavailable.
    """
    bib_path = cfg.bibtex_merge.out_bib
    if not bib_path.exists():
        return set()  # empty = no filtering possible; callers fall back to all
    try:
        from ._pybtex_utils import parse_bibtex_file
        db = parse_bibtex_file(bib_path)
        paper_keys: set[str] = set()
        for key, entry in db.entries.items():
            entry_type = (entry.type or "misc").lower()
            doi = (entry.fields.get("doi") or "").strip() or None
            if classify_entry_type(entry_type, doi):
                paper_keys.add(key)
        return paper_keys
    except Exception:
        return set()


def build_ui_model(cfg: BiblioConfig) -> dict[str, Any]:
    model = _build_site_model(
        cfg,
        BiblioSiteOptions(
            out_dir=default_site_out_dir(root=cfg.repo_root),
            include_graphs=True,
            include_docling=True,
            include_openalex=True,
        ),
    )
    papers = model["papers"]
    graph = model["graph"]
    paper_lookup = {paper["citekey"]: paper for paper in papers}
    return {
        "repo_root": str(cfg.repo_root),
        "papers": papers,
        "graph": graph,
        "status": model["status"],
        "paper_lookup": paper_lookup,
    }


def build_setup_report(cfg: BiblioConfig) -> dict[str, Any]:
    """Fast config-only report — no subprocess, no site model build."""
    cmd = list(cfg.docling_cmd)
    exe = cmd[0] if cmd else "docling"
    resolved = shutil.which(exe) if exe and "/" not in exe else (exe if exe else None)
    rag_path = default_rag_config_path(cfg.repo_root)
    rag_payload = _load_rag_mapping(cfg.repo_root)
    rag_sources = rag_payload.get("sources") or []
    if not isinstance(rag_sources, list):
        rag_sources = []
    stores = rag_payload.get("stores") or {}
    if not isinstance(stores, dict):
        stores = {}
    local_store = stores.get("local") if isinstance(stores.get("local"), dict) else {}
    return {
        "repo_root": str(cfg.repo_root),
        "config_path": str((cfg.repo_root / "bib" / "config" / "biblio.yml").resolve()),
        "docling": {
            "ok": None,
            "command": cmd,
            "resolved_executable": resolved,
            "message": "Click Re-check to verify." if resolved else f"Configured executable not found on PATH: {exe!r}",
            "returncode": None,
        },
        "docling_command_text": " ".join(cmd),
        "suggested_uv_command": str((cfg.repo_root / ".biblio" / "uv" / "docling" / "bin" / "docling").resolve()),
        "rag": {
            "config_path": str(rag_path),
            "exists": rag_path.exists(),
            "embedding_model": str(rag_payload.get("embedding_model") or ""),
            "chunk_size_chars": int(rag_payload.get("chunk_size_chars") or 1000),
            "chunk_overlap_chars": int(rag_payload.get("chunk_overlap_chars") or 200),
            "default_store": str(rag_payload.get("default_store") or "local"),
            "local_persist_directory": str(local_store.get("persist_directory") or ".cache/rag/chroma_db"),
            "source_ids": [
                str(item.get("id"))
                for item in rag_sources
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ],
            "follow_up_build_cmd": "rag build --config .projio/biblio/rag.yaml --sources biblio_docling",
            "backend": "indexio" if _indexio_mod is not None else "vector_store",
        },
        "paths": {
            "citekeys": str(cfg.citekeys_path),
            "pdf_root": str(cfg.pdf_root),
            "out_root": str(cfg.out_root),
            "srcbib": str(cfg.bibtex_merge.src_dir),
            "openalex_out": str(cfg.openalex.out_jsonl),
        },
        "grobid": {
            "url": cfg.grobid.url,
            "installation_path": str(cfg.grobid.installation_path) if cfg.grobid.installation_path else None,
            "timeout_seconds": cfg.grobid.timeout_seconds,
            "consolidate_header": cfg.grobid.consolidate_header,
            "consolidate_citations": cfg.grobid.consolidate_citations,
            "derived_start_cmd": derive_start_cmd(cfg.grobid),
            "ok": None,
            "message": "Click Check to verify.",
            "latency_ms": None,
        },
        "pdf_fetch": {
            "unpaywall_email": cfg.pdf_fetch_cascade.unpaywall_email or "",
            "ezproxy_base": cfg.pdf_fetch_cascade.ezproxy_base or "",
            "ezproxy_mode": cfg.pdf_fetch_cascade.ezproxy_mode,
            "ezproxy_cookie": cfg.pdf_fetch_cascade.ezproxy_cookie or "",
            "sources": list(cfg.pdf_fetch_cascade.sources),
            "delay": cfg.pdf_fetch_cascade.delay,
        },
        "pool": {
            "enabled": bool(cfg.pool_search),
            "search_paths": [str(p) for p in cfg.pool_search],
            "common_pool": str(cfg.common_pool_path) if cfg.common_pool_path else None,
        },
    }


def check_docling_command(cfg: BiblioConfig) -> dict[str, Any]:
    """Run the configured Docling command with --help and return the result."""
    cmd = list(cfg.docling_cmd)
    exe = cmd[0] if cmd else "docling"
    resolved = shutil.which(exe) if exe and "/" not in exe else (exe if exe else None)
    result: dict[str, Any] = {
        "ok": False,
        "command": cmd,
        "resolved_executable": resolved,
        "message": "",
        "returncode": None,
    }
    if resolved is None:
        result["message"] = f"Configured executable not found on PATH: {exe!r}"
        return result
    try:
        proc = subprocess.run(
            [*cmd, "--help"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        result["returncode"] = int(proc.returncode)
        result["ok"] = proc.returncode == 0
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0:
            result["message"] = "Docling command responded to --help."
        else:
            detail = err or out or f"exit code {proc.returncode}"
            result["message"] = f"Docling command failed: {detail}"
    except Exception as e:
        result["message"] = f"Docling check failed: {e}"
    return result


def _config_path(repo_root: Path) -> Path:
    return (repo_root / "bib" / "config" / "biblio.yml").resolve()


def _load_config_mapping(repo_root: Path) -> dict[str, Any]:
    path = _config_path(repo_root)
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"Expected mapping in {path}, got {type(payload).__name__}")
    return payload


def _write_config_mapping(repo_root: Path, payload: dict[str, Any]) -> Path:
    path = _config_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _load_rag_mapping(repo_root: Path) -> dict[str, Any]:
    path = default_rag_config_path(repo_root)
    if path.exists():
        return load_raw_rag_config(path)
    payload = yaml.safe_load(default_biblio_rag_template()) or {}
    if not isinstance(payload, dict):
        raise TypeError("Expected mapping in default RAG template.")
    return payload


def _write_rag_mapping(repo_root: Path, payload: dict[str, Any]) -> Path:
    return write_raw_rag_config(default_rag_config_path(repo_root), payload)


def _update_grobid_config(repo_root: Path, updates: dict[str, Any]) -> Path:
    payload = _load_config_mapping(repo_root)
    grobid = payload.get("grobid")
    if not isinstance(grobid, dict):
        grobid = {}
        payload["grobid"] = grobid
    for key in ("url", "installation_path", "timeout_seconds", "consolidate_header", "consolidate_citations"):
        if key in updates and updates[key] is not None:
            grobid[key] = updates[key]
    return _write_config_mapping(repo_root, payload)


def _update_pdf_fetch_config(repo_root: Path, updates: dict[str, Any]) -> Path:
    payload = _load_config_mapping(repo_root)
    pf = payload.get("pdf_fetch")
    if not isinstance(pf, dict):
        pf = {}
        payload["pdf_fetch"] = pf
    for key in ("unpaywall_email", "ezproxy_base", "ezproxy_mode", "ezproxy_cookie", "sources", "delay"):
        if key in updates:
            val = updates[key]
            if key in ("unpaywall_email", "ezproxy_base", "ezproxy_cookie") and isinstance(val, str):
                val = val.strip()
                if not val:
                    val = None
            pf[key] = val
    return _write_config_mapping(repo_root, payload)


def _update_docling_command(repo_root: Path, cmd_value: str | list[str]) -> Path:
    payload = _load_config_mapping(repo_root)
    docling = payload.get("docling")
    if not isinstance(docling, dict):
        docling = {}
        payload["docling"] = docling
    docling["cmd"] = cmd_value
    return _write_config_mapping(repo_root, payload)


def _install_docling_uv(repo_root: Path) -> dict[str, Any]:
    uv = shutil.which("uv")
    if uv is None:
        raise FileNotFoundError("`uv` was not found on PATH.")
    env_dir = (repo_root / ".biblio" / "uv" / "docling").resolve()
    python_path = env_dir / "bin" / "python"
    docling_bin = env_dir / "bin" / "docling"
    env_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([uv, "venv", str(env_dir)], check=True, capture_output=True, text=True)
    subprocess.run([uv, "pip", "install", "--python", str(python_path), "docling"], check=True, capture_output=True, text=True)
    _update_docling_command(repo_root, [str(docling_bin)])
    return {
        "env_dir": str(env_dir),
        "python": str(python_path),
        "docling": str(docling_bin),
    }


def _static_dir() -> Path:
    return Path(__file__).parent / "static"


def _serve_index() -> str:
    html_path = _static_dir() / "index.html"
    if not html_path.exists():
        raise RuntimeError(
            f"UI static files not found at {html_path}. "
            "Run `make build-frontend` to build the frontend."
        )
    return html_path.read_text(encoding="utf-8")


def create_ui_app(cfg: BiblioConfig):
    fastapi, responses = _require_fastapi()
    static_files_mod = importlib.import_module("fastapi.staticfiles")
    app = fastapi.FastAPI(title="biblio ui", version="0.1")
    app.mount("/static", static_files_mod.StaticFiles(directory=str(_static_dir())), name="static")
    cfg_state: dict[str, BiblioConfig] = {"cfg": cfg}

    def current_cfg() -> BiblioConfig:
        return cfg_state["cfg"]

    def reload_cfg() -> BiblioConfig:
        updated = load_biblio_config(_config_path(cfg.repo_root), root=cfg.repo_root)
        cfg_state["cfg"] = updated
        return updated

    @app.get("/", response_class=responses.HTMLResponse)
    def index() -> str:
        return _serve_index()

    @app.get("/api/model", response_class=responses.JSONResponse)
    def model():
        active_cfg = current_cfg()
        payload = build_ui_model(active_cfg)
        for paper in payload.get("papers", []):
            ck = paper.get("citekey", "")
            paper["has_summary"] = summary_path_for_key(active_cfg, ck).exists() if ck else False
            paper["has_concepts"] = load_concepts(active_cfg, ck) is not None if ck else False
            paper["has_slides"] = slides_path_for_key(active_cfg, ck).exists() if ck else False
            paper["has_autotag"] = autotag_load_cache(active_cfg, ck) is not None if ck else False
            paper["has_notes"] = notes_path(active_cfg, ck).exists() if ck else False
        payload.pop("paper_lookup", None)
        return payload

    @app.get("/api/papers", response_class=responses.JSONResponse)
    def papers():
        payload = build_ui_model(current_cfg())
        return payload["papers"]

    @app.get("/api/status", response_class=responses.JSONResponse)
    def status():
        payload = build_ui_model(current_cfg())
        return payload["status"]

    @app.get("/api/stats", response_class=responses.JSONResponse)
    def stats():
        active_cfg = current_cfg()
        payload = build_ui_model(active_cfg)
        all_papers = payload.get("papers", [])
        lib = load_library(active_cfg)
        total = len(all_papers)
        papers_only = [p for p in all_papers if p.get("is_paper", True)]
        non_papers = total - len(papers_only)

        # Status counts
        status_counts: dict[str, int] = {}
        for paper in all_papers:
            s = (paper.get("library") or {}).get("status") or "unset"
            status_counts[s] = status_counts.get(s, 0) + 1

        # Year histogram
        year_counts: dict[str, int] = {}
        for paper in all_papers:
            y = paper.get("year")
            if y:
                year_counts[str(y)] = year_counts.get(str(y), 0) + 1

        # Tag frequency (top 15) and namespace distribution
        tag_freq: dict[str, int] = {}
        ns_counts: dict[str, int] = {}
        for paper in all_papers:
            tags = (paper.get("library") or {}).get("tags") or []
            for tag in tags:
                tag_freq[tag] = tag_freq.get(tag, 0) + 1
                ns = tag.split(":")[0] if ":" in tag else "_unnamespaced"
                ns_counts[ns] = ns_counts.get(ns, 0) + 1
        top_tags = sorted(tag_freq.items(), key=lambda x: -x[1])[:15]

        # Derivative coverage
        def _pct(n: int) -> float:
            return round(100 * n / total, 1) if total else 0.0

        with_pdf = sum(1 for p in all_papers if p.get("artifacts", {}).get("pdf", {}).get("exists"))
        with_docling = sum(1 for p in all_papers if p.get("artifacts", {}).get("docling_md", {}).get("exists"))
        with_grobid = sum(1 for p in all_papers if p.get("artifacts", {}).get("grobid", {}).get("exists"))
        with_openalex = sum(1 for p in all_papers if p.get("artifacts", {}).get("openalex", {}).get("exists"))
        with_summary = sum(1 for p in all_papers if p.get("has_summary"))
        with_concepts = sum(1 for p in all_papers if p.get("has_concepts"))

        # Fetch queue
        from .fetch_queue import load_queue as _load_fq
        fq = _load_fq(active_cfg)

        return {
            "total": total,
            "papers_count": len(papers_only),
            "non_papers": non_papers,
            "by_status": status_counts,
            "by_year": dict(sorted(year_counts.items())),
            "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
            "tag_namespaces": ns_counts,
            "coverage": {
                "pdf": {"count": with_pdf, "pct": _pct(with_pdf)},
                "docling": {"count": with_docling, "pct": _pct(with_docling)},
                "grobid": {"count": with_grobid, "pct": _pct(with_grobid)},
                "openalex": {"count": with_openalex, "pct": _pct(with_openalex)},
                "summary": {"count": with_summary, "pct": _pct(with_summary)},
                "concepts": {"count": with_concepts, "pct": _pct(with_concepts)},
            },
            "missing_pdf": total - with_pdf,
            "fetch_queue": len(fq),
        }

    @app.get("/api/graph", response_class=responses.JSONResponse)
    def graph():
        payload = build_ui_model(current_cfg())
        return payload["graph"]

    @app.get("/api/graph-candidates", response_class=responses.JSONResponse)
    def graph_candidates():
        active_cfg = current_cfg()
        candidates_path = active_cfg.openalex.out_jsonl.parent / "graph_candidates.json"
        if not candidates_path.exists():
            return []
        return json.loads(candidates_path.read_text(encoding="utf-8"))

    @app.get("/api/files/pdf/{citekey}")
    def file_pdf(citekey: str):
        active_cfg = current_cfg()
        # Validate the *logical* (pre-resolve) path to prevent path traversal,
        # then resolve symlinks for serving (handles git-annex → RIA store chains).
        pdf_root = active_cfg.pdf_root.resolve()
        logical_path = pdf_root / Path(active_cfg.pdf_pattern.format(citekey=citekey))
        try:
            logical_path.relative_to(pdf_root)
        except ValueError:
            raise fastapi.HTTPException(status_code=403, detail="Path traversal denied")
        pdf_path = logical_path.resolve()
        if not pdf_path.exists() or not pdf_path.is_file():
            raise fastapi.HTTPException(status_code=404, detail=f"PDF not found for {citekey}")
        headers = {"Content-Disposition": f'inline; filename="{pdf_path.name}"'}
        return responses.FileResponse(str(pdf_path), media_type="application/pdf", headers=headers)

    @app.get("/api/files/docling/{citekey}/{path:path}")
    def file_docling_artifact(citekey: str, path: str):
        """Serve a file from the docling output directory for a citekey.

        Used to resolve relative image paths in rendered docling markdown, e.g.
        peyrache_2011_..._artifacts/image_000000_....png
        """
        active_cfg = current_cfg()
        # Jail to the docling output root to prevent path traversal.
        # Validate the *logical* (pre-resolve) path so that git-annex symlinks
        # (which resolve outside out_root into a RIA store) are still allowed.
        out_root = active_cfg.out_root.resolve()
        logical_path = out_root / citekey / path
        try:
            logical_path.relative_to(out_root)
        except ValueError:
            raise fastapi.HTTPException(status_code=403, detail="Path traversal denied")
        # Resolve symlinks only for serving (handles git-annex → RIA store chains)
        artifact_path = logical_path.resolve()
        if not artifact_path.exists() or not artifact_path.is_file():
            raise fastapi.HTTPException(status_code=404, detail=f"Artifact not found: {path}")
        return responses.FileResponse(str(artifact_path))

    @app.get("/api/setup", response_class=responses.JSONResponse)
    def setup():
        return build_setup_report(current_cfg())

    @app.post("/api/setup/rag-sync", response_class=responses.JSONResponse)
    def setup_rag_sync(payload: dict[str, Any]):
        active_cfg = current_cfg()
        force_init = bool(payload.get("force_init"))
        result = sync_biblio_rag_config(active_cfg.repo_root, force_init=force_init)
        return _action_result(
            f"Synchronized bibliography-owned RAG sources in {result.config_path}.",
            config_path=str(result.config_path),
            created=result.created,
            initialized=result.initialized,
            added=list(result.added),
            updated=list(result.updated),
            removed=list(result.removed),
            follow_up_cmd=result.follow_up_cmd,
        )

    @app.post("/api/setup/rag-config", response_class=responses.JSONResponse)
    def setup_rag_config(payload: dict[str, Any]):
        active_cfg = current_cfg()
        current = _load_rag_mapping(active_cfg.repo_root)
        current["embedding_model"] = str(payload.get("embedding_model") or current.get("embedding_model") or "")
        current["chunk_size_chars"] = int(payload.get("chunk_size_chars") or current.get("chunk_size_chars") or 1000)
        current["chunk_overlap_chars"] = int(payload.get("chunk_overlap_chars") or current.get("chunk_overlap_chars") or 200)
        current["default_store"] = str(payload.get("default_store") or current.get("default_store") or "local")
        stores = current.get("stores")
        if not isinstance(stores, dict):
            stores = {}
            current["stores"] = stores
        local_store = stores.get("local")
        if not isinstance(local_store, dict):
            local_store = {}
            stores["local"] = local_store
        local_store["persist_directory"] = str(
            payload.get("local_persist_directory") or local_store.get("persist_directory") or ".cache/rag/chroma_db"
        )
        if "read_only" not in local_store:
            local_store["read_only"] = False
        _write_rag_mapping(active_cfg.repo_root, current)
        return _action_result(
            "Saved bibliography-owned RAG config.",
            config_path=str(default_rag_config_path(active_cfg.repo_root)),
        )

    def _action_result(message: str, **extra: Any) -> dict[str, Any]:
        return {"ok": True, "message": message, **extra}

    openalex_job: dict[str, Any] = {
        "running": False,
        "completed": 0,
        "total": 0,
        "citekey": None,
        "message": "",
        "error": None,
        "counts": None,
    }
    graph_job: dict[str, Any] = {
        "running": False,
        "completed": 0,
        "total": 0,
        "seed_openalex_id": None,
        "message": "",
        "error": None,
        "candidates": 0,
        "cancelled": False,
    }
    docling_job: dict[str, Any] = {
        "running": False,
        "message": "",
        "error": None,
        "citekey": None,
        "md_path": None,
        "logs": "",
        "completed": 0,
        "total": 0,
        "cancelled": False,
    }
    grobid_job: dict[str, Any] = {
        "running": False,
        "message": "",
        "error": None,
        "citekey": None,
        "completed": 0,
        "total": 0,
        "references_path": None,
        "logs": "",
        "cancelled": False,
    }
    openalex_lock = threading.Lock()
    graph_lock = threading.Lock()
    docling_lock = threading.Lock()
    grobid_lock = threading.Lock()

    def _openalex_snapshot() -> dict[str, Any]:
        with openalex_lock:
            return dict(openalex_job)

    def _graph_snapshot() -> dict[str, Any]:
        with graph_lock:
            return dict(graph_job)

    def _docling_snapshot() -> dict[str, Any]:
        with docling_lock:
            snap = dict(docling_job)
            # Include sub_progress if present
            if "sub_progress" in snap:
                snap["sub_progress"] = dict(snap["sub_progress"])
            return snap

    def _grobid_snapshot() -> dict[str, Any]:
        with grobid_lock:
            return dict(grobid_job)

    @app.post("/api/actions/bibtex-merge", response_class=responses.JSONResponse)
    def action_bibtex_merge():
        active_cfg = current_cfg()
        n_sources, n_entries = merge_srcbib(active_cfg.bibtex_merge, dry_run=False)
        return _action_result(
            f"Merged {n_sources} source files into {n_entries} entries.",
            sources=n_sources,
            entries=n_entries,
        )

    @app.post("/api/export/bibtex")
    def export_bibtex_endpoint(payload: dict[str, Any]):
        citekeys = payload.get("citekeys")
        if not citekeys or not isinstance(citekeys, list):
            raise fastapi.HTTPException(status_code=400, detail="Missing or invalid 'citekeys' list")
        active_cfg = current_cfg()
        try:
            bib_content = export_bibtex(citekeys, repo_root=active_cfg.repo_root)
        except (FileNotFoundError, KeyError) as exc:
            raise fastapi.HTTPException(status_code=404, detail=str(exc))
        return fastapi.responses.Response(
            content=bib_content,
            media_type="application/x-bibtex",
            headers={"Content-Disposition": 'attachment; filename="export.bib"'},
        )

    @app.post("/api/actions/docling-run", response_class=responses.JSONResponse)
    def action_docling_run(payload: dict[str, Any]):
        active_cfg = current_cfg()
        run_all = bool(payload.get("all"))
        citekey = str(payload.get("citekey") or "").strip()
        force = bool(payload.get("force"))
        include_non_papers = bool(payload.get("include_non_papers"))

        if not run_all and not citekey:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey or all=true")

        with docling_lock:
            if docling_job["running"]:
                return {"ok": True, "async": True, **dict(docling_job)}
            if run_all:
                keys = load_citekeys_md(active_cfg.citekeys_path) if active_cfg.citekeys_path.exists() else []
                if not include_non_papers:
                    paper_keys = _paper_citekeys_from_bib(active_cfg)
                    if paper_keys:
                        keys = [k for k in keys if k in paper_keys]
                # Only papers with PDF but no docling output (checks pool too)
                keys = [
                    k for k in keys
                    if (active_cfg.pdf_root / active_cfg.pdf_pattern.format(citekey=k)).exists()
                    and resolve_docling_outputs(active_cfg, k)[1] == "missing"
                ]
                total = len(keys)
                msg = f"Running Docling for all {total} papers with PDFs but no text extraction..."
            else:
                keys = [citekey]
                total = 1
                msg = f"Running Docling for {citekey}..."
            docling_job.update({
                "running": True,
                "message": msg,
                "error": None,
                "citekey": citekey if not run_all else None,
                "md_path": None,
                "completed": 0,
                "total": total,
                "cancelled": False,
                "logs": "",
            })

        def _run_docling() -> None:
            failures = 0
            cancelled = False
            for idx, ck in enumerate(keys, start=1):
                with docling_lock:
                    if docling_job.get("cancelled"):
                        cancelled = True
                        break

                def _docling_progress(payload: dict) -> None:
                    with docling_lock:
                        # Capture subprocess PID for cancel support
                        if "pid" in payload:
                            docling_job["_subprocess_pid"] = payload["pid"]
                        # Check cancel flag during subprocess execution
                        if docling_job.get("cancelled"):
                            pid = docling_job.get("_subprocess_pid")
                            if pid:
                                import signal
                                try:
                                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                                except (OSError, ProcessLookupError):
                                    try:
                                        os.kill(pid, signal.SIGTERM)
                                    except (OSError, ProcessLookupError):
                                        pass
                        msg = payload.get("message", "")
                        docling_job["message"] = f"Docling {idx}/{total}: {ck} — {msg}"
                        docling_job["logs"] = payload.get("logs", "")
                        progress = payload.get("progress")
                        if progress:
                            docling_job["sub_progress"] = progress

                try:
                    out = run_docling_for_key(active_cfg, ck, force=force, progress_cb=_docling_progress)
                    with docling_lock:
                        if docling_job.get("cancelled"):
                            cancelled = True
                            break
                        docling_job["completed"] = idx
                        docling_job["citekey"] = ck
                        docling_job["md_path"] = str(out.md_path)
                        docling_job["message"] = f"Docling {idx}/{total}: {ck}"
                        docling_job["logs"] = ""
                        docling_job.pop("sub_progress", None)
                        docling_job.pop("_subprocess_pid", None)
                except subprocess.CalledProcessError as e:
                    with docling_lock:
                        if docling_job.get("cancelled"):
                            cancelled = True
                            break
                    failures += 1
                    logs = "\n".join(filter(None, [e.stdout, e.stderr])).strip()
                    with docling_lock:
                        docling_job["completed"] = idx
                        docling_job["citekey"] = ck
                        docling_job["message"] = f"Docling {idx}/{total}: {ck} failed"
                        docling_job["logs"] = logs
                        docling_job.pop("sub_progress", None)
                        docling_job.pop("_subprocess_pid", None)
                except Exception as e:
                    with docling_lock:
                        if docling_job.get("cancelled"):
                            cancelled = True
                            break
                    failures += 1
                    with docling_lock:
                        docling_job["completed"] = idx
                        docling_job["citekey"] = ck
                        docling_job["message"] = f"Docling {idx}/{total}: {ck} failed: {e}"
                        docling_job["logs"] = ""
                        docling_job.pop("sub_progress", None)
                        docling_job.pop("_subprocess_pid", None)
            with docling_lock:
                docling_job["running"] = False
                docling_job["cancelled"] = False
                docling_job.pop("sub_progress", None)
                if cancelled:
                    docling_job["error"] = None
                    docling_job["message"] = f"Docling cancelled after {docling_job['completed']}/{total} papers."
                elif failures == 0:
                    docling_job["error"] = None
                    docling_job["message"] = f"Docling finished ({total} papers, {failures} failures)."
                else:
                    docling_job["error"] = f"{failures} papers failed."
                    docling_job["message"] = f"Docling done with {failures} failures out of {total}."

        threading.Thread(target=_run_docling, daemon=True).start()
        return {"ok": True, "async": True, **_docling_snapshot()}

    @app.get("/api/actions/docling-run/status", response_class=responses.JSONResponse)
    def action_docling_run_status():
        return _docling_snapshot()

    @app.post("/api/actions/docling-run/cancel", response_class=responses.JSONResponse)
    def action_docling_run_cancel():
        with docling_lock:
            if docling_job["running"]:
                docling_job["cancelled"] = True
                docling_job["message"] = "Cancelling Docling..."
        return _docling_snapshot()

    @app.post("/api/actions/openalex-resolve", response_class=responses.JSONResponse)
    def action_openalex_resolve():
        with openalex_lock:
            if openalex_job["running"]:
                return {
                    "ok": True,
                    "async": True,
                    "message": openalex_job["message"] or "OpenAlex resolve already running.",
                    **dict(openalex_job),
                }
            openalex_job.update(
                {
                    "running": True,
                    "completed": 0,
                    "total": 0,
                    "citekey": None,
                    "message": "Starting OpenAlex resolve...",
                    "error": None,
                    "counts": None,
                }
            )

        def _progress(payload: dict[str, Any]) -> None:
            with openalex_lock:
                openalex_job["completed"] = int(payload.get("completed") or 0)
                openalex_job["total"] = int(payload.get("total") or 0)
                openalex_job["citekey"] = payload.get("citekey")
                completed = openalex_job["completed"]
                total = openalex_job["total"]
                citekey = openalex_job["citekey"]
                base = f"Resolving OpenAlex metadata {completed}/{total}" if total else "Resolving OpenAlex metadata..."
                openalex_job["message"] = f"{base}" + (f" ({citekey})" if citekey else "")

        def _run_job() -> None:
            active_cfg = current_cfg()
            try:
                counts = resolve_srcbib_to_openalex(
                    cfg=active_cfg.openalex_client,
                    cache=active_cfg.openalex_cache,
                    src_dir=active_cfg.openalex.src_dir,
                    src_glob=active_cfg.openalex.src_glob,
                    out_path=active_cfg.openalex.out_jsonl,
                    out_format="jsonl",
                    limit=None,
                    opts=ResolveOptions(
                        prefer_doi=True,
                        fallback_title_search=True,
                        per_page=int(active_cfg.openalex_client.per_page),
                        strict=False,
                        force=False,
                    ),
                    progress_cb=_progress,
                )
                with openalex_lock:
                    openalex_job["running"] = False
                    openalex_job["counts"] = counts
                    openalex_job["completed"] = counts["total"]
                    openalex_job["total"] = counts["total"]
                    openalex_job["citekey"] = None
                    openalex_job["message"] = f"Resolved OpenAlex metadata for {counts['resolved']} entries."
                    openalex_job["error"] = None
            except Exception as e:
                with openalex_lock:
                    openalex_job["running"] = False
                    openalex_job["error"] = str(e)
                    openalex_job["message"] = f"OpenAlex resolve failed: {e}"

        threading.Thread(target=_run_job, daemon=True).start()
        return {"ok": True, "async": True, **_openalex_snapshot()}

    @app.get("/api/actions/openalex-resolve/status", response_class=responses.JSONResponse)
    def action_openalex_resolve_status():
        return _openalex_snapshot()

    @app.post("/api/actions/openalex-resolve/cancel", response_class=responses.JSONResponse)
    def action_openalex_resolve_cancel():
        with openalex_lock:
            if openalex_job["running"]:
                openalex_job["running"] = False
                openalex_job["error"] = None
                openalex_job["message"] = "OpenAlex resolve cancelled."
        return _openalex_snapshot()

    @app.post("/api/actions/graph-expand", response_class=responses.JSONResponse)
    def action_graph_expand(payload: dict[str, Any] = {}):
        active_cfg = current_cfg()
        citekey_filter = str(payload.get("citekey") or "").strip() or None
        merge = bool(payload.get("merge", True))
        with graph_lock:
            if graph_job["running"]:
                return {"ok": True, "async": True, **dict(graph_job)}
            graph_job.update(
                {
                    "running": True,
                    "completed": 0,
                    "total": 0,
                    "seed_openalex_id": None,
                    "message": f"Starting graph expansion{f' for {citekey_filter}' if citekey_filter else ''}...",
                    "error": None,
                    "candidates": 0,
                }
            )

        input_path = active_cfg.openalex.out_jsonl
        output_path = active_cfg.openalex.out_jsonl.parent / "graph_candidates.json"
        # Always load full records so all_seed_ids covers the whole corpus
        all_records = load_openalex_seed_records(input_path)

        def _progress(p: dict[str, Any]) -> None:
            with graph_lock:
                if graph_job.get("cancelled"):
                    raise _JobCancelledError("Graph expansion cancelled by user")
                graph_job["completed"] = int(p.get("completed") or 0)
                graph_job["total"] = int(p.get("total") or 0)
                graph_job["seed_openalex_id"] = p.get("seed_openalex_id")
                graph_job["candidates"] = int(p.get("candidates") or 0)
                base = f"Expanding graph {graph_job['completed']}/{graph_job['total']}" if graph_job["total"] else "Expanding graph..."
                seed = graph_job["seed_openalex_id"]
                graph_job["message"] = f"{base}" + (f" ({seed})" if seed else "")

        def _run_graph() -> None:
            try:
                result = expand_openalex_reference_graph(
                    cfg=active_cfg.openalex_client,
                    cache=active_cfg.openalex_cache,
                    records=all_records,
                    out_path=output_path,
                    direction="both",
                    force=False,
                    merge=merge,
                    seed_citekeys=[citekey_filter] if citekey_filter else None,
                    progress_cb=_progress,
                )
                with graph_lock:
                    graph_job["running"] = False
                    graph_job["cancelled"] = False
                    graph_job["completed"] = result.total_inputs
                    graph_job["total"] = result.total_inputs
                    graph_job["seed_openalex_id"] = None
                    graph_job["candidates"] = result.candidates
                    graph_job["message"] = (
                        f"Graph expanded: {result.candidates} total candidates"
                        + (f" (added for {citekey_filter})" if citekey_filter else "") + "."
                    )
                    graph_job["error"] = None
            except _JobCancelledError:
                with graph_lock:
                    graph_job["running"] = False
                    graph_job["cancelled"] = False
                    graph_job["error"] = None
                    graph_job["message"] = "Graph expansion cancelled."
            except Exception as e:
                with graph_lock:
                    graph_job["running"] = False
                    graph_job["cancelled"] = False
                    graph_job["error"] = str(e)
                    graph_job["message"] = f"Graph expansion failed: {e}"

        threading.Thread(target=_run_graph, daemon=True).start()
        return {"ok": True, "async": True, **_graph_snapshot()}

    @app.get("/api/actions/graph-expand/status", response_class=responses.JSONResponse)
    def action_graph_expand_status():
        return _graph_snapshot()

    @app.post("/api/actions/graph-expand/cancel", response_class=responses.JSONResponse)
    def action_graph_expand_cancel():
        with graph_lock:
            if graph_job["running"]:
                graph_job["cancelled"] = True
                graph_job["message"] = "Cancelling graph expansion..."
        return _graph_snapshot()

    @app.post("/api/actions/grobid-run", response_class=responses.JSONResponse)
    def action_grobid_run(payload: dict[str, Any]):
        active_cfg = current_cfg()
        run_all = bool(payload.get("all"))
        citekey = str(payload.get("citekey") or "").strip()
        force = bool(payload.get("force"))
        include_non_papers = bool(payload.get("include_non_papers"))

        if not run_all and not citekey:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey or all=true")

        with grobid_lock:
            if grobid_job["running"]:
                return {"ok": True, "async": True, **dict(grobid_job)}
            if run_all:
                keys = load_citekeys_md(active_cfg.citekeys_path) if active_cfg.citekeys_path.exists() else []
                if not include_non_papers:
                    paper_keys = _paper_citekeys_from_bib(active_cfg)
                    if paper_keys:
                        keys = [k for k in keys if k in paper_keys]
                from .grobid import resolve_grobid_outputs
                keys = [
                    k for k in keys
                    if (active_cfg.pdf_root / active_cfg.pdf_pattern.format(citekey=k)).exists()
                    and resolve_grobid_outputs(active_cfg, k)[1] == "missing"
                ]
                total = len(keys)
                msg = f"Running GROBID for {total} papers with PDFs needing extraction..."
            else:
                keys = [citekey]
                total = 1
                msg = f"Running GROBID for {citekey}..."
            grobid_job.update({
                "running": True,
                "message": msg,
                "error": None,
                "citekey": citekey if not run_all else None,
                "references_path": None,
                "completed": 0,
                "total": total,
                "cancelled": False,
            })

        def _run_grobid() -> None:
            failures = 0
            cancelled = False
            for idx, ck in enumerate(keys, start=1):
                with grobid_lock:
                    if grobid_job.get("cancelled"):
                        cancelled = True
                        break
                try:
                    out = run_grobid_for_key(active_cfg, ck, force=force)
                    with grobid_lock:
                        grobid_job["completed"] = idx
                        grobid_job["citekey"] = ck
                        grobid_job["references_path"] = str(out.references_path)
                        grobid_job["message"] = f"GROBID {idx}/{total}: {ck}"
                except Exception as e:
                    failures += 1
                    with grobid_lock:
                        grobid_job["completed"] = idx
                        grobid_job["citekey"] = ck
                        grobid_job["message"] = f"GROBID {idx}/{total}: {ck} failed: {e}"
            with grobid_lock:
                grobid_job["running"] = False
                grobid_job["cancelled"] = False
                if cancelled:
                    grobid_job["error"] = None
                    grobid_job["message"] = f"GROBID cancelled after {grobid_job['completed']}/{total} papers."
                elif failures == 0:
                    grobid_job["error"] = None
                    grobid_job["message"] = f"GROBID finished ({total} papers, {failures} failures)."
                else:
                    grobid_job["error"] = f"{failures} papers failed."
                    grobid_job["message"] = f"GROBID done with {failures} failures out of {total}."

        threading.Thread(target=_run_grobid, daemon=True).start()
        return {"ok": True, "async": True, **_grobid_snapshot()}

    @app.get("/api/actions/grobid-run/status", response_class=responses.JSONResponse)
    def action_grobid_run_status():
        return _grobid_snapshot()

    @app.post("/api/actions/grobid-run/cancel", response_class=responses.JSONResponse)
    def action_grobid_run_cancel():
        with grobid_lock:
            if grobid_job["running"]:
                grobid_job["cancelled"] = True
                grobid_job["message"] = "Cancelling GROBID..."
        return _grobid_snapshot()

    grobid_match_job: dict[str, Any] = {"running": False, "message": "", "error": None, "matched": 0, "links": 0}
    grobid_match_lock = threading.Lock()

    def _grobid_match_snapshot() -> dict[str, Any]:
        with grobid_match_lock:
            return dict(grobid_match_job)

    @app.post("/api/actions/grobid-match", response_class=responses.JSONResponse)
    def action_grobid_match():
        active_cfg = current_cfg()
        with grobid_match_lock:
            if grobid_match_job["running"]:
                return {"ok": True, "async": True, **dict(grobid_match_job)}
            grobid_match_job.update({"running": True, "message": "Matching GROBID references...", "error": None})

        def _run_match() -> None:
            try:
                _, matches = run_grobid_match(active_cfg)
                total_links = sum(len(v) for v in matches.values())
                with grobid_match_lock:
                    grobid_match_job["running"] = False
                    grobid_match_job["error"] = None
                    grobid_match_job["matched"] = len(matches)
                    grobid_match_job["links"] = total_links
                    grobid_match_job["message"] = (
                        f"Matched {len(matches)} papers with {total_links} local reference links."
                    )
            except Exception as e:
                with grobid_match_lock:
                    grobid_match_job["running"] = False
                    grobid_match_job["error"] = str(e)
                    grobid_match_job["message"] = f"GROBID match failed: {e}"

        threading.Thread(target=_run_match, daemon=True).start()
        return {"ok": True, "async": True, **_grobid_match_snapshot()}

    @app.get("/api/actions/grobid-match/status", response_class=responses.JSONResponse)
    def action_grobid_match_status():
        return _grobid_match_snapshot()

    @app.post("/api/actions/site-build", response_class=responses.JSONResponse)
    def action_site_build():
        result = build_biblio_site(current_cfg(), force=True)
        return _action_result(
            f"Built site with {result.papers_total} papers.",
            out_dir=str(result.out_dir),
            papers=result.papers_total,
        )

    @app.post("/api/actions/add-papers-bulk", response_class=responses.JSONResponse)
    def action_add_papers_bulk(payload: dict[str, Any]):
        active_cfg = current_cfg()
        dois: list[str] = [str(d).strip() for d in (payload.get("dois") or []) if str(d).strip()]
        if not dois:
            raise fastapi.HTTPException(status_code=400, detail="Missing dois list")
        added, failed = [], []
        for doi in dois:
            try:
                result = add_openalex_work_to_bib(
                    cfg=active_cfg.openalex_client,
                    cache=active_cfg.openalex_cache,
                    repo_root=active_cfg.repo_root,
                    doi=doi,
                )
                added.append(result.citekey)
            except Exception as e:
                failed.append({"doi": doi, "error": str(e)})
        return _action_result(
            f"Bulk add: {len(added)} added, {len(failed)} failed.",
            added=added,
            failed=failed,
        )

    @app.post("/api/actions/add-paper", response_class=responses.JSONResponse)
    def action_add_paper(payload: dict[str, Any]):
        active_cfg = current_cfg()
        doi = str(payload.get("doi") or "").strip() or None
        openalex_id = str(payload.get("openalex_id") or "").strip() or None
        if not doi and not openalex_id:
            raise fastapi.HTTPException(status_code=400, detail="Missing doi or openalex_id")
        result = add_openalex_work_to_bib(
            cfg=active_cfg.openalex_client,
            cache=active_cfg.openalex_cache,
            repo_root=active_cfg.repo_root,
            doi=doi,
            openalex_id=openalex_id,
        )
        return _action_result(
            f"Added paper as {result.citekey}.",
            citekey=result.citekey,
            openalex_id=result.openalex_id,
            doi=result.doi,
        )

    # ── ORCID author search & import ─────────────────────────────────────────

    @app.post("/api/authors/search-orcid", response_class=responses.JSONResponse)
    def authors_search_orcid(payload: dict[str, Any]):
        from .author_search import search_by_orcid, get_author_works
        from .ingest import find_existing_dois
        active_cfg = current_cfg()
        orcid = str(payload.get("orcid") or "").strip()
        if not orcid:
            raise fastapi.HTTPException(status_code=400, detail="Missing orcid")
        since_year = payload.get("since_year")
        if since_year is not None:
            since_year = int(since_year)
        min_citations = payload.get("min_citations")
        if min_citations is not None:
            min_citations = int(min_citations)
        try:
            author = search_by_orcid(active_cfg.openalex_client, orcid)
        except ValueError as exc:
            raise fastapi.HTTPException(status_code=404, detail=str(exc))
        works = get_author_works(
            active_cfg.openalex_client,
            author.openalex_id,
            since_year=since_year,
            min_citations=min_citations,
        )
        existing_dois = find_existing_dois(active_cfg.repo_root)
        return {
            "ok": True,
            "author": {
                "openalex_id": author.openalex_id,
                "orcid": author.orcid,
                "display_name": author.display_name,
                "affiliation": author.affiliation,
                "works_count": author.works_count,
                "cited_by_count": author.cited_by_count,
                "h_index": author.h_index,
            },
            "works": [
                {
                    "openalex_id": w.openalex_id,
                    "doi": w.doi,
                    "title": w.title,
                    "year": w.year,
                    "journal": w.journal,
                    "cited_by_count": w.cited_by_count,
                    "is_oa": w.is_oa,
                    "in_library": bool(w.doi and w.doi.lower() in existing_dois),
                }
                for w in works
            ],
        }

    @app.post("/api/authors/import", response_class=responses.JSONResponse)
    def authors_import(payload: dict[str, Any]):
        active_cfg = current_cfg()
        dois: list[str] = [str(d).strip() for d in (payload.get("dois") or []) if str(d).strip()]
        if not dois:
            raise fastapi.HTTPException(status_code=400, detail="Missing dois list")
        added, failed = [], []
        for doi in dois:
            try:
                result = add_openalex_work_to_bib(
                    cfg=active_cfg.openalex_client,
                    cache=active_cfg.openalex_cache,
                    repo_root=active_cfg.repo_root,
                    doi=doi,
                )
                added.append(result.citekey)
            except Exception as e:
                failed.append({"doi": doi, "error": str(e)})
        return _action_result(
            f"Author import: {len(added)} added, {len(failed)} failed.",
            added=added,
            failed=failed,
        )

    # ── Discovery: author/institution search ───────────────────────────────

    @app.post("/api/discover/authors", response_class=responses.JSONResponse)
    def discover_authors(payload: dict[str, Any]):
        """Search authors by name, OpenAlex ID, or ORCID."""
        query = str(payload.get("query") or "").strip()
        author_id = str(payload.get("author_id") or "").strip()
        orcid = str(payload.get("orcid") or "").strip()
        if not any([query, author_id, orcid]):
            raise fastapi.HTTPException(status_code=400, detail="Provide query, author_id, or orcid")
        active_cfg = current_cfg()
        if query:
            from .author_search import search_by_name
            authors = search_by_name(active_cfg.openalex_client, query)
            return {"ok": True, "authors": [
                {"openalex_id": a.openalex_id, "orcid": a.orcid, "display_name": a.display_name,
                 "affiliation": a.affiliation, "works_count": a.works_count,
                 "cited_by_count": a.cited_by_count, "h_index": a.h_index}
                for a in authors
            ]}
        elif author_id:
            from .author_search import get_author_by_id
            a = get_author_by_id(active_cfg.openalex_client, author_id)
            return {"ok": True, "author": {
                "openalex_id": a.openalex_id, "orcid": a.orcid, "display_name": a.display_name,
                "affiliation": a.affiliation, "works_count": a.works_count,
                "cited_by_count": a.cited_by_count, "h_index": a.h_index,
            }}
        else:
            from .author_search import search_by_orcid
            a = search_by_orcid(active_cfg.openalex_client, orcid)
            return {"ok": True, "author": {
                "openalex_id": a.openalex_id, "orcid": a.orcid, "display_name": a.display_name,
                "affiliation": a.affiliation, "works_count": a.works_count,
                "cited_by_count": a.cited_by_count, "h_index": a.h_index,
            }}

    @app.post("/api/discover/institutions", response_class=responses.JSONResponse)
    def discover_institutions(payload: dict[str, Any]):
        """Search institutions by name or fetch by OpenAlex ID."""
        query = str(payload.get("query") or "").strip()
        institution_id = str(payload.get("institution_id") or "").strip()
        if not any([query, institution_id]):
            raise fastapi.HTTPException(status_code=400, detail="Provide query or institution_id")
        active_cfg = current_cfg()
        from .discovery import search_institutions_by_name, get_institution_by_id
        if query:
            institutions = search_institutions_by_name(active_cfg.openalex_client, query)
            return {"ok": True, "institutions": [
                {"openalex_id": i.openalex_id, "ror": i.ror, "display_name": i.display_name,
                 "country_code": i.country_code, "type": i.type,
                 "works_count": i.works_count, "cited_by_count": i.cited_by_count}
                for i in institutions
            ]}
        else:
            i = get_institution_by_id(active_cfg.openalex_client, institution_id)
            return {"ok": True, "institution": {
                "openalex_id": i.openalex_id, "ror": i.ror, "display_name": i.display_name,
                "country_code": i.country_code, "type": i.type,
                "works_count": i.works_count, "cited_by_count": i.cited_by_count,
            }}

    @app.post("/api/discover/author-papers", response_class=responses.JSONResponse)
    def discover_author_papers(payload: dict[str, Any]):
        """Fetch papers by an author, with optional position filtering."""
        author_id = str(payload.get("author_id") or "").strip()
        orcid = str(payload.get("orcid") or "").strip()
        if not any([author_id, orcid]):
            raise fastapi.HTTPException(status_code=400, detail="Provide author_id or orcid")
        position = str(payload.get("position") or "").strip() or None
        since_year = payload.get("since_year")
        if since_year is not None:
            since_year = int(since_year)
        min_citations = payload.get("min_citations")
        if min_citations is not None:
            min_citations = int(min_citations)
        active_cfg = current_cfg()
        from .ingest import find_existing_dois
        # Resolve author_id from ORCID if needed
        resolved_id = author_id
        if not resolved_id and orcid:
            from .author_search import search_by_orcid
            a = search_by_orcid(active_cfg.openalex_client, orcid)
            resolved_id = a.openalex_id
        from .discovery import get_author_works_by_position
        works = get_author_works_by_position(
            active_cfg.openalex_client, resolved_id,
            position=position, since_year=since_year, min_citations=min_citations,
        )
        existing_dois = find_existing_dois(active_cfg.repo_root)
        return {"ok": True, "works": [
            {"openalex_id": w.openalex_id, "doi": w.doi, "title": w.title,
             "year": w.year, "journal": w.journal, "cited_by_count": w.cited_by_count,
             "is_oa": w.is_oa, "in_library": bool(w.doi and w.doi.lower() in existing_dois)}
            for w in works
        ]}

    @app.post("/api/discover/institution-works", response_class=responses.JSONResponse)
    def discover_institution_works(payload: dict[str, Any]):
        """Fetch all works affiliated with an institution."""
        institution_id = str(payload.get("institution_id") or "").strip()
        if not institution_id:
            raise fastapi.HTTPException(status_code=400, detail="Missing institution_id")
        since_year = payload.get("since_year")
        if since_year is not None:
            since_year = int(since_year)
        min_citations = payload.get("min_citations")
        if min_citations is not None:
            min_citations = int(min_citations)
        active_cfg = current_cfg()
        from .discovery import get_institution_works
        from .ingest import find_existing_dois
        works = get_institution_works(
            active_cfg.openalex_client, institution_id,
            since_year=since_year, min_citations=min_citations,
        )
        existing_dois = find_existing_dois(active_cfg.repo_root)
        return {"ok": True, "works": [
            {"openalex_id": w.openalex_id, "doi": w.doi, "title": w.title,
             "year": w.year, "journal": w.journal, "cited_by_count": w.cited_by_count,
             "is_oa": w.is_oa, "in_library": bool(w.doi and w.doi.lower() in existing_dois)}
            for w in works
        ]}

    @app.post("/api/discover/institution-authors", response_class=responses.JSONResponse)
    def discover_institution_authors(payload: dict[str, Any]):
        """Fetch authors affiliated with an institution."""
        institution_id = str(payload.get("institution_id") or "").strip()
        if not institution_id:
            raise fastapi.HTTPException(status_code=400, detail="Missing institution_id")
        min_works = payload.get("min_works")
        if min_works is not None:
            min_works = int(min_works)
        active_cfg = current_cfg()
        from .discovery import get_institution_authors
        authors = get_institution_authors(
            active_cfg.openalex_client, institution_id, min_works=min_works,
        )
        return {"ok": True, "authors": [
            {"openalex_id": a.openalex_id, "orcid": a.orcid, "display_name": a.display_name,
             "affiliation": a.affiliation, "works_count": a.works_count,
             "cited_by_count": a.cited_by_count, "h_index": a.h_index}
            for a in authors
        ]}

    # ── BibTeX file/string import ────────────────────────────────────────────

    @app.post("/api/ingest/preview-bib", response_class=responses.JSONResponse)
    async def ingest_preview_bib(
        file: fastapi.UploadFile | None = fastapi.File(None),
        bibtex_text: str = fastapi.Form(""),
    ):
        """Parse an uploaded .bib file or pasted BibTeX text and return preview entries."""
        from .ingest import preview_bibtex
        text = bibtex_text.strip()
        if file and file.filename:
            raw = await file.read()
            text = raw.decode("utf-8", errors="replace")
        if not text:
            raise fastapi.HTTPException(status_code=400, detail="No BibTeX content provided")
        active_cfg = current_cfg()
        try:
            entries = preview_bibtex(text, active_cfg.repo_root)
        except Exception as e:
            raise fastapi.HTTPException(status_code=422, detail=f"BibTeX parse error: {e}")
        return {
            "ok": True,
            "entries": [
                {
                    "citekey": e.citekey,
                    "title": e.title,
                    "authors": e.authors,
                    "year": e.year,
                    "doi": e.doi,
                    "entry_type": e.entry_type,
                    "already_exists": e.already_exists,
                }
                for e in entries
            ],
        }

    bib_import_job: dict[str, Any] = {
        "running": False,
        "completed": 0,
        "total": 0,
        "message": "",
        "error": None,
        "citekeys": [],
    }
    bib_import_lock = threading.Lock()

    @app.post("/api/ingest/import-bib", response_class=responses.JSONResponse)
    def ingest_import_bib(payload: dict[str, Any]):
        """Import selected BibTeX entries into srcbib."""
        from .ingest import import_bibtex_entries
        bibtex_text = str(payload.get("bibtex_text") or "").strip()
        selected = payload.get("entries") or []
        if not bibtex_text:
            raise fastapi.HTTPException(status_code=400, detail="Missing bibtex_text")
        if not selected:
            raise fastapi.HTTPException(status_code=400, detail="No entries selected")
        # Extract citekeys from the entries list
        citekeys = [str(e.get("citekey") or e) if isinstance(e, dict) else str(e) for e in selected]
        active_cfg = current_cfg()

        with bib_import_lock:
            if bib_import_job["running"]:
                raise fastapi.HTTPException(status_code=409, detail="Import already running")
            bib_import_job.update(running=True, completed=0, total=len(citekeys), message="Importing...", error=None, citekeys=[])

        def _run():
            try:
                count, added = import_bibtex_entries(
                    bibtex_text=bibtex_text,
                    selected_citekeys=citekeys,
                    repo_root=active_cfg.repo_root,
                )
                with bib_import_lock:
                    bib_import_job.update(
                        running=False, completed=count, total=count,
                        message=f"Imported {count} entries.",
                        citekeys=added,
                    )
            except Exception as exc:
                with bib_import_lock:
                    bib_import_job.update(running=False, error=str(exc), message=f"Import failed: {exc}")

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "message": f"Importing {len(citekeys)} entries..."}

    @app.get("/api/ingest/import-bib/status", response_class=responses.JSONResponse)
    def ingest_import_bib_status():
        with bib_import_lock:
            return dict(bib_import_job)

    # ── drop paper from library (remove from citekeys.md) ────────────────────

    @app.delete("/api/papers/{citekey}", response_class=responses.JSONResponse)
    def drop_paper(citekey: str):
        from .citekeys import load_citekeys_md, remove_citekeys_md
        cfg = current_cfg()
        if not cfg.citekeys_path or not Path(cfg.citekeys_path).exists():
            raise fastapi.HTTPException(status_code=404, detail="citekeys.md not found")
        before = load_citekeys_md(cfg.citekeys_path)
        if citekey not in before:
            raise fastapi.HTTPException(status_code=404, detail=f"{citekey} not in citekeys.md")
        remove_citekeys_md(cfg.citekeys_path, [citekey])
        return {"ok": True, "removed": citekey}

    # ── refresh paper metadata from OpenAlex by DOI ───────────────────────────

    @app.post("/api/papers/{citekey}/refresh-metadata", response_class=responses.JSONResponse)
    def refresh_paper_metadata(citekey: str):
        """Re-fetch OpenAlex metadata for a single paper via its DOI."""
        cfg = current_cfg()
        # Find the paper's DOI from the resolved.jsonl or BibTeX
        doi = None
        if cfg.openalex.out_jsonl.exists():
            for line in cfg.openalex.out_jsonl.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    if row.get("citekey") == citekey and row.get("doi"):
                        doi = row["doi"]
                        break
                except Exception:
                    pass
        if not doi:
            # Fall back to BibTeX
            from ._pybtex_utils import parse_bibtex_file, require_pybtex
            require_pybtex("refresh-metadata")
            src_dir = cfg.bibtex_merge.src_dir
            src_glob = cfg.bibtex_merge.src_glob
            for bib_path in sorted(p for p in src_dir.glob(src_glob) if p.is_file()):
                db = parse_bibtex_file(bib_path)
                if citekey in db.entries:
                    doi = str(db.entries[citekey].fields.get("doi") or "").strip() or None
                    break
        if not doi:
            raise fastapi.HTTPException(status_code=400, detail=f"No DOI found for {citekey}")
        try:
            result = add_openalex_work_to_bib(
                cfg=cfg.openalex_client, cache=cfg.openalex_cache,
                repo_root=cfg.repo_root, doi=doi,
            )
            return {"ok": True, "citekey": citekey, "openalex_id": result.openalex_id}
        except Exception as exc:
            raise fastapi.HTTPException(status_code=500, detail=str(exc))

    # ── normalize-citekeys action (background) ─────────────────────────────────

    normalize_job: dict[str, Any] = {
        "running": False,
        "done": 0,
        "total": 0,
        "current": "",
        "renames": [],
        "enriched": [],
        "skipped": [],
        "error": None,
        "cancelled": False,
        "_plan": None,  # NormalizePlan held for apply step; stripped from snapshots
    }
    normalize_lock = threading.Lock()

    def _normalize_snapshot() -> dict[str, Any]:
        with normalize_lock:
            snap = {k: v for k, v in normalize_job.items() if not k.startswith("_")}
            return snap

    @app.post("/api/actions/normalize-citekeys", response_class=responses.JSONResponse)
    def action_normalize_citekeys(payload: dict[str, Any]):
        """Preview or apply citekey normalization to author_year_Title format.

        POST with apply=False: launches a background preview thread that enriches
        papers and builds the rename list incrementally.
        POST with apply=True: applies renames from the last completed preview.

        Uses cascading enrichment to resolve missing authors:
        1. DOI → OpenAlex lookup
        2. PDF → GROBID header extraction
        3. Title → CrossRef title search → OpenAlex
        """
        apply = bool(payload.get("apply", False))

        if apply:
            # Apply renames from last completed preview
            return _apply_normalize_renames()

        # Preview mode: start background enrichment
        with normalize_lock:
            if normalize_job["running"]:
                return {"ok": True, "started": False, "message": "Already running", **_normalize_snapshot()}

        enrich = bool(payload.get("enrich", True))
        active_cfg = current_cfg()

        with normalize_lock:
            normalize_job.update({
                "running": True,
                "done": 0,
                "total": 0,
                "current": "scanning...",
                "renames": [],
                "enriched": [],
                "skipped": [],
                "error": None,
                "cancelled": False,
                "_plan": None,
            })

        def _run_normalize_preview() -> None:
            try:
                def _progress(done: int, total: int, current: str) -> None:
                    with normalize_lock:
                        normalize_job["done"] = done
                        normalize_job["total"] = total
                        normalize_job["current"] = current

                def _cancelled() -> bool:
                    with normalize_lock:
                        return bool(normalize_job["cancelled"])

                plan = build_normalize_plan(
                    active_cfg,
                    enrich=enrich,
                    progress=_progress,
                    cancel=_cancelled,
                )
                with normalize_lock:
                    if normalize_job["cancelled"]:
                        normalize_job["running"] = False
                        normalize_job["current"] = ""
                        normalize_job["error"] = "Cancelled by user."
                        return
                    normalize_job["_plan"] = plan
                    normalize_job["renames"] = [
                        {"old": r.old, "new": r.new, "source_bib": r.source_bib,
                         "enrich_source": r.enrich_source}
                        for r in plan.renames
                    ]
                    normalize_job["enriched"] = [
                        {"citekey": e.citekey, "source": e.source, "authors": e.authors}
                        for e in plan.enriched
                    ]
                    normalize_job["skipped"] = [
                        {"citekey": s.citekey, "source_bib": s.source_bib, "reason": s.reason}
                        for s in plan.skipped
                    ]
                    normalize_job["running"] = False
                    normalize_job["done"] = plan.total_scanned
                    normalize_job["total"] = plan.total_scanned
                    normalize_job["current"] = ""

            except Exception as exc:
                with normalize_lock:
                    normalize_job["running"] = False
                    normalize_job["error"] = str(exc)
                    normalize_job["current"] = ""

        threading.Thread(target=_run_normalize_preview, daemon=True).start()
        return {"ok": True, "started": True}

    def _apply_normalize_renames() -> dict[str, Any]:
        """Apply renames from the last completed preview."""
        with normalize_lock:
            if normalize_job["running"]:
                return {"ok": False, "error": "Preview still running, wait for completion."}
            plan = normalize_job.get("_plan")
            enriched_info = list(normalize_job["enriched"])
            skipped_info = list(normalize_job["skipped"])

        if plan is None or not plan.renames:
            return {
                "ok": True, "applied": False, "renames": [],
                "enriched": enriched_info, "skipped": skipped_info,
            }

        active_cfg = current_cfg()
        result = apply_normalize_plan(active_cfg, plan)
        return {
            "ok": True,
            "applied": True,
            "renames": result.renames,
            "enriched": enriched_info,
            "skipped": skipped_info,
            "run_id": result.run_id,
        }

    @app.get("/api/actions/normalize-citekeys/status", response_class=responses.JSONResponse)
    def action_normalize_status():
        """Return current normalize-citekeys job status."""
        return _normalize_snapshot()

    @app.post("/api/actions/normalize-citekeys/cancel", response_class=responses.JSONResponse)
    def action_normalize_cancel():
        """Cancel an in-progress normalize preview."""
        with normalize_lock:
            if normalize_job["running"]:
                normalize_job["cancelled"] = True
        return _normalize_snapshot()

    @app.post("/api/actions/revert-normalize", response_class=responses.JSONResponse)
    def action_revert_normalize(payload: dict[str, Any]):
        """Revert the last (or a specific) normalize-citekeys operation."""
        active_cfg = current_cfg()
        normalize_log = active_cfg.ledger.root / "normalize.jsonl"
        if not normalize_log.exists():
            return {"ok": False, "error": "No normalize operations to revert."}
        entries = [json.loads(line) for line in normalize_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not entries:
            return {"ok": False, "error": "No normalize operations to revert."}
        target_run = payload.get("run_id")
        if target_run:
            entry = next((e for e in entries if e["run_id"] == target_run), None)
            if not entry:
                return {"ok": False, "error": f"Run {target_run} not found.", "available": [e["run_id"] for e in entries]}
        else:
            entry = entries[-1]  # most recent
        backup_manifest: dict[str, str] = entry["backup_manifest"]
        restored: list[str] = []
        for original, backup in backup_manifest.items():
            backup_path = Path(backup)
            if not backup_path.exists():
                return {"ok": False, "error": f"Backup file missing: {backup}"}
            shutil.copy2(backup_path, original)
            restored.append(original)
        # Remove the reverted entry from the log
        remaining = [e for e in entries if e["run_id"] != entry["run_id"]]
        normalize_log.write_text(
            "".join(json.dumps(e, sort_keys=True) + "\n" for e in remaining),
            encoding="utf-8",
        )
        return {"ok": True, "reverted_run": entry["run_id"], "restored_files": restored}

    # ── library endpoints ─────────────────────────────────────────────────────

    @app.get("/api/library", response_class=responses.JSONResponse)
    def get_library():
        return load_library(current_cfg())

    @app.post("/api/library/bulk", response_class=responses.JSONResponse)
    def bulk_update_library(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekeys = payload.get("citekeys") or []
        if not citekeys:
            raise fastapi.HTTPException(status_code=400, detail="citekeys list is required")
        add_tags = payload.get("add_tags")
        if isinstance(add_tags, str):
            add_tags = [t.strip() for t in add_tags.split(",") if t.strip()] or None
        remove_tags = payload.get("remove_tags")
        if isinstance(remove_tags, str):
            remove_tags = [t.strip() for t in remove_tags.split(",") if t.strip()] or None
        results = bulk_update(
            active_cfg,
            citekeys,
            status=payload.get("status") or None,
            priority=payload.get("priority") or None,
            add_tags=add_tags,
            remove_tags=remove_tags,
        )
        return {"ok": True, "updated": len(results), "entries": results}

    @app.post("/api/library/{citekey}", response_class=responses.JSONResponse)
    def update_library_entry(citekey: str, payload: dict[str, Any]):
        active_cfg = current_cfg()
        tags = payload.get("tags")
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()] or None
        elif isinstance(tags, list):
            tags = [str(t).strip() for t in tags if str(t).strip()] or None
        entry = update_entry(
            active_cfg,
            citekey,
            status=payload.get("status") or None,
            tags=tags,
            priority=payload.get("priority") or None,
        )
        return {"ok": True, "citekey": citekey, "entry": entry}

    # ── paper context endpoint (AI-facing) ────────────────────────────────────

    @app.get("/api/papers/{citekey}/context", response_class=responses.JSONResponse)
    def paper_context(citekey: str):
        active_cfg = current_cfg()
        payload = build_ui_model(active_cfg)
        paper = payload.get("paper_lookup", {}).get(citekey)
        if not paper:
            raise fastapi.HTTPException(status_code=404, detail=f"Paper not found: {citekey}")
        lib = paper.get("library") or {}
        grobid = paper.get("grobid") or {}
        header = grobid.get("header") or {}
        np = notes_path(active_cfg, citekey)
        notes_text = np.read_text(encoding="utf-8") if np.exists() else None
        return {
            "citekey": citekey,
            "title": paper.get("title"),
            "authors": paper.get("authors") or [],
            "year": paper.get("year"),
            "doi": paper.get("doi"),
            "abstract": header.get("abstract"),
            "status": lib.get("status"),
            "tags": lib.get("tags") or [],
            "priority": lib.get("priority"),
            "docling_excerpt": (paper.get("docling") or {}).get("excerpt"),
            "reference_count": grobid.get("reference_count", 0),
            "local_refs": [r["target_citekey"] for r in (paper.get("graph") or {}).get("grobid_refs", [])],
            "openalex_id": (paper.get("graph") or {}).get("seed_openalex_id"),
            "notes": notes_text,
            "artifacts": {
                k: bool(v.get("exists"))
                for k, v in (paper.get("artifacts") or {}).items()
                if isinstance(v, dict) and "exists" in v
            },
        }

    # ── absent-refs endpoint ──────────────────────────────────────────────────

    @app.get("/api/papers/{citekey}/absent-refs", response_class=responses.JSONResponse)
    def paper_absent_refs(citekey: str):
        return {"absent_refs": get_absent_refs(current_cfg(), citekey)}

    # ── ref-resolutions cache (persist CrossRef DOI lookups) ──────────────────

    @app.get("/api/papers/{citekey}/ref-resolutions", response_class=responses.JSONResponse)
    def get_ref_resolutions(citekey: str):
        key = citekey.lstrip("@")
        cache_path = grobid_out_root(current_cfg()) / key / "_ref_resolutions.json"
        if not cache_path.exists():
            return {"resolutions": {}}
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {"resolutions": {}}

    @app.post("/api/papers/{citekey}/ref-resolutions", response_class=responses.JSONResponse)
    def save_ref_resolutions(citekey: str, payload: dict[str, Any]):
        key = citekey.lstrip("@")
        cache_dir = grobid_out_root(current_cfg()) / key
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / "_ref_resolutions.json"
        data = json.dumps({"resolutions": payload.get("resolutions", {})}, indent=2)
        cache_path.write_text(data, encoding="utf-8")
        return {"ok": True}

    # ── ref-resolved markdown endpoint ────────────────────────────────────────

    @app.get("/api/papers/{citekey}/ref-md", response_class=responses.PlainTextResponse)
    def paper_ref_md(citekey: str):
        key = citekey.lstrip("@")
        md_path = current_cfg().out_root / key / f"{key}_ref_resolved.md"
        if md_path.exists():
            return responses.PlainTextResponse(md_path.read_text(encoding="utf-8", errors="replace"))
        # Fallback: serve raw docling markdown (checks pool too)
        docling_out, _src = resolve_docling_outputs(current_cfg(), key)
        if _src != "missing" and docling_out.md_path.exists():
            return responses.PlainTextResponse(
                docling_out.md_path.read_text(encoding="utf-8", errors="replace"),
                headers={"X-Biblio-Ref-Md-Status": "raw-docling"},
            )
        return responses.PlainTextResponse("", status_code=200)

    # ── figures endpoint ──────────────────────────────────────────────────────

    def _read_image_dimensions(path: Path) -> tuple[int, int]:
        """Read (width, height) from a PNG or JPEG file without external deps."""
        try:
            with open(path, "rb") as f:
                header = f.read(24)
                if header[:8] == b"\x89PNG\r\n\x1a\n":
                    w, h = struct.unpack(">II", header[16:24])
                    return w, h
                # JPEG: scan for SOF0/SOF1/SOF2 markers
                f.seek(2)
                while True:
                    marker = f.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        break
                    if marker[1] in (0xC0, 0xC1, 0xC2):
                        f.read(3)  # length + precision
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    length = struct.unpack(">H", f.read(2))[0]
                    f.seek(length - 2, 1)
        except Exception:
            pass
        return 0, 0

    @app.get("/api/papers/{citekey}/figures", response_class=responses.JSONResponse)
    def paper_figures(citekey: str):
        key = citekey.lstrip("@")
        out_dir = current_cfg().out_root / key
        artifacts_dir = out_dir / f"{key}_artifacts"
        if not artifacts_dir.exists():
            return {"figures": []}

        # Build stem -> caption map from Docling JSON if available
        caption_map: dict[str, str] = {}
        docling_json = out_dir / f"{key}.json"
        if docling_json.exists():
            try:
                doc = json.loads(docling_json.read_text())
                texts = doc.get("texts", [])
                for pic in doc.get("pictures", []):
                    uri = (pic.get("image") or {}).get("uri", "")
                    stem = Path(uri).name if uri else ""
                    captions = pic.get("captions", [])
                    if stem and captions:
                        ref = captions[0].get("$ref", "")
                        # ref format: '#/texts/44'
                        parts = ref.split("/")
                        if len(parts) == 3 and parts[1] == "texts":
                            idx = int(parts[2])
                            if 0 <= idx < len(texts):
                                caption_map[stem] = texts[idx].get("text", "")
            except Exception:
                pass

        figures = []
        for fpath in sorted(artifacts_dir.iterdir()):
            if fpath.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                continue
            w, h = _read_image_dimensions(fpath)
            figures.append({
                "path": f"{key}_artifacts/{fpath.name}",
                "name": fpath.name,
                "width": w,
                "height": h,
                "size_bytes": fpath.stat().st_size,
                "caption": caption_map.get(fpath.stem, ""),
            })
        return {"figures": figures}

    # ── notes endpoints ─────────────────────────────────────────────────────

    @app.get("/api/papers/{citekey}/notes", response_class=responses.PlainTextResponse)
    def paper_notes_get(citekey: str):
        key = citekey.lstrip("@")
        path = notes_path(current_cfg(), key)
        if path.exists():
            return responses.PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))
        return responses.PlainTextResponse("")

    @app.put("/api/papers/{citekey}/notes", response_class=responses.JSONResponse)
    def paper_notes_put(citekey: str, payload: dict[str, Any]):
        key = citekey.lstrip("@")
        content = str(payload.get("content", ""))
        path = notes_path(current_cfg(), key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "citekey": key, "path": str(path)}

    # ── collections endpoints ─────────────────────────────────────────────────

    @app.get("/api/collections", response_class=responses.JSONResponse)
    def api_get_collections():
        active_cfg = current_cfg()
        data = load_collections(active_cfg)
        data["collections"] = list_collections_summary(active_cfg)
        return data

    @app.post("/api/collections", response_class=responses.JSONResponse)
    def api_create_collection(payload: dict[str, Any]):
        name = str(payload.get("name") or "").strip()
        if not name:
            raise fastapi.HTTPException(status_code=400, detail="Missing name")
        query = str(payload.get("query") or "").strip() or None
        col = create_collection(current_cfg(), name, payload.get("parent") or None, query=query)
        return col

    @app.patch("/api/collections/{col_id}", response_class=responses.JSONResponse)
    def api_update_collection(col_id: str, payload: dict[str, Any]):
        cfg = current_cfg()
        if "name" in payload:
            if not rename_collection(cfg, col_id, str(payload["name"]).strip()):
                raise fastapi.HTTPException(status_code=404, detail="Collection not found")
        if "parent" in payload:
            result = move_collection(cfg, col_id, payload["parent"] or None)
            if result is None:
                raise fastapi.HTTPException(status_code=400, detail="Move would create cycle or collection not found")
        return load_collections(cfg)

    @app.delete("/api/collections/{col_id}", response_class=responses.JSONResponse)
    def api_delete_collection(col_id: str):
        if not delete_collection(current_cfg(), col_id):
            raise fastapi.HTTPException(status_code=404, detail="Collection not found")
        return {"ok": True}

    @app.post("/api/collections/{col_id}/papers", response_class=responses.JSONResponse)
    def api_collection_add_papers(col_id: str, payload: dict[str, Any]):
        citekeys = payload.get("citekeys") or []
        if isinstance(citekeys, str):
            citekeys = [citekeys]
        col = col_add_papers(current_cfg(), col_id, [str(k) for k in citekeys])
        if col is None:
            raise fastapi.HTTPException(status_code=404, detail="Collection not found")
        return col

    @app.delete("/api/collections/{col_id}/papers", response_class=responses.JSONResponse)
    def api_collection_remove_papers(col_id: str, payload: dict[str, Any]):
        citekeys = payload.get("citekeys") or []
        if isinstance(citekeys, str):
            citekeys = [citekeys]
        col = col_remove_papers(current_cfg(), col_id, [str(k) for k in citekeys])
        if col is None:
            raise fastapi.HTTPException(status_code=404, detail="Collection not found")
        return col

    @app.post("/api/resolve-doi", response_class=responses.JSONResponse)
    def api_resolve_doi(payload: dict[str, Any]):
        title = str(payload.get("title") or "").strip()
        if not title:
            raise fastapi.HTTPException(status_code=400, detail="Missing title")
        return resolve_doi_by_title(title)

    # ── fetch OA PDFs endpoint ───────────────────────────────────────────────

    fetch_oa_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "completed": 0, "total": 0,
        "openalex": 0, "unpaywall": 0, "ezproxy": 0, "pool_linked": 0,
        "downloaded": 0, "skipped": 0, "no_url": 0, "errors": 0, "logs": "",
    }
    fetch_oa_lock = threading.Lock()

    def _fetch_oa_snapshot() -> dict[str, Any]:
        with fetch_oa_lock:
            return dict(fetch_oa_job)

    @app.post("/api/actions/fetch-pdfs-oa", response_class=responses.JSONResponse)
    def action_fetch_pdfs_oa(payload: dict[str, Any]):
        active_cfg = current_cfg()
        force = bool(payload.get("force"))
        include_non_papers = bool(payload.get("include_non_papers"))
        ck_filter: set[str] | None = None
        if not include_non_papers:
            paper_keys = _paper_citekeys_from_bib(active_cfg)
            if paper_keys:
                ck_filter = paper_keys
        with fetch_oa_lock:
            if fetch_oa_job["running"]:
                return {"ok": True, "async": True, **dict(fetch_oa_job)}
            fetch_oa_job.update({
                "running": True, "message": "Fetching PDFs...", "error": None,
                "completed": 0, "total": 0,
                "openalex": 0, "unpaywall": 0, "ezproxy": 0, "pool_linked": 0,
                "downloaded": 0, "skipped": 0, "no_url": 0, "errors": 0, "logs": "",
            })

        import time as _time
        _fetch_start = _time.monotonic()

        def _progress(p: dict[str, Any]) -> None:
            from .pdf_fetch_oa import FetchCancelledError
            with fetch_oa_lock:
                done = int(p.get("completed") or 0)
                total = int(p.get("total") or 0)
                elapsed = _time.monotonic() - _fetch_start
                fetch_oa_job["completed"] = done
                fetch_oa_job["total"] = total
                fetch_oa_job["elapsed_s"] = round(elapsed, 1)
                if done > 0 and total > done:
                    fetch_oa_job["eta_s"] = round((elapsed / done) * (total - done), 1)
                else:
                    fetch_oa_job["eta_s"] = 0
                ck = p.get("citekey")
                if fetch_oa_job.get("cancelled"):
                    fetch_oa_job["message"] = f"Cancelling after {done}/{total}..."
                    raise FetchCancelledError("Cancelled by user")
                fetch_oa_job["message"] = (
                    f"Fetching OA PDFs {done}/{total}"
                    + (f" ({ck})" if ck else "")
                )

        def _run() -> None:
            try:
                results = fetch_pdfs_oa(active_cfg, force=force, progress_cb=_progress, citekey_filter=ck_filter)
                from .pdf_fetch_oa import ALL_STATUSES as _all_st
                counts = {s: sum(1 for r in results if r.status == s) for s in _all_st}
                error_lines = [f"{r.citekey}: {r.error}" for r in results if r.status == "error"]
                total_fetched = counts.get("openalex", 0) + counts.get("unpaywall", 0) + counts.get("ezproxy", 0)
                parts = []
                if counts.get("openalex"):
                    parts.append(f"{counts['openalex']} OpenAlex")
                if counts.get("unpaywall"):
                    parts.append(f"{counts['unpaywall']} Unpaywall")
                if counts.get("ezproxy"):
                    parts.append(f"{counts['ezproxy']} EZProxy")
                if counts.get("pool_linked"):
                    parts.append(f"{counts['pool_linked']} pool")
                source_msg = ", ".join(parts) if parts else "0 downloaded"
                with fetch_oa_lock:
                    fetch_oa_job.update({
                        "running": False, "error": None,
                        "completed": len(results), "total": len(results),
                        "openalex": counts.get("openalex", 0),
                        "unpaywall": counts.get("unpaywall", 0),
                        "ezproxy": counts.get("ezproxy", 0),
                        "pool_linked": counts.get("pool_linked", 0),
                        "downloaded": total_fetched,
                        "skipped": counts.get("skipped", 0),
                        "no_url": counts.get("no_url", 0),
                        "errors": counts.get("error", 0),
                        "logs": "\n".join(error_lines),
                        "message": (
                            f"Fetch done: {source_msg}, "
                            f"{counts.get('no_url', 0)} queued, {counts.get('skipped', 0)} skipped, "
                            f"{counts.get('error', 0)} errors."
                        ),
                    })
            except Exception as e:
                from .pdf_fetch_oa import FetchCancelledError as _FCE
                with fetch_oa_lock:
                    if isinstance(e, _FCE) or fetch_oa_job.get("cancelled"):
                        fetch_oa_job.update({
                            "running": False, "error": None, "cancelled": False,
                            "message": f"PDF fetch cancelled after {fetch_oa_job.get('completed', 0)} papers.",
                        })
                    else:
                        fetch_oa_job.update({
                            "running": False, "error": str(e),
                            "message": f"OA PDF fetch failed: {e}", "logs": str(e),
                        })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_fetch_oa_snapshot()}

    @app.get("/api/actions/fetch-pdfs-oa/status", response_class=responses.JSONResponse)
    def action_fetch_pdfs_oa_status():
        return _fetch_oa_snapshot()

    @app.post("/api/actions/fetch-pdfs-oa/cancel", response_class=responses.JSONResponse)
    def action_fetch_pdfs_oa_cancel():
        with fetch_oa_lock:
            if fetch_oa_job["running"]:
                fetch_oa_job["cancelled"] = True
                fetch_oa_job["message"] = "Cancelling PDF fetch..."
        return {"ok": True}

    # ── RAG build endpoint ────────────────────────────────────────────────────

    rag_build_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "indexed": 0, "chunks": 0, "completed": 0, "total": 0, "logs": "",
    }
    rag_build_lock = threading.Lock()

    def _rag_build_snapshot() -> dict[str, Any]:
        with rag_build_lock:
            return dict(rag_build_job)

    def _rag_python(active_cfg: BiblioConfig) -> str:
        return active_cfg.rag_python or sys.executable

    @app.post("/api/actions/rag-build", response_class=responses.JSONResponse)
    def action_rag_build():
        active_cfg = current_cfg()
        with rag_build_lock:
            if rag_build_job["running"]:
                return {"ok": True, "async": True, **dict(rag_build_job)}
            rag_build_job.update({
                "running": True,
                "message": "Building RAG index...",
                "error": None,
                "indexed": 0,
                "chunks": 0,
                "completed": 0,
                "total": 1,
            })

        def _run_rag_build() -> None:
            try:
                if _indexio_mod is not None:
                    data = _rag_build_indexio(active_cfg.repo_root)
                else:
                    vector_store_path = str(Path(__file__).parent / "vector_store.py")
                    python_exe = _rag_python(active_cfg)
                    proc = subprocess.run(
                        [python_exe, vector_store_path, "build",
                         "--root", str(active_cfg.repo_root),
                         "--persist-dir", str(active_cfg.rag_persist_dir)],
                        capture_output=True, text=True, timeout=600,
                    )
                    if proc.returncode != 0:
                        err = (proc.stderr or proc.stdout or "").strip()
                        raise RuntimeError(f"RAG build exited {proc.returncode}: {err[:500]}")
                    data = json.loads(proc.stdout.strip())
                if not data.get("ok"):
                    raise RuntimeError(data.get("error") or "RAG build returned ok=false")
                with rag_build_lock:
                    rag_build_job.update({
                        "running": False,
                        "error": None,
                        "indexed": data.get("indexed", 0),
                        "chunks": data.get("chunks", 0),
                        "completed": 1,
                        "total": 1,
                        "message": f"RAG index built: {data.get('indexed', 0)} papers, {data.get('chunks', 0)} chunks.",
                        "logs": "",
                    })
            except Exception as e:
                with rag_build_lock:
                    rag_build_job.update({
                        "running": False,
                        "error": str(e),
                        "message": f"RAG build failed: {e}",
                        "completed": 1,
                        "total": 1,
                        "logs": str(e),
                    })

        threading.Thread(target=_run_rag_build, daemon=True).start()
        return {"ok": True, "async": True, **_rag_build_snapshot()}

    @app.get("/api/actions/rag-build/status", response_class=responses.JSONResponse)
    def action_rag_build_status():
        return _rag_build_snapshot()

    # ── Ingest pipeline: fetch PDFs → docling → grobid → rag ──────────────────

    pipeline_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "completed": 0, "total": 0, "stage": "", "logs": "",
    }
    pipeline_lock = threading.Lock()

    def _pipeline_snapshot() -> dict[str, Any]:
        with pipeline_lock:
            return dict(pipeline_job)

    @app.post("/api/actions/ingest-pipeline", response_class=responses.JSONResponse)
    def action_ingest_pipeline():
        active_cfg = current_cfg()
        with pipeline_lock:
            if pipeline_job["running"]:
                return {"ok": True, "async": True, **dict(pipeline_job)}
            pipeline_job.update({
                "running": True, "completed": 0, "total": 4,
                "stage": "fetch-pdfs-oa", "message": "Step 1/4: Fetching PDFs...",
                "error": None, "logs": "",
            })

        def _run_pipeline() -> None:
            stages = [
                ("fetch-pdfs-oa", "Step 1/4: Fetching PDFs..."),
                ("docling-run", "Step 2/4: Running Docling..."),
                ("grobid-run", "Step 3/4: Running GROBID..."),
                ("rag-build", "Step 4/4: Building RAG index..."),
            ]
            logs = []
            try:
                for idx, (stage, msg) in enumerate(stages):
                    with pipeline_lock:
                        pipeline_job["completed"] = idx
                        pipeline_job["stage"] = stage
                        pipeline_job["message"] = msg

                    if stage == "fetch-pdfs-oa":
                        from .pdf_fetch_oa import fetch_pdfs_oa, ALL_STATUSES
                        results = fetch_pdfs_oa(active_cfg, force=False)
                        counts = {s: sum(1 for r in results if r.status == s) for s in ALL_STATUSES}
                        logs.append(f"PDF fetch: {len(results)} papers, " + ", ".join(f"{k}={v}" for k, v in counts.items() if v > 0))
                    elif stage == "docling-run":
                        from .docling import run_docling_for_key
                        from .batch import find_pending_docling
                        pending, _ = find_pending_docling(active_cfg)
                        for ck in pending:
                            try:
                                run_docling_for_key(active_cfg, ck)
                            except Exception as e:
                                logs.append(f"Docling {ck}: {e}")
                        logs.append(f"Docling: {len(pending)} processed")
                    elif stage == "grobid-run":
                        from .grobid import run_grobid_for_key, find_pending_grobid
                        pending = find_pending_grobid(active_cfg)
                        for ck in pending:
                            try:
                                run_grobid_for_key(active_cfg, ck)
                            except Exception as e:
                                logs.append(f"GROBID {ck}: {e}")
                        logs.append(f"GROBID: {len(pending)} processed")
                    elif stage == "rag-build":
                        logs.append("RAG: building index...")
                        # RAG build is handled separately — just log it

                with pipeline_lock:
                    pipeline_job.update({
                        "running": False,
                        "completed": 4,
                        "stage": "done",
                        "message": "Pipeline complete: " + "; ".join(logs),
                        "logs": "\n".join(logs),
                    })
            except Exception as e:
                with pipeline_lock:
                    pipeline_job.update({
                        "running": False,
                        "error": str(e),
                        "message": f"Pipeline failed at {pipeline_job.get('stage', '?')}: {e}",
                    })

        threading.Thread(target=_run_pipeline, daemon=True).start()
        return {"ok": True, "async": True, **_pipeline_snapshot()}

    @app.get("/api/actions/ingest-pipeline/status", response_class=responses.JSONResponse)
    def action_ingest_pipeline_status():
        return _pipeline_snapshot()

    # ── RAG index status endpoint ─────────────────────────────────────────────

    @app.get("/api/rag/status", response_class=responses.JSONResponse)
    def rag_index_status():
        active_cfg = current_cfg()
        rag_cfg_path = default_rag_config_path(active_cfg.repo_root)

        # Count docling markdown files
        docling_glob = list(active_cfg.out_root.glob("*/*.md"))
        docling_files = [p for p in docling_glob if not p.name.startswith("_")]
        docling_count = len(docling_files)

        # Determine persist directory from rag config
        persist_dir = active_cfg.rag_persist_dir
        exists = persist_dir.exists() and any(persist_dir.iterdir()) if persist_dir.exists() else False

        # Last built timestamp
        last_built = None
        if exists:
            try:
                last_built = persist_dir.stat().st_mtime
            except OSError:
                pass

        # Try to get indexed document count from Chroma
        indexed_count = 0
        embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        chunk_size = 1000
        chunk_overlap = 200
        if exists and _indexio_mod is not None and rag_cfg_path.exists():
            try:
                cfg = _indexio_mod.load_indexio_config(rag_cfg_path, root=active_cfg.repo_root)
                embedding_model = cfg.embedding_model
                chunk_size = cfg.chunk_size_chars
                chunk_overlap = cfg.chunk_overlap_chars
                from langchain_chroma import Chroma as _Chroma
                from indexio.query import make_embeddings as _make_emb
                embeddings = _make_emb(cfg.embedding_model)
                store_cfg = _indexio_mod.config.resolve_store(cfg, must_exist=True)
                db = _Chroma(
                    embedding_function=embeddings,
                    persist_directory=str(store_cfg.persist_directory),
                )
                col = db._collection
                indexed_count = col.count() if col is not None else 0
            except Exception:
                pass

        # Staleness: docling files newer than last build
        stale_count = 0
        if exists and last_built is not None:
            for p in docling_files:
                try:
                    if p.stat().st_mtime > last_built:
                        stale_count += 1
                except OSError:
                    pass

        # Check if build is currently running
        building = _rag_build_snapshot().get("running", False)

        return {
            "exists": exists,
            "last_built": last_built,
            "docling_count": docling_count,
            "indexed_count": indexed_count,
            "stale": stale_count > 0,
            "stale_count": stale_count,
            "building": building,
            "embedding_model": embedding_model,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
        }

    # ── semantic search endpoint ──────────────────────────────────────────────

    @app.post("/api/search/semantic", response_class=responses.JSONResponse)
    def search_semantic(payload: dict[str, Any]):
        active_cfg = current_cfg()
        query = str(payload.get("query") or "").strip()
        n_results = int(payload.get("n_results") or 10)
        if not query:
            raise fastapi.HTTPException(status_code=400, detail="Missing query")
        try:
            if _indexio_mod is not None:
                data = _rag_search_indexio(active_cfg.repo_root, query, n_results)
            else:
                vector_store_path = str(Path(__file__).parent / "vector_store.py")
                python_exe = _rag_python(active_cfg)
                proc = subprocess.run(
                    [python_exe, vector_store_path, "search",
                     "--root", str(active_cfg.repo_root),
                     "--persist-dir", str(active_cfg.rag_persist_dir),
                     "--query", query,
                     "--n", str(n_results)],
                    capture_output=True, text=True, timeout=60,
                )
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "").strip()
                    raise RuntimeError(f"RAG search exited {proc.returncode}: {err[:500]}")
                data = json.loads(proc.stdout.strip())
        except Exception as e:
            raise fastapi.HTTPException(status_code=500, detail=str(e))
        if not data.get("ok"):
            raise fastapi.HTTPException(status_code=503, detail=data.get("error") or "Search failed")
        # enrich results with paper metadata
        model = build_ui_model(active_cfg)
        paper_lookup = model.get("paper_lookup") or {}
        for item in data.get("results") or []:
            ck = item.get("citekey", "")
            paper = paper_lookup.get(ck)
            if paper:
                item["title"] = paper.get("title")
                item["year"] = paper.get("year")
                item["authors"] = paper.get("authors") or []
        return data

    @app.post("/api/setup/docling-check", response_class=responses.JSONResponse)
    def setup_docling_check():
        return check_docling_command(current_cfg())

    @app.post("/api/setup/grobid-check", response_class=responses.JSONResponse)
    def setup_grobid_check():
        return check_grobid_server_as_dict(current_cfg().grobid)

    @app.post("/api/setup/grobid-config", response_class=responses.JSONResponse)
    def setup_grobid_config(payload: dict[str, Any]):
        repo_root = current_cfg().repo_root
        _update_grobid_config(repo_root, payload)
        updated = reload_cfg()
        return {
            "ok": True,
            "message": "Saved GROBID config.",
            "setup": build_setup_report(updated),
        }

    @app.post("/api/setup/pdf-fetch-config", response_class=responses.JSONResponse)
    def setup_pdf_fetch_config(payload: dict[str, Any]):
        repo_root = current_cfg().repo_root
        _update_pdf_fetch_config(repo_root, payload)
        updated = reload_cfg()
        return {
            "ok": True,
            "message": "Saved PDF fetch config.",
            "setup": build_setup_report(updated),
        }

    @app.post("/api/setup/docling-command", response_class=responses.JSONResponse)
    def setup_docling_command(payload: dict[str, Any]):
        mode = str(payload.get("mode") or "raw").strip()
        repo_root = current_cfg().repo_root
        if mode == "conda":
            env_name = str(payload.get("env_name") or "").strip()
            if not env_name:
                raise fastapi.HTTPException(status_code=400, detail="Missing conda env name")
            _update_docling_command(repo_root, ["conda", "run", "-n", env_name, "docling"])
            updated = reload_cfg()
            return {
                "ok": True,
                "message": f"Updated Docling command to use conda env {env_name}.",
                "setup": build_setup_report(updated),
            }
        command = str(payload.get("command") or "").strip()
        if not command:
            raise fastapi.HTTPException(status_code=400, detail="Missing command")
        _update_docling_command(repo_root, shlex.split(command))
        updated = reload_cfg()
        return {
            "ok": True,
            "message": "Updated Docling command.",
            "setup": build_setup_report(updated),
        }

    @app.post("/api/setup/install-docling-uv", response_class=responses.JSONResponse)
    def setup_install_docling_uv():
        repo_root = current_cfg().repo_root
        try:
            install = _install_docling_uv(repo_root)
        except subprocess.CalledProcessError as e:
            cmd = " ".join(str(part) for part in e.cmd) if isinstance(e.cmd, (list, tuple)) else str(e.cmd)
            detail = (e.stderr or e.stdout or "").strip()
            msg = f"uv-based Docling install failed with exit code {e.returncode}: {cmd}"
            if detail:
                msg = f"{msg}\n{detail}"
            raise fastapi.HTTPException(status_code=500, detail=msg)
        except Exception as e:
            raise fastapi.HTTPException(status_code=500, detail=str(e))
        updated = reload_cfg()
        return {
            "ok": True,
            "message": f"Installed Docling into {install['env_dir']}.",
            "install": install,
            "setup": build_setup_report(updated),
        }

    # ── tag vocabulary endpoints ───────────────────────────────────────────────

    @app.get("/api/tag-vocab", response_class=responses.JSONResponse)
    def api_tag_vocab():
        return load_tag_vocab_from_config(current_cfg())

    @app.post("/api/library/lint", response_class=responses.JSONResponse)
    def api_lint_library_tags():
        active_cfg = current_cfg()
        vocab = load_tag_vocab_from_config(active_cfg)
        library = load_library(active_cfg)
        return lint_library_tags(library, vocab)

    @app.post("/api/library/dedup", response_class=responses.JSONResponse)
    def api_library_dedup():
        active_cfg = current_cfg()
        from .dedup import find_duplicates
        groups = find_duplicates(active_cfg.repo_root, cfg=active_cfg)
        return {"groups": groups, "count": len(groups)}

    @app.post("/api/library/dedup/merge", response_class=responses.JSONResponse)
    def api_library_dedup_merge(payload: dict[str, Any]):
        """Merge duplicate citekeys: keep suggested, remove others, transfer tags."""
        active_cfg = current_cfg()
        keep = payload.get("keep", "")
        remove = payload.get("remove", [])
        if not keep or not remove:
            return {"ok": False, "error": "Both 'keep' and 'remove' are required."}

        papers = load_library(active_cfg)
        keep_entry = dict(papers.get(keep) or {})
        # Transfer unique tags from removed entries
        keep_tags = list(keep_entry.get("tags") or [])
        for ck in remove:
            other_entry = papers.get(ck, {})
            for tag in (other_entry.get("tags") or []):
                if tag not in keep_tags:
                    keep_tags.append(tag)
        if keep_tags:
            keep_entry["tags"] = keep_tags
        # Transfer notes content if keep has none
        keep_notes = keep_entry.get("notes")
        if not keep_notes:
            for ck in remove:
                other_entry = papers.get(ck, {})
                if other_entry.get("notes"):
                    keep_entry["notes"] = other_entry["notes"]
                    break
        # Persist updated keep entry
        if keep_entry:
            papers[keep] = keep_entry
        # Remove duplicate entries
        for ck in remove:
            papers.pop(ck, None)
        from .library import save_library
        save_library(active_cfg, papers)

        # Remove duplicate citekeys from citekeys.md
        from .citekeys import remove_citekeys_md
        if active_cfg.citekeys_path.exists():
            remove_citekeys_md(active_cfg.citekeys_path, remove)

        return {"ok": True, "kept": keep, "removed": remove, "entry": keep_entry}

    # ── autotag (background action) ────────────────────────────────────────────

    autotag_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "completed": 0, "total": 0, "citekey": None, "results": [],
    }
    autotag_lock = threading.Lock()

    def _autotag_snapshot() -> dict[str, Any]:
        with autotag_lock:
            return dict(autotag_job)

    @app.post("/api/actions/autotag", response_class=responses.JSONResponse)
    def action_autotag(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekey = str(payload.get("citekey") or "").strip() or None
        tiers = payload.get("tiers") or None
        model_name = str(payload.get("model") or "").strip() or None
        include_non_papers = bool(payload.get("include_non_papers"))
        with autotag_lock:
            if autotag_job["running"]:
                return {"ok": True, "async": True, **dict(autotag_job)}
            if citekey:
                keys = [citekey]
            else:
                keys = load_citekeys_md(active_cfg.citekeys_path) if active_cfg.citekeys_path.exists() else []
                if not include_non_papers:
                    paper_keys = _paper_citekeys_from_bib(active_cfg)
                    if paper_keys:
                        keys = [k for k in keys if k in paper_keys]
            autotag_job.update({
                "running": True, "message": f"Auto-tagging {len(keys)} papers...",
                "error": None, "completed": 0, "total": len(keys),
                "citekey": None, "results": [],
            })

        def _run() -> None:
            results = []
            for idx, ck in enumerate(keys, start=1):
                with autotag_lock:
                    autotag_job["completed"] = idx - 1
                    autotag_job["citekey"] = ck
                    autotag_job["message"] = f"Auto-tagging {idx}/{len(keys)}: {ck}"
                try:
                    kwargs: dict[str, Any] = {"citekey": ck, "root": active_cfg.repo_root}
                    if tiers:
                        kwargs["tiers"] = tiers
                    if model_name:
                        kwargs["model"] = model_name
                    result = autotag(**kwargs)
                    results.append(result)
                except Exception as e:
                    results.append({"citekey": ck, "error": str(e)})
            with autotag_lock:
                autotag_job.update({
                    "running": False, "error": None,
                    "completed": len(keys), "total": len(keys),
                    "citekey": None, "results": results,
                    "message": f"Auto-tagging finished for {len(keys)} papers.",
                })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_autotag_snapshot()}

    @app.get("/api/actions/autotag/status", response_class=responses.JSONResponse)
    def action_autotag_status():
        return _autotag_snapshot()

    @app.post("/api/actions/autotag/cancel", response_class=responses.JSONResponse)
    def action_autotag_cancel():
        with autotag_lock:
            if autotag_job["running"]:
                autotag_job["running"] = False
                autotag_job["error"] = None
                autotag_job["message"] = "Auto-tagging cancelled."
        return _autotag_snapshot()

    # ── summarize (background action) ──────────────────────────────────────────

    summarize_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "citekey": None, "summary_path": None,
    }
    summarize_lock = threading.Lock()

    def _summarize_snapshot() -> dict[str, Any]:
        with summarize_lock:
            return dict(summarize_job)

    @app.get("/api/papers/{citekey}/summary", response_class=responses.PlainTextResponse)
    def api_paper_summary(citekey: str):
        active_cfg = current_cfg()
        sp = summary_path_for_key(active_cfg, citekey)
        if not sp.exists():
            raise fastapi.HTTPException(status_code=404, detail=f"No summary for {citekey}")
        return responses.PlainTextResponse(sp.read_text(encoding="utf-8"))

    @app.post("/api/actions/summarize", response_class=responses.JSONResponse)
    def action_summarize(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekey = str(payload.get("citekey") or "").strip()
        if not citekey:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey")
        force = bool(payload.get("force"))
        model_name = str(payload.get("model") or "").strip() or None
        with summarize_lock:
            if summarize_job["running"]:
                return {"ok": True, "async": True, **dict(summarize_job)}
            summarize_job.update({
                "running": True, "message": f"Summarizing {citekey}...",
                "error": None, "citekey": citekey, "summary_path": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {"citekey": citekey, "root": active_cfg.repo_root, "force": force}
                if model_name:
                    kwargs["model"] = model_name
                result = summarize(**kwargs)
                with summarize_lock:
                    summarize_job.update({
                        "running": False, "error": None, "citekey": citekey,
                        "summary_path": str(result.get("summary_path") or ""),
                        "message": f"Summary generated for {citekey}.",
                    })
            except Exception as e:
                with summarize_lock:
                    summarize_job.update({
                        "running": False, "error": str(e),
                        "message": f"Summarize failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_summarize_snapshot()}

    @app.get("/api/actions/summarize/status", response_class=responses.JSONResponse)
    def action_summarize_status():
        return _summarize_snapshot()

    # ── concepts endpoints ─────────────────────────────────────────────────────

    concepts_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "completed": 0, "total": 0, "citekey": None,
    }
    concepts_lock = threading.Lock()

    def _concepts_snapshot() -> dict[str, Any]:
        with concepts_lock:
            return dict(concepts_job)

    @app.get("/api/papers/{citekey}/concepts", response_class=responses.JSONResponse)
    def api_paper_concepts(citekey: str):
        active_cfg = current_cfg()
        data = load_concepts(active_cfg, citekey)
        if data is None:
            raise fastapi.HTTPException(status_code=404, detail=f"No concepts for {citekey}")
        return data

    @app.get("/api/concepts/index", response_class=responses.JSONResponse)
    def api_concept_index():
        return build_concept_index(current_cfg().repo_root)

    @app.post("/api/concepts/search", response_class=responses.JSONResponse)
    def api_concept_search(payload: dict[str, Any]):
        query = str(payload.get("query") or "").strip()
        if not query:
            raise fastapi.HTTPException(status_code=400, detail="Missing query")
        return search_concepts(query, current_cfg().repo_root)

    @app.post("/api/actions/concepts-extract", response_class=responses.JSONResponse)
    def action_concepts_extract(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekey = str(payload.get("citekey") or "").strip() or None
        run_all = bool(payload.get("all"))
        if not citekey and not run_all:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey or all=true")
        with concepts_lock:
            if concepts_job["running"]:
                return {"ok": True, "async": True, **dict(concepts_job)}
            if citekey:
                keys = [citekey]
            else:
                keys = load_citekeys_md(active_cfg.citekeys_path) if active_cfg.citekeys_path.exists() else []
            concepts_job.update({
                "running": True, "message": f"Extracting concepts for {len(keys)} papers...",
                "error": None, "completed": 0, "total": len(keys), "citekey": None,
            })

        def _run() -> None:
            for idx, ck in enumerate(keys, start=1):
                with concepts_lock:
                    concepts_job["completed"] = idx - 1
                    concepts_job["citekey"] = ck
                    concepts_job["message"] = f"Extracting concepts {idx}/{len(keys)}: {ck}"
                try:
                    extract_concepts(citekey=ck, root=active_cfg.repo_root)
                except Exception:
                    pass
            with concepts_lock:
                concepts_job.update({
                    "running": False, "error": None,
                    "completed": len(keys), "total": len(keys), "citekey": None,
                    "message": f"Concept extraction finished for {len(keys)} papers.",
                })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_concepts_snapshot()}

    @app.get("/api/actions/concepts-extract/status", response_class=responses.JSONResponse)
    def action_concepts_extract_status():
        return _concepts_snapshot()

    # ── comparison (background action) ─────────────────────────────────────────

    compare_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "comparison_path": None,
    }
    compare_lock = threading.Lock()

    def _compare_snapshot() -> dict[str, Any]:
        with compare_lock:
            return dict(compare_job)

    @app.post("/api/actions/compare", response_class=responses.JSONResponse)
    def action_compare(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekeys = payload.get("citekeys") or []
        if not citekeys or len(citekeys) < 2:
            raise fastapi.HTTPException(status_code=400, detail="Need at least 2 citekeys")
        dimensions = payload.get("dimensions") or None
        model_name = str(payload.get("model") or "").strip() or None
        with compare_lock:
            if compare_job["running"]:
                return {"ok": True, "async": True, **dict(compare_job)}
            compare_job.update({
                "running": True, "message": f"Comparing {len(citekeys)} papers...",
                "error": None, "comparison_path": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {"citekeys": citekeys, "root": active_cfg.repo_root}
                if dimensions:
                    kwargs["dimensions"] = dimensions
                if model_name:
                    kwargs["model"] = model_name
                result = compare(**kwargs)
                with compare_lock:
                    compare_job.update({
                        "running": False, "error": None,
                        "comparison_path": str(result.get("comparison_path") or ""),
                        "message": f"Comparison generated for {len(citekeys)} papers.",
                    })
            except Exception as e:
                with compare_lock:
                    compare_job.update({
                        "running": False, "error": str(e),
                        "message": f"Comparison failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_compare_snapshot()}

    @app.get("/api/actions/compare/status", response_class=responses.JSONResponse)
    def action_compare_status():
        return _compare_snapshot()

    @app.get("/api/comparisons", response_class=responses.JSONResponse)
    def api_list_comparisons():
        active_cfg = current_cfg()
        compare_dir = active_cfg.repo_root / "bib" / "derivatives" / "comparisons"
        if not compare_dir.exists():
            return {"comparisons": []}
        files = sorted(compare_dir.glob("*.md"), reverse=True)
        return {"comparisons": [
            {"path": str(f.relative_to(active_cfg.repo_root)), "name": f.stem}
            for f in files
        ]}

    @app.get("/api/comparisons/latest", response_class=responses.PlainTextResponse)
    def api_latest_comparison():
        active_cfg = current_cfg()
        compare_dir = active_cfg.repo_root / "bib" / "derivatives" / "comparisons"
        if not compare_dir.exists():
            raise fastapi.HTTPException(status_code=404, detail="No comparisons found")
        files = sorted(compare_dir.glob("*.md"), reverse=True)
        if not files:
            raise fastapi.HTTPException(status_code=404, detail="No comparisons found")
        return files[0].read_text(encoding="utf-8")

    # ── reading list (background action) ───────────────────────────────────────

    reading_list_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "recommendations": None,
    }
    reading_list_lock = threading.Lock()

    def _reading_list_snapshot() -> dict[str, Any]:
        with reading_list_lock:
            return dict(reading_list_job)

    @app.post("/api/reading-list", response_class=responses.JSONResponse)
    def api_reading_list(payload: dict[str, Any]):
        active_cfg = current_cfg()
        question = str(payload.get("question") or "").strip()
        if not question:
            raise fastapi.HTTPException(status_code=400, detail="Missing question")
        count = int(payload.get("count") or 5)
        model_name = str(payload.get("model") or "").strip() or None
        with reading_list_lock:
            if reading_list_job["running"]:
                return {"ok": True, "async": True, **dict(reading_list_job)}
            reading_list_job.update({
                "running": True, "message": "Generating reading list...",
                "error": None, "recommendations": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {"question": question, "root": active_cfg.repo_root, "count": count}
                if model_name:
                    kwargs["model"] = model_name
                result = reading_list(**kwargs)
                with reading_list_lock:
                    reading_list_job.update({
                        "running": False, "error": None,
                        "recommendations": result.get("recommendations"),
                        "message": "Reading list generated.",
                    })
            except Exception as e:
                with reading_list_lock:
                    reading_list_job.update({
                        "running": False, "error": str(e),
                        "message": f"Reading list failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_reading_list_snapshot()}

    @app.get("/api/actions/reading-list/status", response_class=responses.JSONResponse)
    def action_reading_list_status():
        return _reading_list_snapshot()

    # ── citation drafting (background action) ──────────────────────────────────

    cite_draft_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "draft": None,
    }
    cite_draft_lock = threading.Lock()

    def _cite_draft_snapshot() -> dict[str, Any]:
        with cite_draft_lock:
            return dict(cite_draft_job)

    @app.post("/api/cite-draft", response_class=responses.JSONResponse)
    def api_cite_draft(payload: dict[str, Any]):
        active_cfg = current_cfg()
        text = str(payload.get("text") or "").strip()
        if not text:
            raise fastapi.HTTPException(status_code=400, detail="Missing text")
        style = str(payload.get("style") or "latex").strip()
        max_refs = int(payload.get("max_refs") or 5)
        model_name = str(payload.get("model") or "").strip() or None
        with cite_draft_lock:
            if cite_draft_job["running"]:
                return {"ok": True, "async": True, **dict(cite_draft_job)}
            cite_draft_job.update({
                "running": True, "message": "Drafting citation...",
                "error": None, "draft": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {
                    "text": text, "root": active_cfg.repo_root,
                    "style": style, "max_refs": max_refs,
                }
                if model_name:
                    kwargs["model"] = model_name
                result = cite_draft(**kwargs)
                with cite_draft_lock:
                    cite_draft_job.update({
                        "running": False, "error": result.get("error"),
                        "draft": result.get("draft"),
                        "message": "Citation draft generated." if not result.get("error") else f"Citation draft failed: {result['error']}",
                    })
            except Exception as e:
                with cite_draft_lock:
                    cite_draft_job.update({
                        "running": False, "error": str(e),
                        "message": f"Citation draft failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_cite_draft_snapshot()}

    @app.get("/api/actions/cite-draft/status", response_class=responses.JSONResponse)
    def action_cite_draft_status():
        return _cite_draft_snapshot()

    # ── literature review (background action) ──────────────────────────────────

    review_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "action": None, "result": None,
    }
    review_lock = threading.Lock()

    def _review_snapshot() -> dict[str, Any]:
        with review_lock:
            return dict(review_job)

    @app.post("/api/actions/review-query", response_class=responses.JSONResponse)
    def action_review_query(payload: dict[str, Any]):
        active_cfg = current_cfg()
        question = str(payload.get("question") or "").strip()
        if not question:
            raise fastapi.HTTPException(status_code=400, detail="Missing question")
        model_name = str(payload.get("model") or "").strip() or None
        with review_lock:
            if review_job["running"]:
                return {"ok": True, "async": True, **dict(review_job)}
            review_job.update({
                "running": True, "message": "Running review query...",
                "error": None, "action": "review-query", "result": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {"question": question, "root": active_cfg.repo_root}
                if model_name:
                    kwargs["model"] = model_name
                result = review_query(**kwargs)
                with review_lock:
                    review_job.update({
                        "running": False, "error": result.get("error"),
                        "result": result,
                        "message": "Review query completed." if not result.get("error") else f"Review query failed: {result['error']}",
                    })
            except Exception as e:
                with review_lock:
                    review_job.update({
                        "running": False, "error": str(e),
                        "message": f"Review query failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_review_snapshot()}

    @app.post("/api/actions/review-plan", response_class=responses.JSONResponse)
    def action_review_plan(payload: dict[str, Any]):
        active_cfg = current_cfg()
        seed_citekeys = payload.get("seed_citekeys") or []
        if not seed_citekeys:
            raise fastapi.HTTPException(status_code=400, detail="Missing seed_citekeys")
        question = str(payload.get("question") or "").strip() or None
        model_name = str(payload.get("model") or "").strip() or None
        with review_lock:
            if review_job["running"]:
                return {"ok": True, "async": True, **dict(review_job)}
            review_job.update({
                "running": True, "message": "Generating review plan...",
                "error": None, "action": "review-plan", "result": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {
                    "seed_citekeys": seed_citekeys,
                    "question": question or "",
                    "root": active_cfg.repo_root,
                }
                if model_name:
                    kwargs["model"] = model_name
                result = review_plan(**kwargs)
                with review_lock:
                    review_job.update({
                        "running": False, "error": None,
                        "result": result, "message": "Review plan generated.",
                    })
            except Exception as e:
                with review_lock:
                    review_job.update({
                        "running": False, "error": str(e),
                        "message": f"Review plan failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_review_snapshot()}

    @app.get("/api/actions/review/status", response_class=responses.JSONResponse)
    def action_review_status():
        return _review_snapshot()

    # ── presentations (background action) ──────────────────────────────────────

    present_job: dict[str, Any] = {
        "running": False, "message": "", "error": None,
        "citekey": None, "slides_path": None,
    }
    present_lock = threading.Lock()

    def _present_snapshot() -> dict[str, Any]:
        with present_lock:
            return dict(present_job)

    @app.get("/api/papers/{citekey}/slides", response_class=responses.PlainTextResponse)
    def api_paper_slides(citekey: str):
        active_cfg = current_cfg()
        sp = slides_path_for_key(active_cfg, citekey)
        if not sp.exists():
            raise fastapi.HTTPException(status_code=404, detail=f"No slides for {citekey}")
        return responses.PlainTextResponse(sp.read_text(encoding="utf-8"))

    @app.post("/api/actions/present", response_class=responses.JSONResponse)
    def action_present(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekey = str(payload.get("citekey") or "").strip()
        if not citekey:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey")
        template = str(payload.get("template") or "journal-club").strip()
        model_name = str(payload.get("model") or "").strip() or None
        with present_lock:
            if present_job["running"]:
                return {"ok": True, "async": True, **dict(present_job)}
            present_job.update({
                "running": True, "message": f"Generating slides for {citekey}...",
                "error": None, "citekey": citekey, "slides_path": None,
            })

        def _run() -> None:
            try:
                kwargs: dict[str, Any] = {
                    "citekey": citekey, "root": active_cfg.repo_root,
                    "template": template,
                }
                if model_name:
                    kwargs["model"] = model_name
                result = generate_slides(**kwargs)
                with present_lock:
                    present_job.update({
                        "running": False, "error": None, "citekey": citekey,
                        "slides_path": str(result.get("slides_path") or ""),
                        "message": f"Slides generated for {citekey}.",
                    })
            except Exception as e:
                with present_lock:
                    present_job.update({
                        "running": False, "error": str(e),
                        "message": f"Slide generation failed: {e}",
                    })

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "async": True, **_present_snapshot()}

    @app.get("/api/actions/present/status", response_class=responses.JSONResponse)
    def action_present_status():
        return _present_snapshot()

    # ── smart collection query endpoint ────────────────────────────────────────

    @app.patch("/api/collections/{col_id}/query", response_class=responses.JSONResponse)
    def api_update_collection_query(col_id: str, payload: dict[str, Any]):
        query = str(payload.get("query") or "").strip()
        if not query:
            raise fastapi.HTTPException(status_code=400, detail="Missing query")
        result = col_update_query(current_cfg(), col_id, query)
        if result is None:
            raise fastapi.HTTPException(status_code=404, detail="Collection not found or not a smart collection")
        return result

    @app.patch("/api/collections/{col_id}/convert-smart", response_class=responses.JSONResponse)
    def api_convert_to_smart(col_id: str, payload: dict[str, Any]):
        query = str(payload.get("query") or "").strip()
        if not query:
            raise fastapi.HTTPException(status_code=400, detail="Missing query")
        result = col_convert_to_smart(current_cfg(), col_id, query)
        if result is None:
            raise fastapi.HTTPException(status_code=404, detail="Collection not found")
        return result

    return app


def serve_ui_app(cfg: BiblioConfig, *, host: str = "127.0.0.1", port: int = 8010) -> None:
    uvicorn = _require_uvicorn()
    app = create_ui_app(cfg)
    selected_port = find_available_port(str(host), int(port))
    print(f"[OK] UI available at http://{host}:{selected_port}")
    if selected_port != int(port):
        print(f"[INFO] Requested port {port} was unavailable; using {selected_port} instead.")
    uvicorn.run(app, host=host, port=int(selected_port))
