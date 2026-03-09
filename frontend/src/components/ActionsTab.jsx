import React from 'react';

export default function ActionsTab({ activePaper, actionState, triggerAction, addDoi, setAddDoi }) {
  return (
    <div className="panel">
      <h2>Actions</h2>
      <div className="small">
        {activePaper ? `Selected paper for Docling: ${activePaper.citekey}` : "No paper selected."}
      </div>
      <div className="actions">
        <button disabled={actionState.busy} onClick={() => triggerAction("bibtex-merge")} className="primary">
          Merge BibTeX
        </button>
        <button disabled={actionState.busy} onClick={() => triggerAction("openalex-resolve")}>
          Resolve OpenAlex
        </button>
        <button disabled={actionState.busy} onClick={() => triggerAction("graph-expand")}>
          Expand Graph
        </button>
        <button disabled={actionState.busy} onClick={() => triggerAction("site-build")}>
          Build Site
        </button>
        <button
          disabled={actionState.busy || !activePaper}
          onClick={() => activePaper && triggerAction("docling-run", { citekey: activePaper.citekey })}
        >
          Run Docling For Selected
        </button>
      </div>
      <div className="field" style={{ marginTop: "1rem" }}>
        <label>Add paper by DOI</label>
        <input
          value={addDoi}
          onChange={(ev) => setAddDoi(ev.target.value)}
          placeholder="10.1038/nn.4304"
        />
      </div>
      <div className="actions">
        <button
          disabled={actionState.busy || !addDoi.trim()}
          onClick={() => triggerAction("add-paper", { doi: addDoi })}
        >
          Add DOI
        </button>
      </div>
      {actionState.message && (
        <div className={`action-status ${actionState.error ? "error" : ""}`}>
          {actionState.message}
        </div>
      )}
      {(actionState.action === "openalex-resolve" || actionState.action === "graph-expand" || actionState.action === "docling-run") &&
        (actionState.progressTotal > 0 || actionState.busy) && (
          <div className="progress-wrap">
            <div className="small">
              {actionState.progressTotal > 0
                ? `${actionState.progressCompleted}/${actionState.progressTotal} entries`
                : "Running..."}
            </div>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${actionState.progressTotal > 0 ? (actionState.progressPercent || 0) : 100}%` }}
              />
            </div>
          </div>
        )
      }
    </div>
  );
}
