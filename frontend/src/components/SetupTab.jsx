import { useState, useCallback, useEffect, useRef } from 'react';

function NormalizeKeysTool({ actionState }) {
  const [status, setStatus] = useState(null); // null | status object from backend
  const [running, setRunning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const [preview, setPreview] = useState(null); // final renames list after completion
  const pollRef = useRef(null);

  // Poll status while running
  useEffect(() => {
    if (!running) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    const poll = () => {
      fetch("/api/actions/normalize-citekeys/status")
        .then((r) => r.json())
        .then((data) => {
          setStatus(data);
          if (!data.running) {
            setRunning(false);
            setPreview(data.renames || []);
          }
        })
        .catch(() => {});
    };
    poll(); // immediate first poll
    pollRef.current = setInterval(poll, 1500);
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [running]);

  const startPreview = useCallback(() => {
    setRunning(true);
    setPreview(null);
    setApplied(false);
    setStatus(null);
    fetch("/api/actions/normalize-citekeys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apply: false }),
    })
      .then((r) => r.json())
      .catch(() => { setRunning(false); });
  }, []);

  const cancelPreview = useCallback(() => {
    fetch("/api/actions/normalize-citekeys/cancel", { method: "POST" })
      .then((r) => r.json())
      .then((data) => { setStatus(data); setRunning(false); setPreview(data.renames || []); })
      .catch(() => {});
  }, []);

  const applyRenames = useCallback(() => {
    setApplying(true);
    fetch("/api/actions/normalize-citekeys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apply: true }),
    })
      .then((r) => r.json())
      .then(() => { setApplied(true); setPreview(null); setApplying(false); })
      .catch(() => setApplying(false));
  }, []);

  const done = status ? status.done : 0;
  const total = status ? status.total : 0;
  const current = status ? status.current : "";
  const enriched = status ? (status.enriched || []) : [];
  const streamRenames = status ? (status.renames || []) : [];

  return (
    <div style={{ marginTop: "0.6rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
        <button disabled={running || applying || actionState.busy} onClick={startPreview}>
          {running ? "Scanning…" : "Preview renames"}
        </button>
        {running && (
          <button onClick={cancelPreview} style={{ background: "var(--error-bg, #e06c7522)", border: "1px solid var(--error, #e06c75)" }}>
            Cancel
          </button>
        )}
        {!running && preview && preview.length > 0 && (
          <button
            disabled={applying}
            onClick={applyRenames}
            style={{ background: "var(--accent, #4a9eff22)", border: "1px solid var(--accent, #4a9eff)" }}
          >
            {applying ? "Applying…" : `Apply ${preview.length} rename${preview.length !== 1 ? "s" : ""}`}
          </button>
        )}
        {!running && preview && preview.length === 0 && !status?.error && (
          <span className="small" style={{ opacity: 0.6 }}>All citekeys already standard.</span>
        )}
        {applied && <span className="small" style={{ opacity: 0.6 }}>Applied. Re-run pipeline steps to regenerate derivatives.</span>}
      </div>

      {/* Progress bar during preview */}
      {running && total > 0 && (
        <div style={{ marginTop: "0.4rem" }}>
          <div style={{ fontSize: "0.72rem", opacity: 0.7, marginBottom: "0.2rem" }}>
            Enriching paper {done}/{total}{current ? `: ${current}` : ""}
            {enriched.length > 0 && ` · ${enriched.length} enriched`}
            {streamRenames.length > 0 && ` · ${streamRenames.length} rename${streamRenames.length !== 1 ? "s" : ""}`}
          </div>
          <div style={{ height: "4px", background: "var(--border, #333)", borderRadius: "2px", overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${total > 0 ? (done / total) * 100 : 0}%`, background: "var(--accent, #4a9eff)", transition: "width 0.3s" }} />
          </div>
        </div>
      )}

      {/* Error display */}
      {status?.error && !running && (
        <div style={{ marginTop: "0.4rem", fontSize: "0.76rem", color: "var(--error, #e06c75)" }}>
          {status.error}
        </div>
      )}

      {/* Streaming renames during preview */}
      {running && streamRenames.length > 0 && (
        <div style={{ marginTop: "0.5rem", maxHeight: "200px", overflowY: "auto", fontSize: "0.76rem", fontFamily: "monospace" }}>
          {streamRenames.map((r, i) => (
            <div key={i} style={{ padding: "0.15rem 0", opacity: 0.85 }}>
              <span style={{ color: "var(--error, #e06c75)" }}>{r.old}</span>
              {" → "}
              <span style={{ color: "var(--ok, #98c379)" }}>{r.new}</span>
            </div>
          ))}
        </div>
      )}

      {/* Final renames after completion */}
      {!running && preview && preview.length > 0 && (
        <div style={{ marginTop: "0.5rem", maxHeight: "200px", overflowY: "auto", fontSize: "0.76rem", fontFamily: "monospace" }}>
          {preview.map((r, i) => (
            <div key={i} style={{ padding: "0.15rem 0", opacity: 0.85 }}>
              <span style={{ color: "var(--error, #e06c75)" }}>{r.old}</span>
              {" → "}
              <span style={{ color: "var(--ok, #98c379)" }}>{r.new}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function GrobidConfigForm({ setup, actionState, triggerSetupAction }) {
  const [url, setUrl] = useState(setup.grobid.url || "http://127.0.0.1:8070");
  const [installPath, setInstallPath] = useState(setup.grobid.installation_path || "");
  return (
    <div className="setup-grid" style={{ marginTop: "0.9rem" }}>
      <div className="subpanel">
        <div className="actions">
          <button disabled={actionState.busy} onClick={() => triggerSetupAction("/api/setup/grobid-check", {})}>
            Check
          </button>
        </div>
      </div>
      <div className="subpanel">
        <div className="field">
          <label>Server URL</label>
          <input value={url} onChange={(ev) => setUrl(ev.target.value)} placeholder="http://127.0.0.1:8070" />
        </div>
        <div className="field">
          <label>Installation path (optional)</label>
          <input value={installPath} onChange={(ev) => setInstallPath(ev.target.value)} placeholder="/path/to/grobid" />
        </div>
        <div className="actions">
          <button
            disabled={actionState.busy || !url.trim()}
            onClick={() => triggerSetupAction("/api/setup/grobid-config", { url: url.trim(), installation_path: installPath.trim() || null })}
          >
            Save GROBID config
          </button>
        </div>
      </div>
    </div>
  );
}

const ALL_SOURCES = [
  { id: "pool", label: "Pool" },
  { id: "openalex", label: "OpenAlex" },
  { id: "unpaywall", label: "Unpaywall" },
  { id: "ezproxy", label: "EZProxy" },
];

function PdfFetchConfigForm({ setup, actionState, triggerSetupAction }) {
  const pf = setup.pdf_fetch || {};
  const [email, setEmail] = useState(pf.unpaywall_email || "");
  const [proxyBase, setProxyBase] = useState(pf.ezproxy_base || "");
  const [proxyMode, setProxyMode] = useState(pf.ezproxy_mode || "prefix");
  const [sources, setSources] = useState(pf.sources || ["pool", "openalex", "unpaywall", "ezproxy"]);
  const [fetchDelay, setFetchDelay] = useState(String(pf.delay ?? 1.0));

  const toggleSource = (id) => {
    setSources((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]);
  };

  const moveSource = (id, direction) => {
    setSources((prev) => {
      const idx = prev.indexOf(id);
      if (idx < 0) return prev;
      const next = [...prev];
      const swap = idx + direction;
      if (swap < 0 || swap >= next.length) return prev;
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next;
    });
  };

  const save = () => {
    triggerSetupAction("/api/setup/pdf-fetch-config", {
      unpaywall_email: email.trim(),
      ezproxy_base: proxyBase.trim(),
      ezproxy_mode: proxyMode,
      sources,
      delay: parseFloat(fetchDelay) || 1.0,
    });
  };

  return (
    <div className="setup-grid" style={{ marginTop: "0.9rem" }}>
      <div className="subpanel">
        <div className="field">
          <label>Unpaywall email</label>
          <input value={email} onChange={(ev) => setEmail(ev.target.value)} placeholder="your.email@university.edu" />
          <div className="small" style={{ opacity: 0.6, marginTop: "0.2rem" }}>Required for Unpaywall API access (free, 100k queries/day).</div>
        </div>
        <div className="field">
          <label>EZProxy base URL</label>
          <input value={proxyBase} onChange={(ev) => setProxyBase(ev.target.value)} placeholder="https://emedien.ub.uni-muenchen.de" />
          <div className="small" style={{ opacity: 0.6, marginTop: "0.2rem" }}>Your university library proxy URL. Required for accessing paywalled papers.</div>
        </div>
        <div className="field">
          <label>EZProxy mode</label>
          <select value={proxyMode} onChange={(ev) => setProxyMode(ev.target.value)}>
            <option value="prefix">prefix</option>
            <option value="suffix">suffix</option>
          </select>
        </div>
        <div className="field">
          <label>Delay between requests (seconds)</label>
          <input value={fetchDelay} onChange={(ev) => setFetchDelay(ev.target.value)} placeholder="1.0" style={{ width: "5rem" }} />
        </div>
      </div>
      <div className="subpanel">
        <label>Source cascade order</label>
        <div className="small" style={{ opacity: 0.6, marginBottom: "0.4rem" }}>Enable sources and set priority. Papers are tried top-to-bottom.</div>
        {ALL_SOURCES.map((s) => {
          const enabled = sources.includes(s.id);
          const idx = sources.indexOf(s.id);
          return (
            <div key={s.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.2rem 0" }}>
              <input type="checkbox" checked={enabled} onChange={() => toggleSource(s.id)} />
              <span style={{ minWidth: "5rem", opacity: enabled ? 1 : 0.4 }}>{s.label}</span>
              {enabled && (
                <>
                  <button disabled={idx <= 0} onClick={() => moveSource(s.id, -1)} style={{ padding: "0 0.3rem", fontSize: "0.7rem" }}>&uarr;</button>
                  <button disabled={idx >= sources.length - 1} onClick={() => moveSource(s.id, 1)} style={{ padding: "0 0.3rem", fontSize: "0.7rem" }}>&darr;</button>
                </>
              )}
              {enabled && <span className="small" style={{ opacity: 0.5 }}>#{idx + 1}</span>}
            </div>
          );
        })}
        <div className="actions" style={{ marginTop: "0.6rem" }}>
          <button disabled={actionState.busy} onClick={save}>Save PDF fetch config</button>
        </div>
      </div>
    </div>
  );
}

const SUBTABS = ["Overview", "Docling", "GROBID", "RAG", "PDF Fetch"];

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
  triggerAction,
}) {
  const [subtab, setSubtab] = useState("Overview");

  if (setupError) return <div className="action-status error">Setup failed to load: {setupError}</div>;
  if (!setup) return <div className="action-status">Loading setup...</div>;

  return (
    <div className="paper-detail">
      <div className="subtab-bar">
        {SUBTABS.map((t) => (
          <button
            key={t}
            className={`subtab-btn${subtab === t ? " active" : ""}`}
            onClick={() => setSubtab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {subtab === "Overview" && (
        <>
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
            <h3>Config</h3>
            <div className="kv">
              <div className="small">Config file</div>
              <code>{setup.config_path}</code>
              <div className="small">Repo root</div>
              <code>{setup.repo_root}</code>
            </div>
          </div>
          <div className="panel">
            <h3>Pipeline</h3>
            <div className="small" style={{ marginBottom: "0.8rem" }}>
              Run these steps in order to populate the network graph.
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span className="badge" style={{ minWidth: "1.4rem", textAlign: "center" }}>1</span>
                <span className="small" style={{ flex: 1 }}>Fetch PDFs (cascade: {(setup.pdf_fetch?.sources || []).join(" → ") || "openalex"})</span>
                <button disabled={actionState.busy} onClick={() => triggerAction("fetch-pdfs-oa", {})}>Fetch PDFs</button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span className="badge" style={{ minWidth: "1.4rem", textAlign: "center" }}>2</span>
                <span className="small" style={{ flex: 1 }}>Resolve OpenAlex metadata for all papers</span>
                <button disabled={actionState.busy} onClick={() => triggerAction("openalex-resolve", {})}>Resolve OpenAlex</button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span className="badge" style={{ minWidth: "1.4rem", textAlign: "center" }}>3</span>
                <span className="small" style={{ flex: 1 }}>Expand citation graph (fetch references + citing works)</span>
                <button disabled={actionState.busy} onClick={() => triggerAction("graph-expand", {})}>Expand Graph</button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span className="badge" style={{ minWidth: "1.4rem", textAlign: "center" }}>4</span>
                <span className="small" style={{ flex: 1 }}>Run GROBID on all PDFs (extract references)</span>
                <button disabled={actionState.busy} onClick={() => triggerAction("grobid-run", { all: true })}>Run GROBID (all)</button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span className="badge" style={{ minWidth: "1.4rem", textAlign: "center" }}>5</span>
                <span className="small" style={{ flex: 1 }}>Match GROBID references to local library</span>
                <button disabled={actionState.busy} onClick={() => triggerAction("grobid-match", {})}>GROBID Match</button>
              </div>
            </div>
          </div>
          <div className="panel">
            <h3>Normalize citekeys</h3>
            <div className="small" style={{ marginBottom: "0.4rem" }}>
              Rename existing BibTeX citekeys to the standard <code>author_year_Title</code> format.
              Preview first, then apply. Derived artifacts (Docling, GROBID) will need to be re-run after.
            </div>
            <NormalizeKeysTool actionState={actionState} />
          </div>
        </>
      )}

      {subtab === "Docling" && (
        <div className="panel">
          <h2>Docling</h2>
          <div className="kv">
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
      )}

      {subtab === "GROBID" && (
        <div className="panel">
          <h2>GROBID</h2>
          <div className="small">Scholarly structure extraction — references, header metadata, sections from PDFs.</div>
          {setup.grobid && (
            <>
              <div className="kv" style={{ marginTop: "0.8rem" }}>
                <div className="small">URL</div>
                <code>{setup.grobid.url}</code>
                {setup.grobid.installation_path && (
                  <>
                    <div className="small">Install path</div>
                    <code>{setup.grobid.installation_path}</code>
                  </>
                )}
                {setup.grobid.derived_start_cmd && (
                  <>
                    <div className="small">Derived start cmd</div>
                    <code>{setup.grobid.derived_start_cmd.join(" ")}</code>
                  </>
                )}
                {setup.grobid.latency_ms != null && (
                  <>
                    <div className="small">Latency</div>
                    <code>{setup.grobid.latency_ms}ms</code>
                  </>
                )}
              </div>
              <div style={{ marginTop: "0.8rem" }}>
                <span className={`badge ${setup.grobid.ok === true ? "ok" : setup.grobid.ok === false ? "error" : ""}`}>
                  {setup.grobid.ok === true ? "grobid reachable" : setup.grobid.ok === false ? "grobid unreachable" : "not checked"}
                </span>
              </div>
              <div className={`action-status ${setup.grobid.ok === false ? "error" : ""}`}>
                {setup.grobid.message || "Click Check to verify."}
              </div>
              <GrobidConfigForm setup={setup} actionState={actionState} triggerSetupAction={triggerSetupAction} />
            </>
          )}
        </div>
      )}

      {subtab === "PDF Fetch" && (
        <div className="panel">
          <h2>PDF Fetch</h2>
          <div className="small">
            Configure the PDF download cascade: Pool, OpenAlex, Unpaywall, and EZProxy (institutional proxy).
          </div>
          <PdfFetchConfigForm setup={setup} actionState={actionState} triggerSetupAction={triggerSetupAction} />
        </div>
      )}

      {subtab === "RAG" && (
        <div className="panel">
          <h2>RAG</h2>
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
      )}
    </div>
  );
}
