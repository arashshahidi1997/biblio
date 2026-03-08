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

    from pybtex.database import parse_file

    records: list[dict[str, Any]] = []
    for bib_path in bib_files:
        db = parse_file(str(bib_path))
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


def _minimal_markdown_to_html(text: str) -> str:
    blocks: list[str] = []
    lines = text.splitlines()
    in_code = False
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            joined = " ".join(part.strip() for part in paragraph if part.strip())
            if joined:
                blocks.append(f"<p>{escape(joined)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            items = "".join(f"<li>{escape(item)}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items = []

    code_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if line.strip().startswith("```"):
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
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h3>{escape(line[4:].strip())}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h2>{escape(line[3:].strip())}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            blocks.append(f"<h1>{escape(line[2:].strip())}</h1>")
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
@media (max-width: 800px) {
  .split {
    grid-template-columns: 1fr;
  }
}
"""


def _build_site_model(cfg: BiblioConfig, options: BiblioSiteOptions) -> dict[str, Any]:
    repo_root = cfg.repo_root.resolve()
    citekeys = load_citekeys_md(cfg.citekeys_path) if cfg.citekeys_path.exists() else []
    source_records = _iter_srcbib_records(cfg)
    source_by_key: dict[str, list[dict[str, Any]]] = {}
    for record in source_records:
        source_by_key.setdefault(str(record["citekey"]), []).append(record)

    docling_dirs = {p.name: p for p in sorted(cfg.out_root.glob("*")) if p.is_dir()}
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
                if str(item.get("seed_openalex_id")) == seed_id:
                    target_id = str(item.get("openalex_id") or "")
                    outgoing.append(
                        {
                            "openalex_id": target_id,
                            "openalex_url": item.get("openalex_url"),
                            "citekey": openalex_seed_to_citekey.get(target_id),
                        }
                    )
                if str(item.get("openalex_id")) == seed_id:
                    source_id = str(item.get("seed_openalex_id") or "")
                    incoming.append(
                        {
                            "openalex_id": source_id,
                            "openalex_url": f"https://openalex.org/{source_id}" if source_id else None,
                            "citekey": openalex_seed_to_citekey.get(source_id),
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
                "html": _minimal_markdown_to_html(docling_text) if docling_text else "",
                "excerpt": "\n".join(docling_text.splitlines()[:20]).strip(),
            },
            "openalex": openalex_row,
            "graph": {
                "seed_openalex_id": seed_id,
                "outgoing": outgoing,
                "incoming": incoming,
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
        "missing_pdf": sorted(paper["citekey"] for paper in papers if not paper["artifacts"]["pdf"]["exists"]),
        "missing_docling": sorted(paper["citekey"] for paper in papers if not paper["artifacts"]["docling_md"]["exists"]),
        "missing_openalex": sorted(paper["citekey"] for paper in papers if not paper["artifacts"]["openalex"]["exists"]),
        "orphan_docling": sorted(orphan_docling),
    }

    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    if options.include_graphs:
        seen_nodes: set[str] = set()
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
                    }
                )
            for neighbor in paper["graph"]["outgoing"]:
                target_id = f"openalex:{neighbor['openalex_id']}"
                if target_id not in seen_nodes:
                    seen_nodes.add(target_id)
                    graph_nodes.append(
                        {
                            "id": target_id,
                            "citekey": neighbor.get("citekey"),
                            "label": neighbor.get("citekey") or neighbor["openalex_id"],
                            "openalex_id": neighbor["openalex_id"],
                            "kind": "neighbor",
                        }
                    )
                graph_edges.append(
                    {
                        "source": node_id,
                        "target": target_id,
                        "kind": "references",
                    }
                )

    graph_papers = [
        {
            "citekey": paper["citekey"],
            "title": paper["title"],
            "graph": paper["graph"],
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
  <p class="small">Select a seed paper to inspect its immediate local neighborhood.</p>
  <select id="graph-paper" class="search"></select>
</section>
<section class="split">
  <article class="panel">
    <h2>Outgoing references</h2>
    <ul id="graph-outgoing" class="list-clean"></ul>
  </article>
  <article class="panel">
    <h2>Incoming references</h2>
    <ul id="graph-incoming" class="list-clean"></ul>
  </article>
</section>
<script>
fetch("./_data/graph.json").then((resp) => resp.json()).then((graph) => {
  const select = document.getElementById("graph-paper");
  const outgoingEl = document.getElementById("graph-outgoing");
  const incomingEl = document.getElementById("graph-incoming");
  const papers = (graph.papers || []).filter((paper) => paper.graph && paper.graph.seed_openalex_id);
  papers.forEach((paper) => {
    const opt = document.createElement("option");
    opt.value = paper.citekey;
    opt.textContent = `${paper.citekey} — ${paper.title}`;
    select.appendChild(opt);
  });
  function render() {
    const paper = papers.find((item) => item.citekey === select.value) || papers[0];
    if (!paper) {
      outgoingEl.innerHTML = '<li class="small">No graph data available.</li>';
      incomingEl.innerHTML = '<li class="small">No graph data available.</li>';
      return;
    }
    outgoingEl.innerHTML = (paper.graph.outgoing || []).map((item) => `<li>${item.citekey || item.openalex_id}</li>`).join("") || '<li class="small">No outgoing neighbors.</li>';
    incomingEl.innerHTML = (paper.graph.incoming || []).map((item) => `<li>${item.citekey || item.openalex_id}</li>`).join("") || '<li class="small">No incoming neighbors.</li>';
  }
  select.addEventListener("change", render);
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
