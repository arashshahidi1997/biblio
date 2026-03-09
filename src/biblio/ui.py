from __future__ import annotations

import importlib
import json
import socket
from pathlib import Path
from typing import Any

from .bibtex import merge_srcbib
from .config import BiblioConfig
from .docling import run_docling_for_key
from .graph import expand_openalex_reference_graph, load_openalex_seed_records
from .openalex.openalex_resolve import ResolveOptions, resolve_srcbib_to_openalex
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


def _index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>biblio ui</title>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
  <style>
    :root {
      --bg: #f5f1e8;
      --panel: #fffdf8;
      --ink: #1f241f;
      --muted: #5c645c;
      --line: #d8d0be;
      --accent: #0d6b5f;
      --accent-soft: #dcefe9;
      --local: #c67f27;
      --external: #98a0ac;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(13, 107, 95, 0.10), transparent 24rem),
        linear-gradient(180deg, #f8f5ed 0%, var(--bg) 100%);
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    }
    .app {
      width: min(1280px, calc(100vw - 2rem));
      margin: 0 auto;
      padding: 1rem 0 2rem;
    }
    .header, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 12px 36px rgba(30, 33, 29, 0.06);
    }
    .header {
      padding: 1rem 1.25rem;
      margin-bottom: 1rem;
    }
    .header h1 { margin: 0.2rem 0 0.6rem; }
    .small { color: var(--muted); font-size: 0.92rem; }
    .controls {
      display: grid;
      grid-template-columns: 1.2fr 0.9fr 0.8fr;
      gap: 1rem;
      margin-bottom: 1rem;
      align-items: end;
    }
    .field label {
      display: block;
      margin-bottom: 0.35rem;
      font-size: 0.9rem;
      color: var(--muted);
    }
    .field input, .field select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.8rem 0.9rem;
      background: white;
      font-size: 1rem;
    }
    .layout {
      display: grid;
      grid-template-columns: 2.2fr 1fr;
      gap: 1rem;
    }
    .graph-panel {
      padding: 0.75rem;
      min-height: 42rem;
    }
    #cy {
      width: 100%;
      height: 40rem;
      border-radius: 14px;
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at top left, rgba(13, 107, 95, 0.08), transparent 18rem),
        linear-gradient(180deg, #fffdfa 0%, #f5f1e7 100%);
    }
    .side {
      display: grid;
      gap: 1rem;
    }
    .panel {
      padding: 1rem 1.1rem;
    }
    .panel h2, .panel h3 {
      margin-top: 0;
    }
    .metric-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.6rem;
    }
    .metric {
      padding: 0.8rem 0.9rem;
      border-radius: 14px;
      background: var(--accent-soft);
    }
    .metric strong { display: block; font-size: 1.25rem; }
    .list-clean {
      list-style: none;
      padding: 0;
      margin: 0;
    }
    .list-clean li + li { margin-top: 0.55rem; }
    .badge {
      display: inline-block;
      padding: 0.16rem 0.45rem;
      border-radius: 999px;
      background: #ece7db;
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 700;
      margin-right: 0.35rem;
    }
    .badge.ok {
      background: var(--accent-soft);
      color: var(--accent);
    }
    .paper-card-title {
      display: flex;
      align-items: baseline;
      gap: 0.6rem;
      flex-wrap: wrap;
    }
    .legend {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .legend span::before {
      content: "";
      display: inline-block;
      width: 0.7rem;
      height: 0.7rem;
      border-radius: 999px;
      margin-right: 0.4rem;
      vertical-align: middle;
    }
    .legend-seed::before { background: var(--accent); }
    .legend-local::before { background: var(--local); }
    .legend-external::before { background: var(--external); }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.55rem;
      margin-top: 0.9rem;
    }
    .actions button {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 0.55rem 0.85rem;
      background: white;
      cursor: pointer;
      font-size: 0.92rem;
      font-family: inherit;
    }
    .actions button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    .actions button:disabled {
      opacity: 0.55;
      cursor: wait;
    }
    .tabs {
      display: flex;
      gap: 0.6rem;
      flex-wrap: wrap;
      margin-bottom: 1rem;
    }
    .tab {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 0.55rem 0.9rem;
      background: rgba(255,255,255,0.75);
      cursor: pointer;
      font-size: 0.94rem;
      font-family: inherit;
    }
    .tab.active {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    .action-status {
      margin-top: 0.65rem;
      padding: 0.7rem 0.85rem;
      border-radius: 12px;
      background: #eef4f1;
      color: var(--accent);
    }
    .action-status.error {
      background: #f7e8e5;
      color: #8f3b2a;
    }
    .table-wrap {
      overflow: auto;
    }
    .paper-table {
      width: 100%;
      border-collapse: collapse;
    }
    .paper-table th, .paper-table td {
      padding: 0.65rem 0.7rem;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    .paper-table tr {
      cursor: pointer;
    }
    .paper-table tr:hover {
      background: rgba(13, 107, 95, 0.05);
    }
    .paper-detail {
      display: grid;
      gap: 1rem;
    }
    .docling-box {
      white-space: pre-wrap;
      max-height: 20rem;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      padding: 0.9rem 1rem;
      font-size: 0.95rem;
    }
    @media (max-width: 960px) {
      .controls, .layout, .metric-row {
        grid-template-columns: 1fr;
      }
      #cy { height: 28rem; }
    }
  </style>
</head>
<body>
  <div id="root"></div>
  <script>
    const e = React.createElement;

    function App() {
      const [payload, setPayload] = React.useState(null);
      const [query, setQuery] = React.useState("");
      const [activeKey, setActiveKey] = React.useState("");
      const [localOnly, setLocalOnly] = React.useState(false);
      const [activeTab, setActiveTab] = React.useState("explore");
      const [actionState, setActionState] = React.useState({busy: false, message: "", error: false});
      const cyRef = React.useRef(null);

      const loadModel = React.useCallback(() => {
        fetch("/api/model").then((resp) => resp.json()).then((data) => {
          setPayload(data);
          if (data.papers && data.papers.length) {
            setActiveKey((prev) => prev && data.papers.some((paper) => paper.citekey === prev) ? prev : data.papers[0].citekey);
          }
        });
      }, []);

      React.useEffect(() => {
        loadModel();
      }, [loadModel]);

      const papers = React.useMemo(() => {
        if (!payload) return [];
        const q = query.trim().toLowerCase();
        return (payload.papers || []).filter((paper) => {
          if (!q) return true;
          return `${paper.citekey} ${paper.title}`.toLowerCase().includes(q);
        });
      }, [payload, query]);

      const activePaper = React.useMemo(() => {
        if (!payload) return null;
        return (payload.papers || []).find((paper) => paper.citekey === activeKey) || papers[0] || null;
      }, [payload, papers, activeKey]);

      async function triggerAction(action, body) {
        setActionState({busy: true, message: `Running ${action}...`, error: false});
        try {
          const resp = await fetch(`/api/actions/${action}`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body || {}),
          });
          const data = await resp.json();
          if (!resp.ok) {
            throw new Error(data.detail || data.error || `Request failed: ${resp.status}`);
          }
          setActionState({busy: false, message: data.message || `${action} finished`, error: false});
          loadModel();
        } catch (err) {
          setActionState({busy: false, message: String(err.message || err), error: true});
        }
      }

      React.useEffect(() => {
        if (!payload || !activePaper || activeTab !== "explore") return;
        const container = document.getElementById("cy");
        if (!container) return;
        const graph = payload.graph || {nodes: [], edges: []};
        const related = new Set((activePaper.related_local || []).map((item) => `paper:${item.citekey}`));
        const activeNodeId = `paper:${activePaper.citekey}`;
        const outgoing = new Set((activePaper.graph.outgoing || []).map((item) => item.citekey ? `paper:${item.citekey}` : `openalex:${item.openalex_id}`));
        const incoming = new Set((activePaper.graph.incoming || []).map((item) => item.citekey ? `paper:${item.citekey}` : `openalex:${item.openalex_id}`));
        const allowed = new Set([activeNodeId, ...related, ...outgoing, ...incoming]);
        const nodes = (graph.nodes || []).filter((node) => allowed.has(node.id) && (!localOnly || node.is_local));
        const nodeIds = new Set(nodes.map((node) => node.id));
        const edges = (graph.edges || []).filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
        const elements = [
          ...nodes.map((node) => ({
            data: {
              id: node.id,
              label: node.citekey || node.label,
              kind: node.kind,
              isLocal: !!node.is_local,
              active: node.id === activeNodeId,
              related: related.has(node.id),
            }
          })),
          ...edges.map((edge, idx) => ({
            data: {
              id: `edge-${idx}-${edge.source}-${edge.target}`,
              source: edge.source,
              target: edge.target,
            }
          })),
        ];
        if (!cyRef.current) {
          cyRef.current = cytoscape({
            container,
            elements,
            style: [
              { selector: "node", style: {
                "label": "data(label)",
                "text-valign": "bottom",
                "text-margin-y": 10,
                "text-wrap": "wrap",
                "text-max-width": 90,
                "font-size": 11,
                "background-color": "#98a0ac",
                "width": 18,
                "height": 18,
                "border-width": 1.5,
                "border-color": "rgba(31,36,31,0.18)"
              }},
              { selector: "node[isLocal]", style: { "background-color": "#c67f27" }},
              { selector: "node[active]", style: { "background-color": "#0d6b5f", "width": 28, "height": 28, "border-width": 3, "border-color": "#0d6b5f" }},
              { selector: "node[related]", style: { "border-width": 3, "border-color": "#c67f27" }},
              { selector: "edge", style: { "line-color": "rgba(92,100,92,0.35)", "width": 1.5, "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": "rgba(92,100,92,0.45)" }},
            ],
            layout: { name: "cose", fit: true, padding: 30, animate: false }
          });
          cyRef.current.on("tap", "node", (evt) => {
            const id = evt.target.id();
            if (id.startsWith("paper:")) {
              setActiveKey(id.slice("paper:".length));
            }
          });
        } else {
          cyRef.current.elements().remove();
          cyRef.current.add(elements);
          cyRef.current.layout({ name: "cose", fit: true, padding: 30, animate: false }).run();
        }
      }, [payload, activePaper, localOnly, activeTab]);

      if (!payload) {
        return e("div", {className: "app"}, e("div", {className: "header"}, "Loading bibliography UI..."));
      }

      const status = payload.status || {};
      const activeArtifacts = activePaper ? activePaper.artifacts : null;
      const tabs = [
        ["explore", "Explore"],
        ["corpus", "Corpus"],
        ["paper", "Paper"],
        ["actions", "Actions"],
      ];
      const actionButtons = e("div", {className: "actions"},
        e("button", {disabled: actionState.busy, onClick: () => triggerAction("bibtex-merge"), className: "primary"}, "Merge BibTeX"),
        e("button", {disabled: actionState.busy, onClick: () => triggerAction("openalex-resolve")}, "Resolve OpenAlex"),
        e("button", {disabled: actionState.busy, onClick: () => triggerAction("graph-expand")}, "Expand Graph"),
        e("button", {disabled: actionState.busy, onClick: () => triggerAction("site-build")}, "Build Site"),
        e("button", {disabled: actionState.busy || !activePaper, onClick: () => activePaper && triggerAction("docling-run", {citekey: activePaper.citekey})}, "Run Docling For Selected")
      );

      return e("div", {className: "app"},
        e("div", {className: "header"},
          e("div", {className: "small"}, "Local FastAPI bibliography explorer"),
          e("h1", null, "biblio ui"),
          e("div", {className: "legend small"},
            e("span", {className: "legend-seed"}, "active seed"),
            e("span", {className: "legend-local"}, "local paper"),
            e("span", {className: "legend-external"}, "external neighbor")
          )
        ),
        e("div", {className: "small", style: {marginBottom: "0.9rem"}},
          activePaper ? `Focused paper: ${activePaper.citekey}` : "No active paper"
          )
        ,
        e("div", {className: "tabs"},
          tabs.map(([value, label]) =>
            e("button", {
              key: value,
              className: `tab ${activeTab === value ? "active" : ""}`,
              onClick: () => setActiveTab(value),
            }, label)
          )
        ),
        e("div", {className: "controls"},
          e("div", {className: "field"},
            e("label", null, "Search papers"),
            e("input", {value: query, onChange: (ev) => setQuery(ev.target.value), placeholder: "citekey or title"})
          ),
          e("div", {className: "field"},
            e("label", null, "Focus paper"),
            e("select", {value: activePaper ? activePaper.citekey : "", onChange: (ev) => setActiveKey(ev.target.value)},
              papers.map((paper) => e("option", {key: paper.citekey, value: paper.citekey}, `${paper.citekey} — ${paper.title}`))
            )
          ),
          e("div", {className: "field"},
            e("label", null, "Graph filter"),
            e("select", {value: localOnly ? "local" : "all", onChange: (ev) => setLocalOnly(ev.target.value === "local")},
              e("option", {value: "all"}, "Local + external"),
              e("option", {value: "local"}, "Local only")
            )
          )
        ),
        activeTab === "explore" && e("div", {className: "layout"},
          e("div", {className: "panel graph-panel"}, e("div", {id: "cy"})),
          e("div", {className: "side"},
            e("div", {className: "panel"},
              e("div", {className: "metric-row"},
                e("div", {className: "metric"}, e("span", {className: "small"}, "papers"), e("strong", null, String(status.papers_total || 0))),
                e("div", {className: "metric"}, e("span", {className: "small"}, "docling"), e("strong", null, String(status.papers_with_docling || 0))),
                e("div", {className: "metric"}, e("span", {className: "small"}, "openalex"), e("strong", null, String(status.papers_with_openalex || 0)))
              )
            ),
            activePaper && e("div", {className: "panel"},
              e("div", {className: "paper-card-title"},
                e("h2", null, activePaper.citekey),
                e("span", {className: "small"}, activePaper.year || "n.d.")
              ),
              e("div", {className: "small"}, activePaper.title),
              e("p", null, (activePaper.authors || []).join(", ") || "Unknown authors"),
              e("div", null,
                e("span", {className: `badge ${activeArtifacts && activeArtifacts.pdf.exists ? "ok" : ""}`}, activeArtifacts && activeArtifacts.pdf.exists ? "pdf" : "no pdf"),
                e("span", {className: `badge ${activeArtifacts && activeArtifacts.docling_md.exists ? "ok" : ""}`}, activeArtifacts && activeArtifacts.docling_md.exists ? "docling" : "no docling"),
                e("span", {className: `badge ${activeArtifacts && activeArtifacts.openalex.exists ? "ok" : ""}`}, activeArtifacts && activeArtifacts.openalex.exists ? "openalex" : "no openalex")
              )
            ),
            activePaper && e("div", {className: "panel"},
              e("h3", null, "Related local papers"),
              e("ul", {className: "list-clean"},
                ((activePaper.related_local || []).length ? activePaper.related_local : [{citekey: null}]).map((item, idx) =>
                  item.citekey
                    ? e("li", {key: `${item.citekey}-${idx}`},
                        e("strong", null, item.citekey),
                        e("span", {className: "small"}, ` score ${item.score}, shared outgoing ${item.shared_outgoing}, shared incoming ${item.shared_incoming}`)
                      )
                    : e("li", {key: "none", className: "small"}, "No related local papers yet.")
                )
              )
            ),
            activePaper && e("div", {className: "panel"},
              e("h3", null, "Neighborhood"),
              e("div", {className: "small"}, `${(activePaper.graph.outgoing || []).length} outgoing, ${(activePaper.graph.incoming || []).length} incoming local links`),
              e("ul", {className: "list-clean"},
                (activePaper.graph.outgoing || []).slice(0, 6).map((item, idx) => e("li", {key: `o-${idx}`}, item.citekey || item.openalex_id))
              )
            )
          )
        ),
        activeTab === "corpus" && e("div", {className: "panel table-wrap"},
          e("table", {className: "paper-table"},
            e("thead", null,
              e("tr", null,
                e("th", null, "Citekey"),
                e("th", null, "Title"),
                e("th", null, "Year"),
                e("th", null, "Artifacts")
              )
            ),
            e("tbody", null,
              papers.map((paper) =>
                e("tr", {
                  key: paper.citekey,
                  onClick: () => { setActiveKey(paper.citekey); setActiveTab("paper"); },
                },
                  e("td", null, paper.citekey),
                  e("td", null, paper.title),
                  e("td", null, paper.year || "n.d."),
                  e("td", null,
                    e("span", {className: `badge ${paper.artifacts.pdf.exists ? "ok" : ""}`}, paper.artifacts.pdf.exists ? "pdf" : "no pdf"),
                    e("span", {className: `badge ${paper.artifacts.docling_md.exists ? "ok" : ""}`}, paper.artifacts.docling_md.exists ? "docling" : "no docling"),
                    e("span", {className: `badge ${paper.artifacts.openalex.exists ? "ok" : ""}`}, paper.artifacts.openalex.exists ? "openalex" : "no openalex")
                  )
                )
              )
            )
          )
        ),
        activeTab === "paper" && activePaper && e("div", {className: "paper-detail"},
          e("div", {className: "panel"},
            e("div", {className: "paper-card-title"},
              e("h2", null, activePaper.citekey),
              e("span", {className: "small"}, activePaper.year || "n.d.")
            ),
            e("div", {className: "small"}, activePaper.title),
            e("p", null, (activePaper.authors || []).join(", ") || "Unknown authors"),
            e("div", null,
              e("span", {className: `badge ${activeArtifacts && activeArtifacts.pdf.exists ? "ok" : ""}`}, activeArtifacts && activeArtifacts.pdf.exists ? "pdf" : "no pdf"),
              e("span", {className: `badge ${activeArtifacts && activeArtifacts.docling_md.exists ? "ok" : ""}`}, activeArtifacts && activeArtifacts.docling_md.exists ? "docling" : "no docling"),
              e("span", {className: `badge ${activeArtifacts && activeArtifacts.openalex.exists ? "ok" : ""}`}, activeArtifacts && activeArtifacts.openalex.exists ? "openalex" : "no openalex")
            )
          ),
          e("div", {className: "panel"},
            e("h3", null, "Docling excerpt"),
            e("div", {className: "docling-box"}, (activePaper.docling && activePaper.docling.excerpt) || "No Docling content available.")
          ),
          e("div", {className: "layout"},
            e("div", {className: "panel"},
              e("h3", null, "Related local papers"),
              e("ul", {className: "list-clean"},
                ((activePaper.related_local || []).length ? activePaper.related_local : [{citekey: null}]).map((item, idx) =>
                  item.citekey
                    ? e("li", {key: `${item.citekey}-${idx}`},
                        e("strong", null, item.citekey),
                        e("span", {className: "small"}, ` score ${item.score}, shared outgoing ${item.shared_outgoing}, shared incoming ${item.shared_incoming}`)
                      )
                    : e("li", {key: "none", className: "small"}, "No related local papers yet.")
                )
              )
            ),
            e("div", {className: "panel"},
              e("h3", null, "Neighborhood"),
              e("div", {className: "small"}, `${(activePaper.graph.outgoing || []).length} outgoing, ${(activePaper.graph.incoming || []).length} incoming local links`),
              e("ul", {className: "list-clean"},
                (activePaper.graph.outgoing || []).slice(0, 8).map((item, idx) => e("li", {key: `o-${idx}`}, item.citekey || item.openalex_id))
              )
            )
          )
        ),
        activeTab === "actions" && e("div", {className: "panel"},
          e("h2", null, "Actions"),
          e("div", {className: "small"}, activePaper ? `Selected paper for Docling: ${activePaper.citekey}` : "No paper selected."),
          actionButtons,
          actionState.message && e("div", {className: `action-status ${actionState.error ? "error" : ""}`}, actionState.message)
        )
      );
    }

    ReactDOM.createRoot(document.getElementById("root")).render(e(App));
  </script>
