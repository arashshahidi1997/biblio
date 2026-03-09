import { useState } from "react";

export default function SearchTab({ setActiveKey, setActiveTab }) {
  const [query, setQuery] = useState("");
  const [nResults, setNResults] = useState(10);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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

  return (
    <div className="panel">
      <h2>Semantic Search</h2>
      <div className="small" style={{ marginBottom: "0.8rem" }}>
        Full-text semantic search over indexed docling documents.
        Use <strong>Actions → Build RAG Index</strong> first.
      </div>
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
            />
          </div>
          <div className="field">
            <label>Results</label>
            <select value={nResults} onChange={(ev) => setNResults(Number(ev.target.value))}>
              {[5, 10, 20, 50].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <div className="field" style={{ alignSelf: "flex-end" }}>
            <button type="submit" className="primary" disabled={loading || !query.trim()}>
              {loading ? "Searching..." : "Search"}
            </button>
          </div>
        </div>
      </form>

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
                    <span className="badge ok" style={{ fontSize: "0.7rem" }}>
                      dist {item.distance}
                    </span>
                    <span className="badge" style={{ fontSize: "0.7rem" }}>
                      chunk {item.chunk_index}
                    </span>
                  </div>
                </div>
                <div className="small" style={{ marginTop: "0.4rem", whiteSpace: "pre-wrap", opacity: 0.85 }}>
                  {item.text && item.text.length > 400 ? item.text.slice(0, 400) + "…" : item.text}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
