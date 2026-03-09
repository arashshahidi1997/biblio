import React, { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';

export default function ExploreTab({
  payload,
  activePaper,
  activeExternalNode,
  localOnly,
  graphMode,
  graphDirection,
  actionState,
  triggerAction,
  setActiveKey,
  setActiveExternalNode,
  activeTab,
}) {
  const cyRef = useRef(null);
  const status = (payload && payload.status) || {};
  const activeArtifacts = activePaper ? activePaper.artifacts : null;

  useEffect(() => {
    if (activeTab !== "explore") {
      if (cyRef.current) {
        try {
          cyRef.current.destroy();
        } catch (err) {}
        cyRef.current = null;
      }
      return;
    }
    if (!payload || !activePaper) return;
    const container = document.getElementById("cy");
    if (!container) return;
    const graph = payload.graph || { nodes: [], edges: [] };
    const related = new Set((activePaper.related_local || []).map((item) => `paper:${item.citekey}`));
    const activeNodeId = `paper:${activePaper.citekey}`;
    const outgoing = new Set((activePaper.graph.outgoing || []).map((item) => item.citekey ? `paper:${item.citekey}` : `openalex:${item.openalex_id}`));
    const incoming = new Set((activePaper.graph.incoming || []).map((item) => item.citekey ? `paper:${item.citekey}` : `openalex:${item.openalex_id}`));
    const grobidRefs = new Set((activePaper.graph.grobid_refs || []).map((item) => `paper:${item.target_citekey}`));
    const allowed = graphMode === "all"
      ? null
      : new Set([activeNodeId, ...related, ...outgoing, ...incoming, ...grobidRefs]);
    const nodes = (graph.nodes || []).filter((node) => (!allowed || allowed.has(node.id)) && (!localOnly || node.is_local));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges = (graph.edges || []).filter((edge) => {
      if (!(nodeIds.has(edge.source) && nodeIds.has(edge.target))) return false;
      if (graphDirection === "past") return edge.direction === "references" || edge.kind === "grobid_ref";
      if (graphDirection === "future") return edge.direction === "citing";
      return true;
    });
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
          kind: edge.kind || "openalex",
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
          { selector: "edge[kind='grobid_ref']", style: { "line-color": "rgba(13,107,95,0.55)", "line-style": "dashed", "width": 1.5, "target-arrow-color": "rgba(13,107,95,0.65)" }},
        ],
        layout: { name: "cose", fit: true, padding: 30, animate: false }
      });
      cyRef.current.on("tap", "node", (evt) => {
        const id = evt.target.id();
        if (id.startsWith("paper:")) {
          setActiveExternalNode(null);
          setActiveKey(id.slice("paper:".length));
        } else if (id.startsWith("openalex:")) {
          const node = (payload.graph.nodes || []).find((item) => item.id === id) || null;
          setActiveExternalNode(node);
        }
      });
    } else {
      cyRef.current.elements().remove();
      cyRef.current.add(elements);
      cyRef.current.resize();
      cyRef.current.layout({ name: "cose", fit: true, padding: 30, animate: false }).run();
      window.setTimeout(() => {
        if (cyRef.current) {
          cyRef.current.resize();
          cyRef.current.fit(undefined, 30);
        }
      }, 30);
    }
  }, [payload, activePaper, localOnly, activeTab, graphMode, graphDirection]);

  // Build candidates list: outgoing + incoming, local first, max 20
  const candidates = React.useMemo(() => {
    if (!activePaper) return [];
    const outgoing = (activePaper.graph.outgoing || []).map((item) => ({ ...item, direction: "outgoing" }));
    const incoming = (activePaper.graph.incoming || []).map((item) => ({ ...item, direction: "incoming" }));
    const grobidRefs = (activePaper.graph.grobid_refs || []).map((item) => ({
      citekey: item.target_citekey,
      title: item.ref_title,
      direction: "grobid_ref",
      match_type: item.match_type,
    }));
    const all = [...outgoing, ...incoming, ...grobidRefs];
    // Sort: local (has citekey) first, then external
    all.sort((a, b) => {
      const aLocal = a.citekey ? 1 : 0;
      const bLocal = b.citekey ? 1 : 0;
      return bLocal - aLocal;
    });
    return all.slice(0, 20);
  }, [activePaper]);

  return (
    <div className="layout">
      <div className="panel graph-panel">
        <div id="cy"></div>
      </div>
      <div className="side">
        <div className="panel">
          <h3>Inspector</h3>
          <div className="small">
            {activeExternalNode
              ? "External graph node selected."
              : activePaper
                ? `Inspecting ${activePaper.citekey}.`
                : "No current selection."}
          </div>
        </div>
        <div className="panel">
          <div className="metric-row">
            <div className="metric">
              <span className="small">papers</span>
              <strong>{String(status.papers_total || 0)}</strong>
            </div>
            <div className="metric">
              <span className="small">docling</span>
              <strong>{String(status.papers_with_docling || 0)}</strong>
            </div>
            <div className="metric">
              <span className="small">openalex</span>
              <strong>{String(status.papers_with_openalex || 0)}</strong>
            </div>
            <div className="metric">
              <span className="small">grobid</span>
              <strong>{String(status.papers_with_grobid || 0)}</strong>
            </div>
          </div>
        </div>
        {activePaper && (
          <div className="panel">
            <div className="paper-card-title">
              <h2>{activePaper.citekey}</h2>
              <span className="small">{activePaper.year || "n.d."}</span>
            </div>
            <div className="small">{activePaper.title}</div>
            <p>{(activePaper.authors || []).join(", ") || "Unknown authors"}</p>
            <div>
              <span className={`badge ${activeArtifacts && activeArtifacts.pdf.exists ? "ok" : ""}`}>
                {activeArtifacts && activeArtifacts.pdf.exists ? "pdf" : "no pdf"}
              </span>
              <span className={`badge ${activeArtifacts && activeArtifacts.docling_md.exists ? "ok" : ""}`}>
                {activeArtifacts && activeArtifacts.docling_md.exists ? "docling" : "no docling"}
              </span>
              <span className={`badge ${activeArtifacts && activeArtifacts.openalex.exists ? "ok" : ""}`}>
                {activeArtifacts && activeArtifacts.openalex.exists ? "openalex" : "no openalex"}
              </span>
            </div>
          </div>
        )}
        {activePaper && (
          <div className="panel">
            <h3>Related local papers</h3>
            <ul className="list-clean">
              {((activePaper.related_local || []).length ? activePaper.related_local : [{ citekey: null }]).map((item, idx) =>
                item.citekey
                  ? (
                    <li key={`${item.citekey}-${idx}`}>
                      <strong>{item.citekey}</strong>
                      <span className="small"> score {item.score}, shared outgoing {item.shared_outgoing}, shared incoming {item.shared_incoming}</span>
                    </li>
                  )
                  : <li key="none" className="small">No related local papers yet.</li>
              )}
            </ul>
          </div>
        )}
        {activePaper && (
          <div className="panel">
            <h3>Candidates</h3>
            <div className="small" style={{ marginBottom: "0.5rem" }}>
              {(activePaper.graph.outgoing || []).length} outgoing (refs), {(activePaper.graph.incoming || []).length} incoming (citing)
              {(activePaper.graph.grobid_refs || []).length > 0 && `, ${activePaper.graph.grobid_refs.length} grobid refs`}
            </div>
            {candidates.length === 0 && (
              <div className="small">No candidates yet. Run Resolve OpenAlex + Expand Graph first.</div>
            )}
            {candidates.map((item, idx) => (
              <div key={`cand-${idx}`} className="candidate-item">
                <div className="candidate-title">
                  {item.title || item.openalex_id || "Unknown"}
                </div>
                <div className="candidate-meta">
                  {item.year && <span className="badge">{item.year}</span>}
                  <span className="badge">
                    {item.direction === "outgoing" ? "→ ref" : item.direction === "grobid_ref" ? `↗ grobid (${item.match_type})` : "← citing"}
                  </span>
                  {item.citekey
                    ? <span className="badge ok">in corpus</span>
                    : (
                      <button
                        className="candidate-add"
                        disabled={actionState.busy}
                        onClick={() => triggerAction("add-paper", { openalex_id: item.openalex_id })}
                      >
                        Add to Bib
                      </button>
                    )
                  }
                </div>
              </div>
            ))}
          </div>
        )}
        {activeExternalNode && (
          <div className="panel">
            <h3>Selected external paper</h3>
            <div className="small">{activeExternalNode.title || activeExternalNode.label || activeExternalNode.openalex_id}</div>
            <p>{activeExternalNode.openalex_id}</p>
            <div>
              <span className="badge">{activeExternalNode.year || "n.d."}</span>
              <span className="badge">{activeExternalNode.doi || "no doi"}</span>
            </div>
            <div className="actions">
              <button
                disabled={actionState.busy}
                onClick={() => triggerAction("add-paper", { openalex_id: activeExternalNode.openalex_id })}
              >
                Add To Bib
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
