import React from 'react';

export default function PaperTab({ activePaper, activeArtifacts, showPdf, setShowPdf, doclingHtml }) {
  if (!activePaper) return null;

  return (
    <div className="paper-detail">
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
      <div className="paper-split">
        <div className="panel">
          <h3>PDF</h3>
          <div className="actions">
            <button
              disabled={!activeArtifacts || !activeArtifacts.pdf.exists}
              onClick={() => setShowPdf((prev) => !prev)}
            >
              {showPdf ? "Hide PDF" : "Show PDF"}
            </button>
          </div>
          {activeArtifacts && activeArtifacts.pdf.exists
            ? (showPdf
                ? (
                  <iframe
                    className="pdf-frame"
                    src={`/api/files/pdf/${encodeURIComponent(activePaper.citekey)}`}
                    title={`${activePaper.citekey} PDF`}
                  />
                )
                : <div className="small">PDF viewer hidden. Use the button above to open it.</div>
              )
            : <div className="small">No PDF available for this paper.</div>
          }
        </div>
        <div className="panel">
          <h3>Docling excerpt</h3>
          <div
            className="docling-box"
            dangerouslySetInnerHTML={{ __html: doclingHtml }}
          />
        </div>
      </div>
      <div className="layout">
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
        <div className="panel">
          <h3>Neighborhood</h3>
          <div className="small">
            {(activePaper.graph.outgoing || []).length} outgoing, {(activePaper.graph.incoming || []).length} incoming local links
          </div>
          <ul className="list-clean">
            {(activePaper.graph.outgoing || []).slice(0, 8).map((item, idx) => (
              <li key={`o-${idx}`}>{item.citekey || item.openalex_id}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
