import { useState, useEffect, useRef, useCallback } from "react";

export default function SearchTab({ setActiveKey, setActiveTab, triggerAction, actionState }) {
  const [query, setQuery] = useState("");
  const [nResults, setNResults] = useState(10);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // RAG index status
  const [ragStatus, setRagStatus] = useState(null);
  const [ragLoading, setRagLoading] = useState(true);
  const [buildConfirm, setBuildConfirm] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);
  const pollRef = useRef(null);

  const fetchRagStatus = useCallback(async () => {
    try {
      const resp = await fetch("/api/rag/status");
      if (resp.ok) {
        const data = await resp.json();
        setRagStatus(data);
        return data;
      }
    } catch (_) {}
    setRagLoading(false);
    return null;
  }, []);

  // Initial load
  useEffect(() => {
    fetchRagStatus().then(() => setRagLoading(false));
  }, [fetchRagStatus]);

  // Poll while building
  const isBuilding = ragStatus?.building ||
    (actionState?.busy && actionState?.action === "rag-build");

  useEffect(() => {
    if (isBuilding) {
      pollRef.current = window.setInterval(() => {
        fetchRagStatus();
      }, 1500);
    } else if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [isBuilding, fetchRagStatus]);

  // Refresh status when build finishes
  useEffect(() => {
    if (actionState?.action === "rag-build" && !actionState?.busy && !actionState?.error) {
      fetchRagStatus();
    }
  }, [actionState?.busy, actionState?.action, actionState?.error, fetchRagStatus]);

  async function doSearch(e) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const resp = await fetch("/api/search/semantic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), n_results: nResults }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setResults(data.results || []);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  function handleBuild() {
    setBuildConfirm(false);
    triggerAction("rag-build");
    // Immediately start polling
    fetchRagStatus();
  }

  function formatTimeAgo(ts) {
    if (!ts) return "";
    const diff = (Date.now() / 1000) - ts;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  }

  const indexExists = ragStatus?.exists;
  const isStale = ragStatus?.stale;
  const doclingCount = ragStatus?.docling_count || 0;
  const indexedCount = ragStatus?.indexed_count || 0;
  const staleCount = ragStatus?.stale_count || 0;
  const buildBusy = isBuilding || (actionState?.busy && actionState?.action === "rag-build");
  const buildProgress = actionState?.action === "rag-build" ? actionState : null;

  // Show loading placeholder
  if (ragLoading) {
    return (
      <div className="panel">
        <h2>Semantic Search</h2>
        <div className="small">Loading index status...</div>
      </div>
    );
  }

  // ── Empty state: no RAG index ──────────────────────────────────────────
  if (!indexExists && !buildBusy) {
    return (
      <div className="panel">
        <h2>Semantic Search</h2>
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: "1rem", padding: "2rem 1rem", textAlign: "center",
        }}>
          <div style={{ fontSize: "2.5rem", opacity: 0.4 }}>&#128270;</div>
          <div>
            <strong>Semantic search requires a RAG index</strong>
          </div>
          <div className="small" style={{ maxWidth: "28rem" }}>
            Your library has <strong>{doclingCount}</strong> paper{doclingCount !== 1 ? "s" : ""} with
            text extraction (docling). Build the index to enable semantic search across all papers.
          </div>
          {!buildConfirm ? (
            <button
              className="primary"
              disabled={doclingCount === 0}
              onClick={() => setBuildConfirm(true)}
            >
              Build Index ({doclingCount} paper{doclingCount !== 1 ? "s" : ""})
            </button>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
              <div className="small">
                This will embed {doclingCount} document{doclingCount !== 1 ? "s" : ""} and may take several minutes. Proceed?
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button className="primary" onClick={handleBuild}>Build</button>
                <button onClick={() => setBuildConfirm(false)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <h2>Semantic Search</h2>

      {/* ── Build progress ──────────────────────────────────────────── */}
      {buildBusy && (
        <div style={{
          padding: "0.6rem 0.8rem", marginBottom: "0.6rem",
          background: "var(--bg2, #1a1a1a)", borderRadius: "4px",
          border: "1px solid var(--border, #333)",
        }}>
          <div className="small" style={{ marginBottom: "0.3rem" }}>
            Building index...
            {buildProgress?.progressTotal > 0
              ? ` ${buildProgress.progressCompleted}/${buildProgress.progressTotal} documents embedded`
              : ""}
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${buildProgress?.progressTotal > 0
                  ? (buildProgress.progressPercent || 0)
                  : 100}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* ── Staleness banner ────────────────────────────────────────── */}
      {!buildBusy && indexExists && isStale && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0.5rem 0.8rem", marginBottom: "0.6rem",
          background: "var(--bg2, #1a1a1a)", borderRadius: "4px",
          border: "1px solid var(--warning, #e5c07b)",
          fontSize: "0.78rem",
        }}>
          <span>
            Index is outdated — {staleCount} new paper{staleCount !== 1 ? "s" : ""} since last build.
            {ragStatus?.last_built && (
              <span style={{ opacity: 0.7 }}>
                {" "}Last built: {formatTimeAgo(ragStatus.last_built)} · {indexedCount}/{doclingCount} papers indexed
              </span>
            )}
          </span>
          {!buildConfirm ? (
            <button
              style={{ marginLeft: "0.5rem", fontSize: "0.75rem", padding: "0.2rem 0.6rem" }}
              onClick={() => setBuildConfirm(true)}
            >
              Rebuild
            </button>
          ) : (
            <span style={{ display: "flex", gap: "0.3rem", marginLeft: "0.5rem" }}>
              <span className="small" style={{ alignSelf: "center" }}>
                Embed {doclingCount} docs?
              </span>
              <button style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }} className="primary" onClick={handleBuild}>Build</button>
              <button style={{ fontSize: "0.75rem", padding: "0.2rem 0.5rem" }} onClick={() => setBuildConfirm(false)}>Cancel</button>
            </span>
          )}
        </div>
      )}

      {/* ── Search form ─────────────────────────────────────────────── */}
      <form onSubmit={doSearch}>
        <div className="controls" style={{ marginBottom: "0.6rem" }}>
          <div className="field" style={{ flexGrow: 1 }}>
            <label>Query</label>
            <input
              value={query}
              onChange={(ev) => setQuery(ev.target.value)}
              placeholder="e.g. hippocampal replay during sleep"
              style={{ width: "100%" }}
              autoFocus
              disabled={buildBusy}
            />
          </div>
          <div className="field">
            <label>Results</label>
            <select value={nResults} onChange={(ev) => setNResults(Number(ev.target.value))} disabled={buildBusy}>
              {[5, 10, 20, 50].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="field" style={{ alignSelf: "flex-end" }}>
            <button type="submit" className="primary" disabled={loading || !query.trim() || buildBusy}>
              {loading ? "Searching..." : "Search"}
            </button>
          </div>
        </div>
      </form>

      {/* ── Index stats line ────────────────────────────────────────── */}
      {indexExists && !buildBusy && (
        <div
          className="small"
          style={{ marginBottom: "0.6rem", cursor: "pointer", position: "relative" }}
          onClick={() => setShowTooltip((v) => !v)}
        >
          {indexedCount} paper{indexedCount !== 1 ? "s" : ""} indexed
          {ragStatus?.last_built && ` · Last built ${formatTimeAgo(ragStatus.last_built)}`}
          {showTooltip && (
            <div style={{
              position: "absolute", top: "1.4rem", left: 0, zIndex: 10,
              background: "var(--bg2, #1a1a1a)", border: "1px solid var(--border, #333)",
              borderRadius: "4px", padding: "0.5rem 0.7rem", fontSize: "0.72rem",
              minWidth: "16rem", boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
            }}>
              <div>Embedding model: {ragStatus?.embedding_model || "unknown"}</div>
              <div>Chunk size: {ragStatus?.chunk_size || "?"} chars</div>
              <div>Chunk overlap: {ragStatus?.chunk_overlap || "?"} chars</div>
              <div>Persist dir: {ragStatus?.exists ? "exists" : "missing"}</div>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="action-status error">{error}</div>
      )}

      {results !== null && results.length === 0 && (
        <div className="small">No results found.</div>
      )}

      {results && results.length > 0 && (
        <div>
          <div className="small" style={{ marginBottom: "0.5rem" }}>
            {results.length} result{results.length !== 1 ? "s" : ""} for <em>"{query}"</em>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            {results.map((item, idx) => (
              <div
                key={item.id || idx}
                className="panel"
                style={{ cursor: "pointer", padding: "0.7rem 1rem" }}
                onClick={() => {
                  if (item.citekey) {
                    setActiveKey(item.citekey);
                    setActiveTab("paper");
                  }
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
                  <div>
                    <strong>{item.citekey}</strong>
                    {item.title && <span className="small" style={{ marginLeft: "0.5rem" }}>{item.title}</span>}
                    {item.year && <span className="small" style={{ marginLeft: "0.4rem" }}>({item.year})</span>}
                  </div>
                  <div style={{ display: "flex", gap: "0.4rem", flexShrink: 0 }}>
                    {item.distance != null && (
                      <span className="badge ok" style={{ fontSize: "0.7rem" }}>
                        dist {item.distance}
                      </span>
                    )}
                    <span className="badge" style={{ fontSize: "0.7rem" }}>
                      chunk {item.chunk_index}
                    </span>
                  </div>
                </div>
                <div className="small" style={{ marginTop: "0.4rem", whiteSpace: "pre-wrap", opacity: 0.85 }}>
                  {item.text && item.text.length > 400 ? item.text.slice(0, 400) + "\u2026" : item.text}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
