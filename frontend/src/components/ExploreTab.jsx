import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import cytoscape from 'cytoscape';

// ── color / size helpers ────────────────────────────────────────────────────

const CATEGORICAL_PALETTE = [
  "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
  "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990",
  "#dcbeff", "#9A6324", "#800000", "#aaffc3", "#808000",
  "#000075", "#a9a9a9",
];

const STATUS_COLORS = {
  unread:    "#4a9eff",
  reading:   "#f0c040",
  processed: "#3cb44b",
  archived:  "#999",
};

function yearToColor(year, minYear, maxYear) {
  if (!year || !minYear || !maxYear || minYear === maxYear) return null;
  const t = (Number(year) - minYear) / (maxYear - minYear);
  const lightness = Math.round(65 - 32 * t);
  return `hsl(218, 58%, ${lightness}%)`;
}

function citedByToSize(citedBy) {
  return Math.max(9, Math.min(32, 9 + 7 * Math.log10(1 + (citedBy || 0))));
}

function shortLabel(citekey) {
  if (!citekey) return "";
  const parts = citekey.split("_");
  if (parts.length < 2) return citekey;
  const author = parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
  return `${author} ${parts[1]}`;
}

/** Build a map from citekey → paper object for quick lookup */
function buildPaperLookup(papers) {
  const map = {};
  (papers || []).forEach((p) => { map[p.citekey] = p; });
  return map;
}

/** Extract unique tag namespaces from all papers */
function extractTagNamespaces(papers) {
  const nsSet = new Set();
  (papers || []).forEach((p) => {
    ((p.library || {}).tags || []).forEach((t) => {
      const idx = t.indexOf(":");
      if (idx > 0) nsSet.add(t.slice(0, idx));
    });
  });
  return [...nsSet].sort();
}

/** Get primary tag value in namespace for a paper */
function primaryTagInNamespace(paper, ns) {
  if (!paper) return null;
  const tags = (paper.library || {}).tags || [];
  for (const t of tags) {
    if (t.startsWith(ns + ":")) return t.slice(ns.length + 1);
  }
  return null;
}

/** Build tag→color mapping for a namespace */
function buildTagColorMap(papers, ns) {
  const values = new Set();
  (papers || []).forEach((p) => {
    const v = primaryTagInNamespace(p, ns);
    if (v) values.add(v);
  });
  const sorted = [...values].sort();
  const map = {};
  sorted.forEach((v, i) => { map[v] = CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length]; });
  return map;
}

/** Simple connected-components detection */
function findConnectedComponents(cy) {
  const visited = new Set();
  const components = [];
  cy.nodes().forEach((node) => {
    if (visited.has(node.id())) return;
    const component = [];
    const queue = [node];
    while (queue.length) {
      const n = queue.shift();
      if (visited.has(n.id())) continue;
      visited.add(n.id());
      component.push(n);
      n.neighborhood("node").forEach((nb) => {
        if (!visited.has(nb.id())) queue.push(nb);
      });
    }
    components.push(component);
  });
  return components;
}

// ── visual update helpers ───────────────────────────────────────────────────

function getNodeColor(node, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, clusterColors) {
  const isLocal = !!node.data("isLocal");
  const isActive = !!node.data("active");
  if (isActive) return "#1a9e8a";

  if (clusterColors) {
    return clusterColors[node.id()] || "#999";
  }

  if (colorBy === "status" && isLocal) {
    const ck = (node.id() || "").replace(/^paper:/, "");
    const paper = paperLookup[ck];
    const status = paper && (paper.library || {}).status;
    return STATUS_COLORS[status] || "#999";
  }

  if (colorBy === "tag" && isLocal && tagNamespace) {
    const ck = (node.id() || "").replace(/^paper:/, "");
    const paper = paperLookup[ck];
    const val = primaryTagInNamespace(paper, tagNamespace);
    return val ? (tagColorMap[val] || "#999") : "#999";
  }

  if (colorBy === "year") {
    if (!isLocal) return yearToColor(node.data("year"), minYear, maxYear) || "#7f8fa8";
    return isLocal ? "#d4813a" : "#7f8fa8";
  }

  return isLocal ? "#d4813a" : "#7f8fa8";
}

