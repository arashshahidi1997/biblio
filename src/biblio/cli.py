from __future__ import annotations

import argparse
import shlex
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from .citekeys import add_citekeys_md, load_citekeys_md, remove_citekeys_md
from .config import default_config_path, load_biblio_config
from .bibtex import merge_srcbib
from .docling import run_docling_for_key
from .openalex import resolve_openalex
from .paths import find_repo_root
from .rag import sync_biblio_rag_config
from .graph import add_openalex_work_to_bib, expand_openalex_reference_graph, load_openalex_seed_records
from .ingest import default_import_bib_path, ingest_file
from .scaffold import init_bib_scaffold
from .pdf_fetch import fetch_pdfs
from .site import (
    BiblioSiteOptions,
    _build_site_model,
    build_biblio_site,
    clean_biblio_site,
    default_site_out_dir,
    doctor_biblio_site,
    serve_biblio_site,
)
from .openalex.openalex_resolve import ResolveOptions, resolve_srcbib_to_openalex
from .ui import serve_ui_app
from .grobid import check_grobid_server, run_grobid_for_key

try:
    import argcomplete
except Exception:  # pragma: no cover
    argcomplete = None


def _build_screen_bash_command(
    *,
    repo_root: Path,
    python_exe: str,
    docling_args: list[str],
) -> str:
    cmd = [
        python_exe,
        "-m",
        "biblio.cli",
        "docling",
        "run",
        "--root",
        str(repo_root),
        *docling_args,
    ]
    return f"cd {shlex.quote(str(repo_root))} && " + " ".join(shlex.quote(part) for part in cmd)


