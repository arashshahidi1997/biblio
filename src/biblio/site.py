from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ._pybtex_utils import parse_bibtex_file, require_pybtex
from .citekeys import load_citekeys_md
from .config import BiblioConfig

SITE_OUT_REL = Path("bib/site")


@dataclass(frozen=True)
class BiblioSiteOptions:
    out_dir: Path
    include_graphs: bool = True
    include_docling: bool = True
    include_openalex: bool = True


@dataclass(frozen=True)
class BiblioSiteDoctorReport:
    config_path: Path
    repo_root: Path
    out_dir: Path
    papers_total: int
    configured_citekeys: int
    source_bib_entries: int
    papers_with_pdf: int
    papers_with_docling: int
    papers_with_openalex: int
    missing_pdf: int
    missing_docling: int
    missing_openalex: int
    orphan_docling: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class BiblioSiteBuildResult:
    out_dir: Path
    papers_total: int
    pages_written: int
    data_files_written: int
    doctor: BiblioSiteDoctorReport


def default_site_out_dir(*, root: str | Path | None = None) -> Path:
    repo_root = Path(root) if root is not None else Path.cwd()
    return (repo_root / SITE_OUT_REL).resolve()


def _safe_rel(path: Path, start: Path) -> str:
    return os.path.relpath(path, start)


def _path_under(root: Path, path: Path) -> bool:
    root = root.resolve()
    path = path.resolve()
    return path == root or root in path.parents


def _ensure_safe_out_dir(repo_root: Path, out_dir: Path) -> None:
    if not _path_under(repo_root, out_dir):
        raise ValueError(f"Site output must stay under repo root: {out_dir}")
    if out_dir == repo_root or out_dir == repo_root / "bib":
        raise ValueError(f"Refusing to use unsafe site output directory: {out_dir}")