// Apply per-node size and color via node.style() — no layout side-effects
function applyVisuals(cy, sizeBy, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, clusterColors) {
  cy.batch(() => {
    cy.nodes().forEach((node) => {
      const isLocal  = !!node.data("isLocal");
      const isActive = !!node.data("active");
      const citedBy  = node.data("citedBy") || 0;

      if (!isActive) {
        const size = sizeBy === "cited_by" ? citedByToSize(citedBy) : (isLocal ? 17 : 12);
        node.style({ width: size, height: size });
      }
      if (!isActive) {
        const color = getNodeColor(node, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, clusterColors);
        node.style("background-color", color);
      }
    });
  });
}

// Update which node is "active" and which are "related" — no layout
function applyActiveStyling(cy, activePaper, sizeBy, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, clusterColors) {
  if (!cy || !activePaper) return;
  const activeId = `paper:${activePaper.citekey}`;
  const related  = new Set((activePaper.related_local || []).map((r) => `paper:${r.citekey}`));

  cy.batch(() => {
    cy.nodes().forEach((node) => {
      const id       = node.id();
      const isActive = id === activeId;
      const isRel    = related.has(id);
      node.data("active",  isActive);
      node.data("related", isRel);
      // reset related border
      node.style("border-width", isRel ? 3 : 1.5);
      node.style("border-color", isRel ? "#d4813a" : "rgba(31,36,31,0.15)");
    });
  });

  applyVisuals(cy, sizeBy, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, clusterColors);

  // Active node override (on top of applyVisuals)
  const activeNode = cy.getElementById(activeId);
  if (activeNode.length) {
    activeNode.style({
      "background-color": "#1a9e8a",
      "width":  24,
      "height": 24,
      "border-width": 3,
      "border-color": "#1a9e8a",
    });
  }
}

// ── legend components ───────────────────────────────────────────────────────

function YearLegend({ minYear, maxYear }) {
  if (!minYear || !maxYear || minYear === maxYear) return null;
  const stops = Array.from({ length: 6 }, (_, i) => {
    const lightness = Math.round(65 - 32 * (i / 5));
    return `hsl(218, 58%, ${lightness}%)`;
  });
  return (
    <div className="graph-legend">
      <span className="small">{minYear}</span>
      <div className="graph-year-gradient" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} />
      <span className="small">{maxYear}</span>
    </div>
  );
}