def _launch_screen_session(*, name: str, bash_cmd: str) -> None:
    if shutil.which("screen") is None:
        raise FileNotFoundError(
            "GNU screen is not available on PATH. Install it (e.g. `apt install screen`) "
            "or run without `--screen`."
        )
    # -d -m: start detached; run bash -lc so the user gets a shell-like environment.
    subprocess.run(["screen", "-S", name, "-d", "-m", "bash", "-lc", bash_cmd], check=True)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="biblio", description="Portable bib/ Docling scaffolding and runner.")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize a repo-local bib/ Docling scaffold.")
    p_init.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")

    p_ck = sub.add_parser("citekeys", help="Manage bib/config/citekeys.md")
    ck_sub = p_ck.add_subparsers(dest="citekeys_cmd", required=True)
    ck_list = ck_sub.add_parser("list", help="List configured citekeys.")
    ck_list.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ck_list.add_argument("--path", type=Path, help="Path to citekeys.md (overrides config).")
    ck_add = ck_sub.add_parser("add", help="Add one or more citekeys.")
    ck_add.add_argument("keys", nargs="+", help="Keys like @foo_2020_Bar or foo_2020_Bar.")
    ck_add.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ck_add.add_argument("--path", type=Path, help="Path to citekeys.md (overrides config).")
    ck_rm = ck_sub.add_parser("remove", help="Remove one or more citekeys.")
    ck_rm.add_argument("keys", nargs="+", help="Keys like @foo_2020_Bar or foo_2020_Bar.")
    ck_rm.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ck_rm.add_argument("--path", type=Path, help="Path to citekeys.md (overrides config).")
    ck_status = ck_sub.add_parser("status", help="Show discovered papers and whether they are in citekeys.md.")
    ck_status.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ck_status.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    ck_status.add_argument("--json", action="store_true", help="Emit JSON instead of plain text.")

    p_ingest = sub.add_parser("ingest", help="Import non-BibTeX inputs into bib/srcbib/imported.bib.")
    ingest_sub = p_ingest.add_subparsers(dest="ingest_cmd", required=True)
    for name, help_text in (
        ("dois", "Import one DOI per line from a text file."),
        ("csljson", "Import CSL JSON records into a managed BibTeX source."),
        ("ris", "Import RIS records into a managed BibTeX source."),
    ):
        p_in = ingest_sub.add_parser(name, help=help_text)
        p_in.add_argument("input_path", type=Path, help="Input file to import.")
        p_in.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
        p_in.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
        p_in.add_argument(
            "--out-bib",
            type=Path,
            help="Managed output BibTeX file (default: bib/srcbib/imported.bib).",
        )
        p_in.add_argument("--dry-run", action="store_true", help="Parse and report without writing output.")
        p_in.add_argument("--stdout", action="store_true", help="Print generated BibTeX to stdout.")
    p_pdf = ingest_sub.add_parser("pdfs", help="Import local PDFs into bib/articles and emit managed BibTeX entries.")
    p_pdf.add_argument("input_paths", nargs="+", type=Path, help="PDF files or directories containing PDFs.")
    p_pdf.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_pdf.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    p_pdf.add_argument(
        "--out-bib",
        type=Path,
        help="Managed output BibTeX file (default: bib/srcbib/imported.bib).",
    )
    p_pdf.add_argument("--dry-run", action="store_true", help="Parse and report without writing output.")
    p_pdf.add_argument("--stdout", action="store_true", help="Print generated BibTeX to stdout.")

    p_doc = sub.add_parser("docling", help="Run Docling to generate Markdown/JSON artifacts.")
    doc_sub = p_doc.add_subparsers(dest="doc_cmd", required=True)
    p_run = doc_sub.add_parser("run", help="Run Docling for one key or all keys.")
    p_run.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_run.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    group = p_run.add_mutually_exclusive_group(required=True)
    group.add_argument("--key", help="Single citekey (with or without leading @).")
    group.add_argument("--all", action="store_true", help="Run for all citekeys in citekeys.md.")
    p_run.add_argument("--force", action="store_true", help="Re-run Docling even if outputs exist.")
    p_run.add_argument(
        "--screen",
        action="store_true",
        help="Run in a detached GNU screen session (background).",
    )
    p_run.add_argument(
        "--screen-name",
        default="docling",
        help="Screen session name when using --screen (default: docling).",
    )

    p_bt = sub.add_parser("bibtex", help="Work with BibTeX sources (srcbib merge).")
    bt_sub = p_bt.add_subparsers(dest="bibtex_cmd", required=True)
    bt_merge = bt_sub.add_parser("merge", help="Merge bib/srcbib/*.bib into a single main bib file.")
    bt_merge.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    bt_merge.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    bt_merge.add_argument("--dry-run", action="store_true", help="Parse and report, but do not write output.")

    bt_fetch = bt_sub.add_parser(
        "fetch-pdfs",
        help="Copy/symlink PDFs referenced by `file` fields in bib/srcbib/*.bib into bib/articles/...",
    )
    bt_fetch.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    bt_fetch.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    bt_fetch.add_argument("--dry-run", action="store_true")
    bt_fetch.add_argument("--force", action="store_true", help="Overwrite/recopy even if unchanged.")

    p_oa = sub.add_parser("openalex", help="Resolve srcbib entries to OpenAlex works.")
    oa_sub = p_oa.add_subparsers(dest="openalex_cmd", required=True)
    oa_resolve = oa_sub.add_parser("resolve", help="Resolve bib/srcbib/*.bib entries to OpenAlex works.")
    oa_resolve.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    oa_resolve.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    oa_resolve.add_argument("--src-dir", type=Path, help="Source bib directory (default: bib/srcbib).")
    oa_resolve.add_argument("--src-glob", default="*.bib", help="Glob for source bib files (default: *.bib).")
    oa_resolve.add_argument(
        "--out",
        type=Path,
        help="Output path (default: bib/derivatives/openalex/resolved.<format>).",
    )
    oa_resolve.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    oa_resolve.add_argument("--limit", type=int, default=None)
    oa_resolve.add_argument("--prefer-doi", action="store_true", default=True)
    oa_resolve.add_argument("--no-prefer-doi", dest="prefer_doi", action="store_false")
    oa_resolve.add_argument("--fallback-title-search", action="store_true", default=True)
    oa_resolve.add_argument("--no-fallback-title-search", dest="fallback_title_search", action="store_false")
    oa_resolve.add_argument("--force", action="store_true", help="Ignore cache and re-fetch.")
    oa_resolve.add_argument(
        "--strict",
        action="store_true",
        help="Fail fast on any resolution error (default: write error into row and continue).",
    )

    p_rag = sub.add_parser("rag", help="Manage bibliography-owned RAG sources.")
    rag_sub = p_rag.add_subparsers(dest="rag_cmd", required=True)
    rag_sync = rag_sub.add_parser("sync", help="Upsert bibliography-owned sources in the shared RAG config.")
    rag_sync.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    rag_sync.add_argument(
        "--config",
        type=Path,
        help="Path to the bibliography-owned RAG config (default: bib/config/rag.yaml).",
    )
    rag_sync.add_argument(
        "--force-init",
        action="store_true",
        help="Reinitialize the RAG config from defaults before syncing biblio-owned sources.",
    )

    p_add = sub.add_parser("add", help="Add a paper to the bibliography from DOI or OpenAlex.")
    add_sub = p_add.add_subparsers(dest="add_cmd", required=True)
    add_doi = add_sub.add_parser("doi", help="Add a paper by DOI via OpenAlex metadata.")
    add_doi.add_argument("doi", help="DOI to add.")
    add_doi.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    add_doi.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    add_oa = add_sub.add_parser("openalex", help="Add a paper by OpenAlex work id.")
    add_oa.add_argument("openalex_id", help="OpenAlex ID like W123 or https://openalex.org/W123.")
    add_oa.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    add_oa.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")

    p_graph = sub.add_parser("graph", help="Expand graph-style literature candidates from OpenAlex results.")
    graph_sub = p_graph.add_subparsers(dest="graph_cmd", required=True)
    graph_expand = graph_sub.add_parser("expand", help="Expand referenced-work candidates from OpenAlex-resolved seeds.")
    graph_expand.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    graph_expand.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        help="Input JSONL from `biblio openalex resolve` (default: bib/derivatives/openalex/resolved.jsonl).",
    )
    graph_expand.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        help="Output JSON for discovered candidates (default: bib/derivatives/openalex/graph_candidates.json).",
    )
    graph_expand.add_argument(
        "--force",
        action="store_true",
        help="Ignore cached OpenAlex work payloads and refetch them.",
    )
    graph_expand.add_argument(
        "--direction",
        choices=["references", "citing", "both"],
        default="both",
        help="Expand past works, future works, or both (default: both).",
    )

    p_site = sub.add_parser("site", help="Build and inspect a standalone bibliography site.")
    site_sub = p_site.add_subparsers(dest="site_cmd", required=True)
    site_build = site_sub.add_parser("build", help="Build a standalone site under bib/site/.")
    site_build.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    site_build.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    site_build.add_argument("--out-dir", type=Path, help="Site output directory (default: bib/site).")
    site_build.add_argument("--force", action="store_true", help="Delete and rebuild the output directory if it exists.")
    site_build.add_argument("--include-graphs", dest="include_graphs", action="store_true", default=True)
    site_build.add_argument("--no-graphs", dest="include_graphs", action="store_false")
    site_build.add_argument("--include-docling", dest="include_docling", action="store_true", default=True)
    site_build.add_argument("--no-docling", dest="include_docling", action="store_false")
    site_build.add_argument("--include-openalex", dest="include_openalex", action="store_true", default=True)
    site_build.add_argument("--no-openalex", dest="include_openalex", action="store_false")

    site_serve = site_sub.add_parser("serve", help="Serve a generated site directory over HTTP.")
    site_serve.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    site_serve.add_argument("--out-dir", type=Path, help="Site output directory (default: bib/site).")
    site_serve.add_argument("--port", type=int, default=8008, help="Port to bind (default: 8008).")

    site_clean = site_sub.add_parser("clean", help="Remove the generated site output directory.")
    site_clean.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    site_clean.add_argument("--out-dir", type=Path, help="Site output directory (default: bib/site).")

    site_doctor = site_sub.add_parser("doctor", help="Report current bibliography site readiness.")
    site_doctor.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    site_doctor.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    site_doctor.add_argument("--out-dir", type=Path, help="Site output directory (default: bib/site).")
    site_doctor.add_argument("--include-graphs", dest="include_graphs", action="store_true", default=True)
    site_doctor.add_argument("--no-graphs", dest="include_graphs", action="store_false")
    site_doctor.add_argument("--include-docling", dest="include_docling", action="store_true", default=True)
    site_doctor.add_argument("--no-docling", dest="include_docling", action="store_false")
    site_doctor.add_argument("--include-openalex", dest="include_openalex", action="store_true", default=True)
    site_doctor.add_argument("--no-openalex", dest="include_openalex", action="store_false")

    p_grobid = sub.add_parser("grobid", help="GROBID scholarly structure extraction.")
    grobid_sub = p_grobid.add_subparsers(dest="grobid_cmd", required=True)
    grobid_check = grobid_sub.add_parser("check", help="Check connectivity to the configured GROBID server.")
    grobid_check.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    grobid_check.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    grobid_check.add_argument("--url", help="GROBID server URL (overrides config).")

    grobid_run = grobid_sub.add_parser("run", help="Extract scholarly structure from PDFs via GROBID.")
    grobid_run.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    grobid_run.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    grobid_run_group = grobid_run.add_mutually_exclusive_group(required=True)
    grobid_run_group.add_argument("--key", help="Single citekey (with or without leading @).")
    grobid_run_group.add_argument("--all", action="store_true", help="Run for all citekeys in citekeys.md.")
    grobid_run.add_argument("--force", action="store_true", help="Re-run even if outputs already exist.")

    p_ui = sub.add_parser("ui", help="Serve a local interactive bibliography UI.")
    ui_sub = p_ui.add_subparsers(dest="ui_cmd", required=True)
    ui_serve = ui_sub.add_parser("serve", help="Serve the local FastAPI/React/Cytoscape UI.")
    ui_serve.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ui_serve.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    ui_serve.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1).")
    ui_serve.add_argument("--port", type=int, default=8010, help="Port to bind (default: 8010).")

    return p


