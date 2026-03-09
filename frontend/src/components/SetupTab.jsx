import React from 'react';

export default function SetupTab({
  setup,
  setupError,
  modelStatus,
  setupCommand,
  setSetupCommand,
  setupCondaEnv,
  setSetupCondaEnv,
  ragConfig,
  setRagConfig,
  actionState,
  triggerSetupAction,
}) {
  if (setupError) return <div className="action-status error">Setup failed to load: {setupError}</div>;
  if (!setup) return <div className="action-status">Loading setup...</div>;

  return (
    <div className="paper-detail">
      <div className="panel">
        <h2>Setup</h2>
        <div className="kv">
          <div className="small">Config</div>
          <code>{setup.config_path}</code>
          <div className="small">Repo root</div>
          <code>{setup.repo_root}</code>
          <div className="small">Docling command</div>
          <code>{(setup.docling.command || []).join(" ")}</code>
          <div className="small">Executable</div>
          <code>{setup.docling.resolved_executable || "not found"}</code>
        </div>
        <div style={{ marginTop: "0.8rem" }}>
          <span className={`badge ${setup.docling.ok === true ? "ok" : setup.docling.ok === false ? "error" : ""}`}>
            {setup.docling.ok === true ? "docling ok" : setup.docling.ok === false ? "docling check failed" : "not checked"}
          </span>
        </div>
        <div className={`action-status ${setup.docling.ok === false ? "error" : ""}`}>
          {setup.docling.message || "Click Re-check to verify."}
        </div>
        <div className="field" style={{ marginTop: "0.9rem" }}>
          <label>Raw Docling command</label>
          <input
            value={setupCommand}
            onChange={(ev) => setSetupCommand(ev.target.value)}
            placeholder="docling"
          />
        </div>
        <div className="actions">
          <button
            disabled={actionState.busy || !setupCommand.trim()}
            onClick={() => triggerSetupAction("/api/setup/docling-command", { mode: "raw", command: setupCommand })}
          >
            Save raw command
          </button>
          <button
            disabled={actionState.busy}
            onClick={() => triggerSetupAction("/api/setup/docling-check", {})}
          >
            Re-check
          </button>
        </div>
        <div className="field" style={{ marginTop: "0.9rem" }}>
          <label>Conda env name</label>
          <input
            value={setupCondaEnv}
            onChange={(ev) => setSetupCondaEnv(ev.target.value)}
            placeholder="docling"
          />
        </div>
        <div className="actions">
          <button
            disabled={actionState.busy || !setupCondaEnv.trim()}
            onClick={() => triggerSetupAction("/api/setup/docling-command", { mode: "conda", env_name: setupCondaEnv })}
          >
            Use conda env
          </button>
          <button
            disabled={actionState.busy}
            onClick={() => triggerSetupAction("/api/setup/install-docling-uv", {})}
          >
            Install Docling in local uv env
          </button>
        </div>
      </div>
      <div className="panel">
        <h3>Workspace</h3>
        <div className="kv">
          <div className="small">citekeys</div>
          <code>{setup.paths.citekeys}</code>
          <div className="small">srcbib</div>
          <code>{setup.paths.srcbib}</code>
          <div className="small">pdf_root</div>
          <code>{setup.paths.pdf_root}</code>
          <div className="small">docling out</div>
          <code>{setup.paths.out_root}</code>
          <div className="small">openalex out</div>
          <code>{setup.paths.openalex_out}</code>
        </div>
      </div>
      <div className="panel">
        <h3>Readiness</h3>
        {modelStatus ? (
          <>
            <div className="small">
              {`papers=${modelStatus.papers_total} configured=${modelStatus.configured_citekeys} srcbib=${modelStatus.source_bib_entries}`}
            </div>
            <div className="small">
              {`pdf=${modelStatus.papers_with_pdf} docling=${modelStatus.papers_with_docling} openalex=${modelStatus.papers_with_openalex}`}
            </div>
            <div className="small">
              {`missing_pdf=${(modelStatus.missing_pdf || []).length} missing_docling=${(modelStatus.missing_docling || []).length} missing_openalex=${(modelStatus.missing_openalex || []).length}`}
            </div>
          </>
        ) : (
          <div className="small">Loading…</div>
        )}
      </div>
      <div className="panel">
        <h3>RAG</h3>
        <div className="small">
          This UI manages the bibliography-owned RAG config at bib/config/rag.yaml. Index building itself is still done by the generic `rag` tool.
        </div>
        <div className="setup-grid" style={{ marginTop: "0.8rem" }}>
          <div className="subpanel">
            <div className="kv">
              <div className="small">Config</div>
              <code>{setup.rag.config_path}</code>
              <div className="small">Status</div>
              <code>{setup.rag.exists ? "existing" : "will be created"}</code>
              <div className="small">Sources</div>
              <code>{(setup.rag.source_ids || []).join(", ") || "none"}</code>
            </div>
            <div className="actions" style={{ marginTop: "0.8rem" }}>
              <button
                disabled={actionState.busy}
                onClick={() => triggerSetupAction("/api/setup/rag-sync", {})}
              >
                Sync owned sources
              </button>
              <button
                disabled={actionState.busy}
                onClick={() => triggerSetupAction("/api/setup/rag-sync", { force_init: true })}
              >
                Reinitialize + sync
              </button>
            </div>
            <div className="small" style={{ marginTop: "0.8rem" }}>Follow-up build command</div>
            <code>{setup.rag.follow_up_build_cmd}</code>
          </div>
          <div className="subpanel">
            <div className="field">
              <label>Embedding model</label>
              <input
                value={ragConfig.embedding_model}
                onChange={(ev) => setRagConfig((prev) => ({ ...prev, embedding_model: ev.target.value }))}
                placeholder="sentence-transformers/all-MiniLM-L6-v2"
              />
            </div>
            <div className="field">
              <label>Chunk size (chars)</label>
              <input
                value={ragConfig.chunk_size_chars}
                onChange={(ev) => setRagConfig((prev) => ({ ...prev, chunk_size_chars: ev.target.value }))}
                placeholder="1000"
              />
            </div>
            <div className="field">
              <label>Chunk overlap (chars)</label>
              <input
                value={ragConfig.chunk_overlap_chars}
                onChange={(ev) => setRagConfig((prev) => ({ ...prev, chunk_overlap_chars: ev.target.value }))}
                placeholder="200"
              />
            </div>
            <div className="field">
              <label>Default store</label>
              <input
                value={ragConfig.default_store}
                onChange={(ev) => setRagConfig((prev) => ({ ...prev, default_store: ev.target.value }))}
                placeholder="local"
              />
            </div>
            <div className="field">
              <label>Local persist directory</label>
              <input
                value={ragConfig.local_persist_directory}
                onChange={(ev) => setRagConfig((prev) => ({ ...prev, local_persist_directory: ev.target.value }))}
                placeholder=".cache/rag/chroma_db"
              />
            </div>
            <div className="actions">
              <button
                disabled={actionState.busy}
                onClick={() => triggerSetupAction("/api/setup/rag-config", ragConfig)}
              >
                Save RAG config
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
