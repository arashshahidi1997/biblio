import { useMemo } from 'react';

export default function GraphInspector({ activePaper, activeExternalNode, status, actionState, triggerAction }) {
  const activeArtifacts = activePaper ? activePaper.artifacts : null;

  const candidates = useMemo(() => {
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
    all.sort((a, b) => (b.citekey ? 1 : 0) - (a.citekey ? 1 : 0));
    return all.slice(0, 20);
  }, [activePaper]);

  return (
    <div className="inspector-col">
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
            {(activePaper.graph.outgoing || []).length} outgoing, {(activePaper.graph.incoming || []).length} incoming
            {(activePaper.graph.grobid_refs || []).length > 0 && `, ${activePaper.graph.grobid_refs.length} grobid`}
          </div>
          {candidates.length === 0 && (
            <div className="small">No candidates yet. Run Resolve OpenAlex + Expand Graph first.</div>
          )}
          {candidates.map((item, idx) => (
            <div key={`cand-${idx}`} className="candidate-item">
              <div className="candidate-title">{item.title || item.openalex_id || "Unknown"}</div>
              <div className="candidate-meta">
                {item.year && <span className="badge">{item.year}</span>}
                <span className="badge">
                  {item.direction === "outgoing" ? "→ ref" : item.direction === "grobid_ref" ? `↗ grobid (${item.match_type})` : "← citing"}
                </span>
                {item.citekey
                  ? <span className="badge ok">in library</span>
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
  );
}
