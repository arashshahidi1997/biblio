from __future__ import annotations

import argparse
import os
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
from .bibtex_export import export_bibtex
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
from .grobid import check_grobid_server, run_grobid_for_key, run_grobid_match
from .fetch_queue import add_to_queue, load_queue, remove_from_queue
from .library import load_library, update_entry
from .pool import ingest_inbox, link_project, sync_pool_symlinks
from .pool_serve import serve_pool
from .ref_md import run_ref_md_for_key

try:
    import argcomplete
except Exception:  # pragma: no cover
    argcomplete = None


def _fmt_duration(seconds: float | None) -> str:
    """Format seconds as e.g. '1h23m' or '4m12s'."""
    if seconds is None or seconds < 0:
        return "?"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _build_screen_bash_command(
    *,
    repo_root: Path,
    python_exe: str,
    docling_args: list[str],
    subcmd: str = "run",
) -> str:
    cmd = [
        python_exe,
        "-m",
        "biblio.cli",
        "docling",
        subcmd,
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
        p_in.add_argument("--force", action="store_true", help="Re-ingest even if DOI already exists in library.")
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
    p_pdf.add_argument("--force", action="store_true", help="Re-ingest even if DOI already exists in library.")

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

    p_batch = doc_sub.add_parser("batch", help="Batch-process all pending citekeys (PDFs without docling output).")
    p_batch.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_batch.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    p_batch.add_argument("--concurrency", type=int, default=1, help="Max parallel docling jobs (default: 1). Use with care on shared HPC nodes.")
    p_batch.add_argument("--filter", dest="filter_glob", default=None, help="fnmatch glob to filter citekeys (e.g. 'smith*').")
    p_batch.add_argument("--force", action="store_true", help="Re-run Docling even if outputs exist.")
    p_batch.add_argument(
        "--screen",
        action="store_true",
        help="Run in a detached GNU screen session (background).",
    )
    p_batch.add_argument(
        "--screen-name",
        default="docling-batch",
        help="Screen session name when using --screen (default: docling-batch).",
    )

    p_bt = sub.add_parser("bibtex", help="Work with BibTeX sources (srcbib merge).")
    bt_sub = p_bt.add_subparsers(dest="bibtex_cmd", required=True)
    bt_merge = bt_sub.add_parser("merge", help="Merge bib/srcbib/*.bib into a single main bib file.")
    bt_merge.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    bt_merge.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    bt_merge.add_argument("--dry-run", action="store_true", help="Parse and report, but do not write output.")

    bt_export = bt_sub.add_parser("export", help="Export BibTeX entries for selected citekeys.")
    bt_export.add_argument("citekeys", nargs="*", help="Citekeys to export. Omit to use --all or --status.")
    bt_export.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    bt_export.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    bt_export.add_argument("--all", action="store_true", dest="export_all", help="Export all entries from merged bib.")
    bt_export.add_argument("--status", type=str, default=None, help="Export entries with this library status.")
    bt_export.add_argument("--collection", type=str, default=None, help="Export entries from this collection.")
    bt_export.add_argument("-o", "--output", type=Path, default=None, help="Output file (default: stdout).")

    bt_fetch = bt_sub.add_parser(
        "fetch-pdfs",
        help="Copy/symlink PDFs referenced by `file` fields in bib/srcbib/*.bib into bib/articles/...",
    )
    bt_fetch.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    bt_fetch.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    bt_fetch.add_argument("--dry-run", action="store_true")
    bt_fetch.add_argument("--force", action="store_true", help="Overwrite/recopy even if unchanged.")

    bt_fetch_oa = bt_sub.add_parser(
        "fetch-pdfs-oa",
        help="Download PDFs via open-access cascade (pool → OpenAlex → Unpaywall → EZProxy).",
    )
    bt_fetch_oa.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    bt_fetch_oa.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    bt_fetch_oa.add_argument("--force", action="store_true", help="Download even if PDF already exists.")
    bt_fetch_oa.add_argument("--citekeys", nargs="*", default=None, help="Only fetch these citekeys (default: all).")

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
    add_orcid = add_sub.add_parser("orcid", help="Add papers by author ORCID via OpenAlex.")
    add_orcid.add_argument("orcid", help="ORCID identifier (e.g. 0000-0002-1234-5678).")
    add_orcid.add_argument("--since", type=int, default=None, help="Only include works from this year onward.")
    add_orcid.add_argument("--min-citations", type=int, default=None, help="Only include works with at least N citations.")
    add_orcid.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    add_orcid.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")

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

    grobid_match = grobid_sub.add_parser("match", help="Match GROBID references against the local corpus.")
    grobid_match.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    grobid_match.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")

    p_summarize = sub.add_parser("summarize", help="Generate structured paper summaries via LLM.")
    p_summarize.add_argument("key", nargs="?", help="Single citekey (with or without leading @).")
    p_summarize.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_summarize.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    p_summarize.add_argument("--prompt-only", action="store_true", help="Print assembled prompt to stdout (no LLM call).")
    p_summarize.add_argument("--status", help="Batch mode: summarize all papers with this library status (e.g. unread).")
    p_summarize.add_argument("--force", action="store_true", help="Regenerate existing summaries.")
    p_summarize.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model to use.")

    p_present = sub.add_parser("present", help="Generate Marp slide decks from paper context.")
    p_present.add_argument("key", help="Citekey (with or without leading @).")
    p_present.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_present.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    p_present.add_argument("--template", choices=["journal-club", "conference-talk", "lab-meeting"],
                           default="journal-club", help="Slide template (default: journal-club).")
    p_present.add_argument("--prompt-only", action="store_true", help="Print assembled prompt to stdout (no LLM call).")
    p_present.add_argument("--force", action="store_true", help="Regenerate existing slides.")
    p_present.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model to use.")
    p_present.add_argument("--export", choices=["html", "pdf", "pptx"], help="Export slides via marp-cli.")

    p_lib = sub.add_parser("library", help="Manage per-paper status, tags, and priority in bib/config/library.yml.")
    lib_sub = p_lib.add_subparsers(dest="library_cmd", required=True)
    lib_list = lib_sub.add_parser("list", help="List all library entries.")
    lib_list.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    lib_list.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    lib_list.add_argument("--status", help="Filter by status.")
    lib_list.add_argument("--tag", help="Filter by tag.")
    lib_list.add_argument("--json", action="store_true", help="Emit JSON.")
    lib_set = lib_sub.add_parser("set", help="Set status, tags, or priority for a paper.")
    lib_set.add_argument("key", help="Citekey (with or without leading @).")
    lib_set.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    lib_set.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    lib_set.add_argument("--status", help="Status: unread|reading|processed|archived.")
    lib_set.add_argument("--tags", help="Comma-separated tags (replaces existing tags).")
    lib_set.add_argument("--priority", help="Priority: low|normal|high.")

    lib_lint = lib_sub.add_parser("lint", help="Scan library tags for non-vocabulary, duplicate, or inconsistent tags.")
    lib_lint.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    lib_lint.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    lib_lint.add_argument("--json", action="store_true", help="Emit JSON output.")

    lib_dedup = lib_sub.add_parser("dedup", help="Detect duplicate papers by DOI, title similarity, or OpenAlex ID.")
    lib_dedup.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    lib_dedup.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    lib_dedup.add_argument("--json", action="store_true", help="Emit JSON output.")

    lib_autotag = lib_sub.add_parser("autotag", help="Auto-tag papers via LLM classification and/or reference propagation.")
    lib_autotag.add_argument("key", nargs="?", help="Single citekey (with or without leading @).")
    lib_autotag.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    lib_autotag.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    lib_at_group = lib_autotag.add_mutually_exclusive_group()
    lib_at_group.add_argument("--all", action="store_true", help="Process all papers in the library.")
    lib_at_group.add_argument("--untagged", action="store_true", help="Process only papers with no tags.")
    lib_autotag.add_argument("--tier", choices=["llm", "propagate", "all"], default="all", help="Which tagging tier(s) to run (default: all).")
    lib_autotag.add_argument("--force", action="store_true", help="Re-run even if cached results exist.")
    lib_autotag.add_argument("--model", default="claude-haiku-4-5-20251001", help="Anthropic model for LLM tier.")
    lib_autotag.add_argument("--threshold", type=int, default=3, help="Minimum cited-paper count for propagation (default: 3).")
    lib_autotag.add_argument("--json", action="store_true", help="Emit JSON output.")

    p_col = sub.add_parser("collection", help="Manage paper collections (manual and smart/query-driven).")
    col_sub = p_col.add_subparsers(dest="collection_cmd", required=True)

    col_create = col_sub.add_parser("create", help="Create a collection (manual or smart).")
    col_create.add_argument("name", help="Collection name.")
    col_create.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    col_create.add_argument("--config", type=Path, help="Path to biblio.yml.")
    col_create.add_argument("--smart", metavar="QUERY", help="Query string for a smart (dynamic) collection.")
    col_create.add_argument("--description", help="Optional description.")

    col_list = col_sub.add_parser("list", help="List all collections with membership counts.")
    col_list.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    col_list.add_argument("--config", type=Path, help="Path to biblio.yml.")
    col_list.add_argument("--json", action="store_true", help="Emit JSON.")

    col_show = col_sub.add_parser("show", help="Show collection details and members.")
    col_show.add_argument("name", help="Collection name.")
    col_show.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    col_show.add_argument("--config", type=Path, help="Path to biblio.yml.")
    col_show.add_argument("--json", action="store_true", help="Emit JSON.")

    col_edit = col_sub.add_parser("edit-query", help="Update the query of a smart collection.")
    col_edit.add_argument("name", help="Collection name.")
    col_edit.add_argument("query", help="New query string.")
    col_edit.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    col_edit.add_argument("--config", type=Path, help="Path to biblio.yml.")

    p_ref_md = sub.add_parser("ref-md", help="Produce reference-resolved markdown from docling+GROBID outputs.")
    ref_md_sub = p_ref_md.add_subparsers(dest="ref_md_cmd", required=True)
    ref_md_run = ref_md_sub.add_parser("run", help="Resolve in-text citations for one key or all keys.")
    ref_md_run.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ref_md_run.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    ref_md_run_group = ref_md_run.add_mutually_exclusive_group(required=True)
    ref_md_run_group.add_argument("--key", help="Single citekey (with or without leading @).")
    ref_md_run_group.add_argument("--all", action="store_true", help="Run for all citekeys in citekeys.md.")
    ref_md_run.add_argument("--force", action="store_true", help="Re-run even if outputs already exist.")

    p_q = sub.add_parser("queue", help="Manage the needs-PDF queue.")
    q_sub = p_q.add_subparsers(dest="queue_cmd", required=True)
    q_list = q_sub.add_parser("list", help="List queued papers needing PDFs.")
    q_list.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    q_list.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    q_open = q_sub.add_parser("open", help="Open a queued paper's URL in the default browser.")
    q_open.add_argument("key", help="Citekey to open (with or without leading @).")
    q_open.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    q_open.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    q_drain = q_sub.add_parser("drain", help="Re-attempt OA fetch for all queued papers.")
    q_drain.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    q_drain.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    q_drain.add_argument("--force", action="store_true", help="Download even if PDF already exists locally.")
    q_remove = q_sub.add_parser("remove", help="Remove a citekey from the queue.")
    q_remove.add_argument("key", help="Citekey to remove (with or without leading @).")
    q_remove.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    q_remove.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")

    p_pool = sub.add_parser("pool", help="Manage the shared PDF pool workspace.")
    pool_sub = p_pool.add_subparsers(dest="pool_cmd", required=True)

    _pool_args = [
        ("--pool", dict(type=Path, help="Pool workspace root (default: read from project config).")),
        ("--root", dict(type=Path, help="Repository root (default: auto-detect from cwd).")),
        ("--config", dict(type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")),
    ]

    pool_ingest = pool_sub.add_parser("ingest", help="Ingest PDFs from an inbox directory into the pool.")
    pool_ingest.add_argument("inbox_dir", type=Path, help="Directory containing PDF files to ingest.")
    for flag, kwargs in _pool_args:
        pool_ingest.add_argument(flag, **kwargs)
    pool_ingest.add_argument("--dry-run", action="store_true", help="Report what would happen without writing.")
    pool_ingest.add_argument("--move", action="store_true", help="Remove PDFs from inbox after ingesting.")

    pool_watch = pool_sub.add_parser("watch", help="Watch an inbox directory and ingest new PDFs continuously.")
    pool_watch.add_argument("inbox_dir", type=Path, help="Directory to watch for new PDFs.")
    for flag, kwargs in _pool_args:
        pool_watch.add_argument(flag, **kwargs)
    pool_watch.add_argument("--interval", type=int, default=30, help="Poll interval in seconds (default: 30).")
    pool_watch.add_argument("--move", action="store_true", help="Remove PDFs from inbox after ingesting.")
    pool_watch.add_argument("--screen", action="store_true", help="Run in a detached GNU screen session.")
    pool_watch.add_argument("--screen-name", default="biblio-pool-watch",
                            help="Screen session name (default: biblio-pool-watch).")

    pool_link = pool_sub.add_parser("link", help="Configure project to use a pool and gitignore bib/articles/.")
    for flag, kwargs in _pool_args:
        pool_link.add_argument(flag, **kwargs)
    pool_link.add_argument("--lab", type=Path,
                           help="Shared lab pool root to prepend to pool.search (checked before personal pool).")
    pool_link.add_argument("--no-sync", action="store_true",
                           help="Skip symlinking existing pool PDFs for active citekeys.")

    pool_serve = pool_sub.add_parser("serve", help="Start a local HTTP server that accepts PDF drops.")
    pool_serve.add_argument("--inbox", type=Path, required=True,
                            help="Directory where dropped PDFs are saved.")
    pool_serve.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1).")
    pool_serve.add_argument("--port", type=int, default=7171, help="Port to bind (default: 7171).")

    pool_promote = pool_sub.add_parser("promote", help="Move project-local papers into a pool.")
    pool_promote.add_argument("--citekeys", nargs="+", help="Citekeys to promote.")
    pool_promote.add_argument("--all-local", action="store_true",
                              help="Promote all local papers not already in pool.")
    for flag, kwargs in _pool_args:
        pool_promote.add_argument(flag, **kwargs)
    pool_promote.add_argument("--dry-run", action="store_true",
                              help="Report what would happen without writing.")

    pool_bm = pool_sub.add_parser("bookmarklet",
                                  help="Print a browser bookmarklet JS snippet for one-click PDF drop.")
    pool_bm.add_argument("--port", type=int, default=7171,
                         help="Pool server port (default: 7171).")

    # --- zotero ---
    p_zotero = sub.add_parser("zotero", help="Zotero integration (pull/push/status).")
    zotero_sub = p_zotero.add_subparsers(dest="zotero_cmd", required=True)

    _zotero_common = [
        ("--root", dict(type=Path, help="Repository root (default: auto-detect from cwd).")),
        ("--config", dict(type=Path, help="Path to biblio.yml.")),
    ]

    zotero_pull = zotero_sub.add_parser("pull", help="Pull items and PDFs from Zotero.")
    for flag, kwargs in _zotero_common:
        zotero_pull.add_argument(flag, **kwargs)
    zotero_pull.add_argument("--collection", help="Zotero collection key to pull (overrides config).")
    zotero_pull.add_argument("--tags", help="Comma-separated tags to filter by.")
    zotero_pull.add_argument("--dry-run", action="store_true",
                             help="Report what would happen without writing.")

    zotero_push = zotero_sub.add_parser("push", help="Push enrichments back to Zotero.")
    for flag, kwargs in _zotero_common:
        zotero_push.add_argument(flag, **kwargs)
    zotero_push.add_argument("--citekeys", help="Comma-separated citekeys to push (default: all synced).")
    zotero_push.add_argument("--tags", action="store_true", default=True,
                             help="Push tags (default: yes).")
    zotero_push.add_argument("--no-tags", action="store_false", dest="tags",
                             help="Skip tag push.")
    zotero_push.add_argument("--notes", action="store_true", default=False,
                             help="Push LLM summaries as Zotero notes.")
    zotero_push.add_argument("--ids", action="store_true", default=True,
                             help="Push DOI/OpenAlex IDs (default: yes).")
    zotero_push.add_argument("--no-ids", action="store_false", dest="ids",
                             help="Skip ID push.")
    zotero_push.add_argument("--force", action="store_true",
                             help="Push even if Zotero item was modified since last sync.")
    zotero_push.add_argument("--dry-run", action="store_true",
                             help="Report what would happen without writing.")

    zotero_status = zotero_sub.add_parser("status", help="Show Zotero sync state.")
    for flag, kwargs in _zotero_common:
        zotero_status.add_argument(flag, **kwargs)

    p_profile = sub.add_parser("profile", help="Manage user-level biblio profiles.")
    profile_sub = p_profile.add_subparsers(dest="profile_cmd", required=True)

    profile_sub.add_parser("list", help="List available bundled profiles.")

    profile_use = profile_sub.add_parser("use", help="Apply a profile to ~/.config/biblio/config.yml.")
    profile_use.add_argument("name", help="Profile name (e.g. sirota).")
    profile_use.add_argument("--storage", type=Path,
                             help="Personal storage root (e.g. /storage2/username). "
                                  "Auto-detected if omitted.")
    profile_use.add_argument("--yes", action="store_true",
                             help="Accept detected storage path without prompting.")

    profile_sub.add_parser("show", help="Print current ~/.config/biblio/config.yml.")

    p_auth = sub.add_parser("auth", help="Manage authentication for external services.")
    auth_sub = p_auth.add_subparsers(dest="auth_cmd", required=True)

    auth_ez = auth_sub.add_parser(
        "ezproxy",
        help="Set up EZProxy session cookie for institutional PDF access.",
    )
    auth_ez.add_argument("--open", action="store_true", default=True,
                         help="Open EZProxy login page in browser (default: yes).")
    auth_ez.add_argument("--no-open", action="store_true",
                         help="Skip opening browser.")
    auth_ez.add_argument("--login", action="store_true",
                         help="Log in with institutional credentials (Shibboleth SAML). "
                              "No browser needed — works over plain SSH.")
    auth_ez.add_argument("--push", metavar="HOST",
                         help="Push cookies from local browser to a remote host via SSH "
                              "(e.g. --push gamma2). Like ssh-copy-id for EZProxy.")
    auth_ez.add_argument("--export", action="store_true",
                         help="Print cookie string to stdout (for piping).")
    auth_ez.add_argument("--import", dest="import_stdin", action="store_true",
                         help="Read cookie string from stdin (for piping).")

    p_ui = sub.add_parser("ui", help="Serve a local interactive bibliography UI.")
    ui_sub = p_ui.add_subparsers(dest="ui_cmd", required=True)
    ui_serve = ui_sub.add_parser("serve", help="Serve the local FastAPI/React/Cytoscape UI.")
    ui_serve.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    ui_serve.add_argument("--config", type=Path, help="Path to biblio.yml (default: bib/config/biblio.yml).")
    ui_serve.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1).")
    ui_serve.add_argument("--port", type=int, default=8010, help="Port to bind (default: 8010).")

    # ── concepts ──────────────────────────────────────────────────────────
    p_concepts = sub.add_parser("concepts", help="Extract and search key concepts from papers.")
    concepts_sub = p_concepts.add_subparsers(dest="concepts_cmd", required=True)

    concepts_extract = concepts_sub.add_parser("extract", help="Extract concepts from a paper.")
    concepts_extract.add_argument("key", nargs="?", help="Single citekey (with or without leading @).")
    concepts_extract.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    concepts_extract.add_argument("--config", type=Path, help="Path to biblio.yml.")
    concepts_extract.add_argument("--all", action="store_true", help="Process all papers in the library.")
    concepts_extract.add_argument("--prompt-only", action="store_true", help="Print assembled prompt (no LLM call).")
    concepts_extract.add_argument("--force", action="store_true", help="Regenerate existing concepts.")
    concepts_extract.add_argument("--model", default="claude-haiku-4-5-20251001", help="Anthropic model to use.")
    concepts_extract.add_argument("--json", action="store_true", help="Emit JSON output.")

    concepts_index = concepts_sub.add_parser("index", help="Build cross-paper concept index.")
    concepts_index.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    concepts_index.add_argument("--json", action="store_true", help="Emit JSON output.")

    concepts_search = concepts_sub.add_parser("search", help="Search concepts across papers.")
    concepts_search.add_argument("query", help="Concept to search for.")
    concepts_search.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    concepts_search.add_argument("--json", action="store_true", help="Emit JSON output.")

    # ── compare ───────────────────────────────────────────────────────────
    p_compare = sub.add_parser("compare", help="Generate comparison tables for multiple papers.")
    p_compare.add_argument("keys", nargs="+", help="Two or more citekeys to compare.")
    p_compare.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_compare.add_argument("--config", type=Path, help="Path to biblio.yml.")
    p_compare.add_argument("--dimensions", help="Comma-separated dimensions (default: method,dataset,metrics,key findings,limitations).")
    p_compare.add_argument("--prompt-only", action="store_true", help="Print assembled prompt (no LLM call).")
    p_compare.add_argument("--force", action="store_true", help="Regenerate existing comparison.")
    p_compare.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model to use.")

    # ── reading-list ──────────────────────────────────────────────────────
    p_rl = sub.add_parser("reading-list", help="Curate a reading list for a research question.")
    p_rl.add_argument("question", help="Research question to find papers for.")
    p_rl.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_rl.add_argument("--config", type=Path, help="Path to biblio.yml.")
    p_rl.add_argument("--count", type=int, default=5, help="Number of papers to recommend (default: 5).")
    p_rl.add_argument("--prompt-only", action="store_true", help="Print assembled prompt (no LLM call).")
    p_rl.add_argument("--model", default="claude-haiku-4-5-20251001", help="Anthropic model to use.")
    p_rl.add_argument("--json", action="store_true", help="Emit JSON output.")

    # ── cite-draft ────────────────────────────────────────────────────────
    p_cd = sub.add_parser("cite-draft", help="Draft a citation paragraph grounding a claim in indexed papers.")
    p_cd.add_argument("text", help="Claim or section heading to ground with citations.")
    p_cd.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_cd.add_argument("--style", choices=["latex", "pandoc"], default="latex", help="Citation style (default: latex).")
    p_cd.add_argument("--max-refs", type=int, default=5, help="Maximum number of references (default: 5).")
    p_cd.add_argument("--prompt-only", action="store_true", help="Print assembled prompt (no LLM call).")
    p_cd.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model to use.")
    p_cd.add_argument("--json", action="store_true", help="Emit JSON output.")

    # ── review ────────────────────────────────────────────────────────────
    p_rev = sub.add_parser("review", help="Literature review synthesis and planning.")
    p_rev.add_argument("question", help="Research question for the review.")
    p_rev.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p_rev.add_argument("--seeds", help="Comma-separated seed citekeys for review planning.")
    p_rev.add_argument("--style", choices=["latex", "pandoc"], default="latex", help="Citation style (default: latex).")
    p_rev.add_argument("--prompt-only", action="store_true", help="Print assembled prompt (no LLM call).")
    p_rev.add_argument("--model", default="claude-sonnet-4-20250514", help="Anthropic model to use.")
    p_rev.add_argument("--json", action="store_true", help="Emit JSON output.")

    return p


def _bookmarklet_js(port: int) -> str:
    """Return a javascript: URI that drops the current page's PDF to the pool server."""
    js = (
        "(function(){"
        "var doi=document.querySelector('meta[name=\"citation_doi\"]')?.content"
        "||document.querySelector('meta[name=\"dc.identifier\"]')?.content"
        "||location.href.match(/10\\.\\d{4,}\\/[^\\s\"<>]+/)?.[0];"
        "var pdf=document.querySelector('a[href$=\".pdf\"]')"
        "||document.querySelector('[data-track-action*=\"pdf\"]')"
        "||document.querySelector('a[class*=\"download\"]');"
        f"var srv='http://127.0.0.1:{port}';"
        "if(!pdf&&!doi){{alert('biblio: no DOI or PDF link found on this page');return;}}"
        "if(pdf){{"
        "fetch(pdf.href,{{credentials:'include'}})"
        ".then(function(r){{return r.blob();}})"
        ".then(function(b){{"
        "var fd=new FormData();"
        "fd.append('file',b,pdf.href.split('/').pop()||'paper.pdf');"
        "if(doi)fd.append('doi',doi);"
        "fd.append('url',location.href);"
        "return fetch(srv+'/drop',{{method:'POST',body:fd}});"
        "}})"
        ".then(function(r){{return r.json();}})"
        ".then(function(d){{alert('biblio: '+JSON.stringify(d));}})"
        ".catch(function(e){{alert('biblio error: '+e);}});"
        "}}else{{"
        "var fd=new FormData();"
        "fd.append('doi',doi);"
        "fd.append('url',location.href);"
        "fetch(srv+'/drop-doi',{{method:'POST',body:fd}})"
        ".then(function(r){{return r.json();}})"
        ".then(function(d){{alert('biblio: '+JSON.stringify(d));}})"
        ".catch(function(e){{alert('biblio error: '+e);}});"
        "}}"
        "})();"
    )
    import urllib.parse
    return "javascript:" + urllib.parse.quote(js, safe="")


def _extract_browser_cookies(proxy_base: str) -> str | None:
    """Try to extract EZProxy cookies from Firefox or Chromium cookie stores.

    Returns cookie string (name1=value1; name2=value2) or None if not found.
    """
    import sqlite3
    import tempfile
    from pathlib import Path
    from urllib.parse import urlparse

    host = urlparse(proxy_base).hostname or proxy_base
    # Match the domain and subdomains (e.g. .emedien.ub.uni-muenchen.de)
    host_patterns = [host, f".{host}"]

    # Known browser cookie store locations
    home = Path.home()
    candidates: list[Path] = []
    # Firefox
    for profile_dir in sorted(home.glob(".mozilla/firefox/*/"), reverse=True):
        db = profile_dir / "cookies.sqlite"
        if db.exists():
            candidates.append(db)
    # Chromium / Chrome (cookies are encrypted on Linux, so this only works
    # on systems where the keyring is accessible or cookies are unencrypted)
    for chrome_dir in [
        home / ".config" / "google-chrome" / "Default" / "Cookies",
        home / ".config" / "chromium" / "Default" / "Cookies",
    ]:
        if chrome_dir.exists():
            candidates.append(chrome_dir)

    for db_path in candidates:
        try:
            # Copy DB to temp file to avoid locking the browser's DB
            tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
            tmp.close()
            import shutil
            shutil.copy2(db_path, tmp.name)

            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row

            # Firefox uses moz_cookies
            try:
                rows = conn.execute(
                    "SELECT name, value FROM moz_cookies WHERE host IN (?, ?) AND value != ''",
                    tuple(host_patterns),
                ).fetchall()
            except sqlite3.OperationalError:
                # Chromium uses 'cookies' table — but values are encrypted on Linux
                # Only works if unencrypted (e.g. some older versions)
                try:
                    rows = conn.execute(
                        "SELECT name, value FROM cookies WHERE host_key IN (?, ?) AND value != ''",
                        tuple(host_patterns),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []

            conn.close()
            Path(tmp.name).unlink(missing_ok=True)

            if rows:
                cookie_str = "; ".join(f"{r['name']}={r['value']}" for r in rows)
                return cookie_str
        except Exception:
            continue

    return None


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
            force=bool(getattr(args, "force", False)),
        )
        out_stream = sys.stderr if args.stdout else sys.stdout
        suffix = " (dry-run)" if result.dry_run else ""
        n_skipped = len(result.skipped)
        skip_part = f" skipped={n_skipped}" if n_skipped else ""
        print(
            f"[OK] source_type={result.source_type} parsed={result.parsed} "
            f"emitted={result.emitted}{skip_part} output={result.output_path}{suffix}",
            file=out_stream,
        )
        if n_skipped:
            print(
                f"[OK] {result.emitted} added, {n_skipped} skipped (already in library)",
                file=out_stream,
            )
            for doi, existing_ck in result.skipped:
                print(f"  [SKIP] {doi} → @{existing_ck}", file=out_stream)
        if result.citekeys:
            citekeys_line = ",".join(result.citekeys)
            print(f"[OK] citekeys={citekeys_line}", file=out_stream)
        if args.stdout:
            print(bibtex_text, end="")
        return
    if args.command == "docling":
        if args.doc_cmd == "batch":
            repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
            cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
            cfg = load_biblio_config(cfg_path, root=repo_root)

            if args.screen:
                batch_args: list[str] = []
                if args.config:
                    batch_args += ["--config", str(args.config)]
                if args.force:
                    batch_args += ["--force"]
                if args.concurrency != 1:
                    batch_args += ["--concurrency", str(args.concurrency)]
                if args.filter_glob:
                    batch_args += ["--filter", args.filter_glob]
                bash_cmd = _build_screen_bash_command(
                    repo_root=repo_root,
                    python_exe=sys.executable,
                    docling_args=batch_args,
                    subcmd="batch",
                )
                _launch_screen_session(name=str(args.screen_name), bash_cmd=bash_cmd)
                print(f"[OK] started screen session: {args.screen_name}", flush=True)
                print(f"Attach:  screen -r {args.screen_name}", flush=True)
                print("Detach:  Ctrl-A then D", flush=True)
                print("List:    screen -ls", flush=True)
                return

            from .batch import find_pending_docling, run_docling_batch

            pending, already_done = find_pending_docling(
                cfg, filter_glob=args.filter_glob, force=args.force,
            )
            cmd_preview = " ".join(cfg.docling_cmd)
            print(
                f"[INFO] repo_root={repo_root} config={cfg_path} docling_cmd={cmd_preview}",
                file=sys.stderr, flush=True,
            )
            print(
                f"[INFO] pending={len(pending)} already_done={len(already_done)} concurrency={args.concurrency}",
                file=sys.stderr, flush=True,
            )
            if not pending:
                print("[OK] Nothing to process — all citekeys already have docling output.", flush=True)
                return

            def _cli_progress(prog):
                elapsed = _fmt_duration(prog.elapsed_s)
                eta = _fmt_duration(prog.eta_s) if prog.eta_s is not None else "?"
                print(
                    f"[{prog.done}/{prog.total}] {prog.current_key}  elapsed={elapsed}  eta={eta}  failed={prog.failed}",
                    file=sys.stderr, flush=True,
                )

            result = run_docling_batch(
                cfg, pending,
                concurrency=args.concurrency,
                force=args.force,
                progress_cb=_cli_progress,
            )
            elapsed = _fmt_duration(result.elapsed_s)
            print(
                f"[DONE] processed={result.processed} failed={result.failed} "
                f"skipped={len(already_done)} elapsed={elapsed}",
                flush=True,
            )
            if result.failures:
                for f in result.failures:
                    print(f"  [FAIL] {f['citekey']}: {f['error']}", file=sys.stderr)
            raise SystemExit(0 if result.failed == 0 else 1)

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
            n_sources, n_entries, quality_warnings = merge_srcbib(cfg.bibtex_merge, dry_run=args.dry_run)
            suffix = " (dry-run)" if args.dry_run else ""
            print(f"[OK] merged sources={n_sources} entries={n_entries} -> {cfg.bibtex_merge.out_bib}{suffix}")
            if cfg.bibtex_merge.duplicates_log.exists() and not args.dry_run:
                print(f"[WARN] duplicates log: {cfg.bibtex_merge.duplicates_log}", file=sys.stderr)
            if quality_warnings:
                print(f"[WARN] {len(quality_warnings)} low-quality entries (noise/stub):", file=sys.stderr)
                for w in quality_warnings[:5]:
                    print(f"  {w}", file=sys.stderr)
                if len(quality_warnings) > 5:
                    log_path = cfg.bibtex_merge.duplicates_log.parent / "low_quality_entries.txt"
                    print(f"  ... and {len(quality_warnings) - 5} more. See {log_path}", file=sys.stderr)
            return
        if args.bibtex_cmd == "export":
            citekeys = list(args.citekeys)
            if args.export_all:
                from ._pybtex_utils import parse_bibtex_file
                bib_path = cfg.bibtex_merge.out_bib
                if not bib_path.exists():
                    print(f"[ERROR] merged bib not found: {bib_path}", file=sys.stderr)
                    raise SystemExit(1)
                db = parse_bibtex_file(bib_path)
                citekeys = sorted(db.entries.keys())
            if args.status:
                from .library import load_library
                lib = load_library(cfg)
                citekeys = sorted(k for k, v in lib.items() if v.get("status") == args.status)
            if args.collection:
                from .collections import load_collections
                col_data = load_collections(cfg)
                col = next((c for c in col_data.get("collections", []) if c.get("name") == args.collection), None)
                if col is None:
                    print(f"[ERROR] collection not found: {args.collection}", file=sys.stderr)
                    raise SystemExit(1)
                citekeys = sorted(col.get("citekeys", []))
            if not citekeys:
                print("[ERROR] no citekeys specified (use positional args, --all, --status, or --collection)", file=sys.stderr)
                raise SystemExit(1)
            bib_text = export_bibtex(citekeys, repo_root=repo_root)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(bib_text, encoding="utf-8")
                print(f"[OK] exported {len(citekeys)} entries -> {args.output}")
            else:
                print(bib_text, end="")
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
        if args.bibtex_cmd == "fetch-pdfs-oa":
            from .pdf_fetch_oa import fetch_pdfs_oa, ALL_STATUSES
            ck_filter = set(args.citekeys) if args.citekeys else None

            def _progress(p: dict) -> None:
                total = p.get("total", "?")
                done = p.get("completed", 0)
                ck = p.get("citekey", "")
                print(f"  [{done}/{total}] {ck}", flush=True)

            results = fetch_pdfs_oa(cfg, force=args.force, citekey_filter=ck_filter, progress_cb=_progress)
            counts = {s: sum(1 for r in results if r.status == s) for s in ALL_STATUSES}
            parts = [f"{k}={v}" for k, v in counts.items() if v > 0]
            print(f"[OK] total={len(results)} {' '.join(parts)}")
            errors = [r for r in results if r.error]
            for r in errors[:5]:
                print(f"[ERROR] {r.citekey}: {r.error}", file=sys.stderr)
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more errors", file=sys.stderr)
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
        elif args.add_cmd == "orcid":
            from .author_search import search_by_orcid, get_author_works
            from .ingest import find_existing_dois
            author = search_by_orcid(cfg.openalex_client, args.orcid)
            print(f"Author: {author.display_name}")
            if author.affiliation:
                print(f"Affiliation: {author.affiliation}")
            if author.h_index is not None:
                print(f"h-index: {author.h_index}")
            print(f"Works: {author.works_count}  Citations: {author.cited_by_count}")
            works = get_author_works(
                cfg.openalex_client,
                author.openalex_id,
                since_year=args.since,
                min_citations=args.min_citations,
            )
            if not works:
                print("No works found matching filters.")
                return
            existing_dois = find_existing_dois(repo_root)
            print(f"\n{'#':>3}  {'Year':>4}  {'Cit':>5}  {'OA':>2}  {'Status':>8}  Title")
            print("-" * 80)
            for i, w in enumerate(works, 1):
                doi_norm = (w.doi or "").lower()
                in_lib = "exists" if doi_norm and doi_norm in existing_dois else "new"
                oa_mark = "Y" if w.is_oa else " "
                title_trunc = (w.title[:50] + "...") if len(w.title) > 53 else w.title
                print(f"{i:>3}  {w.year or '':>4}  {w.cited_by_count:>5}  {oa_mark:>2}  {in_lib:>8}  {title_trunc}")
            print(f"\nTotal: {len(works)} works")
            # Collect DOIs of new works for import
            new_dois = [w.doi for w in works if w.doi and (w.doi.lower() not in existing_dois)]
            if not new_dois:
                print("All works already in library.")
                return
            answer = input(f"\nImport {len(new_dois)} new papers? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                print("Aborted.")
                return
            added = []
            for doi in new_dois:
                try:
                    r = add_openalex_work_to_bib(
                        cfg=cfg.openalex_client,
                        cache=cfg.openalex_cache,
                        repo_root=repo_root,
                        doi=doi,
                    )
                    added.append(r.citekey)
                    print(f"  + {r.citekey} ({doi})")
                except Exception as exc:
                    print(f"  ! Failed {doi}: {exc}")
            print(f"\n[OK] Imported {len(added)} papers.")
            return
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
        elif args.grobid_cmd == "match":
            out_path, matches = run_grobid_match(cfg)
            total_links = sum(len(v) for v in matches.values())
            print(f"[OK] matched papers={len(matches)} local_links={total_links} -> {out_path}")
        return

    if args.command == "summarize":
        from .summarize import summarize as run_summarize

        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)

        # Build list of citekeys to process
        keys_to_process: list[str] = []
        if args.status:
            lib = load_library(cfg)
            keys_to_process = [k for k, v in lib.items() if v.get("status") == args.status]
            if not keys_to_process:
                print(f"[WARN] No papers with status={args.status!r}")
                return
        elif args.key:
            keys_to_process = [args.key.lstrip("@")]
        else:
            print("[ERROR] Provide a citekey or use --status for batch mode.")
            return

        for key in keys_to_process:
            result = run_summarize(
                key,
                repo_root,
                prompt_only=args.prompt_only,
                force=args.force,
                model=args.model,
            )
            if args.prompt_only:
                print(result["prompt"])
            elif result.get("error"):
                print(f"[ERROR] {key}: {result['error']}", file=sys.stderr)
            elif result.get("skipped"):
                print(f"[SKIP] {key}: summary exists (use --force to regenerate)")
            else:
                print(f"[OK] {key}: {result['summary_path']}")
        return

    if args.command == "present":
        from .present import export_slides, generate_slides as run_present

        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        key = args.key.lstrip("@")

        result = run_present(
            key,
            repo_root,
            template=args.template,
            prompt_only=args.prompt_only,
            force=args.force,
            model=args.model,
        )
        if args.prompt_only:
            print(result["prompt"])
        elif result.get("error"):
            print(f"[ERROR] {key}: {result['error']}", file=sys.stderr)
        elif result.get("skipped"):
            print(f"[SKIP] {key}: slides exist (use --force to regenerate)")
        else:
            print(f"[OK] {key}: {result['slides_path']}")

        # Export if requested (and slides exist)
        if getattr(args, "export", None) and not args.prompt_only:
            slides_path = result.get("slides_path")
            if slides_path:
                export_result = export_slides(key, repo_root, fmt=args.export)
                if export_result.get("error"):
                    print(f"[WARN] Export: {export_result['error']}", file=sys.stderr)
                else:
                    print(f"[OK] Exported: {export_result['output_path']}")
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

    if args.command == "library":
        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        if args.library_cmd == "list":
            entries = load_library(cfg)
            status_filter = getattr(args, "status", None)
            tag_filter = getattr(args, "tag", None)
            filtered = {
                k: v for k, v in entries.items()
                if (not status_filter or v.get("status") == status_filter)
                and (not tag_filter or tag_filter in (v.get("tags") or []))
            }
            if args.json:
                print(json.dumps(filtered, indent=2))
            else:
                for ck, entry in sorted(filtered.items()):
                    status = entry.get("status") or "-"
                    tags = ",".join(entry.get("tags") or []) or "-"
                    priority = entry.get("priority") or "-"
                    print(f"{ck}\tstatus={status}\ttags={tags}\tpriority={priority}")
            return
        if args.library_cmd == "set":
            key = args.key.lstrip("@")
            tags = [t.strip() for t in args.tags.split(",") if t.strip()] if getattr(args, "tags", None) else None
            entry = update_entry(cfg, key, status=args.status or None, tags=tags, priority=args.priority or None)
            print(f"[OK] {key}: {entry}")
            return
        if args.library_cmd == "lint":
            from .tag_vocab import default_tag_vocab_path, lint_library_tags, load_tag_vocab

            vocab = load_tag_vocab(default_tag_vocab_path(repo_root))
            entries = load_library(cfg)
            report = lint_library_tags(entries, vocab)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                if report["non_vocab"]:
                    print("Non-vocabulary tags:")
                    for item in report["non_vocab"]:
                        sug = f"  (suggest: {item['suggestion']})" if item.get("suggestion") else ""
                        print(f"  {item['citekey']}: {item['tag']}{sug}")
                if report["duplicates"]:
                    print("Duplicate/inconsistent tags:")
                    for item in report["duplicates"]:
                        print(f"  {item['citekey']}: {item['normalized']} -> {item['forms']}")
                if report["suggestions"]:
                    print("Suggested mappings:")
                    for item in report["suggestions"]:
                        print(f"  {item['citekey']}: {item['tag']} -> {item['suggestion']}")
                if not any(report.values()):
                    print("[OK] All tags are valid.")
            return
        if args.library_cmd == "dedup":
            from .dedup import find_duplicates

            groups = find_duplicates(repo_root, cfg=cfg)
            if args.json:
                print(json.dumps(groups, indent=2))
            else:
                if not groups:
                    print("[OK] No duplicate papers detected.")
                else:
                    print(f"Found {len(groups)} duplicate group(s):\n")
                    for g in groups:
                        cks = ", ".join(g["citekeys"])
                        print(f"  [{g['reason']}] {cks}")
                        print(f"    {g['detail']}  (confidence: {g['confidence']:.0%})")
                        print(f"    suggested keep: {g['suggested_keep']}")
                        print()
            return
        if args.library_cmd == "autotag":
            from .autotag import autotag as run_autotag

            tiers = ["llm", "propagate"] if args.tier == "all" else [args.tier]

            # Build list of citekeys to process
            keys_to_process: list[str] = []
            if getattr(args, "all", False):
                keys_to_process = list(load_library(cfg).keys())
            elif getattr(args, "untagged", False):
                keys_to_process = [
                    k for k, v in load_library(cfg).items()
                    if not v.get("tags")
                ]
            elif args.key:
                keys_to_process = [args.key.lstrip("@")]
            else:
                print("[ERROR] Provide a citekey, --all, or --untagged.", file=sys.stderr)
                raise SystemExit(2)

            if not keys_to_process:
                print("[WARN] No papers to process.")
                return

            results = []
            for i, key in enumerate(keys_to_process, 1):
                if len(keys_to_process) > 1:
                    print(f"[{i}/{len(keys_to_process)}] {key}...", file=sys.stderr)
                result = run_autotag(
                    key, repo_root,
                    tiers=tiers,
                    force=args.force,
                    model=args.model,
                    threshold=args.threshold,
                )
                results.append(result)
                if not getattr(args, "json", False):
                    tags = result.get("all_tags", [])
                    if tags:
                        print(f"[OK] {key}: {', '.join(tags)}")
                    else:
                        errors = [
                            r.get("error", "")
                            for r in result.get("tiers", {}).values()
                            if r.get("error")
                        ]
                        if errors:
                            print(f"[WARN] {key}: {'; '.join(errors)}")
                        else:
                            print(f"[OK] {key}: (no tags assigned)")

            if getattr(args, "json", False):
                print(json.dumps(results, indent=2))
            return
        raise SystemExit(2)

    if args.command == "collection":
        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)

        if args.collection_cmd == "create":
            from .collections import create_collection
            col = create_collection(
                cfg, args.name,
                query=getattr(args, "smart", None),
                description=getattr(args, "description", None),
            )
            kind = "smart" if "query" in col else "manual"
            print(f"[OK] Created {kind} collection '{col['name']}' (id={col['id']})")
            if "query" in col:
                print(f"     query: {col['query']}")
            return

        if args.collection_cmd == "list":
            from .collections import list_collections_summary
            summaries = list_collections_summary(cfg)
            if args.json:
                print(json.dumps(summaries, indent=2))
            else:
                if not summaries:
                    print("No collections.")
                    return
                for s in summaries:
                    kind = "smart" if s["smart"] else "manual"
                    desc = f"  ({s['description']})" if s.get("description") else ""
                    query_info = f"  query={s['query']}" if s.get("query") else ""
                    print(f"{s['name']}\t{kind}\tcount={s['count']}{query_info}{desc}")
            return

        if args.collection_cmd == "show":
            from .collections import _find_by_name, is_smart, load_collections, resolve_smart
            data = load_collections(cfg)
            col = _find_by_name(data, args.name)
            if col is None:
                print(f"Collection '{args.name}' not found.", file=sys.stderr)
                raise SystemExit(1)
            if is_smart(col):
                citekeys = resolve_smart(cfg, col["id"])
            else:
                citekeys = col.get("citekeys") or []
            if args.json:
                print(json.dumps({"name": col["name"], "id": col["id"], "smart": is_smart(col),
                                   "query": col.get("query"), "citekeys": citekeys,
                                   "count": len(citekeys)}, indent=2))
            else:
                kind = "smart" if is_smart(col) else "manual"
                print(f"{col['name']} ({kind}, {len(citekeys)} papers)")
                if is_smart(col):
                    print(f"  query: {col['query']}")
                for ck in citekeys:
                    print(f"  @{ck}")
            return

        if args.collection_cmd == "edit-query":
            from .collections import _find_by_name, load_collections, update_query
            data = load_collections(cfg)
            col = _find_by_name(data, args.name)
            if col is None:
                print(f"Collection '{args.name}' not found.", file=sys.stderr)
                raise SystemExit(1)
            updated = update_query(cfg, col["id"], args.query)
            if updated is None:
                print(f"Failed to update collection.", file=sys.stderr)
                raise SystemExit(1)
            print(f"[OK] Updated query for '{args.name}': {args.query}")
            return

        raise SystemExit(2)

    if args.command == "ref-md":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        if args.ref_md_cmd == "run":
            if args.all:
                try:
                    keys = load_citekeys_md(cfg.citekeys_path)
                except FileNotFoundError:
                    print(f"Missing citekeys file: {cfg.citekeys_path}", file=sys.stderr)
                    raise SystemExit(2)
                if not keys:
                    print(f"No citekeys found in {cfg.citekeys_path}", file=sys.stderr)
                    raise SystemExit(2)
                print(f"[INFO] repo_root={repo_root} keys={len(keys)}", file=sys.stderr, flush=True)
                failures = 0
                for idx, key in enumerate(keys, start=1):
                    try:
                        print(f"[RUN {idx}/{len(keys)}] {key}", file=sys.stderr, flush=True)
                        out = run_ref_md_for_key(cfg, key, force=args.force)
                    except Exception as e:
                        failures += 1
                        print(f"[FAIL {idx}/{len(keys)}] {key}: {e}", file=sys.stderr)
                    else:
                        print(f"[OK {idx}/{len(keys)}] {key}: {out.md_path}", flush=True)
                raise SystemExit(0 if failures == 0 else 1)
            else:
                print(f"[RUN] {args.key.lstrip('@')}", file=sys.stderr, flush=True)
                out = run_ref_md_for_key(cfg, args.key, force=args.force)
                print(f"[OK] {args.key.lstrip('@')}: {out.md_path}")
        return

    if args.command == "ui":
        if args.ui_cmd != "serve":
            raise SystemExit(2)
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)
        serve_ui_app(cfg, host=str(args.host), port=int(args.port))
        return

    if args.command == "queue":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (repo_root / args.config).resolve() if args.config else (repo_root / "bib" / "config" / "biblio.yml")
        cfg = load_biblio_config(cfg_path, root=repo_root)

        if args.queue_cmd == "list":
            entries = load_queue(cfg)
            if not entries:
                print("Queue is empty.")
                return
            col_w = max(len(k) for k in entries)
            header = f"{'CITEKEY':<{col_w}}  {'ADDED':<26}  {'OA_STATUS':<10}  DOI"
            print(header)
            print("-" * len(header))
            for key, entry in sorted(entries.items()):
                added = str(entry.get("added") or "")[:26]
                oa = str(entry.get("oa_status") or "")
                doi = str(entry.get("doi") or "")
                print(f"{key:<{col_w}}  {added:<26}  {oa:<10}  {doi}")
            return

        if args.queue_cmd == "open":
            import webbrowser
            key = args.key.lstrip("@")
            entries = load_queue(cfg)
            entry = entries.get(key)
            if entry is None:
                print(f"'{key}' is not in the queue.", file=sys.stderr)
                raise SystemExit(1)
            url = entry.get("url") or entry.get("doi")
            if not url:
                print(f"No URL recorded for '{key}'.", file=sys.stderr)
                raise SystemExit(1)
            if str(url).startswith("10."):
                url = "https://doi.org/" + url
            webbrowser.open(str(url))
            print(f"Opened: {url}")
            return

        if args.queue_cmd == "drain":
            from .pdf_fetch_oa import _oa_pdf_url, _download
            import json as _json
            entries = load_queue(cfg)
            if not entries:
                print("Queue is empty.")
                return
            jsonl_path = cfg.openalex.out_jsonl
            if not jsonl_path.exists():
                print(f"OpenAlex data not found: {jsonl_path}. Run 'biblio openalex resolve' first.", file=sys.stderr)
                raise SystemExit(1)
            oa_records: dict[str, dict] = {}
            with jsonl_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    ck = str(rec.get("citekey") or "").strip()
                    if ck:
                        oa_records[ck] = rec
            downloaded = 0
            failed = 0
            no_url = 0
            for key in list(entries):
                rec = oa_records.get(key)
                if rec is None:
                    continue
                dest = (cfg.pdf_root / cfg.pdf_pattern.format(citekey=key)).resolve()
                if dest.exists() and not args.force:
                    remove_from_queue(cfg, key)
                    print(f"[already exists] {key}")
                    continue
                url = _oa_pdf_url(rec)
                if not url:
                    no_url += 1
                    print(f"[no_url] {key}")
                    continue
                try:
                    _download(url, dest)
                    remove_from_queue(cfg, key)
                    downloaded += 1
                    print(f"[downloaded] {key}: {url}")
                except Exception as e:
                    failed += 1
                    print(f"[error] {key}: {e}", file=sys.stderr)
            print(f"\nDrain complete: {downloaded} downloaded, {no_url} still no URL, {failed} errors.")
            return

        if args.queue_cmd == "remove":
            key = args.key.lstrip("@")
            removed = remove_from_queue(cfg, key)
            if removed:
                print(f"Removed '{key}' from queue.")
            else:
                print(f"'{key}' was not in the queue.")
            return

    if args.command == "pool":
        if args.pool_cmd == "bookmarklet":
            print(_bookmarklet_js(args.port))
            return

        if args.pool_cmd == "serve":
            inbox = args.inbox.expanduser().resolve()
            serve_pool(inbox, host=str(args.host), port=int(args.port))
            return

        # Commands that need project cfg to resolve pool root
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (
            (repo_root / args.config).resolve() if args.config
            else (repo_root / "bib" / "config" / "biblio.yml")
        )
        cfg = load_biblio_config(cfg_path, root=repo_root)

        # Resolve pool root: --pool flag > project config
        if args.pool_cmd in ("ingest", "watch", "link", "promote"):
            pool_root_arg = getattr(args, "pool", None)
            if pool_root_arg is not None:
                pool_root = pool_root_arg.expanduser().resolve()
            elif cfg.common_pool_path is not None:
                pool_root = cfg.common_pool_path
            else:
                print(
                    "No pool configured. Pass --pool <path> or run 'biblio pool link --pool <path>' first.",
                    file=sys.stderr,
                )
                raise SystemExit(1)

        if args.pool_cmd == "ingest":
            from .pool import load_pool_config
            pool_cfg = load_pool_config(pool_root)
            inbox = args.inbox_dir.expanduser().resolve()
            results = ingest_inbox(pool_cfg, inbox, dry_run=args.dry_run, move=args.move)
            counts: dict[str, int] = {}
            for r in results:
                counts[r.status] = counts.get(r.status, 0) + 1
                icon = {"ingested": "+", "duplicate": "=", "error": "!", "dry_run": "?"}.get(r.status, " ")
                print(f"[{icon}] {r.pdf_path.name} → {r.citekey or '?'}"
                      + (f"  (DOI: {r.doi})" if r.doi else "")
                      + (f"  ERROR: {r.error}" if r.error else ""))
            summary = " | ".join(f"{v} {k}" for k, v in sorted(counts.items()))
            print(f"\n{summary}")
            return

        if args.pool_cmd == "watch":
            inbox = args.inbox_dir.expanduser().resolve()
            if args.screen:
                import shlex as _shlex
                watch_cmd_parts = [
                    sys.executable, "-m", "biblio.cli", "pool", "watch",
                    str(inbox),
                    "--pool", str(pool_root),
                    "--interval", str(args.interval),
                ]
                if args.move:
                    watch_cmd_parts.append("--move")
                bash_cmd = " ".join(_shlex.quote(p) for p in watch_cmd_parts)
                _launch_screen_session(name=args.screen_name, bash_cmd=bash_cmd)
                print(f"Started pool watch in screen session '{args.screen_name}'.")
                return
            import time as _time
            from .pool import load_pool_config
            pool_cfg = load_pool_config(pool_root)
            print(f"Watching {inbox} every {args.interval}s. Press Ctrl+C to stop.")
            while True:
                results = ingest_inbox(pool_cfg, inbox, dry_run=False, move=args.move)
                new = [r for r in results if r.status == "ingested"]
                if new:
                    for r in new:
                        print(f"[+] {r.pdf_path.name} → {r.citekey}")
                _time.sleep(args.interval)

        if args.pool_cmd == "link":
            lab_pool = args.lab.expanduser().resolve() if getattr(args, "lab", None) else None
            result = link_project(cfg, pool_root, lab_pool=lab_pool)
            if result["config_updated"]:
                if lab_pool:
                    print(f"Updated bib/config/biblio.yml: pool.path = {pool_root}, pool.search = [{lab_pool}, {pool_root}]")
                else:
                    print(f"Updated bib/config/biblio.yml: pool.path = {pool_root}")
            else:
                print("biblio.yml already has this pool path — no change.")
            if result["gitignore_updated"]:
                print("Added 'articles/' to bib/.gitignore")
            else:
                print("bib/.gitignore already excludes articles/ — no change.")
            if not args.no_sync:
                # Reload config so common_pool_path is set
                cfg2 = load_biblio_config(cfg_path, root=repo_root)
                sync_results = sync_pool_symlinks(cfg2)
                linked = sum(1 for v in sync_results.values() if v == "linked")
                not_in_pool = sum(1 for v in sync_results.values() if v == "not_in_pool")
                if linked:
                    print(f"Symlinked {linked} PDF(s) from pool.")
                if not_in_pool:
                    print(f"{not_in_pool} citekey(s) not yet in pool — run 'biblio queue list' to see them.")
            return

        if args.pool_cmd == "promote":
            from .pool import promote_to_pool

            citekey_list: list[str] = []
            if getattr(args, "all_local", False):
                # Gather all citekeys that have a real local PDF (not a symlink)
                articles_dir = cfg.pdf_root
                if articles_dir.is_dir():
                    for child in articles_dir.iterdir():
                        if child.is_dir():
                            pdf = child / f"{child.name}.pdf"
                            if pdf.is_file() and not pdf.is_symlink():
                                citekey_list.append(child.name)
                if not citekey_list:
                    print("No local (non-symlinked) PDFs found to promote.")
                    return
            elif args.citekeys:
                citekey_list = args.citekeys
            else:
                print("Specify --citekeys or --all-local.", file=sys.stderr)
                raise SystemExit(1)

            results = promote_to_pool(cfg, pool_root, citekey_list, dry_run=args.dry_run)
            counts: dict[str, int] = {}
            for r in results:
                counts[r.status] = counts.get(r.status, 0) + 1
                icon = {
                    "promoted": "+", "already_in_pool": "=",
                    "no_local_pdf": "-", "error": "!", "dry_run": "?",
                }.get(r.status, " ")
                line = f"[{icon}] {r.citekey} → {r.status}"
                if r.error:
                    line += f"  ERROR: {r.error}"
                print(line)
            summary = " | ".join(f"{v} {k}" for k, v in sorted(counts.items()))
            print(f"\n{summary}")
            return

    if args.command == "zotero":
        repo_root = (args.root.expanduser().resolve() if args.root else find_repo_root())
        cfg_path = (
            (repo_root / args.config).resolve() if args.config
            else default_config_path(root=repo_root)
        )

        # Load config and extract zotero section
        import yaml as _yaml
        from .zotero import load_zotero_config, pull as zotero_pull_fn, status as zotero_status_fn

        raw_payload: dict = {}
        if cfg_path.exists():
            raw_payload = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        zcfg = load_zotero_config(raw_payload, repo_root)
        if zcfg is None:
            print(
                "No zotero section configured in biblio.yml. Add a 'zotero:' section "
                "with at least 'library_id' to enable Zotero integration.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        if args.zotero_cmd == "pull":
            tags_list = [t.strip() for t in args.tags.split(",")] if args.tags else None
            result = zotero_pull_fn(
                repo_root=repo_root,
                zotero_cfg=zcfg,
                collection=args.collection or None,
                tags=tags_list,
                dry_run=args.dry_run,
            )
            prefix = "[DRY RUN] " if result.dry_run else ""
            print(f"{prefix}Pulled {result.pulled} item(s) from Zotero")
            if result.pdfs_downloaded:
                print(f"  PDFs downloaded: {result.pdfs_downloaded}")
            if result.deleted:
                print(f"  Deleted entries: {result.deleted}")
            if result.skipped:
                print(f"  Skipped: {result.skipped}")
            if result.errors:
                for err in result.errors:
                    print(f"  [!] {err}")
            if result.citekeys:
                print(f"  Citekeys: {', '.join(result.citekeys[:20])}"
                      + (f" ... (+{len(result.citekeys) - 20})" if len(result.citekeys) > 20 else ""))
            return

        if args.zotero_cmd == "push":
            from .zotero import push as zotero_push_fn
            ck_list = [c.strip() for c in args.citekeys.split(",")] if args.citekeys else None
            push_result = zotero_push_fn(
                repo_root=repo_root,
                zotero_cfg=zcfg,
                citekeys=ck_list,
                push_tags=args.tags,
                push_notes=args.notes,
                push_ids=args.ids,
                force=args.force,
                dry_run=args.dry_run,
            )
            prefix = "[DRY RUN] " if push_result.dry_run else ""
            print(f"{prefix}Updated {push_result.updated} item(s) in Zotero")
            if push_result.created:
                print(f"  Notes created: {push_result.created}")
            if push_result.skipped:
                print(f"  Skipped: {push_result.skipped}")
            if push_result.conflicts:
                print(f"  Conflicts ({len(push_result.conflicts)}):")
                for c in push_result.conflicts:
                    print(f"    {c}")
            if push_result.errors:
                for err in push_result.errors:
                    print(f"  [!] {err}")
            return

        if args.zotero_cmd == "status":
            info = zotero_status_fn(zotero_cfg=zcfg)
            print(f"Library:      {info['library_type']}:{info['library_id']}")
            if info["collection"]:
                print(f"Collection:   {info['collection']}")
            print(f"Last sync:    {info['last_sync']}")
            print(f"Last version: {info['last_version']}")
            print(f"Total items:  {info['total_items']}")
            print(f"With PDF:     {info['items_with_pdf']}")
            print(f"State file:   {info['sync_state_path']}")
            return

    if args.command == "concepts":
        from .concepts import build_concept_index, extract_concepts, search_concepts

        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())

        if args.concepts_cmd == "extract":
            keys_to_process: list[str] = []
            if getattr(args, "all", False):
                cfg_path = (repo_root / args.config).resolve() if getattr(args, "config", None) else (repo_root / "bib" / "config" / "biblio.yml")
                cfg = load_biblio_config(cfg_path, root=repo_root)
                lib = load_library(cfg)
                keys_to_process = list(lib.keys())
            elif args.key:
                keys_to_process = [args.key.lstrip("@")]
            else:
                print("[ERROR] Provide a citekey or use --all for batch mode.")
                return

            results = []
            for key in keys_to_process:
                result = extract_concepts(
                    key, repo_root,
                    prompt_only=args.prompt_only,
                    force=args.force,
                    model=args.model,
                )
                results.append(result)
                if not getattr(args, "json", False):
                    if args.prompt_only:
                        print(result["prompt"])
                    elif result.get("error"):
                        print(f"[ERROR] {key}: {result['error']}", file=sys.stderr)
                    elif result.get("skipped"):
                        print(f"[SKIP] {key}: concepts exist (use --force to regenerate)")
                    else:
                        concepts = result.get("concepts") or {}
                        total = sum(len(v) for v in concepts.values())
                        print(f"[OK] {key}: {total} concepts extracted → {result['concepts_path']}")
            if getattr(args, "json", False):
                print(json.dumps(results, indent=2))
            return

        if args.concepts_cmd == "index":
            result = build_concept_index(repo_root)
            if getattr(args, "json", False):
                print(json.dumps(result, indent=2))
            else:
                print(f"[OK] Indexed {result['total_papers']} papers, {result['total_concepts']} unique concepts → {result['index_path']}")
            return

        if args.concepts_cmd == "search":
            result = search_concepts(args.query, repo_root)
            if getattr(args, "json", False):
                print(json.dumps(result, indent=2))
            else:
                if not result["matches"]:
                    print(f"No concepts matching '{args.query}'.")
                else:
                    for m in result["matches"]:
                        cks = ", ".join(f"@{ck}" for ck in m["citekeys"])
                        print(f"{m['concept']}: {cks}")
            return

        raise SystemExit(2)

    if args.command == "compare":
        from .compare import compare as run_compare

        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        dims = [d.strip() for d in args.dimensions.split(",")] if args.dimensions else None
        result = run_compare(
            args.keys, repo_root,
            dimensions=dims,
            prompt_only=args.prompt_only,
            force=args.force,
            model=args.model,
        )
        if result.get("error"):
            print(f"[ERROR] {result['error']}", file=sys.stderr)
        elif args.prompt_only:
            print(result["prompt"])
        elif result.get("skipped"):
            print(f"[SKIP] Comparison exists (use --force to regenerate): {result['comparison_path']}")
        else:
            print(f"[OK] Comparison saved → {result['comparison_path']}")
        return

    if args.command == "reading-list":
        from .reading_list import reading_list as run_reading_list

        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        result = run_reading_list(
            args.question, repo_root,
            count=args.count,
            prompt_only=args.prompt_only,
            model=args.model,
        )
        if result.get("error"):
            print(f"[ERROR] {result['error']}", file=sys.stderr)
        elif args.prompt_only:
            print(result["prompt"])
        elif getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        else:
            recs = result.get("recommendations") or []
            if not recs:
                print(f"No recommendations found ({result.get('candidates_count', 0)} candidates evaluated).")
            else:
                print(f"Reading list for: {args.question}")
                print(f"({result.get('candidates_count', 0)} candidates evaluated)\n")
                for i, rec in enumerate(recs, 1):
                    score = rec.get("score", 0)
                    justification = rec.get("justification", "")
                    print(f"{i}. @{rec['citekey']}  (score: {score:.2f})")
                    if justification:
                        print(f"   {justification}")
        return

    if args.command == "cite-draft":
        from .cite_draft import cite_draft as run_cite_draft

        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        result = run_cite_draft(
            args.text, repo_root,
            style=args.style,
            max_refs=args.max_refs,
            prompt_only=args.prompt_only,
            model=args.model,
        )
        if result.get("error"):
            print(f"[ERROR] {result['error']}", file=sys.stderr)
        elif args.prompt_only:
            print(result["prompt"])
        elif getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        else:
            draft = result.get("draft") or ""
            if draft:
                passages = result.get("passages") or []
                print(f"Sources: {', '.join('@' + p['citekey'] for p in passages)}\n")
                print(draft)
            else:
                print("No draft generated.")
        return

    if args.command == "review":
        repo_root = (args.root.expanduser().resolve() if getattr(args, "root", None) else find_repo_root())
        seed_keys = [s.strip().lstrip("@") for s in args.seeds.split(",")] if args.seeds else None

        if seed_keys:
            from .lit_review import review_plan as run_review_plan

            result = run_review_plan(
                seed_keys, args.question, repo_root,
                prompt_only=args.prompt_only,
                model=args.model,
            )
            if result.get("error"):
                print(f"[ERROR] {result['error']}", file=sys.stderr)
            elif args.prompt_only:
                print(result["prompt"])
            elif getattr(args, "json", False):
                print(json.dumps(result, indent=2))
            else:
                plan = result.get("plan")
                if plan:
                    print(f"Review plan for: {args.question}\n")
                    print(f"Scope: {plan.get('scope', '')}\n")
                    themes = plan.get("themes") or []
                    if themes:
                        print("Themes:")
                        for t in themes:
                            print(f"  - {t}")
                    gaps = plan.get("gaps") or []
                    if gaps:
                        print(f"\nGaps ({len(gaps)}):")
                        for g in gaps:
                            print(f"  - {g}")
                    expansions = plan.get("expansion_directions") or []
                    if expansions:
                        print(f"\nExpansion directions:")
                        for e in expansions:
                            print(f"  - {e.get('direction', '')}: {e.get('rationale', '')}")
                    est = plan.get("estimated_additional_papers")
                    if est:
                        print(f"\nEstimated additional papers needed: {est}")
                else:
                    print("No plan generated.")
        else:
            from .lit_review import review_query as run_review_query

            result = run_review_query(
                args.question, repo_root,
                style=args.style,
                prompt_only=args.prompt_only,
                model=args.model,
            )
            if result.get("error"):
                print(f"[ERROR] {result['error']}", file=sys.stderr)
            elif args.prompt_only:
                print(result["prompt"])
            elif getattr(args, "json", False):
                print(json.dumps(result, indent=2))
            else:
                synthesis = result.get("synthesis") or ""
                if synthesis:
                    passages = result.get("passages") or []
                    print(f"Sources: {', '.join('@' + p['citekey'] for p in passages)}\n")
                    print(synthesis)
                else:
                    print("No synthesis generated.")
        return

    if args.command == "profile":
        from .profile import apply_profile, list_profiles, load_user_config, user_config_path
        if args.profile_cmd == "list":
            profiles = list_profiles()
            if not profiles:
                print("No bundled profiles found.")
            else:
                for p in profiles:
                    print(f"  {p['slug']:<20} {p['name']}")
                    if p["description"]:
                        print(f"  {'':20} {p['description']}")
            return
        if args.profile_cmd == "show":
            cfg_path = user_config_path()
            if not cfg_path.exists():
                print(f"No user config found at {cfg_path}")
            else:
                print(f"# {cfg_path}")
                print(cfg_path.read_text(encoding="utf-8"), end="")
            return
        if args.profile_cmd == "use":
            storage = args.storage.expanduser().resolve() if args.storage else None
            dest = apply_profile(args.name, personal_storage=storage, yes=args.yes)
            print(f"Profile '{args.name}' applied → {dest}")
            return

    if args.command == "auth":
        from .profile import load_user_config, user_config_path
        if args.auth_cmd == "ezproxy":
            cfg_path = user_config_path()
            user_cfg = load_user_config()

            # Read current ezproxy_base from config
            pf = user_cfg.get("pdf_fetch") or {}
            ezproxy_base = pf.get("ezproxy_base") or ""

            if not ezproxy_base and not args.import_stdin:
                print("No ezproxy_base configured in your user config.")
                print("Run 'biblio profile use lmu-munich' first, or enter the URL now.")
                ezproxy_base = input("EZProxy base URL: ").strip()
                if not ezproxy_base:
                    print("Aborted.", file=sys.stderr)
                    raise SystemExit(1)

            # --login: Shibboleth SAML login (no browser needed)
            if args.login:
                from .ezproxy import shibboleth_login, ShibbolethLoginError
                import getpass

                print(f"\nShibboleth login to {ezproxy_base}")
                username = input("Username (LMU Kennung): ").strip()
                if not username:
                    print("Aborted.", file=sys.stderr)
                    raise SystemExit(1)
                password = getpass.getpass("Password: ")
                if not password:
                    print("Aborted.", file=sys.stderr)
                    raise SystemExit(1)

                print("Authenticating...", end="", flush=True)
                try:
                    cookie_input = shibboleth_login(ezproxy_base, username, password)
                    print(" OK")
                    print(f"Got {len(cookie_input.split(';'))} cookies")
                except ShibbolethLoginError as exc:
                    print(f" FAILED\n{exc}", file=sys.stderr)
                    raise SystemExit(1)
                except ImportError as exc:
                    print(f" FAILED\n{exc}", file=sys.stderr)
                    raise SystemExit(1)

            # --import: read cookie from stdin (for piping)
            elif args.import_stdin:
                raw = sys.stdin.read().strip()
                if not raw:
                    print("No cookie on stdin. Aborted.", file=sys.stderr)
                    raise SystemExit(1)
                # Accept either "base=URL\tcookie=VALUE" or plain cookie string
                if "\t" in raw:
                    parts = dict(p.split("=", 1) for p in raw.split("\t") if "=" in p)
                    ezproxy_base = parts.get("base", ezproxy_base)
                    cookie_input = parts.get("cookie", raw)
                else:
                    cookie_input = raw

            # --push HOST: extract local cookies and push to remote via SSH
            elif args.push:
                cookie_input = _extract_browser_cookies(ezproxy_base)
                if not cookie_input:
                    print("No cookies found in local browser. Log in first.", file=sys.stderr)
                    raise SystemExit(1)
                host = args.push
                export_payload = f"base={ezproxy_base}\tcookie={cookie_input}"
                print(f"Pushing EZProxy cookies to {host}...")
                result = subprocess.run(
                    ["ssh", host, "biblio", "auth", "ezproxy", "--import"],
                    input=export_payload, text=True,
                    capture_output=True,
                )
                if result.returncode == 0:
                    print(f"Cookies pushed to {host} successfully.")
                    if result.stdout.strip():
                        print(result.stdout.strip())
                else:
                    print(f"Failed to push cookies to {host}:", file=sys.stderr)
                    print(result.stderr.strip(), file=sys.stderr)
                    raise SystemExit(1)
                return

            # --export: print cookie to stdout (for piping)
            elif args.export:
                cookie_input = _extract_browser_cookies(ezproxy_base)
                if not cookie_input:
                    print("No cookies found in local browser. Log in first.", file=sys.stderr)
                    raise SystemExit(1)
                print(f"base={ezproxy_base}\tcookie={cookie_input}")
                return

            else:
                login_url = f"{ezproxy_base.rstrip('/')}/login"
                print(f"\nEZProxy base: {ezproxy_base}")
                print(f"Login URL:    {login_url}")

                # Try to auto-extract cookies from browser stores
                cookie_input = _extract_browser_cookies(ezproxy_base)
                if cookie_input:
                    print(f"\nAuto-detected cookies from browser ({len(cookie_input.split(';'))} cookies)")
                else:
                    # Open browser if requested and a display is available
                    if not args.no_open:
                        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform == "darwin")
                        if has_display:
                            import webbrowser
                            print(f"\nOpening {login_url} in your browser...")
                            webbrowser.open(login_url)
                        else:
                            print(f"\nOpen this URL in your browser:\n  {login_url}")

                    print("\nAfter logging in:")
                    print("  1. Open DevTools (F12)")
                    print("  2. Go to Application > Cookies > " + ezproxy_base)
                    print("  3. Copy all cookie Name=Value pairs\n")
                    print("Paste cookies (format: name1=value1; name2=value2):")
                    try:
                        import getpass
                        cookie_input = getpass.getpass("> ").strip()
                    except (EOFError, OSError):
                        cookie_input = input("> ").strip()

            if not cookie_input:
                print("No cookie provided. Aborted.", file=sys.stderr)
                raise SystemExit(1)

            # Update user config
            if not isinstance(user_cfg.get("pdf_fetch"), dict):
                user_cfg["pdf_fetch"] = {}
            if ezproxy_base:
                user_cfg["pdf_fetch"]["ezproxy_base"] = ezproxy_base
            user_cfg["pdf_fetch"]["ezproxy_cookie"] = cookie_input

            import yaml as _yaml
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                _yaml.safe_dump(user_cfg, sort_keys=False, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
            os.chmod(cfg_path, 0o600)
            print(f"\nCookie saved to {cfg_path} (permissions: 600)")
            print("You can now run: biblio bibtex fetch-pdfs-oa")
            return

    raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover
    main()
