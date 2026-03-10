import { useEffect, useRef, useState } from 'react';
import cytoscape from 'cytoscape';

// ── color / size helpers ────────────────────────────────────────────────────

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

// ── visual update helpers ───────────────────────────────────────────────────

// Apply per-node size and year-color via node.style() — no layout side-effects
function applyVisuals(cy, sizeBy, colorBy, minYear, maxYear) {
  cy.batch(() => {
    cy.nodes().forEach((node) => {
      const isLocal  = !!node.data("isLocal");
      const isActive = !!node.data("active");
      const citedBy  = node.data("citedBy") || 0;
      const year     = node.data("year");

      if (!isActive) {
        const size = sizeBy === "cited_by" ? citedByToSize(citedBy) : (isLocal ? 17 : 12);
        node.style({ width: size, height: size });
      }
      if (!isLocal && !isActive) {
        const color = colorBy === "year"
          ? (yearToColor(year, minYear, maxYear) || "#7f8fa8")
          : "#7f8fa8";
        node.style("background-color", color);
      }
    });
  });
}

// Update which node is "active" and which are "related" — no layout
function applyActiveStyling(cy, activePaper, sizeBy, colorBy, minYear, maxYear) {
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

  applyVisuals(cy, sizeBy, colorBy, minYear, maxYear);

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

// ── legend ──────────────────────────────────────────────────────────────────

function YearLegend({ minYear, maxYear }) {
  if (!minYear || !maxYear || minYear === maxYear) return null;
  const stops = Array.from({ length: 6 }, (_, i) => {
    const lightness = Math.round(65 - 32 * (i / 5));
    return `hsl(218, 58%, ${lightness}%)`;
  });
  return (
    <div className="graph-year-legend">
      <span className="small">{minYear}</span>
      <div className="graph-year-gradient" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} />
      <span className="small">{maxYear}</span>
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
  // Bump to force a graph rebuild when focused mode needs it
  const [rebuildKey, setRebuildKey] = useState(0);

  // Keep refs in sync on every render
  activePaperRef.current = activePaper;
  sizeByRef.current      = sizeBy;
  colorByRef.current     = colorBy;

  // Destroy on unmount
  useEffect(() => () => {
    if (cyRef.current) { try { cyRef.current.destroy(); } catch (_) {} cyRef.current = null; }
  }, []);

  // ── Effect A: re-apply size/color when controls change (no layout) ──────
  useEffect(() => {
    if (!cyRef.current) return;
    const { minYear, maxYear } = yearRangeRef.current;
    applyVisuals(cyRef.current, sizeBy, colorBy, minYear, maxYear);
    // Re-apply active highlight on top
    const ap = activePaperRef.current;
    if (ap) {
      const activeNode = cyRef.current.getElementById(`paper:${ap.citekey}`);
      if (activeNode.length) {
        activeNode.style({ "background-color": "#1a9e8a", width: 32, height: 32, "border-width": 3, "border-color": "#1a9e8a" });
      }
    }
  }, [sizeBy, colorBy]);

  // ── Effect B: active paper changed ─────────────────────────────────────
  // In "all" mode: just re-style. In "focused" mode: trigger a full rebuild.
  useEffect(() => {
    if (!activePaper) return;
    if (graphMode !== "all") {
      setRebuildKey((k) => k + 1);
    } else if (cyRef.current) {
      const { minYear, maxYear } = yearRangeRef.current;
      applyActiveStyling(cyRef.current, activePaper, sizeBy, colorBy, minYear, maxYear);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePaper]);

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

    const elements = [
      ...nodes.map((node) => ({
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
        },
      })),
      ...edges.map((e, i) => ({
        data: { id: `e${i}-${e.source}-${e.target}`, source: e.source, target: e.target, kind: e.kind || "openalex" },
      })),
    ];

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
        ],
        layout: { name: "cose", fit: true, padding: 36, animate: false, randomize: true },
      });

      // ── events ────────────────────────────────────────────────────────
      cyRef.current.on("tap", "node", (evt) => {
        const id = evt.target.id();
        cyRef.current.elements().addClass("faded");
        evt.target.removeClass("faded");
        evt.target.neighborhood().removeClass("faded");
        cyRef.current.elements().unselect();
        evt.target.select();
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
          cyRef.current.elements().unselect();
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
        tooltipRef.current.innerHTML = [fullLabel, title, year, cb].filter(Boolean).join("<br>");
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
      cyRef.current.layout({ name: "cose", fit: true, padding: 36, animate: false, randomize: true }).run();
      window.setTimeout(() => {
        if (cyRef.current) { cyRef.current.resize(); cyRef.current.fit(undefined, 36); }
      }, 30);
    }

    applyActiveStyling(cyRef.current, ap, sizeByRef.current, colorByRef.current, minYear, maxYear);

  // activePaper intentionally excluded — handled by Effect B
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, localOnly, graphMode, graphDirection, rebuildKey]);

  const { minYear, maxYear } = yearRangeRef.current;

  return (
    <div style={{ position: "relative", flex: 1, minWidth: 0 }}>
      <div className="panel graph-panel">
        <div id="cy" />
        {colorBy === "year" && <YearLegend minYear={minYear} maxYear={maxYear} />}

        {/* Top-right overlay */}
        <div className="graph-overlay-toolbar">
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
      </div>
      <div
        ref={tooltipRef}
        className="graph-tooltip"
        style={{ display: "none", position: "fixed", pointerEvents: "none", zIndex: 9999 }}
      />
    </div>
  );
}
