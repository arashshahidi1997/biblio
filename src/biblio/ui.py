from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from .config import BiblioConfig
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
      const cyRef = React.useRef(null);

      React.useEffect(() => {
        fetch("/api/model").then((resp) => resp.json()).then((data) => {
          setPayload(data);
          if (data.papers && data.papers.length) {
            setActiveKey(data.papers[0].citekey);
          }
        });
      }, []);

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

      React.useEffect(() => {
        if (!payload || !activePaper) return;
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
            container: document.getElementById("cy"),
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
      }, [payload, activePaper, localOnly]);

      if (!payload) {
        return e("div", {className: "app"}, e("div", {className: "header"}, "Loading bibliography UI..."));
      }

      const status = payload.status || {};
      const activeArtifacts = activePaper ? activePaper.artifacts : null;

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
        e("div", {className: "layout"},
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

    return app


def serve_ui_app(cfg: BiblioConfig, *, host: str = "127.0.0.1", port: int = 8010) -> None:
    uvicorn = _require_uvicorn()
    app = create_ui_app(cfg)
    uvicorn.run(app, host=host, port=int(port))

