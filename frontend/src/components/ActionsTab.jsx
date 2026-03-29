import { useState } from "react";

function LintPanel({ updateLibraryEntry }) {
  const [lintResults, setLintResults] = useState(null);
  const [lintLoading, setLintLoading] = useState(false);
  const [lintError, setLintError] = useState(null);
  const [applying, setApplying] = useState({});

  async function runLint() {
    setLintLoading(true);
    setLintError(null);
    try {
      const resp = await fetch("/api/library/lint", { method: "POST" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setLintResults(data);
    } catch (err) {
      setLintError(String(err.message || err));
    } finally {
      setLintLoading(false);
    }
  }

  async function applySuggestion(citekey, oldTag, newTag) {
    const key = `${citekey}:${oldTag}`;
    setApplying((p) => ({ ...p, [key]: true }));
    try {
      // Fetch current tags, replace oldTag with newTag
      const resp = await fetch(`/api/library/${encodeURIComponent(citekey)}`);
      const data = await resp.json();
      const currentTags = (data.tags || []).slice();
      const idx = currentTags.indexOf(oldTag);
      if (idx >= 0) {
        currentTags[idx] = newTag;
      }
      await updateLibraryEntry(citekey, { tags: currentTags });
      // Refresh lint
      runLint();
    } catch (err) {
      console.error("apply suggestion failed", err);
    } finally {
      setApplying((p) => ({ ...p, [key]: false }));
    }
  }

  const hasIssues = lintResults && (
    (lintResults.non_vocab || []).length > 0 ||
    (lintResults.duplicates || []).length > 0 ||
    (lintResults.suggestions || []).length > 0
  );

  return (
    <div className="lint-section">
      <h3>Tag Health</h3>
      <div className="actions">
        <button onClick={runLint} disabled={lintLoading}>
          {lintLoading ? "Linting..." : "Lint Tags"}
        </button>
      </div>
      {lintError && <div className="action-status error">{lintError}</div>}
      {lintResults && !hasIssues && (
        <div className="small" style={{ marginTop: "0.5rem", color: "var(--accent)" }}>
          All tags are healthy.
        </div>
      )}
      {lintResults && hasIssues && (
        <div style={{ marginTop: "0.6rem" }}>
          {(lintResults.non_vocab || []).length > 0 && (
            <div className="lint-group">
              <div className="lint-group-title">Non-vocabulary tags</div>
              {lintResults.non_vocab.map((item, idx) => (
                <div key={idx} className="lint-issue">
                  <div className="lint-issue-detail">
                    <span className="lint-issue-citekey">{item.citekey}</span>
                    {" "}<span className="lint-issue-tag">{item.tag}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {(lintResults.duplicates || []).length > 0 && (
            <div className="lint-group">
              <div className="lint-group-title">Duplicate tags</div>
              {lintResults.duplicates.map((item, idx) => (
                <div key={idx} className="lint-issue">
                  <div className="lint-issue-detail">
                    <span className="lint-issue-citekey">{item.citekey}</span>
                    {" "}<span className="lint-issue-tag">{item.tag}</span>
                    <span className="lint-issue-suggestion"> (appears {item.count}x)</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {(lintResults.suggestions || []).length > 0 && (
            <div className="lint-group">
              <div className="lint-group-title">Suggestions</div>
              {lintResults.suggestions.map((item, idx) => (
                <div key={idx} className="lint-issue">
                  <div className="lint-issue-detail">
                    <span className="lint-issue-citekey">{item.citekey}</span>
                    {" "}<span className="lint-issue-tag">{item.tag}</span>
                    {item.suggestion && (
                      <span className="lint-issue-suggestion"> → {item.suggestion}</span>
                    )}
                  </div>
                  {item.suggestion && (
                    <button
                      className="lint-apply-btn"
                      disabled={applying[`${item.citekey}:${item.tag}`]}
                      onClick={() => applySuggestion(item.citekey, item.tag, item.suggestion)}
                    >
                      Apply
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DedupPanel() {
  const [groups, setGroups] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [merging, setMerging] = useState({});

  async function runDedup() {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/library/dedup", { method: "POST" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setGroups(data.groups || []);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  async function mergeGroup(group) {
    const key = group.citekeys.join(",");
    setMerging((p) => ({ ...p, [key]: true }));
    try {
      const keep = group.suggested_keep;
      const remove = group.citekeys.filter((ck) => ck !== keep);
      const resp = await fetch("/api/library/dedup/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keep, remove }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      // Refresh
      runDedup();
    } catch (err) {
      console.error("merge failed", err);
    } finally {
      setMerging((p) => ({ ...p, [key]: false }));
    }
  }

  const reasonLabel = { doi: "Same DOI", title: "Similar title", openalex: "Same OpenAlex ID" };

  return (
    <div className="lint-section">
      <h3>Duplicates</h3>
      <div className="actions">
        <button onClick={runDedup} disabled={loading}>
          {loading ? "Scanning..." : "Detect Duplicates"}
        </button>
      </div>
      {error && <div className="action-status error">{error}</div>}
      {groups !== null && groups.length === 0 && (
        <div className="small" style={{ marginTop: "0.5rem", color: "var(--accent)" }}>
          No duplicates found.
        </div>
      )}
      {groups !== null && groups.length > 0 && (
        <div style={{ marginTop: "0.6rem" }}>
          {groups.map((g, idx) => {
            const key = g.citekeys.join(",");
            return (
              <div key={idx} className="lint-group">
                <div className="lint-group-title">
                  {reasonLabel[g.reason] || g.reason}
                  <span className="lint-issue-suggestion"> ({g.detail})</span>
                </div>
                {g.citekeys.map((ck) => (
                  <div key={ck} className="lint-issue">
                    <div className="lint-issue-detail">
                      <span className="lint-issue-citekey">{ck}</span>
                      {ck === g.suggested_keep && (
                        <span className="lint-issue-suggestion"> (keep)</span>
                      )}
                    </div>
                  </div>
                ))}
                <button
                  className="lint-apply-btn"
                  disabled={merging[key]}
                  onClick={() => mergeGroup(g)}
                  style={{ marginTop: "0.3rem" }}
                >
                  {merging[key] ? "Merging..." : "Merge"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ActionsTab({ activePaper, actionState, triggerAction, addDoi, setAddDoi, updateLibraryEntry, paperCount }) {
  const [expandConfirm, setExpandConfirm] = useState(false);
  return (
    <div className="panel">
      <h2>Actions</h2>
      <div className="small">
        {activePaper ? `Selected paper: ${activePaper.citekey}` : "No paper selected."}
      </div>
      <div className="actions">
        <button disabled={actionState.busy} onClick={() => triggerAction("bibtex-merge")} className="primary">
          Merge BibTeX
        </button>
        <button disabled={actionState.busy} onClick={() => triggerAction("openalex-resolve")}>
          Resolve OpenAlex
        </button>
        {!expandConfirm ? (
          <button disabled={actionState.busy} onClick={() => setExpandConfirm(true)}>
            Expand Graph
          </button>
        ) : (
          <span className="expand-confirm-inline">
            <span className="small">Query OpenAlex for {paperCount || "all"} papers? This may take several minutes.</span>
            <button onClick={() => { setExpandConfirm(false); triggerAction("graph-expand"); }}>Expand</button>
            <button onClick={() => setExpandConfirm(false)}>Cancel</button>
          </span>
        )}
        <button disabled={actionState.busy} onClick={() => triggerAction("site-build")}>
          Build Site
        </button>
        <button
          disabled={actionState.busy || !activePaper}
          onClick={() => activePaper && triggerAction("docling-run", { citekey: activePaper.citekey })}
        >
          Run Docling For Selected
        </button>
        <button
          disabled={actionState.busy || !activePaper}
          onClick={() => activePaper && triggerAction("grobid-run", { citekey: activePaper.citekey })}
        >
          Run GROBID For Selected
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("grobid-run", { all: true })}
        >
          Run GROBID For All
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("grobid-match")}
        >
          Match GROBID References
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("rag-build")}
        >
          Build RAG Index
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("fetch-pdfs-oa")}
        >
          Fetch OA PDFs
        </button>
      </div>

      {/* Auto-tag buttons */}
      <div className="actions" style={{ marginTop: "0.6rem" }}>
        <button
          disabled={actionState.busy || !activePaper}
          onClick={() => activePaper && triggerAction("autotag", { citekey: activePaper.citekey })}
        >
          Auto-tag Selected
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("autotag", {})}
        >
          Auto-tag All Untagged
        </button>
      </div>

      {/* Batch actions */}
      <h3 style={{ marginTop: "1.2rem", marginBottom: "0.4rem" }}>Batch Actions</h3>
      <div className="actions">
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("summarize", { status: "unread" })}
        >
          Summarize All Unread
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("concepts-extract", { all: true })}
        >
          Extract All Concepts
        </button>
        <button
          disabled={actionState.busy}
          onClick={() => triggerAction("autotag", { all_untagged: true })}
        >
          Auto-tag All Untagged
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
      {actionState.logs && (
        <pre style={{
          marginTop: "0.5rem",
          padding: "0.5rem",
          background: "var(--bg2, #1a1a1a)",
          border: "1px solid var(--border, #333)",
          borderRadius: "4px",
          fontSize: "0.72rem",
          maxHeight: "12rem",
          overflowY: "auto",
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          color: actionState.error ? "var(--error, #e06c75)" : "var(--fg2, #aaa)",
        }}>
          {actionState.logs}
        </pre>
      )}
      {(actionState.action === "openalex-resolve" || actionState.action === "graph-expand" || actionState.action === "docling-run" || actionState.action === "grobid-run" || actionState.action === "grobid-match" || actionState.action === "rag-build" || actionState.action === "fetch-pdfs-oa" || actionState.action === "autotag") &&
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

      {/* Tag Health lint panel */}
      <LintPanel updateLibraryEntry={updateLibraryEntry} />

      {/* Duplicate detection panel */}
      <DedupPanel />
    </div>
  );
}