function CategoricalLegend({ colorMap, label }) {
  const entries = Object.entries(colorMap);
  if (!entries.length) return null;
  return (
    <div className="graph-legend graph-legend-categorical">
      {label && <span className="small graph-legend-label">{label}</span>}
      <div className="graph-legend-items">
        {entries.map(([name, color]) => (
          <span key={name} className="graph-legend-item">
            <span className="graph-legend-swatch" style={{ background: color }} />
            <span className="small">{name}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function PathInfo({ pathLength, onClear }) {
  return (
    <div className="graph-path-info">
      <span className="small">Path length: {pathLength} hop{pathLength !== 1 ? "s" : ""}</span>
      <button className="graph-path-clear" onClick={onClear}>Clear</button>
    </div>
  );
}

function ClusterInfo({ count, onClear }) {
  return (
    <div className="graph-path-info">
      <span className="small">{count} cluster{count !== 1 ? "s" : ""} detected</span>
      <button className="graph-path-clear" onClick={onClear}>Clear</button>
    </div>
  );
}

// ── component ───────────────────────────────────────────────────────────────

export default function ExploreTab({
  payload,
  activePaper,
  localOnly,
  graphMode,
  graphDirection,
  sizeBy,
  colorBy,
  tagNamespace,
  setActiveKey,
  setActiveExternalNode,
  openInPaperTab,
  onSelectNode,
  onCyInit,
  setGraphDirection,
  setGraphMode,
}) {
  const cyRef         = useRef(null);
  const tooltipRef    = useRef(null);
  const yearRangeRef  = useRef({ minYear: null, maxYear: null });
  const activePaperRef = useRef(activePaper);
  const sizeByRef     = useRef(sizeBy);
  const colorByRef    = useRef(colorBy);
  const tagNamespaceRef = useRef(tagNamespace);
  // Bump to force a graph rebuild when focused mode needs it
  const [rebuildKey, setRebuildKey] = useState(0);
  // Path highlighting
  const [pathEndpoints, setPathEndpoints] = useState([]); // [nodeId, nodeId]
  const [pathLength, setPathLength] = useState(null);
  // Cluster detection
  const [showClusters, setShowClusters] = useState(false);
  const [clusterColors, setClusterColors] = useState(null); // { nodeId: color }
  const [clusterCount, setClusterCount] = useState(0);

  const paperLookup = useMemo(
    () => buildPaperLookup(payload?.papers),
    [payload],
  );

  const tagColorMap = useMemo(
    () => tagNamespace ? buildTagColorMap(payload?.papers, tagNamespace) : {},
    [payload, tagNamespace],
  );

  // Keep refs in sync on every render
  activePaperRef.current = activePaper;
  sizeByRef.current      = sizeBy;
  colorByRef.current     = colorBy;
  tagNamespaceRef.current = tagNamespace;

  // Destroy on unmount
  useEffect(() => () => {
    if (cyRef.current) { try { cyRef.current.destroy(); } catch (_) {} cyRef.current = null; }
  }, []);

  // ── clear path/cluster on colorBy change ─────────────────────────────────
  useEffect(() => {
    if (showClusters) {
      setShowClusters(false);
      setClusterColors(null);
      setClusterCount(0);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [colorBy]);

  // ── Effect A: re-apply size/color when controls change (no layout) ──────
  useEffect(() => {
    if (!cyRef.current) return;
    const { minYear, maxYear } = yearRangeRef.current;
    const activeCluster = showClusters ? clusterColors : null;
    applyVisuals(cyRef.current, sizeBy, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, activeCluster);
    // Re-apply active highlight on top
    const ap = activePaperRef.current;
    if (ap) {
      const activeNode = cyRef.current.getElementById(`paper:${ap.citekey}`);
      if (activeNode.length) {
        activeNode.style({ "background-color": "#1a9e8a", width: 32, height: 32, "border-width": 3, "border-color": "#1a9e8a" });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sizeBy, colorBy, tagNamespace, tagColorMap, clusterColors]);

  // ── Effect B: active paper changed ─────────────────────────────────────
  // In "all" mode: just re-style. In "focused" mode: trigger a full rebuild.
  useEffect(() => {
    if (!activePaper) return;
    if (graphMode !== "all") {
      setRebuildKey((k) => k + 1);
    } else if (cyRef.current) {
      const { minYear, maxYear } = yearRangeRef.current;
      const activeCluster = showClusters ? clusterColors : null;
      applyActiveStyling(cyRef.current, activePaper, sizeBy, colorBy, minYear, maxYear, paperLookup, tagNamespace, tagColorMap, activeCluster);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePaper]);

  // ── Path highlighting logic ──────────────────────────────────────────────
  const clearPath = useCallback(() => {
    setPathEndpoints([]);
    setPathLength(null);
    if (cyRef.current) {
      cyRef.current.elements().removeClass("faded path-highlight");
    }
  }, []);

  useEffect(() => {
    if (pathEndpoints.length !== 2 || !cyRef.current) return;
    const cy = cyRef.current;
    const src = cy.getElementById(pathEndpoints[0]);
    const tgt = cy.getElementById(pathEndpoints[1]);
    if (!src.length || !tgt.length) { clearPath(); return; }

    const dijkstra = cy.elements().dijkstra(src, () => 1, false);
    const path = dijkstra.pathTo(tgt);

    if (!path || path.length === 0) {
      setPathLength(-1);
      return;
    }

    const edgeCount = path.edges().length;
    setPathLength(edgeCount);

    cy.batch(() => {
      cy.elements().addClass("faded");
      path.removeClass("faded").addClass("path-highlight");
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathEndpoints]);

  // ── Cluster detection ─────────────────────────────────────────────────────
  const toggleClusters = useCallback(() => {
    if (showClusters) {
      setShowClusters(false);
      setClusterColors(null);
      setClusterCount(0);
      if (cyRef.current) {
        const { minYear, maxYear } = yearRangeRef.current;
        applyVisuals(cyRef.current, sizeByRef.current, colorByRef.current, minYear, maxYear, paperLookup, tagNamespaceRef.current, tagColorMap, null);
        const ap = activePaperRef.current;
        if (ap) {
          const activeNode = cyRef.current.getElementById(`paper:${ap.citekey}`);
          if (activeNode.length) {
            activeNode.style({ "background-color": "#1a9e8a", width: 24, height: 24, "border-width": 3, "border-color": "#1a9e8a" });
          }
        }
      }
      return;
    }

    if (!cyRef.current) return;
    const components = findConnectedComponents(cyRef.current);
    setClusterCount(components.length);
    const colors = {};
    components.forEach((comp, i) => {
      const color = CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length];
      comp.forEach((n) => { colors[n.id()] = color; });
    });
    setClusterColors(colors);
    setShowClusters(true);
  }, [showClusters, paperLookup, tagColorMap]);

  // ── Effect C: full graph rebuild + layout ───────────────────────────────
  useEffect(() => {
    if (!payload) return;
    const ap = activePaperRef.current;
    const container = document.getElementById("cy");
    if (!container) return;

    const graph    = payload.graph || { nodes: [], edges: [] };
    const activeId = ap ? `paper:${ap.citekey}` : null;
    const related  = new Set((ap?.related_local || []).map((r) => `paper:${r.citekey}`));
    const outgoing = new Set((ap?.graph?.outgoing || []).map((i) => i.citekey ? `paper:${i.citekey}` : `openalex:${i.openalex_id}`));
    const incoming = new Set((ap?.graph?.incoming || []).map((i) => i.citekey ? `paper:${i.citekey}` : `openalex:${i.openalex_id}`));
    const grobid   = new Set((ap?.graph?.grobid_refs || []).map((i) => `paper:${i.target_citekey}`));
    const allowed  = graphMode === "all"
      ? null
      : new Set([activeId, ...related, ...outgoing, ...incoming, ...grobid].filter(Boolean));

    const nodes = (graph.nodes || []).filter((n) => (!allowed || allowed.has(n.id)) && (!localOnly || n.is_local));
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = (graph.edges || []).filter((e) => {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) return false;
      if (graphDirection === "past")   return e.direction === "references" || e.kind === "grobid_ref";
      if (graphDirection === "future") return e.direction === "citing";
      return true;
    });

    const extYears = nodes.filter((n) => !n.is_local).map((n) => Number(n.year)).filter((y) => y > 1000);
    const minYear  = extYears.length ? Math.min(...extYears) : null;
    const maxYear  = extYears.length ? Math.max(...extYears) : null;
    yearRangeRef.current = { minYear, maxYear };

    // Build tags string for tooltip
    const elements = [
      ...nodes.map((node) => {
        const paper = node.is_local ? paperLookup[node.citekey] : null;
        const tags = paper ? ((paper.library || {}).tags || []).slice(0, 3).join(", ") : "";
        const status = paper ? ((paper.library || {}).status || "") : "";
        return {
          data: {
            id:        node.id,
            label:     node.is_local ? shortLabel(node.citekey) : "",
            fullLabel: node.citekey || node.label || "",
            isLocal:   !!node.is_local,
            active:    node.id === activeId,
            related:   related.has(node.id),
            year:      node.year,
            citedBy:   node.cited_by || 0,
            title:     node.title || node.label || node.citekey || "",
            tags,
            status,
          },
        };
      }),
      ...edges.map((e, i) => ({
        data: { id: `e${i}-${e.source}-${e.target}`, source: e.source, target: e.target, kind: e.kind || "openalex" },
      })),
    ];

    // Clear path/cluster state on rebuild
    setPathEndpoints([]);
    setPathLength(null);
    if (showClusters) {
      setShowClusters(false);
      setClusterColors(null);
      setClusterCount(0);
    }

    if (!cyRef.current) {
      cyRef.current = cytoscape({
        container,
        elements,
        style: [
          { selector: "node", style: {
            "label":                    "data(label)",
            "text-valign":              "bottom",
            "text-halign":              "center",
            "text-margin-y":            6,
            "text-wrap":                "none",
            "font-size":                9,
            "font-family":              "system-ui, sans-serif",
            "color":                    "#555",
            "text-background-color":    "rgba(255,253,246,0.82)",
            "text-background-opacity":  1,
            "text-background-padding":  "2px",
            "text-background-shape":    "roundrectangle",
            "background-color":         "#7f8fa8",
            "width":  12,
            "height": 12,
            "border-width": 1.5,
            "border-color": "rgba(31,36,31,0.15)",
            "transition-property":      "opacity",
            "transition-duration":      "0.12s",
          }},
          { selector: "node[?isLocal]", style: { "background-color": "#d4813a" }},
          { selector: "node[?active]",  style: {
            "background-color": "#1a9e8a",
            "width":  24, "height": 24,
            "border-width": 3, "border-color": "#1a9e8a",
            "label": "data(fullLabel)",
            "font-size": 10,
          }},
          { selector: "node[?related]", style: { "border-width": 2.5, "border-color": "#d4813a" }},
          { selector: "node:selected", style: {
            "label":           "data(fullLabel)",
            "font-size":       10,
            "border-width":    2.5,
            "border-color":    "#4a9eff",
            "shadow-blur":     20,
            "shadow-color":    "#4a9eff",
            "shadow-opacity":  0.9,
            "shadow-offset-x": 0,
            "shadow-offset-y": 0,
          }},
          { selector: "node.faded", style: { "opacity": 0.1 }},
          { selector: "node.path-highlight", style: {
            "border-width":    3,
            "border-color":    "#ff6600",
            "shadow-blur":     12,
            "shadow-color":    "#ff6600",
            "shadow-opacity":  0.7,
            "shadow-offset-x": 0,
            "shadow-offset-y": 0,
          }},
          { selector: "edge", style: {
            "line-color":          "rgba(100,110,100,0.28)",
            "width":               1.2,
            "curve-style":         "bezier",
            "target-arrow-shape":  "triangle",
            "target-arrow-color":  "rgba(100,110,100,0.38)",
          }},
          { selector: "edge[kind='grobid_ref']", style: {
            "line-color":         "rgba(26,158,138,0.5)",
            "line-style":         "dashed",
            "width":              1.5,
            "target-arrow-color": "rgba(26,158,138,0.6)",
          }},
          { selector: "edge.faded", style: { "opacity": 0.04 }},
          { selector: "edge.path-highlight", style: {
            "line-color":         "#ff6600",
            "width":              3,
            "target-arrow-color": "#ff6600",
            "opacity":            1,
          }},
        ],
        layout: { name: "cose", fit: true, padding: 36, animate: false, randomize: true },
      });

      // ── events ────────────────────────────────────────────────────────
      cyRef.current.on("tap", "node", (evt) => {
        const id = evt.target.id();
        const originalEvent = evt.originalEvent;

        // Shift-click: path endpoint selection
        if (originalEvent && originalEvent.shiftKey) {
          setPathEndpoints((prev) => {
            if (prev.length === 0) return [id];
            if (prev.length === 1) return prev[0] === id ? prev : [prev[0], id];
            return [id]; // reset if already 2
          });
          return;
        }

        // Normal click: existing behavior
        cyRef.current.elements().addClass("faded");
        cyRef.current.elements().removeClass("path-highlight");
        evt.target.removeClass("faded");
        evt.target.neighborhood().removeClass("faded");
        cyRef.current.elements().unselect();
        evt.target.select();
        setPathEndpoints([]);
        setPathLength(null);

        if (id.startsWith("paper:")) {
          const ck = id.slice("paper:".length);
          setActiveExternalNode(null);
          setActiveKey(ck);
          if (onSelectNode) onSelectNode({ kind: "local", citekey: ck });
        } else if (id.startsWith("openalex:")) {
          const node = (payload.graph.nodes || []).find((n) => n.id === id) || null;
          setActiveExternalNode(node);
          if (onSelectNode) onSelectNode({ kind: "external", node });
        }
      });

      cyRef.current.on("tap", (evt) => {
        if (evt.target === cyRef.current) {
          cyRef.current.elements().removeClass("faded");
          cyRef.current.elements().removeClass("path-highlight");
          cyRef.current.elements().unselect();
          setPathEndpoints([]);
          setPathLength(null);
          if (onSelectNode) onSelectNode(null);
        }
      });

      cyRef.current.on("dbltap", "node", (evt) => {
        const id = evt.target.id();
        if (id.startsWith("paper:") && openInPaperTab) openInPaperTab(id.slice("paper:".length));
      });

      cyRef.current.on("mouseover", "node", (evt) => {
        const node = evt.target;
        const pos  = node.renderedPosition();
        const rect = container.getBoundingClientRect();
        if (!tooltipRef.current) return;
        const fullLabel = node.data("fullLabel") || "";
        const title     = node.data("title") !== fullLabel ? node.data("title") : "";
        const year      = node.data("year") ? `${node.data("year")}` : "";
        const cb        = node.data("citedBy") > 0 ? `${node.data("citedBy").toLocaleString()} citations` : "";
        const tags      = node.data("tags") || "";
        const status    = node.data("status") || "";
        const parts = [fullLabel, title, year, cb];
        if (tags) parts.push(tags);
        if (status) parts.push(`status: ${status}`);
        tooltipRef.current.innerHTML = parts.filter(Boolean).join("<br>");
        tooltipRef.current.style.left    = `${rect.left + pos.x + 14}px`;
        tooltipRef.current.style.top     = `${rect.top  + pos.y - 14}px`;
        tooltipRef.current.style.display = "block";
      });

      cyRef.current.on("mouseout", "node", () => {
        if (tooltipRef.current) tooltipRef.current.style.display = "none";
      });
      cyRef.current.on("pan zoom", () => {
        if (tooltipRef.current) tooltipRef.current.style.display = "none";
      });

      if (onCyInit) onCyInit(cyRef.current);

    } else {
      cyRef.current.elements().remove();
      cyRef.current.add(elements);
      cyRef.current.elements().removeClass("faded");
      cyRef.current.elements().removeClass("path-highlight");
      cyRef.current.layout({ name: "cose", fit: true, padding: 36, animate: false, randomize: true }).run();
      window.setTimeout(() => {
        if (cyRef.current) { cyRef.current.resize(); cyRef.current.fit(undefined, 36); }
      }, 30);
    }

    applyActiveStyling(cyRef.current, ap, sizeByRef.current, colorByRef.current, minYear, maxYear, paperLookup, tagNamespaceRef.current, tagColorMap, null);

  // activePaper intentionally excluded — handled by Effect B
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, localOnly, graphMode, graphDirection, rebuildKey]);

  const { minYear, maxYear } = yearRangeRef.current;

  // Build legend data
  const statusLegendMap = colorBy === "status" ? STATUS_COLORS : null;
  const tagLegendMap = colorBy === "tag" && tagNamespace ? tagColorMap : null;
  const clusterLegendMap = showClusters && clusterColors
    ? (() => {
        const map = {};
        for (let i = 0; i < clusterCount; i++) {
          map[`Cluster ${i + 1}`] = CATEGORICAL_PALETTE[i % CATEGORICAL_PALETTE.length];
        }
        return map;
      })()
    : null;

  return (
    <div style={{ position: "relative", flex: 1, minWidth: 0 }}>
      <div className="panel graph-panel">
        <div id="cy" />

        {/* Legends */}
        {colorBy === "year" && !showClusters && <YearLegend minYear={minYear} maxYear={maxYear} />}
        {statusLegendMap && !showClusters && <CategoricalLegend colorMap={statusLegendMap} label="Status" />}
        {tagLegendMap && !showClusters && <CategoricalLegend colorMap={tagLegendMap} label={tagNamespace} />}
        {clusterLegendMap && <CategoricalLegend colorMap={clusterLegendMap} label="Clusters" />}

        {/* Path info */}
        {pathLength !== null && pathLength >= 0 && <PathInfo pathLength={pathLength} onClear={clearPath} />}
        {pathLength === -1 && (
          <div className="graph-path-info">
            <span className="small">No path found between selected nodes</span>
            <button className="graph-path-clear" onClick={clearPath}>Clear</button>
          </div>
        )}

        {/* Cluster info */}
        {showClusters && <ClusterInfo count={clusterCount} onClear={toggleClusters} />}

        {/* Top-right overlay */}
        <div className="graph-overlay-toolbar">
          <button
            className={`graph-overlay-btn${showClusters ? " active" : ""}`}
            title="Detect clusters (connected components)"
            onClick={toggleClusters}
          >
            C
          </button>
          <div className="graph-overlay-sep" />
          <button
            className={`graph-overlay-btn${graphMode === "focused" ? " active" : ""}`}
            title="Focused neighborhood"
            onClick={() => setGraphMode(graphMode === "focused" ? "all" : "focused")}
          >
            ⊙
          </button>
          <div className="graph-overlay-sep" />
          <button
            className={`graph-overlay-btn${graphDirection === "past" ? " active" : ""}`}
            title="Past works (references)"
            onClick={() => setGraphDirection("past")}
          >
            ←
          </button>
          <button
            className={`graph-overlay-btn${graphDirection === "both" ? " active" : ""}`}
            title="Past + future"
            onClick={() => setGraphDirection("both")}
          >
            ⟷
          </button>
          <button
            className={`graph-overlay-btn${graphDirection === "future" ? " active" : ""}`}
            title="Future works (citing)"
            onClick={() => setGraphDirection("future")}
          >
            →
          </button>
        </div>

        {/* Shift-click hint */}
        {pathEndpoints.length === 1 && (
          <div className="graph-path-hint">
            <span className="small">Shift-click another node to find path</span>
          </div>
        )}
      </div>
      <div
        ref={tooltipRef}
        className="graph-tooltip"
        style={{ display: "none", position: "fixed", pointerEvents: "none", zIndex: 9999 }}
      />
    </div>
  );
}