</body>
</html>
"""


def create_ui_app(cfg: BiblioConfig):
    fastapi, responses = _require_fastapi()
    app = fastapi.FastAPI(title="biblio ui", version="0.1")

    @app.get("/", response_class=responses.HTMLResponse)
    def index() -> str:
        return _index_html()

    @app.get("/api/model", response_class=responses.JSONResponse)
    def model():
        payload = build_ui_model(cfg)
        payload.pop("paper_lookup", None)
        return payload

    @app.get("/api/papers", response_class=responses.JSONResponse)
    def papers():
        payload = build_ui_model(cfg)
        return payload["papers"]

    @app.get("/api/status", response_class=responses.JSONResponse)
    def status():
        payload = build_ui_model(cfg)
        return payload["status"]

    @app.get("/api/graph", response_class=responses.JSONResponse)
    def graph():
        payload = build_ui_model(cfg)
        return payload["graph"]

    def _action_result(message: str, **extra: Any) -> dict[str, Any]:
        return {"ok": True, "message": message, **extra}

    @app.post("/api/actions/bibtex-merge", response_class=responses.JSONResponse)
    def action_bibtex_merge():
        n_sources, n_entries = merge_srcbib(cfg.bibtex_merge, dry_run=False)
        return _action_result(
            f"Merged {n_sources} source files into {n_entries} entries.",
            sources=n_sources,
            entries=n_entries,
        )

    @app.post("/api/actions/docling-run", response_class=responses.JSONResponse)
    def action_docling_run(payload: dict[str, Any]):
        citekey = str(payload.get("citekey") or "").strip()
        if not citekey:
            raise fastapi.HTTPException(status_code=400, detail="Missing citekey")
        out = run_docling_for_key(cfg, citekey, force=False)
        return _action_result(
            f"Docling finished for {citekey}.",
            citekey=citekey,
            md_path=str(out.md_path),
        )

    @app.post("/api/actions/openalex-resolve", response_class=responses.JSONResponse)
    def action_openalex_resolve():
        counts = resolve_srcbib_to_openalex(
            cfg=cfg.openalex_client,
            cache=cfg.openalex_cache,
            src_dir=cfg.openalex.src_dir,
            src_glob=cfg.openalex.src_glob,
            out_path=cfg.openalex.out_jsonl,
            out_format="jsonl",
            limit=None,
            opts=ResolveOptions(
                prefer_doi=True,
                fallback_title_search=True,
                per_page=int(cfg.openalex_client.per_page),
                strict=False,
                force=False,
            ),
        )
        return _action_result(
            f"Resolved OpenAlex metadata for {counts['resolved']} entries.",
            counts=counts,
        )

    @app.post("/api/actions/graph-expand", response_class=responses.JSONResponse)
    def action_graph_expand():
        input_path = cfg.openalex.out_jsonl
        output_path = cfg.openalex.out_jsonl.parent / "graph_candidates.json"
        records = load_openalex_seed_records(input_path)
        result = expand_openalex_reference_graph(
            cfg=cfg.openalex_client,
            cache=cfg.openalex_cache,
            records=records,
            out_path=output_path,
            force=False,
        )
        return _action_result(
            f"Expanded {result.candidates} graph candidates.",
            candidates=result.candidates,
            output_path=str(result.output_path),
        )

    @app.post("/api/actions/site-build", response_class=responses.JSONResponse)
    def action_site_build():
        result = build_biblio_site(cfg, force=True)
        return _action_result(
            f"Built site with {result.papers_total} papers.",
            out_dir=str(result.out_dir),
            papers=result.papers_total,
        )

    return app


def serve_ui_app(cfg: BiblioConfig, *, host: str = "127.0.0.1", port: int = 8010) -> None:
    uvicorn = _require_uvicorn()
    app = create_ui_app(cfg)
    selected_port = find_available_port(str(host), int(port))
    print(f"[OK] UI available at http://{host}:{selected_port}")
    if selected_port != int(port):
        print(f"[INFO] Requested port {port} was unavailable; using {selected_port} instead.")
    uvicorn.run(app, host=host, port=int(selected_port))