def _iter_srcbib_records(cfg: BiblioConfig) -> list[dict[str, Any]]:
    src_dir = cfg.bibtex_merge.src_dir
    if not src_dir.exists():
        return []

    bib_files = sorted(p for p in src_dir.glob(cfg.bibtex_merge.src_glob) if p.is_file())
    if not bib_files:
        return []

    require_pybtex("site generation")

    records: list[dict[str, Any]] = []
    for bib_path in bib_files:
        db = parse_bibtex_file(bib_path)
        for citekey, entry in sorted(db.entries.items(), key=lambda kv: kv[0]):
            persons = entry.persons.get("author", [])
            authors: list[str] = []
            for person in persons:
                parts = []
                if person.first_names:
                    parts.extend(person.first_names)
                if person.middle_names:
                    parts.extend(person.middle_names)
                if person.last_names:
                    parts.extend(person.last_names)
                if parts:
                    authors.append(" ".join(parts))
            title = str(entry.fields.get("title") or "").replace("{", "").replace("}", "").strip()
            year_raw = str(entry.fields.get("year") or "").strip()
            year: int | None = None
            if year_raw:
                try:
                    year = int(year_raw.split("-", 1)[0])
                except Exception:
                    year = None
            doi = str(entry.fields.get("doi") or "").strip() or None
            records.append(
                {
                    "citekey": citekey,
                    "source_bib": bib_path.name,
                    "title": title or citekey,
                    "year": year,
                    "doi": doi,
                    "authors": authors,
                }
            )
    return records


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _find_optional_derivatives(docling_dir: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {"notes": [], "summaries": []}
    if not docling_dir.exists():
        return found
    for path in sorted(docling_dir.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name == "_biblio.json":
            continue
        if "summary" in name:
            found["summaries"].append(path)
        elif "note" in name:
            found["notes"].append(path)
    return found


def _minimal_markdown_to_html(text: str, *, image_url_prefix: str = "") -> str:
    """Convert a minimal subset of Markdown to HTML.

    image_url_prefix: prepended to relative image src paths, e.g.
    "/api/files/docling/mypaper" so that ![alt](img.png) becomes
    <img src="/api/files/docling/mypaper/img.png" alt="alt">.
    """
    blocks: list[str] = []
    lines = text.splitlines()
    in_code = False
    paragraph: list[str] = []
    list_items: list[str] = []

    def _inline(line: str) -> str:
        """Apply inline formatting: images, bold, italic, code, links."""
        # Images: ![alt](src)
        def _img(m: re.Match) -> str:  # type: ignore[type-arg]
            alt = escape(m.group(1))
            src = m.group(2)
            if image_url_prefix and not src.startswith(("http://", "https://", "/")):
                src = f"{image_url_prefix}/{src}"
            return f'<img src="{escape(src)}" alt="{alt}" style="max-width:100%;height:auto;">'
        out = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _img, line)
        # Inline code
        out = re.sub(r"`([^`]+)`", lambda m: f"<code>{escape(m.group(1))}</code>", out)
        # Bold
        out = re.sub(r"\*\*([^*]+)\*\*", lambda m: f"<strong>{escape(m.group(1))}</strong>", out)
        # Italic
        out = re.sub(r"\*([^*]+)\*", lambda m: f"<em>{escape(m.group(1))}</em>", out)
        # Links
        out = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: f'<a href="{escape(m.group(2))}" target="_blank" rel="noreferrer">{escape(m.group(1))}</a>',
            out,
        )
        return out

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            joined = " ".join(part.strip() for part in paragraph if part.strip())
            if joined:
                blocks.append(f"<p>{_inline(joined)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            items = "".join(f"<li>{_inline(item)}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items = []

    code_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        trimmed = line.strip()
        if trimmed.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code:
                blocks.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not trimmed:
            flush_paragraph()
            flush_list()
            continue
        # Standalone image line → render directly as a block
        if re.match(r"^!\[", trimmed):
            flush_paragraph()
            flush_list()
            blocks.append(_inline(trimmed))
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h3>{_inline(line[4:].strip())}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{_inline(line[3:].strip())}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h1>{_inline(line[2:].strip())}</h1>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            flush_paragraph()
            list_items.append(re.sub(r"^\s*[-*]\s+", "", line).strip())
            continue
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    if in_code:
        blocks.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(blocks) if blocks else "<p>No Docling markdown available.</p>"


def _page_shell(title: str, body: str, *, root_prefix: str = ".") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="{escape(root_prefix)}/style.css">
</head>
<body>
  <header class="site-header">
    <div class="site-width">
      <p class="eyebrow">biblio site</p>
      <h1>{escape(title)}</h1>
      <nav class="site-nav">
        <a href="{escape(root_prefix)}/index.html">Home</a>
        <a href="{escape(root_prefix)}/papers/index.html">Papers</a>
        <a href="{escape(root_prefix)}/status.html">Status</a>
        <a href="{escape(root_prefix)}/graph.html">Graph</a>
      </nav>
    </div>
  </header>
  <main class="site-width">
    {body}
  </main>
</body>
</html>
"""


def _render_style() -> str:
    return """
:root {
  --bg: #f6f3ea;
  --panel: #fffdf8;
  --ink: #1f241f;
  --muted: #5c645c;
  --line: #d8d0be;
  --accent: #0d6b5f;
  --accent-soft: #dcefe9;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(circle at top right, rgba(13, 107, 95, 0.10), transparent 24rem),
    linear-gradient(180deg, #f8f5ed 0%, var(--bg) 100%);
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
  line-height: 1.55;
}
a { color: var(--accent); }
code, pre, .mono {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
.site-width {
  width: min(1120px, calc(100vw - 2rem));
  margin: 0 auto;
}
.site-header {
  border-bottom: 1px solid var(--line);
  background: rgba(255, 253, 248, 0.82);
  backdrop-filter: blur(6px);
  position: sticky;
  top: 0;
}
.site-header .site-width {
  padding: 1rem 0 1.25rem;
}
.eyebrow {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
  font-size: 0.75rem;
}
.site-nav {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}
.site-nav a {
  text-decoration: none;
  font-weight: 600;
}
main.site-width {
  padding: 1.5rem 0 3rem;
}
.hero, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 1rem 1.25rem;
  box-shadow: 0 12px 36px rgba(30, 33, 29, 0.06);
}
.hero {
  margin-bottom: 1.25rem;
}
.grid {
  display: grid;
  gap: 1rem;
}
.grid.cols-3 {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}
.metric {
  background: var(--accent-soft);
  border-radius: 14px;
  padding: 0.9rem 1rem;
}
.metric strong {
  display: block;
  font-size: 1.4rem;
}
.paper-table, .kv-table {
  width: 100%;
  border-collapse: collapse;
}
.paper-table th, .paper-table td, .kv-table th, .kv-table td {
  padding: 0.6rem 0.7rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
.paper-table th, .kv-table th {
  text-align: left;
}
.badge {
  display: inline-block;
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.82rem;
  font-weight: 700;
}
.badge.muted {
  background: #ece7db;
  color: var(--muted);
}
.split {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 1rem;
}
.docling {
  max-height: 60vh;
  overflow: auto;
}
.small {
  color: var(--muted);
  font-size: 0.92rem;
}
.search {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.8rem 0.9rem;
  background: white;
  font-size: 1rem;
}
.list-clean {
  list-style: none;
  padding: 0;
  margin: 0;
}
.list-clean li + li {
  margin-top: 0.5rem;
}
.graph-layout {
  display: grid;
  grid-template-columns: 2.2fr 1fr;
  gap: 1rem;
}
.graph-stage {
  min-height: 36rem;
  padding: 0.25rem;
}
.graph-stage svg {
  width: 100%;
  height: 34rem;
  display: block;
  border-radius: 14px;
  background:
    radial-gradient(circle at top left, rgba(13, 107, 95, 0.08), transparent 18rem),
    linear-gradient(180deg, #fffdfa 0%, #f5f1e7 100%);
  border: 1px solid var(--line);
}
.graph-controls {
  display: grid;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.graph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
}
.graph-legend span::before {
  content: "";
  display: inline-block;
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 999px;
  margin-right: 0.4rem;
  vertical-align: middle;
}
.legend-seed::before { background: #0d6b5f; }
.legend-local::before { background: #c67f27; }
.legend-neighbor::before { background: #8d98a7; }
.graph-meta {
  display: grid;
  gap: 0.75rem;
}
.graph-card {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0.9rem 1rem;
  background: rgba(255,255,255,0.65);
}
.graph-card h3 {
  margin-top: 0;
}
.graph-node text {
  font-size: 11px;
  fill: #243126;
  pointer-events: none;
}
.graph-node circle {
  stroke: rgba(31, 36, 31, 0.15);
  stroke-width: 1.5px;
}
.graph-edge {
  stroke: rgba(92, 100, 92, 0.35);
  stroke-width: 1.3px;
}
.graph-edge.is-faded,
.graph-node.is-faded {
  opacity: 0.18;
}
.graph-node.is-active circle {
  stroke: #0d6b5f;
  stroke-width: 3px;
}
.graph-node.is-related circle {
  stroke: #c67f27;
  stroke-width: 2.5px;
}
@media (max-width: 800px) {
  .split {
    grid-template-columns: 1fr;
  }
  .graph-layout {
    grid-template-columns: 1fr;
  }
}
"""


def _grobid_artifact(grobid_root: Path, key: str, repo_root: Path) -> dict[str, Any]:
    header_path = grobid_root / key / "header.json"
    refs_path = grobid_root / key / "references.json"
    exists = header_path.exists()
    return {
        "exists": exists,
        "path": _safe_rel(header_path, repo_root) if exists else None,
        "references_path": _safe_rel(refs_path, repo_root) if refs_path.exists() else None,
    }


def _load_grobid_data(grobid_root: Path, key: str) -> dict[str, Any]:
    header_path = grobid_root / key / "header.json"
    refs_path = grobid_root / key / "references.json"
    header: dict[str, Any] = {}
    ref_count = 0
    if header_path.exists():
        try:
            header = json.loads(header_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if refs_path.exists():
        try:
            ref_count = len(json.loads(refs_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {"header": header, "reference_count": ref_count}


def _build_site_model(cfg: BiblioConfig, options: BiblioSiteOptions) -> dict[str, Any]:
    repo_root = cfg.repo_root.resolve()
    citekeys = load_citekeys_md(cfg.citekeys_path) if cfg.citekeys_path.exists() else []
    source_records = _iter_srcbib_records(cfg)
    source_by_key: dict[str, list[dict[str, Any]]] = {}
    for record in source_records:
        source_by_key.setdefault(str(record["citekey"]), []).append(record)

    from .grobid import grobid_out_root, local_refs_path
    from .library import load_library
    docling_dirs = {p.name: p for p in sorted(cfg.out_root.glob("*")) if p.is_dir()}
    grobid_root = grobid_out_root(cfg)
    _lr_path = local_refs_path(cfg)
    grobid_local_refs: dict[str, list[dict[str, Any]]] = (
        json.loads(_lr_path.read_text(encoding="utf-8")) if _lr_path.exists() else {}
    )
    lib_entries = load_library(cfg)
    openalex_rows = _load_jsonl(cfg.openalex.out_jsonl) if options.include_openalex else []
    openalex_by_key = {str(row.get("citekey")): row for row in openalex_rows if row.get("citekey")}

    graph_candidates_path = cfg.openalex.out_jsonl.parent / "graph_candidates.json"
    graph_candidates: list[dict[str, Any]] = []
    if options.include_graphs and graph_candidates_path.exists():
        payload = json.loads(graph_candidates_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            graph_candidates = [item for item in payload if isinstance(item, dict)]

    all_keys = set(citekeys) | set(source_by_key) | set(docling_dirs) | set(openalex_by_key)
    papers: list[dict[str, Any]] = []
    orphan_docling: list[str] = []

    openalex_seed_to_citekey = {
        str(row.get("openalex_id")): str(row.get("citekey"))
        for row in openalex_rows
        if row.get("openalex_id") and row.get("citekey")
    }

    for citekey in sorted(all_keys):
        source_list = source_by_key.get(citekey, [])
        primary = source_list[0] if source_list else None
        pdf_rel = Path(cfg.pdf_pattern.format(citekey=citekey))
        pdf_path = (cfg.pdf_root / pdf_rel).resolve()
        docling_dir = docling_dirs.get(citekey)
        md_path = docling_dir / f"{citekey}.md" if docling_dir else None
        json_path = docling_dir / f"{citekey}.json" if docling_dir else None
        meta_path = docling_dir / "_biblio.json" if docling_dir else None
        docling_text = ""
        if options.include_docling and md_path and md_path.exists():
            docling_text = md_path.read_text(encoding="utf-8", errors="replace")
        extras = _find_optional_derivatives(docling_dir) if docling_dir else {"notes": [], "summaries": []}
        openalex_row = openalex_by_key.get(citekey)
        seed_id = str(openalex_row.get("openalex_id")) if openalex_row and openalex_row.get("openalex_id") else None
        outgoing: list[dict[str, Any]] = []
        incoming: list[dict[str, Any]] = []
        if options.include_graphs and seed_id:
            for item in graph_candidates:
                if str(item.get("seed_openalex_id")) == seed_id and str(item.get("direction") or "references") == "references":
                    target_id = str(item.get("openalex_id") or "")
                    outgoing.append(
                        {
                            "openalex_id": target_id,
                            "openalex_url": item.get("openalex_url"),
                            "citekey": openalex_seed_to_citekey.get(target_id),
                            "title": item.get("display_name"),
                            "year": item.get("publication_year"),
                            "doi": item.get("doi"),
                            "cited_by_count": item.get("cited_by_count"),
                            "direction": "references",
                        }
                    )
                if str(item.get("seed_openalex_id")) == seed_id and str(item.get("direction") or "") == "citing":
                    source_id = str(item.get("openalex_id") or "")
                    incoming.append(
                        {
                            "openalex_id": source_id,
                            "openalex_url": item.get("openalex_url") or (f"https://openalex.org/{source_id}" if source_id else None),
                            "citekey": openalex_seed_to_citekey.get(source_id),
                            "title": item.get("display_name"),
                            "year": item.get("publication_year"),
                            "doi": item.get("doi"),
                            "cited_by_count": item.get("cited_by_count"),
                            "direction": "citing",
                        }
                    )

        paper = {
            "citekey": citekey,
            "title": (primary or {}).get("title") or (openalex_row or {}).get("display_name") or citekey,
            "year": (primary or {}).get("year") or (openalex_row or {}).get("publication_year"),
            "doi": (primary or {}).get("doi") or (openalex_row or {}).get("doi"),
            "authors": (primary or {}).get("authors") or [],
            "source_bibs": sorted({str(item["source_bib"]) for item in source_list}),
            "configured": citekey in citekeys,
            "artifacts": {
                "pdf": {
                    "exists": pdf_path.exists(),
                    "path": _safe_rel(pdf_path, repo_root) if pdf_path.exists() else None,
                },
                "docling_md": {
                    "exists": bool(md_path and md_path.exists()),
                    "path": _safe_rel(md_path, repo_root) if md_path and md_path.exists() else None,
                },
                "docling_json": {
                    "exists": bool(json_path and json_path.exists()),
                    "path": _safe_rel(json_path, repo_root) if json_path and json_path.exists() else None,
                },
                "docling_meta": {
                    "exists": bool(meta_path and meta_path.exists()),
                    "path": _safe_rel(meta_path, repo_root) if meta_path and meta_path.exists() else None,
                },
                "openalex": {
                    "exists": openalex_row is not None,
                    "path": _safe_rel(cfg.openalex.out_jsonl, repo_root) if openalex_row is not None else None,
                },
                "grobid": _grobid_artifact(grobid_root, citekey, repo_root),
                "notes": [
                    {"path": _safe_rel(path, repo_root), "name": path.name}
                    for path in extras["notes"]
                ],
                "summaries": [
                    {"path": _safe_rel(path, repo_root), "name": path.name}
                    for path in extras["summaries"]
                ],
            },
            "docling": {
                "html": _minimal_markdown_to_html(
                    docling_text,
                    image_url_prefix=f"/api/files/docling/{citekey}",
                ) if docling_text else "",
                "excerpt": "\n".join(docling_text.splitlines()[:20]).strip(),
            },
            "grobid": _load_grobid_data(grobid_root, citekey),
            "library": lib_entries.get(citekey, {}),
            "openalex": openalex_row,
            "graph": {
                "seed_openalex_id": seed_id,
                "outgoing": outgoing,
                "incoming": incoming,
                "grobid_refs": grobid_local_refs.get(citekey, []),
            },
        }
        papers.append(paper)
        if citekey in docling_dirs and not source_list and citekey not in citekeys:
            orphan_docling.append(citekey)

    papers.sort(key=lambda item: (str(item["year"] or ""), str(item["citekey"])))

    status = {
        "papers_total": len(papers),
        "configured_citekeys": len(citekeys),
        "source_bib_entries": len(source_records),
        "papers_with_pdf": sum(1 for paper in papers if paper["artifacts"]["pdf"]["exists"]),
        "papers_with_docling": sum(1 for paper in papers if paper["artifacts"]["docling_md"]["exists"]),
        "papers_with_openalex": sum(1 for paper in papers if paper["artifacts"]["openalex"]["exists"]),
        "papers_with_grobid": sum(1 for paper in papers if paper["artifacts"]["grobid"]["exists"]),
        "missing_pdf": sorted(paper["citekey"] for paper in papers if not paper["artifacts"]["pdf"]["exists"]),
        "missing_docling": sorted(paper["citekey"] for paper in papers if not paper["artifacts"]["docling_md"]["exists"]),
        "missing_openalex": sorted(paper["citekey"] for paper in papers if not paper["artifacts"]["openalex"]["exists"]),
        "orphan_docling": sorted(orphan_docling),
    }

    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    if options.include_graphs:
        seen_nodes: set[str] = set()
        edge_pairs: set[tuple[str, str]] = set()
        for paper in papers:
            node_id = f"paper:{paper['citekey']}"
            if node_id not in seen_nodes:
                seen_nodes.add(node_id)
                graph_nodes.append(
                    {
                        "id": node_id,
                        "citekey": paper["citekey"],
                        "label": paper["title"],
                        "openalex_id": paper["graph"]["seed_openalex_id"],
                        "kind": "seed",
                        "is_local": True,
                        "year": paper.get("year"),
                        "cited_by": (paper.get("openalex") or {}).get("cited_by_count"),
                    }
                )
            for neighbor in paper["graph"]["outgoing"]:
                target_citekey = neighbor.get("citekey")
                target_id = f"paper:{target_citekey}" if target_citekey else f"openalex:{neighbor['openalex_id']}"
                if target_id not in seen_nodes:
                    seen_nodes.add(target_id)
                    graph_nodes.append(
                        {
                            "id": target_id,
                            "citekey": target_citekey,
                            "label": neighbor.get("citekey") or neighbor["openalex_id"],
                            "openalex_id": neighbor["openalex_id"],
                            "title": neighbor.get("title"),
                            "year": neighbor.get("year"),
                            "doi": neighbor.get("doi"),
                            "kind": "local_seed" if target_citekey else "neighbor",
                            "is_local": bool(target_citekey),
                            "cited_by": neighbor.get("cited_by_count"),
                        }
                    )
                edge_key = (node_id, target_id)
                if edge_key not in edge_pairs:
                    edge_pairs.add(edge_key)
                    graph_edges.append(
                        {
                            "source": node_id,
                            "target": target_id,
                            "kind": "references",
                            "source_citekey": paper["citekey"],
                            "target_citekey": target_citekey,
                            "target_openalex_id": neighbor["openalex_id"],
                            "direction": "references",
                        }
                    )
            for neighbor in paper["graph"]["incoming"]:
                source_citekey = neighbor.get("citekey")
                source_id = f"paper:{source_citekey}" if source_citekey else f"openalex:{neighbor['openalex_id']}"
                if source_id not in seen_nodes:
                    seen_nodes.add(source_id)
                    graph_nodes.append(
                        {
                            "id": source_id,
                            "citekey": source_citekey,
                            "label": neighbor.get("citekey") or neighbor["openalex_id"],
                            "openalex_id": neighbor["openalex_id"],
                            "title": neighbor.get("title"),
                            "year": neighbor.get("year"),
                            "doi": neighbor.get("doi"),
                            "kind": "local_seed" if source_citekey else "neighbor",
                            "is_local": bool(source_citekey),
                            "cited_by": neighbor.get("cited_by_count"),
                        }
                    )
                edge_key = (source_id, node_id)
                if edge_key not in edge_pairs:
                    edge_pairs.add(edge_key)
                    graph_edges.append(
                        {
                            "source": source_id,
                            "target": node_id,
                            "kind": "cites",
                            "source_citekey": source_citekey,
                            "target_citekey": paper["citekey"],
                            "source_openalex_id": neighbor["openalex_id"],
                            "direction": "citing",
                        }
                    )

    # Add grobid_ref edges to the graph (always local-to-local)
    if options.include_graphs:
        for paper in papers:
            src_id = f"paper:{paper['citekey']}"
            for ref in paper["graph"]["grobid_refs"]:
                tgt_ck = str(ref.get("target_citekey") or "")
                if not tgt_ck:
                    continue
                tgt_id = f"paper:{tgt_ck}"
                if tgt_id not in seen_nodes:
                    seen_nodes.add(tgt_id)
                    graph_nodes.append({
                        "id": tgt_id,
                        "citekey": tgt_ck,
                        "label": tgt_ck,
                        "openalex_id": None,
                        "kind": "local_seed",
                        "is_local": True,
                    })
                edge_key = (src_id, tgt_id)
                if edge_key not in edge_pairs:
                    edge_pairs.add(edge_key)
                    graph_edges.append({
                        "source": src_id,
                        "target": tgt_id,
                        "kind": "grobid_ref",
                        "source_citekey": paper["citekey"],
                        "target_citekey": tgt_ck,
                        "match_type": ref.get("match_type"),
                        "direction": "references",
                    })

    node_by_id = {node["id"]: node for node in graph_nodes}
    outgoing_local_by_seed: dict[str, set[str]] = {}
    incoming_local_by_seed: dict[str, set[str]] = {}
    for paper in papers:
        grobid_outgoing = {
            str(ref["target_citekey"])
            for ref in paper["graph"]["grobid_refs"]
            if ref.get("target_citekey")
        }
        outgoing_local_by_seed[paper["citekey"]] = grobid_outgoing | {
            str(item["citekey"])
            for item in paper["graph"]["outgoing"]
            if item.get("citekey")
        }
        incoming_local_by_seed[paper["citekey"]] = {
            str(item["citekey"])
            for item in paper["graph"]["incoming"]
            if item.get("citekey")
        }

    related_by_seed: dict[str, list[dict[str, Any]]] = {}
    for paper in papers:
        related: list[dict[str, Any]] = []
        a = str(paper["citekey"])
        for other in papers:
            b = str(other["citekey"])
            if a == b:
                continue
            shared_out = len(outgoing_local_by_seed[a] & outgoing_local_by_seed[b])
            shared_in = len(incoming_local_by_seed[a] & incoming_local_by_seed[b])
            direct = int(b in outgoing_local_by_seed[a]) + int(b in incoming_local_by_seed[a])
            score = shared_out * 2 + shared_in + direct * 3
            if score <= 0:
                continue
            related.append(
                {
                    "citekey": b,
                    "title": other["title"],
                    "score": score,
                    "shared_outgoing": shared_out,
                    "shared_incoming": shared_in,
                    "direct_links": direct,
                }
            )
        related.sort(key=lambda item: (-int(item["score"]), str(item["citekey"])))
        related_by_seed[a] = related[:8]

    degrees: dict[str, int] = {node["id"]: 0 for node in graph_nodes}
    for edge in graph_edges:
        degrees[edge["source"]] = degrees.get(edge["source"], 0) + 1
        degrees[edge["target"]] = degrees.get(edge["target"], 0) + 1
    for node in graph_nodes:
        node["degree"] = degrees.get(node["id"], 0)

    graph_papers = [
        {
            "citekey": paper["citekey"],
            "title": paper["title"],
            "graph": paper["graph"],
            "related_local": related_by_seed.get(str(paper["citekey"]), []),
        }
        for paper in papers
    ]

    return {
        "papers": papers,
        "artifacts": [
            {"citekey": paper["citekey"], **paper["artifacts"]}
            for paper in papers
        ],
        "status": status,
        "graph": {"nodes": graph_nodes, "edges": graph_edges, "papers": graph_papers},
    }


def doctor_biblio_site(
    cfg: BiblioConfig,
    *,
    options: BiblioSiteOptions | None = None,
    config_path: str | Path | None = None,
) -> BiblioSiteDoctorReport:
    site_options = options or BiblioSiteOptions(out_dir=default_site_out_dir(root=cfg.repo_root))
    model = _build_site_model(cfg, site_options)
    status = model["status"]
    warnings: list[str] = []
    if not cfg.citekeys_path.exists():
        warnings.append(f"Missing citekeys file: {cfg.citekeys_path}")
    if not cfg.bibtex_merge.src_dir.exists():
        warnings.append(f"Missing srcbib directory: {cfg.bibtex_merge.src_dir}")
    if status["missing_pdf"]:
        warnings.append(f"Missing PDFs for {len(status['missing_pdf'])} papers.")
    if status["missing_docling"]:
        warnings.append(f"Missing Docling outputs for {len(status['missing_docling'])} papers.")
    if site_options.include_openalex and status["missing_openalex"]:
        warnings.append(f"Missing OpenAlex records for {len(status['missing_openalex'])} papers.")
    if status["orphan_docling"]:
        warnings.append(f"Found {len(status['orphan_docling'])} orphan Docling directories.")
    return BiblioSiteDoctorReport(
        config_path=Path(config_path).resolve() if config_path is not None else cfg.repo_root / "bib" / "config" / "biblio.yml",
        repo_root=cfg.repo_root.resolve(),
        out_dir=site_options.out_dir.resolve(),
        papers_total=int(status["papers_total"]),
        configured_citekeys=int(status["configured_citekeys"]),
        source_bib_entries=int(status["source_bib_entries"]),
        papers_with_pdf=int(status["papers_with_pdf"]),
        papers_with_docling=int(status["papers_with_docling"]),
        papers_with_openalex=int(status["papers_with_openalex"]),
        missing_pdf=len(status["missing_pdf"]),
        missing_docling=len(status["missing_docling"]),
        missing_openalex=len(status["missing_openalex"]),
        orphan_docling=list(status["orphan_docling"]),
        warnings=warnings,
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _render_index_page(model: dict[str, Any]) -> str:
    status = model["status"]
    body = f"""
<section class="hero">
  <p class="small">Standalone bibliography explorer generated by <span class="mono">biblio site build</span>.</p>
  <div class="grid cols-3">
    <div class="metric"><span class="small">papers</span><strong>{status['papers_total']}</strong></div>
    <div class="metric"><span class="small">Docling ready</span><strong>{status['papers_with_docling']}</strong></div>
    <div class="metric"><span class="small">OpenAlex resolved</span><strong>{status['papers_with_openalex']}</strong></div>
  </div>
</section>
<section class="grid cols-3">
  <article class="panel">
    <h2>Browse papers</h2>
    <p>Search the corpus, inspect artifact coverage, and open per-paper pages.</p>
    <p><a href="./papers/index.html">Open corpus index</a></p>
  </article>
  <article class="panel">
    <h2>Status</h2>
    <p>Find missing PDFs, missing Docling outputs, unresolved OpenAlex records, and orphan derivatives.</p>
    <p><a href="./status.html">Open status view</a></p>
  </article>
  <article class="panel">
    <h2>Graph</h2>
    <p>Inspect local neighborhood relationships built from OpenAlex seed papers and graph candidates.</p>
    <p><a href="./graph.html">Open graph view</a></p>
  </article>
</section>
"""
    return _page_shell("Bibliography Portal", body)


def _render_papers_index(model: dict[str, Any]) -> str:
    rows = []
    for paper in model["papers"]:
        badges = []
        badges.append('<span class="badge">pdf</span>' if paper["artifacts"]["pdf"]["exists"] else '<span class="badge muted">no pdf</span>')
        badges.append('<span class="badge">docling</span>' if paper["artifacts"]["docling_md"]["exists"] else '<span class="badge muted">no docling</span>')
        badges.append('<span class="badge">openalex</span>' if paper["artifacts"]["openalex"]["exists"] else '<span class="badge muted">no openalex</span>')
        rows.append(
            f"<tr data-search=\"{escape((paper['citekey'] + ' ' + paper['title']).lower())}\">"
            f"<td><a href=\"./{escape(paper['citekey'])}.html\">{escape(paper['citekey'])}</a></td>"
            f"<td>{escape(str(paper['title']))}</td>"
            f"<td>{escape(', '.join(paper['authors']) or '-')}</td>"
            f"<td>{escape(str(paper['year'] or '-'))}</td>"
            f"<td>{''.join(badges)}</td>"
            "</tr>"
        )
    body = f"""
<section class="panel">
  <p class="small">Filter by citekey or title.</p>
  <input id="paper-search" class="search" type="search" placeholder="Search papers...">
</section>
<section class="panel">
  <table class="paper-table" id="papers-table">
    <thead>
      <tr><th>Citekey</th><th>Title</th><th>Authors</th><th>Year</th><th>Artifacts</th></tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</section>
<script>
const input = document.getElementById("paper-search");
const rows = Array.from(document.querySelectorAll("#papers-table tbody tr"));
input.addEventListener("input", () => {{
  const q = input.value.trim().toLowerCase();
  rows.forEach((row) => {{
    const hay = row.getAttribute("data-search") || "";
    row.style.display = !q || hay.includes(q) ? "" : "none";
  }});
}});
</script>
"""
    return _page_shell("Papers", body, root_prefix="..")


def _repo_link(repo_root: Path, page_path: Path, rel_path: str | None, label: str) -> str:
    if not rel_path:
        return "<span class=\"small\">-</span>"
    href = _safe_rel((repo_root / rel_path).resolve(), page_path.parent.resolve())
    return f"<a href=\"{escape(href)}\">{escape(label)}</a>"


def _render_paper_page(repo_root: Path, paper: dict[str, Any], out_path: Path) -> str:
    artifacts = paper["artifacts"]
    notes = "".join(
        f"<li>{_repo_link(repo_root, out_path, item['path'], item['name'])}</li>"
        for item in artifacts["notes"]
    ) or "<li class=\"small\">No notes discovered.</li>"
    summaries = "".join(
        f"<li>{_repo_link(repo_root, out_path, item['path'], item['name'])}</li>"
        for item in artifacts["summaries"]
    ) or "<li class=\"small\">No summaries discovered.</li>"
    outgoing = "".join(
        f"<li>{escape(item.get('citekey') or item['openalex_id'])}</li>"
        for item in paper["graph"]["outgoing"]
    ) or "<li class=\"small\">No outgoing neighbors recorded.</li>"
    incoming = "".join(
        f"<li>{escape(item.get('citekey') or item['openalex_id'])}</li>"
        for item in paper["graph"]["incoming"]
    ) or "<li class=\"small\">No incoming neighbors recorded.</li>"

    body = f"""
<section class="panel">
  <p class="small mono">@{escape(paper['citekey'])}</p>
  <h2>{escape(str(paper['title']))}</h2>
  <p>{escape(', '.join(paper['authors']) or 'Unknown authors')}</p>
  <table class="kv-table">
    <tr><th>Year</th><td>{escape(str(paper['year'] or '-'))}</td></tr>
    <tr><th>DOI</th><td>{escape(str(paper['doi'] or '-'))}</td></tr>
    <tr><th>Source bib files</th><td>{escape(', '.join(paper['source_bibs']) or '-')}</td></tr>
    <tr><th>PDF</th><td>{_repo_link(repo_root, out_path, artifacts['pdf']['path'], 'Open PDF') if artifacts['pdf']['exists'] else '<span class="small">Missing</span>'}</td></tr>
    <tr><th>Docling markdown</th><td>{_repo_link(repo_root, out_path, artifacts['docling_md']['path'], 'Open markdown') if artifacts['docling_md']['exists'] else '<span class="small">Missing</span>'}</td></tr>
    <tr><th>Docling JSON</th><td>{_repo_link(repo_root, out_path, artifacts['docling_json']['path'], 'Open JSON') if artifacts['docling_json']['exists'] else '<span class="small">Missing</span>'}</td></tr>
    <tr><th>OpenAlex</th><td>{escape(str((paper['openalex'] or {}).get('openalex_url') or (paper['openalex'] or {}).get('openalex_id') or '-'))}</td></tr>
  </table>
</section>
<section class="split">
  <article class="panel docling">
    <h3>Docling content</h3>
    {paper['docling']['html'] or '<p class="small">No Docling markdown available.</p>'}
  </article>
  <aside class="grid">
    <article class="panel">
      <h3>Summaries</h3>
      <ul class="list-clean">{summaries}</ul>
    </article>
    <article class="panel">
      <h3>Notes</h3>
      <ul class="list-clean">{notes}</ul>
    </article>
    <article class="panel">
      <h3>Graph neighborhood</h3>
      <p class="small">Outgoing references from this paper.</p>
      <ul class="list-clean">{outgoing}</ul>
      <p class="small">Incoming links from other local seed papers.</p>
      <ul class="list-clean">{incoming}</ul>
    </article>
  </aside>
</section>
"""
    return _page_shell(f"Paper: {paper['citekey']}", body, root_prefix="..")


def _render_status_page(model: dict[str, Any]) -> str:
    status = model["status"]
    body = f"""
<section class="grid cols-3">
  <div class="metric"><span class="small">Missing PDFs</span><strong>{len(status['missing_pdf'])}</strong></div>
  <div class="metric"><span class="small">Missing Docling</span><strong>{len(status['missing_docling'])}</strong></div>
  <div class="metric"><span class="small">Missing OpenAlex</span><strong>{len(status['missing_openalex'])}</strong></div>
</section>
<section class="grid cols-3">
  <article class="panel"><h2>Missing PDFs</h2><ul class="list-clean">{''.join(f'<li>{escape(item)}</li>' for item in status['missing_pdf']) or '<li class="small">None</li>'}</ul></article>
  <article class="panel"><h2>Missing Docling</h2><ul class="list-clean">{''.join(f'<li>{escape(item)}</li>' for item in status['missing_docling']) or '<li class="small">None</li>'}</ul></article>
  <article class="panel"><h2>Missing OpenAlex</h2><ul class="list-clean">{''.join(f'<li>{escape(item)}</li>' for item in status['missing_openalex']) or '<li class="small">None</li>'}</ul></article>
</section>
<section class="panel">
  <h2>Orphan Docling directories</h2>
  <ul class="list-clean">{''.join(f'<li>{escape(item)}</li>' for item in status['orphan_docling']) or '<li class="small">None</li>'}</ul>
</section>
"""
    return _page_shell("Status", body)


def _render_graph_page() -> str:
    body = """
<section class="panel">
  <div class="graph-controls">
    <div>
      <p class="small">Select a seed paper to inspect its immediate local neighborhood.</p>
      <select id="graph-paper" class="search"></select>
    </div>
    <label class="small"><input id="graph-only-local" type="checkbox"> Focus on local papers only</label>
  </div>
  <div class="graph-legend small">
    <span class="legend-seed">active seed</span>
    <span class="legend-local">local related paper</span>
    <span class="legend-neighbor">external OpenAlex neighbor</span>
  </div>
</section>
<section class="graph-layout">
  <article class="panel graph-stage">
    <svg id="graph-canvas" viewBox="0 0 920 540" role="img" aria-label="Local paper graph"></svg>
  </article>
  <aside class="graph-meta">
    <article class="panel graph-card">
      <h3 id="graph-title">Graph focus</h3>
      <p id="graph-summary" class="small">Select a paper to explore.</p>
    </article>
    <article class="panel graph-card">
      <h3>Outgoing references</h3>
      <ul id="graph-outgoing" class="list-clean"></ul>
    </article>
    <article class="panel graph-card">
      <h3>Incoming references</h3>
      <ul id="graph-incoming" class="list-clean"></ul>
    </article>
    <article class="panel graph-card">
      <h3>Related local papers</h3>
      <ul id="graph-related" class="list-clean"></ul>
    </article>
  </aside>
</section>
<script>
fetch("./_data/graph.json").then((resp) => resp.json()).then((graph) => {
  const select = document.getElementById("graph-paper");
  const onlyLocal = document.getElementById("graph-only-local");
  const outgoingEl = document.getElementById("graph-outgoing");
  const incomingEl = document.getElementById("graph-incoming");
  const relatedEl = document.getElementById("graph-related");
  const titleEl = document.getElementById("graph-title");
  const summaryEl = document.getElementById("graph-summary");
  const svg = document.getElementById("graph-canvas");
  const papers = (graph.papers || []).filter((paper) => paper.graph && paper.graph.seed_openalex_id);
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const seedNodeByCitekey = new Map(nodes.filter((node) => node.citekey).map((node) => [node.citekey, node]));
  papers.forEach((paper) => {
    const opt = document.createElement("option");
    opt.value = paper.citekey;
    opt.textContent = `${paper.citekey} — ${paper.title}`;
    select.appendChild(opt);
  });

  const width = 920;
  const height = 540;
  const centerX = width / 2;
  const centerY = height / 2;

  function buildSubgraph(paper) {
    if (!paper) return {nodes: [], edges: []};
    const localOnly = onlyLocal.checked;
    const paperNode = seedNodeByCitekey.get(paper.citekey);
    const neighborIds = new Set();
    (paper.graph.outgoing || []).forEach((item) => {
      if (localOnly && !item.citekey) return;
      neighborIds.add(item.citekey ? `paper:${item.citekey}` : `openalex:${item.openalex_id}`);
    });
    (paper.related_local || []).forEach((item) => neighborIds.add(`paper:${item.citekey}`));
    const nodeIds = new Set([paperNode ? paperNode.id : `paper:${paper.citekey}`, ...neighborIds]);
    const subNodes = nodes.filter((node) => nodeIds.has(node.id));
    const subEdges = edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
    return {nodes: subNodes, edges: subEdges};
  }

  function layoutNodes(subgraph, activeCitekey, relatedCitekeys) {
    const activeId = `paper:${activeCitekey}`;
    const relatedSet = new Set(relatedCitekeys.map((item) => `paper:${item.citekey}`));
    const active = subgraph.nodes.find((node) => node.id === activeId);
    const others = subgraph.nodes.filter((node) => node.id !== activeId);
    if (active) {
      active.x = centerX;
      active.y = centerY;
    }
    const local = others.filter((node) => node.is_local);
    const external = others.filter((node) => !node.is_local);
    local.forEach((node, idx) => {
      const angle = (Math.PI * 2 * idx) / Math.max(local.length, 1);
      node.x = centerX + Math.cos(angle) * 160;
      node.y = centerY + Math.sin(angle) * 150;
    });
    external.forEach((node, idx) => {
      const angle = (Math.PI * 2 * idx) / Math.max(external.length, 1);
      node.x = centerX + Math.cos(angle) * 280;
      node.y = centerY + Math.sin(angle) * 220;
    });
    return {activeId, relatedSet};
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function renderGraph(subgraph, activeId, relatedSet) {
    const edgeMarkup = subgraph.edges.map((edge) => {
      const source = subgraph.nodes.find((node) => node.id === edge.source);
      const target = subgraph.nodes.find((node) => node.id === edge.target);
      if (!source || !target) return "";
      const isConnected = edge.source === activeId || edge.target === activeId || relatedSet.has(edge.source) || relatedSet.has(edge.target);
      return `<line class="graph-edge${isConnected ? "" : " is-faded"}" x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}"></line>`;
    }).join("");
    const nodeMarkup = subgraph.nodes.map((node) => {
      const radius = node.id === activeId ? 18 : (node.is_local ? 13 : 10);
      const fill = node.id === activeId ? "#0d6b5f" : (node.is_local ? "#cf9b55" : "#97a1af");
      const cls = [
        "graph-node",
        node.id === activeId ? "is-active" : "",
        relatedSet.has(node.id) ? "is-related" : "",
        (node.id === activeId || relatedSet.has(node.id)) ? "" : "is-faded",
      ].filter(Boolean).join(" ");
      return `
        <g class="${cls}" transform="translate(${node.x}, ${node.y})">
          <circle r="${radius}" fill="${fill}"></circle>
          <text x="0" y="${radius + 16}" text-anchor="middle">${escapeHtml(node.citekey || node.label)}</text>
        </g>
      `;
    }).join("");
    svg.innerHTML = `<g>${edgeMarkup}${nodeMarkup}</g>`;
  }

  function render() {
    const paper = papers.find((item) => item.citekey === select.value) || papers[0];
    if (!paper) {
      titleEl.textContent = "Graph focus";
      summaryEl.textContent = "No graph data available.";
      outgoingEl.innerHTML = '<li class="small">No graph data available.</li>';
      incomingEl.innerHTML = '<li class="small">No graph data available.</li>';
      relatedEl.innerHTML = '<li class="small">No graph data available.</li>';
      svg.innerHTML = "";
      return;
    }
    titleEl.textContent = `${paper.citekey} — ${paper.title}`;
    summaryEl.textContent = `${(paper.graph.outgoing || []).length} outgoing references, ${(paper.graph.incoming || []).length} incoming local links, ${(paper.related_local || []).length} related local papers.`;
    outgoingEl.innerHTML = (paper.graph.outgoing || []).map((item) => `<li>${escapeHtml(item.citekey || item.openalex_id)}</li>`).join("") || '<li class="small">No outgoing neighbors.</li>';
    incomingEl.innerHTML = (paper.graph.incoming || []).map((item) => `<li>${escapeHtml(item.citekey || item.openalex_id)}</li>`).join("") || '<li class="small">No incoming neighbors.</li>';
    relatedEl.innerHTML = (paper.related_local || []).map((item) => `<li><strong>${escapeHtml(item.citekey)}</strong> <span class="small">score ${item.score}, shared outgoing ${item.shared_outgoing}, shared incoming ${item.shared_incoming}</span></li>`).join("") || '<li class="small">No related local papers yet.</li>';
    const subgraph = buildSubgraph(paper);
    const layout = layoutNodes(subgraph, paper.citekey, paper.related_local || []);
    renderGraph(subgraph, layout.activeId, layout.relatedSet);
  }
  select.addEventListener("change", render);
  onlyLocal.addEventListener("change", render);
  render();
});
</script>
"""
    return _page_shell("Graph", body)


def build_biblio_site(
    cfg: BiblioConfig,
    *,
    options: BiblioSiteOptions | None = None,
    force: bool = False,
    config_path: str | Path | None = None,
) -> BiblioSiteBuildResult:
    site_options = options or BiblioSiteOptions(out_dir=default_site_out_dir(root=cfg.repo_root))
    out_dir = site_options.out_dir.resolve()
    _ensure_safe_out_dir(cfg.repo_root.resolve(), out_dir)
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"Site output already exists: {out_dir} (use --force to rebuild)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model = _build_site_model(cfg, site_options)
    doctor = doctor_biblio_site(cfg, options=site_options, config_path=config_path)

    data_dir = out_dir / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_text(out_dir / "style.css", _render_style())
    _write_text(out_dir / "index.html", _render_index_page(model))
    _write_text(out_dir / "papers" / "index.html", _render_papers_index(model))
    _write_text(out_dir / "status.html", _render_status_page(model))
    _write_text(out_dir / "graph.html", _render_graph_page())

    for paper in model["papers"]:
        page_path = out_dir / "papers" / f"{paper['citekey']}.html"
        _write_text(page_path, _render_paper_page(cfg.repo_root.resolve(), paper, page_path))

    data_files = {
        "papers.json": model["papers"],
        "artifacts.json": model["artifacts"],
        "status.json": model["status"],
        "graph.json": model["graph"],
    }
    for name, payload in data_files.items():
        _write_text(data_dir / name, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    return BiblioSiteBuildResult(
        out_dir=out_dir,
        papers_total=len(model["papers"]),
        pages_written=4 + len(model["papers"]),
        data_files_written=len(data_files),
        doctor=doctor,
    )


def clean_biblio_site(repo_root: str | Path, out_dir: str | Path | None = None) -> Path:
    repo_root = Path(repo_root).expanduser().resolve()
    target = Path(out_dir).expanduser().resolve() if out_dir is not None else default_site_out_dir(root=repo_root)
    _ensure_safe_out_dir(repo_root, target)
    if target.exists():
        shutil.rmtree(target)
    return target


def serve_biblio_site(out_dir: str | Path, *, port: int = 8008) -> None:
    root = Path(out_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Site directory does not exist: {root}")

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

    with ThreadingHTTPServer(("0.0.0.0", int(port)), Handler) as server:
        print(f"[OK] serving {root} at http://127.0.0.1:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[OK] stopped")
