from __future__ import annotations

import importlib
import json
import shlex
import socket
import subprocess
import threading
import shutil
from pathlib import Path
from typing import Any
import yaml

from .bibtex import merge_srcbib
from .config import BiblioConfig, load_biblio_config
from .docling import run_docling_for_key
from .graph import add_openalex_work_to_bib, expand_openalex_reference_graph, load_openalex_seed_records
from .openalex.openalex_resolve import ResolveOptions, resolve_srcbib_to_openalex
from .rag import default_biblio_rag_template, default_rag_config_path, sync_biblio_rag_config
from .rag_support import load_raw_rag_config, write_raw_rag_config
from .site import build_biblio_site
from .site import BiblioSiteOptions, _build_site_model, default_site_out_dir


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
            "follow_up_build_cmd": "rag build --config bib/config/rag.yaml --sources biblio_docling",
        },
        "paths": {
            "citekeys": str(cfg.citekeys_path),
            "pdf_root": str(cfg.pdf_root),
            "out_root": str(cfg.out_root),
            "srcbib": str(cfg.bibtex_merge.src_dir),
            "openalex_out": str(cfg.openalex.out_jsonl),
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
        payload = build_ui_model(current_cfg())
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
        paper_path = active_cfg.pdf_root / Path(active_cfg.pdf_pattern.format(citekey=citekey))
        pdf_path = paper_path.resolve()
        if not pdf_path.exists() or not pdf_path.is_file():
            raise fastapi.HTTPException(status_code=404, detail=f"PDF not found for {citekey}")
        headers = {"Content-Disposition": f'inline; filename="{pdf_path.name}"'}
        return responses.FileResponse(str(pdf_path), media_type="application/pdf", headers=headers)

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
    }
    docling_job: dict[str, Any] = {
        "running": False,
        "message": "",
        "error": None,
        "citekey": None,
        "md_path": None,
    }
    openalex_lock = threading.Lock()
    graph_lock = threading.Lock()
    docling_lock = threading.Lock()

    def _openalex_snapshot() -> dict[str, Any]:
        with openalex_lock:
            return dict(openalex_job)

    def _graph_snapshot() -> dict[str, Any]:
        with graph_lock:
            return dict(graph_job)

    def _docling_snapshot() -> dict[str, Any]:
        with docling_lock:
            return dict(docling_job)

    @app.post("/api/actions/bibtex-merge", response_class=responses.JSONResponse)
    def action_bibtex_merge():
        active_cfg = current_cfg()
        n_sources, n_entries = merge_srcbib(active_cfg.bibtex_merge, dry_run=False)
        return _action_result(
            f"Merged {n_sources} source files into {n_entries} entries.",
            sources=n_sources,
            entries=n_entries,
        )

    @app.post("/api/actions/docling-run", response_class=responses.JSONResponse)
    def action_docling_run(payload: dict[str, Any]):
        active_cfg = current_cfg()
        citekey = str(payload.get("citekey") or "").strip()
        if not citekey:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey")
        with docling_lock:
            if docling_job["running"]:
                return {"ok": True, "async": True, **dict(docling_job)}
            docling_job.update(
                {
                    "running": True,
                    "message": f"Running Docling for {citekey}...",
                    "error": None,
                    "citekey": citekey,
                    "md_path": None,
                    "completed": 0,
                    "total": 1,
                }
            )

        def _run_docling() -> None:
            try:
                out = run_docling_for_key(active_cfg, citekey, force=False)
                with docling_lock:
                    docling_job["running"] = False
                    docling_job["message"] = f"Docling finished for {citekey}."
                    docling_job["error"] = None
                    docling_job["md_path"] = str(out.md_path)
                    docling_job["completed"] = 1
                    docling_job["total"] = 1
            except subprocess.CalledProcessError as e:
                cmd = " ".join(str(part) for part in e.cmd) if isinstance(e.cmd, (list, tuple)) else str(e.cmd)
                with docling_lock:
                    docling_job["running"] = False
                    docling_job["error"] = f"Docling command failed with exit code {e.returncode}: {cmd}"
                    docling_job["message"] = docling_job["error"]
            except Exception as e:
                with docling_lock:
                    docling_job["running"] = False
                    docling_job["error"] = str(e)
                    docling_job["message"] = f"Docling failed: {e}"

        threading.Thread(target=_run_docling, daemon=True).start()
        return {"ok": True, "async": True, **_docling_snapshot()}

    @app.get("/api/actions/docling-run/status", response_class=responses.JSONResponse)
    def action_docling_run_status():
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

    @app.post("/api/actions/graph-expand", response_class=responses.JSONResponse)
    def action_graph_expand():
        active_cfg = current_cfg()
        with graph_lock:
            if graph_job["running"]:
                return {"ok": True, "async": True, **dict(graph_job)}
            graph_job.update(
                {
                    "running": True,
                    "completed": 0,
                    "total": 0,
                    "seed_openalex_id": None,
                    "message": "Starting graph expansion...",
                    "error": None,
                    "candidates": 0,
                }
            )

        input_path = active_cfg.openalex.out_jsonl
        output_path = active_cfg.openalex.out_jsonl.parent / "graph_candidates.json"
        records = load_openalex_seed_records(input_path)

        def _progress(payload: dict[str, Any]) -> None:
            with graph_lock:
                graph_job["completed"] = int(payload.get("completed") or 0)
                graph_job["total"] = int(payload.get("total") or 0)
                graph_job["seed_openalex_id"] = payload.get("seed_openalex_id")
                graph_job["candidates"] = int(payload.get("candidates") or 0)
                base = f"Expanding graph {graph_job['completed']}/{graph_job['total']}" if graph_job["total"] else "Expanding graph..."
                seed = graph_job["seed_openalex_id"]
                graph_job["message"] = f"{base}" + (f" ({seed})" if seed else "")

        def _run_graph() -> None:
            try:
                result = expand_openalex_reference_graph(
                    cfg=active_cfg.openalex_client,
                    cache=active_cfg.openalex_cache,
                    records=records,
                    out_path=output_path,
                    direction="both",
                    force=False,
                    progress_cb=_progress,
                )
                with graph_lock:
                    graph_job["running"] = False
                    graph_job["completed"] = len(records)
                    graph_job["total"] = len(records)
                    graph_job["seed_openalex_id"] = None
                    graph_job["candidates"] = result.candidates
                    graph_job["message"] = f"Expanded {result.candidates} graph candidates."
                    graph_job["error"] = None
            except Exception as e:
                with graph_lock:
                    graph_job["running"] = False
                    graph_job["error"] = str(e)
                    graph_job["message"] = f"Graph expansion failed: {e}"

        threading.Thread(target=_run_graph, daemon=True).start()
        return {"ok": True, "async": True, **_graph_snapshot()}

    @app.get("/api/actions/graph-expand/status", response_class=responses.JSONResponse)
    def action_graph_expand_status():
        return _graph_snapshot()

    @app.post("/api/actions/site-build", response_class=responses.JSONResponse)
    def action_site_build():
        result = build_biblio_site(current_cfg(), force=True)
        return _action_result(
            f"Built site with {result.papers_total} papers.",
            out_dir=str(result.out_dir),
            papers=result.papers_total,
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

    @app.post("/api/setup/docling-check", response_class=responses.JSONResponse)
    def setup_docling_check():
        return check_docling_command(current_cfg())

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

    return app


def serve_ui_app(cfg: BiblioConfig, *, host: str = "127.0.0.1", port: int = 8010) -> None:
    uvicorn = _require_uvicorn()
    app = create_ui_app(cfg)
    selected_port = find_available_port(str(host), int(port))
    print(f"[OK] UI available at http://{host}:{selected_port}")
    if selected_port != int(port):
        print(f"[INFO] Requested port {port} was unavailable; using {selected_port} instead.")
    uvicorn.run(app, host=host, port=int(selected_port))
