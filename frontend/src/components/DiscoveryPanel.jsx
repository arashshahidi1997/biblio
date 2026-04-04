import { useState } from "react";

/**
 * Lightweight panel for importing papers from OpenAlex.
 * The user browses openalex.org, then pastes URLs here to import.
 * Supports: single work URLs, multiple URLs (one per line).
 */
export default function DiscoveryPanel({ onClose }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null); // [{citekey, doi, openalex_id, error}]
  const [error, setError] = useState(null);

  function parseInput(text) {
    // Extract OpenAlex work IDs from URLs
    const re = /https?:\/\/(?:api\.)?openalex\.org\/(?:works\/)?(W\d+)/gi;
    const ids = [];
    const seen = new Set();
    let m;
    while ((m = re.exec(text)) !== null) {
      const wid = m[1].toUpperCase();
      if (!seen.has(wid)) { seen.add(wid); ids.push(wid); }
    }
    // Also try bare work IDs (W1234567890)
    const bareRe = /\b(W\d{5,})\b/g;
    while ((m = bareRe.exec(text)) !== null) {
      const wid = m[1].toUpperCase();
      if (!seen.has(wid)) { seen.add(wid); ids.push(wid); }
    }
    // Also extract DOIs
    const doiRe = /10\.\d{4,}\/\S+/g;
    const cleaned = text.replace(/https?:\/\/(?:dx\.)?doi\.org\//g, "");
    const dois = [];
    const seenDoi = new Set();
    while ((m = doiRe.exec(cleaned)) !== null) {
      let doi = m[0].replace(/[.,;:)\]}>]+$/, "");
      if (!seenDoi.has(doi)) { seenDoi.add(doi); dois.push(doi); }
    }
    return { openalex_ids: ids, dois };
  }

  async function doImport() {
    const { openalex_ids, dois } = parseInput(input);
    if (!openalex_ids.length && !dois.length) {
      setError("No OpenAlex work IDs or DOIs found in input");
      return;
    }
    setLoading(true);
    setError(null);
    setResults(null);

    const items = [
      ...openalex_ids.map((id) => ({ openalex_id: id })),
      ...dois.map((doi) => ({ doi })),
    ];

    const out = [];
    for (const item of items) {
      try {
        const resp = await fetch("/api/actions/add-paper", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(item),
        });
        const data = await resp.json();
        if (!resp.ok) {
          out.push({ ...item, error: data.detail || `HTTP ${resp.status}` });
        } else {
          out.push({ ...item, citekey: data.citekey, doi: data.doi, openalex_id: data.openalex_id });
        }
      } catch (err) {
        out.push({ ...item, error: String(err.message || err) });
      }
    }
    setResults(out);
    setLoading(false);
  }

  const { openalex_ids, dois } = input.trim() ? parseInput(input) : { openalex_ids: [], dois: [] };
  const totalParsed = openalex_ids.length + dois.length;

  return (
    <div className="discovery-panel">
      <div className="discovery-panel-header">
        <h3 style={{ margin: 0 }}>Import from OpenAlex</h3>
        {onClose && <button className="icon-btn" onClick={onClose} title="Close">&#x2715;</button>}
      </div>

      <div className="small" style={{ opacity: 0.7, marginBottom: "0.5rem" }}>
        Browse <a href="https://openalex.org" target="_blank" rel="noreferrer">openalex.org</a> to
        find papers, then paste URLs or work IDs here.
      </div>

      {!results && (
        <>
          <textarea
            value={input}
            onChange={(ev) => setInput(ev.target.value)}
            placeholder={"Paste OpenAlex URLs, work IDs (W...), or DOIs\ne.g. https://openalex.org/works/W2741809807\nor one per line for bulk import"}
            rows={4}
            style={{
              width: "100%",
              fontFamily: "monospace",
              fontSize: "0.78rem",
              background: "var(--bg2, #1a1a1a)",
              color: "var(--fg, #ddd)",
              border: "1px solid var(--border, #333)",
              borderRadius: "4px",
              padding: "0.4rem",
              resize: "vertical",
            }}
          />
          {totalParsed > 0 && (
            <div className="small" style={{ marginTop: "0.3rem", opacity: 0.7 }}>
              Found: {openalex_ids.length > 0 && `${openalex_ids.length} OpenAlex work${openalex_ids.length > 1 ? "s" : ""}`}
              {openalex_ids.length > 0 && dois.length > 0 && ", "}
              {dois.length > 0 && `${dois.length} DOI${dois.length > 1 ? "s" : ""}`}
            </div>
          )}
          <div className="actions" style={{ marginTop: "0.4rem" }}>
            <button
              className="primary"
              disabled={loading || totalParsed === 0}
              onClick={doImport}
            >
              {loading ? "Importing..." : `Import ${totalParsed} paper${totalParsed !== 1 ? "s" : ""}`}
            </button>
          </div>
        </>
      )}

      {error && <div className="action-status error" style={{ marginTop: "0.5rem" }}>{error}</div>}

      {results && (
        <div style={{ marginTop: "0.5rem" }}>
          <div className="small" style={{ color: "var(--accent, #61afef)", marginBottom: "0.3rem" }}>
            {results.filter((r) => r.citekey).length} of {results.length} imported successfully
          </div>
          <div style={{ maxHeight: "12rem", overflowY: "auto", fontSize: "0.75rem" }}>
            {results.map((r, idx) => (
              <div key={idx} style={{ padding: "0.2rem 0", borderBottom: "1px solid var(--border, #333)" }}>
                {r.citekey ? (
                  <span style={{ color: "var(--accent, #61afef)" }}>
                    <code>{r.citekey}</code>
                    {r.openalex_id && (
                      <a href={`https://openalex.org/works/${r.openalex_id}`} target="_blank" rel="noreferrer"
                        style={{ marginLeft: "0.4rem", opacity: 0.6, fontSize: "0.7rem" }}>
                        OpenAlex &#x2197;
                      </a>
                    )}
                  </span>
                ) : (
                  <span style={{ color: "var(--error, #e06c75)" }}>
                    <code>{r.openalex_id || r.doi}</code> {" \u2014 "} {r.error}
                  </span>
                )}
              </div>
            ))}
          </div>
          <div className="actions" style={{ marginTop: "0.4rem" }}>
            <button onClick={() => { setResults(null); setInput(""); }}>Import More</button>
          </div>
        </div>
      )}
    </div>
  );
}