def main(argv: Iterable[str] | None = None) -> None:
    parser = _build_parser()
    if argcomplete is not None:
        argcomplete.autocomplete(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "init":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        res = init_bib_scaffold(repo_root, force=args.force)
        if res.files_written:
            rels = "\n".join(str(p.relative_to(res.root)) for p in res.files_written)
            print(f"Wrote {len(res.files_written)} file(s):\n{rels}")
        else:
            print("No files written (already initialized).")
        return

    if args.command == "citekeys":
        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        # Resolve citekeys.md path: explicit --path wins; else try config; else default.
        if getattr(args, "path", None) is not None:
            citekeys_path = (repo_root / args.path).resolve() if not args.path.is_absolute() else args.path
        else:
            cfg_file = default_config_path(root=repo_root)
            try:
                cfg = load_biblio_config(cfg_file, root=repo_root)
                citekeys_path = cfg.citekeys_path
            except Exception:
                citekeys_path = (repo_root / "bib" / "config" / "citekeys.md").resolve()

        if args.citekeys_cmd == "list":
            keys = load_citekeys_md(citekeys_path) if citekeys_path.exists() else []
            for k in keys:
                print(f"@{k}")
            return
        if args.citekeys_cmd == "add":
            keys = add_citekeys_md(citekeys_path, args.keys)
            print(f"[OK] citekeys={len(keys)} path={citekeys_path}")
            return
        if args.citekeys_cmd == "remove":
            keys = remove_citekeys_md(citekeys_path, args.keys)
            print(f"[OK] citekeys={len(keys)} path={citekeys_path}")
            return
        if args.citekeys_cmd == "status":
            cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
            cfg = load_biblio_config(cfg_path, root=repo_root)
            model = _build_site_model(
                cfg,
                BiblioSiteOptions(
                    out_dir=default_site_out_dir(root=repo_root),
                    include_graphs=True,
                    include_docling=True,
                    include_openalex=True,
                ),
            )
            manifest = [
                {
                    "citekey": paper["citekey"],
                    "title": paper["title"],
                    "configured": bool(paper["configured"]),
                    "source_bibs": list(paper["source_bibs"]),
                    "pdf": bool(paper["artifacts"]["pdf"]["exists"]),
                    "docling": bool(paper["artifacts"]["docling_md"]["exists"]),
                    "openalex": bool(paper["artifacts"]["openalex"]["exists"]),
                    "suggest_add": not bool(paper["configured"]),
                }
                for paper in model["papers"]
            ]
            if args.json:
                print(json.dumps(manifest, indent=2, sort_keys=True))
            else:
                for item in manifest:
                    flags = []
                    flags.append("configured" if item["configured"] else "candidate")
                    if item["pdf"]:
                        flags.append("pdf")
                    if item["docling"]:
                        flags.append("docling")
                    if item["openalex"]:
                        flags.append("openalex")
                    print(f"{item['citekey']}\t{','.join(flags)}\t{item['title']}")
            return

    if args.command == "ingest":
        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        cfg = None
        if getattr(args, "config", None):
            cfg_path = (repo_root / args.config).resolve() if not args.config.is_absolute() else args.config.resolve()
            cfg = load_biblio_config(cfg_path, root=repo_root)
        else:
            cfg = load_biblio_config(repo_root / "bib" / "config" / "biblio.yml", root=repo_root)
        out_bib = (
            (repo_root / args.out_bib).resolve() if getattr(args, "out_bib", None) and not args.out_bib.is_absolute()
            else (args.out_bib.resolve() if getattr(args, "out_bib", None) else default_import_bib_path(repo_root))
        )
        result, bibtex_text = ingest_file(
            repo_root=repo_root,
            source_type=str(args.ingest_cmd),
            input_path=getattr(args, "input_path", None),
            input_paths=getattr(args, "input_paths", None),
            output_path=out_bib,
            dry_run=bool(args.dry_run),
            stdout=bool(args.stdout),
            pdf_root=cfg.pdf_root if cfg is not None else None,
            pdf_pattern=cfg.pdf_pattern if cfg is not None else "{citekey}/{citekey}.pdf",
            doi_api_base=cfg.openalex.api_base if cfg is not None else "https://api.openalex.org",
            doi_mailto=cfg.openalex.mailto if cfg is not None else None,
        )
        suffix = " (dry-run)" if result.dry_run else ""
        print(
            f"[OK] source_type={result.source_type} parsed={result.parsed} emitted={result.emitted} output={result.output_path}{suffix}",
            file=sys.stderr if args.stdout else sys.stdout,
        )
        if result.citekeys:
            citekeys_line = ",".join(result.citekeys)
            print(f"[OK] citekeys={citekeys_line}", file=sys.stderr if args.stdout else sys.stdout)
        if args.stdout:
            print(bibtex_text, end="")
        return
    if args.command == "docling":
        if args.doc_cmd != "run":
            raise SystemExit(2)
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)

        if args.screen:
            docling_args: list[str] = []
            if args.config:
                docling_args += ["--config", str(args.config)]
            if args.force:
                docling_args += ["--force"]
            if args.all:
                docling_args += ["--all"]
            else:
                docling_args += ["--key", str(args.key)]

            bash_cmd = _build_screen_bash_command(
                repo_root=repo_root,
                python_exe=sys.executable,
                docling_args=docling_args,
            )
            _launch_screen_session(name=str(args.screen_name), bash_cmd=bash_cmd)
            print(f"[OK] started screen session: {args.screen_name}", flush=True)
            print(f"Attach:  screen -r {args.screen_name}", flush=True)
            print("Detach:  Ctrl-A then D", flush=True)
            print("List:    screen -ls", flush=True)
            return

        if args.all:
            try:
                keys = load_citekeys_md(cfg.citekeys_path)
            except FileNotFoundError:
                print(f"Missing citekeys file: {cfg.citekeys_path}", file=sys.stderr)
                raise SystemExit(2)
            if not keys:
                print(f"No citekeys found in {cfg.citekeys_path}", file=sys.stderr)
                raise SystemExit(2)
            cmd_preview = " ".join(cfg.docling_cmd)
            print(
                f"[INFO] repo_root={repo_root} config={cfg_path} keys={len(keys)} docling_cmd={cmd_preview}",
                file=sys.stderr,
                flush=True,
            )
            failures = 0
            total = len(keys)
            for idx, key in enumerate(keys, start=1):
                try:
                    print(f"[RUN {idx}/{total}] {key}", file=sys.stderr, flush=True)
                    out = run_docling_for_key(cfg, key, force=args.force)
                except Exception as e:
                    failures += 1
                    print(f"[FAIL {idx}/{total}] {key}: {e}", file=sys.stderr)
                else:
                    print(f"[OK {idx}/{total}] {key}: {out.md_path}", flush=True)
            raise SystemExit(0 if failures == 0 else 1)
        else:
            cmd_preview = " ".join(cfg.docling_cmd)
            print(
                f"[INFO] repo_root={repo_root} config={cfg_path} docling_cmd={cmd_preview}",
                file=sys.stderr,
                flush=True,
            )
            print(f"[RUN] {args.key.lstrip('@')}", file=sys.stderr, flush=True)
            out = run_docling_for_key(cfg, args.key, force=args.force)
            print(f"[OK] {args.key.lstrip('@')}: {out.md_path}")
            return

    if args.command == "bibtex":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        if args.bibtex_cmd == "merge":
            n_sources, n_entries = merge_srcbib(cfg.bibtex_merge, dry_run=args.dry_run)
            suffix = " (dry-run)" if args.dry_run else ""
            print(f"[OK] merged sources={n_sources} entries={n_entries} -> {cfg.bibtex_merge.out_bib}{suffix}")
            if cfg.bibtex_merge.duplicates_log.exists() and not args.dry_run:
                print(f"[WARN] duplicates log: {cfg.bibtex_merge.duplicates_log}", file=sys.stderr)
            return
        if args.bibtex_cmd == "fetch-pdfs":
            counts = fetch_pdfs(cfg.pdf_fetch, dry_run=args.dry_run, force=args.force)
            suffix = " (dry-run)" if args.dry_run else ""
            print(
                f"[OK] sources={counts['sources']} linked={counts['linked']} skipped={counts['skipped']} missing={counts['missing']}{suffix}"
            )
            if not args.dry_run and counts["missing"]:
                print(f"[WARN] missing log: {cfg.pdf_fetch.missing_log}", file=sys.stderr)
            return
        raise SystemExit(2)

    if args.command == "openalex":
        if args.openalex_cmd != "resolve":
            raise SystemExit(2)
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)

        src_dir = args.src_dir or (repo_root / "bib" / "srcbib")
        src_dir = (repo_root / src_dir).resolve() if not src_dir.is_absolute() else src_dir

        out_default = repo_root / "bib" / "derivatives" / "openalex" / f"resolved.{args.format}"
        out_path = args.out or out_default
        out_path = (repo_root / out_path).resolve() if not out_path.is_absolute() else out_path

        opts = ResolveOptions(
            prefer_doi=bool(args.prefer_doi),
            fallback_title_search=bool(args.fallback_title_search),
            per_page=int(cfg.openalex_client.per_page),
            strict=bool(args.strict),
            force=bool(args.force),
        )

        print(
            f"[INFO] repo_root={repo_root} src_dir={src_dir} src_glob={args.src_glob} out={out_path} format={args.format}",
            file=sys.stderr,
            flush=True,
        )
        print(
            f"[INFO] openalex.base_url={cfg.openalex_client.base_url} cache_dir={cfg.openalex_cache.root} select={','.join(cfg.openalex_client.select)}",
            file=sys.stderr,
            flush=True,
        )

        counts = resolve_srcbib_to_openalex(
            cfg=cfg.openalex_client,
            cache=cfg.openalex_cache,
            src_dir=src_dir,
            src_glob=str(args.src_glob),
            out_path=out_path,
            out_format=str(args.format),
            limit=args.limit,
            opts=opts,
        )
        print(
            f"[OK] wrote {out_path} total={counts['total']} resolved={counts['resolved']} unresolved={counts['unresolved']} errors={counts['errors']}"
        )
        return

    if args.command == "rag":
        if args.rag_cmd != "sync":
            raise SystemExit(2)
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        result = sync_biblio_rag_config(
            repo_root,
            config_path=args.config,
            force_init=bool(args.force_init),
        )
        print(f"[OK] config={result.config_path}")
        state = "created" if result.created else ("initialized" if result.initialized else "updated")
        print(f"[OK] action={state}")
        print(
            f"[OK] added={','.join(result.added) or '-'} updated={','.join(result.updated) or '-'} removed={','.join(result.removed) or '-'}"
        )
        print(f"[NEXT] {result.follow_up_cmd}")
        return

    if args.command == "add":
        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        if args.add_cmd == "doi":
            result = add_openalex_work_to_bib(
                cfg=cfg.openalex_client,
                cache=cfg.openalex_cache,
                repo_root=repo_root,
                doi=str(args.doi),
            )
        elif args.add_cmd == "openalex":
            result = add_openalex_work_to_bib(
                cfg=cfg.openalex_client,
                cache=cfg.openalex_cache,
                repo_root=repo_root,
                openalex_id=str(args.openalex_id),
            )
        else:
            raise SystemExit(2)
        print(
            f"[OK] citekey={result.citekey} openalex_id={result.openalex_id or '-'} doi={result.doi or '-'} "
            f"srcbib={result.output_path} citekeys={result.citekeys_path}"
        )
        return

    if args.command == "graph":
        if args.graph_cmd != "expand":
            raise SystemExit(2)
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / "bib" / "config" / "biblio.yml").resolve()
        cfg = load_biblio_config(cfg_path, root=repo_root)
        input_path = args.input_path or (repo_root / "bib" / "derivatives" / "openalex" / "resolved.jsonl")
        input_path = (repo_root / input_path).resolve() if not input_path.is_absolute() else input_path
        output_path = args.output_path or (repo_root / "bib" / "derivatives" / "openalex" / "graph_candidates.json")
        output_path = (repo_root / output_path).resolve() if not output_path.is_absolute() else output_path
        records = load_openalex_seed_records(input_path)
        result = expand_openalex_reference_graph(
            cfg=cfg.openalex_client,
            cache=cfg.openalex_cache,
            records=records,
            out_path=output_path,
            direction=str(args.direction),
            force=bool(args.force),
        )
        print(
            f"[OK] seeds={result.total_inputs} seeds_with_openalex={result.seeds_with_openalex} "
            f"direction={args.direction} candidates={result.candidates} -> {result.output_path}"
        )
        return

    if args.command == "grobid":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        if args.grobid_cmd == "check":
            from .config import GrobidConfig
            grobid_cfg = cfg.grobid
            if args.url:
                grobid_cfg = GrobidConfig(
                    url=args.url,
                    installation_path=grobid_cfg.installation_path,
                    timeout_seconds=grobid_cfg.timeout_seconds,
                    consolidate_header=grobid_cfg.consolidate_header,
                    consolidate_citations=grobid_cfg.consolidate_citations,
                )
            result = check_grobid_server(grobid_cfg)
            status = "[OK]" if result.ok else "[FAIL]"
            print(f"{status} url={result.url} latency={result.latency_ms}ms message={result.message}")
            if not result.ok:
                raise SystemExit(1)
        elif args.grobid_cmd == "run":
            if args.all:
                try:
                    keys = load_citekeys_md(cfg.citekeys_path)
                except FileNotFoundError:
                    print(f"Missing citekeys file: {cfg.citekeys_path}", file=sys.stderr)
                    raise SystemExit(2)
                if not keys:
                    print(f"No citekeys found in {cfg.citekeys_path}", file=sys.stderr)
                    raise SystemExit(2)
                print(
                    f"[INFO] repo_root={repo_root} keys={len(keys)} grobid_url={cfg.grobid.url}",
                    file=sys.stderr,
                    flush=True,
                )
                failures = 0
                for idx, key in enumerate(keys, start=1):
                    try:
                        print(f"[RUN {idx}/{len(keys)}] {key}", file=sys.stderr, flush=True)
                        out = run_grobid_for_key(cfg, key, force=args.force)
                    except Exception as e:
                        failures += 1
                        print(f"[FAIL {idx}/{len(keys)}] {key}: {e}", file=sys.stderr)
                    else:
                        print(f"[OK {idx}/{len(keys)}] {key}: refs={out.references_path}", flush=True)
                raise SystemExit(0 if failures == 0 else 1)
            else:
                print(f"[RUN] {args.key.lstrip('@')}", file=sys.stderr, flush=True)
                out = run_grobid_for_key(cfg, args.key, force=args.force)
                print(f"[OK] {args.key.lstrip('@')}: refs={out.references_path}")
        return

    if args.command == "site":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        out_dir = (repo_root / args.out_dir).resolve() if getattr(args, "out_dir", None) and not args.out_dir.is_absolute() else (
            args.out_dir.resolve() if getattr(args, "out_dir", None) else default_site_out_dir(root=repo_root)
        )
        site_options = BiblioSiteOptions(
            out_dir=out_dir,
            include_graphs=bool(getattr(args, "include_graphs", True)),
            include_docling=bool(getattr(args, "include_docling", True)),
            include_openalex=bool(getattr(args, "include_openalex", True)),
        )

        if args.site_cmd == "serve":
            serve_biblio_site(out_dir, port=int(args.port))
            return
        if args.site_cmd == "clean":
            removed = clean_biblio_site(repo_root, out_dir)
            print(f"[OK] cleaned {removed}")
            return

        cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)

        if args.site_cmd == "doctor":
            report = doctor_biblio_site(cfg, options=site_options, config_path=cfg_path)
            print(f"[OK] config={report.config_path}")
            print(f"[OK] out_dir={report.out_dir}")
            print(
                f"[OK] papers={report.papers_total} configured={report.configured_citekeys} "
                f"srcbib={report.source_bib_entries} pdf={report.papers_with_pdf} "
                f"docling={report.papers_with_docling} openalex={report.papers_with_openalex}"
            )
            print(
                f"[OK] missing_pdf={report.missing_pdf} missing_docling={report.missing_docling} "
                f"missing_openalex={report.missing_openalex} orphan_docling={len(report.orphan_docling)}"
            )
            for warning in report.warnings:
                print(f"[WARN] {warning}")
            return

        if args.site_cmd == "build":
            result = build_biblio_site(cfg, options=site_options, force=bool(args.force), config_path=cfg_path)
            print(f"[OK] out_dir={result.out_dir}")
            print(
                f"[OK] papers={result.papers_total} pages={result.pages_written} "
                f"data_files={result.data_files_written}"
            )
            print(
                f"[OK] missing_pdf={result.doctor.missing_pdf} missing_docling={result.doctor.missing_docling} "
                f"missing_openalex={result.doctor.missing_openalex}"
            )
            print(f"[NEXT] biblio site serve --root {repo_root} --out-dir {result.out_dir}")
            return

    if args.command == "ui":
        if args.ui_cmd != "serve":
            raise SystemExit(2)
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        serve_ui_app(cfg, host=str(args.host), port=int(args.port))
        return

    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover
    main()
