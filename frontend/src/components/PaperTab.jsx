import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { renderMarkdown } from "../utils/markdown.js";

const STATUSES = ["", "unread", "reading", "processed", "archived"];
const PRIORITIES = ["", "low", "normal", "high"];

function ArtifactBadge({ exists, label, onAction, busy, actionLabel }) {
  if (exists) return <span className="badge ok">{label}</span>;
  if (onAction) {
    return (
      <button
        className="badge badge-action"
        disabled={busy}
        onClick={onAction}
        title={actionLabel || `Run ${label}`}
      >
        {`no ${label}`} ↻
      </button>
    );
  }
  return <span className="badge">{`no ${label}`}</span>;
}

function LibraryPanel({ activePaper, updateLibraryEntry }) {
  const lib = activePaper.library || {};
  const [status, setStatus] = useState(lib.status || "");
  const [priority, setPriority] = useState(lib.priority || "");
  const [tagsText, setTagsText] = useState((lib.tags || []).join(", "));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const l = activePaper.library || {};
    setStatus(l.status || "");
    setPriority(l.priority || "");
    setTagsText((l.tags || []).join(", "));
  }, [activePaper.citekey]);

  async function save() {
    setSaving(true);
    const tags = tagsText.split(",").map((t) => t.trim()).filter(Boolean);
    await updateLibraryEntry(activePaper.citekey, { status: status || null, priority: priority || null, tags });
    setSaving(false);
  }

  return (
    <div className="panel">
      <h3>Library</h3>
      <div className="kv">
        <div className="small">Status</div>
        <select value={status} onChange={(ev) => setStatus(ev.target.value)}>
          {STATUSES.map((s) => <option key={s} value={s}>{s || "—"}</option>)}
        </select>
        <div className="small">Priority</div>
        <select value={priority} onChange={(ev) => setPriority(ev.target.value)}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p || "—"}</option>)}
        </select>
        <div className="small">Tags</div>
        <input
          value={tagsText}
          onChange={(ev) => setTagsText(ev.target.value)}
          placeholder="comma-separated"
          style={{ width: "100%" }}
        />
      </div>
      <div className="actions" style={{ marginTop: "0.6rem" }}>
        <button onClick={save} disabled={saving}>{saving ? "Saving..." : "Save"}</button>
      </div>
    </div>
  );
}

function MatchBadge({ similarity }) {
  const pct = Math.round(similarity * 100);
  const color = pct >= 90 ? "#4caf7d" : pct >= 70 ? "#e0a84b" : "#e06c75";
  return (
    <span style={{
      fontSize: "0.72rem", fontWeight: 700, color,
      background: `${color}18`, borderRadius: "999px",
      padding: "0.05rem 0.4rem", whiteSpace: "nowrap",
    }}>
      {pct}%
    </span>
  );
}

function AbsentRefsPanel({ citekey, triggerAction }) {
  const [refs, setRefs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [addDoi, setAddDoi] = useState("");
  const [resolving, setResolving] = useState({});
  const [resolved, setResolved] = useState({});
  const [threshold, setThreshold] = useState(70);
  const [copied, setCopied] = useState(false);

  function load() {
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/absent-refs`)
      .then((r) => r.json())
      .then((data) => { setRefs(data.absent_refs || []); setLoading(false); })
      .catch(() => { setRefs([]); setLoading(false); });
  }

  function resolveDoi(idx, title) {
    setResolving((p) => ({ ...p, [idx]: true }));
    fetch("/api/resolve-doi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
      .then((r) => r.json())
      .then((data) => {
        setResolved((p) => ({ ...p, [idx]: data }));
        setResolving((p) => ({ ...p, [idx]: false }));
      })
      .catch((err) => {
        setResolved((p) => ({ ...p, [idx]: { error: String(err) } }));
        setResolving((p) => ({ ...p, [idx]: false }));
      });
  }

  function resolveAll() {
    if (!refs) return;
    refs.forEach((ref, idx) => {
      if (!ref.doi && !resolved[idx] && !resolving[idx] && ref.title) {
        resolveDoi(idx, ref.title);
      }
    });
  }

  // DOIs that pass the threshold filter
  function getQualifiedDois() {
    if (!refs) return [];
    const dois = [];
    refs.forEach((ref, idx) => {
      if (ref.doi) {
        dois.push(ref.doi);
      } else {
        const res = resolved[idx];
        if (res && !res.error && res.doi && Math.round(res.similarity * 100) >= threshold) {
          dois.push(res.doi);
        }
      }
    });
    return [...new Set(dois)];
  }

  function addAll() {
    const dois = getQualifiedDois();
    if (dois.length) triggerAction("add-papers-bulk", { dois });
  }

  function copyAll() {
    const dois = getQualifiedDois();
    if (!dois.length) return;
    navigator.clipboard.writeText(dois.join("\n")).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const qualifiedDois = getQualifiedDois();
  const pendingResolve = refs ? refs.filter((r, idx) => !r.doi && !resolved[idx] && !resolving[idx] && r.title).length : 0;
  const resolveInProgress = Object.values(resolving).filter(Boolean).length;

  return (
    <div className="panel absent-refs-panel">
      {/* Header row */}
      <div className="absent-refs-header">
        <span className="absent-refs-title">
          Absent refs{refs !== null ? ` (${refs.length})` : ""}
        </span>
        <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", flexWrap: "wrap" }}>
          {refs !== null && pendingResolve > 0 && (
            <button
              className="absent-refs-btn-small"
              onClick={resolveAll}
              disabled={resolveInProgress > 0}
              title="Resolve DOIs for all unresolved refs"
            >
              {resolveInProgress > 0 ? `Resolving ${resolveInProgress}…` : `Resolve all (${pendingResolve})`}
            </button>
          )}
          {qualifiedDois.length > 0 && (
            <button className="absent-refs-btn-small" onClick={copyAll} title="Copy all qualified DOIs to clipboard">
              {copied ? "Copied!" : `Copy DOIs (${qualifiedDois.length})`}
            </button>
          )}
          {qualifiedDois.length > 0 && (
            <button className="absent-refs-btn-small absent-refs-btn-primary" onClick={addAll}>
              Add all ({qualifiedDois.length})
            </button>
          )}
          <button
            className="absent-refs-btn-small"
            onClick={load}
            disabled={loading}
            title="Reload absent references"
          >
            {loading ? "Loading…" : refs === null ? "Load" : "↺"}
          </button>
        </div>
      </div>

      {/* Threshold slider — only shown once we have some resolved results */}
      {refs !== null && Object.keys(resolved).some((k) => resolved[k] && resolved[k].doi) && (
        <div className="absent-refs-threshold">
          <label className="absent-refs-threshold-label">
            Min match
          </label>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={threshold}
            onChange={(ev) => setThreshold(Number(ev.target.value))}
            className="absent-refs-slider"
          />
          <span className="absent-refs-threshold-val">{threshold}%</span>
        </div>
      )}

      {/* Table */}
      {refs !== null && (
        refs.length === 0 ? (
          <div className="small" style={{ padding: "0.4rem 0", opacity: 0.7 }}>
            All references matched locally.
          </div>
        ) : (
          <div className="absent-refs-table">
            <div className="absent-refs-table-head">
              <span>#</span>
              <span>Reference</span>
              <span>DOI</span>
            </div>
            {refs.map((ref, idx) => {
              const res = resolved[idx];
              const belowThreshold = res && !res.error && res.doi &&
                Math.round(res.similarity * 100) < threshold;

              return (
                <div key={idx} className={`absent-refs-row${belowThreshold ? " absent-refs-row-dim" : ""}`}>
                  {/* # */}
                  <span className="absent-refs-num">{idx + 1}</span>

                  {/* Title */}
                  <span className="absent-ref-title" title={ref.title || ""}>
                    {ref.title || <em style={{ opacity: 0.45 }}>No title</em>}
                  </span>

                  {/* DOI column */}
                  <span className="absent-ref-doi-col">
                    {ref.doi ? (
                      <span className="absent-ref-doi-row">
                        <code className="absent-ref-doi">{ref.doi}</code>
                        <button
                          className="absent-refs-btn-small absent-refs-btn-primary"
                          onClick={() => triggerAction("add-paper", { doi: ref.doi })}
                        >Add</button>
                      </span>
                    ) : res ? (
                      res.error ? (
                        <span style={{ color: "var(--error, #e06c75)", fontSize: "0.78rem" }} title={res.error}>
                          error
                        </span>
                      ) : res.doi ? (
                        <span className="absent-ref-doi-row">
                          <code className="absent-ref-doi" title={res.matched_title}>{res.doi}</code>
                          <MatchBadge similarity={res.similarity} />
                          {!belowThreshold && (
                            <button
                              className="absent-refs-btn-small absent-refs-btn-primary"
                              onClick={() => triggerAction("add-paper", { doi: res.doi })}
                            >Add</button>
                          )}
                          <button
                            className="absent-refs-btn-small"
                            style={{ opacity: 0.4 }}
                            title="Dismiss"
                            onClick={() => setResolved((p) => { const n = {...p}; delete n[idx]; return n; })}
                          >✕</button>
                        </span>
                      ) : (
                        <span style={{ opacity: 0.4, fontSize: "0.78rem" }}>not found</span>
                      )
                    ) : (
                      <button
                        className="absent-refs-btn-small"
                        disabled={resolving[idx] || !ref.title}
                        onClick={() => resolveDoi(idx, ref.title)}
                        title={ref.title ? "Look up on CrossRef" : "No title"}
                      >
                        {resolving[idx] ? "…" : "Resolve"}
                      </button>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )
      )}

      {/* Manual DOI input */}
      {refs !== null && (
        <div className="absent-refs-add-row">
          <input
            className="absent-refs-doi-input"
            value={addDoi}
            onChange={(ev) => setAddDoi(ev.target.value)}
            placeholder="Add by DOI…"
            onKeyDown={(ev) => {
              if (ev.key === "Enter" && addDoi.trim()) {
                triggerAction("add-paper", { doi: addDoi.trim() });
                setAddDoi("");
              }
            }}
          />
          <button
            className="absent-refs-btn-small absent-refs-btn-primary"
            disabled={!addDoi.trim()}
            onClick={() => { triggerAction("add-paper", { doi: addDoi.trim() }); setAddDoi(""); }}
          >
            Add
          </button>
        </div>
      )}
    </div>
  );
}

function addCitationLinks(html) {
  // Post-process rendered HTML to turn [@citekey] and [@k1; @k2] into clickable spans
  return html.replace(/\[@([^\]]+)\]/g, (_, inner) => {
    const keys = inner.split(";").map((k) => k.trim().replace(/^@/, ""));
    return keys
      .map((key) => `<a class="cite-link" data-key="${key}">[@${key}]</a>`)
      .join("");
  });
}

function CitationTooltip({ paper, x, y }) {
  if (!paper) return null;
  const style = {
    position: "fixed",
    left: Math.min(x + 12, window.innerWidth - 320),
    top: y + 16,
    zIndex: 9999,
    maxWidth: 300,
    background: "var(--bg2, #1e2230)",
    border: "1px solid var(--border, #333)",
    borderRadius: 6,
    padding: "0.6rem 0.8rem",
    boxShadow: "0 4px 16px rgba(0,0,0,0.5)",
    pointerEvents: "none",
  };
  return (
    <div style={style}>
      <div style={{ fontWeight: 600, fontSize: "0.82rem", marginBottom: "0.25rem", lineHeight: 1.3 }}>
        {paper.title || paper.citekey}
      </div>
      <div style={{ fontSize: "0.76rem", opacity: 0.7 }}>
        {(paper.authors || []).slice(0, 3).join(", ")}{(paper.authors || []).length > 3 ? " et al." : ""}
        {paper.year ? ` · ${paper.year}` : ""}
      </div>
    </div>
  );
}

function StandardizedTab({ citekey, papers }) {
  const [text, setText] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tooltip, setTooltip] = useState(null); // { paper, x, y }
  const loadedFor = useRef(null);

  const paperMap = useMemo(() => {
    const m = {};
    (papers || []).forEach((p) => { m[p.citekey] = p; });
    return m;
  }, [papers]);

  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setText(null);
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/ref-md`)
      .then((r) => r.text())
      .then((t) => { setText(t); setLoading(false); })
      .catch(() => { setText(""); setLoading(false); });
  }, [citekey]);

  const html = useMemo(() => {
    if (!text) return "";
    const raw = renderMarkdown(text, { imageBase: `/api/files/docling/${citekey}` });
    return addCitationLinks(raw);
  }, [text, citekey]);

  function handleMouseMove(e) {
    const a = e.target.closest(".cite-link");
    if (!a) {
      if (tooltip) setTooltip(null);
      return;
    }
    const key = a.dataset.key;
    const paper = paperMap[key] || null;
    setTooltip({ paper: paper || { citekey: key, title: key }, x: e.clientX, y: e.clientY });
  }

  if (loading || text === null) {
    return <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>Loading…</div>;
  }
  if (!text.trim()) {
    return (
      <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>
        No standardized markdown yet. Run: <code>biblio ref-md run --key {citekey}</code>
      </div>
    );
  }
  return (
    <div onMouseMove={handleMouseMove} onMouseLeave={() => setTooltip(null)}>
      <div className="docling-box docling-box-full" dangerouslySetInnerHTML={{ __html: html }} />
      {tooltip && <CitationTooltip paper={tooltip.paper} x={tooltip.x} y={tooltip.y} />}
    </div>
  );
}

function isLogoImage(fig) {
  if (!fig.width || !fig.height) return true;
  const minDim = Math.min(fig.width, fig.height);
  const maxDim = Math.max(fig.width, fig.height);
  return minDim < 150 || maxDim / minDim > 4 || fig.size_bytes < 8000;
}

function FiguresTab({ citekey }) {
  const [figures, setFigures] = useState(null);
  const [loading, setLoading] = useState(false);
  const [figIdx, setFigIdx] = useState(0);
  const [filterLogos, setFilterLogos] = useState(true);
  const loadedFor = useRef(null);

  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setFigures(null);
    setFigIdx(0);
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/figures`)
      .then((r) => r.json())
      .then((data) => { setFigures(data.figures || []); setLoading(false); })
      .catch(() => { setFigures([]); setLoading(false); });
  }, [citekey]);

  if (loading || figures === null) {
    return <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>Loading figures…</div>;
  }

  const visible = filterLogos ? figures.filter((f) => !isLogoImage(f)) : figures;
  const hiddenCount = figures.length - visible.length;
  const safeIdx = Math.min(figIdx, Math.max(0, visible.length - 1));
  const current = visible[safeIdx] || null;

  return (
    <div className="figures-tab">
      <div className="figures-toolbar">
        <button
          className="figures-nav-btn"
          disabled={safeIdx === 0}
          onClick={() => setFigIdx((i) => Math.max(0, i - 1))}
        >←</button>
        <span className="figures-counter">
          {visible.length ? `${safeIdx + 1} / ${visible.length}` : "No figures"}
        </span>
        <button
          className="figures-nav-btn"
          disabled={safeIdx >= visible.length - 1}
          onClick={() => setFigIdx((i) => Math.min(visible.length - 1, i + 1))}
        >→</button>
        <label className="figures-filter-label">
          <input
            type="checkbox"
            checked={filterLogos}
            onChange={(ev) => { setFilterLogos(ev.target.checked); setFigIdx(0); }}
          />
          Filter logos
        </label>
        {hiddenCount > 0 && filterLogos && (
          <span className="small" style={{ opacity: 0.5 }}>{hiddenCount} hidden</span>
        )}
      </div>

      {current ? (
        <div className="figures-viewer">
          <img
            key={current.path}
            src={`/api/files/docling/${encodeURIComponent(citekey)}/${current.path}`}
            alt={`Figure ${safeIdx + 1}`}
            className="figures-img"
          />
          {current.caption && (
            <div className="figures-caption">{current.caption}</div>
          )}
          <div className="figures-img-meta">
            {current.width}×{current.height} · {Math.round(current.size_bytes / 1024)}KB
          </div>
        </div>
      ) : (
        <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>
          {figures.length === 0 ? "No figures extracted for this paper." : "All images filtered out — uncheck Filter logos to see them."}
        </div>
      )}
    </div>
  );
}

const CONTENT_SUBTABS = ["PDF", "Docling", "Standardized", "Figures", "GROBID"];

export default function PaperTab({
  activePaper, activeArtifacts, doclingHtml,
  updateLibraryEntry, triggerAction, actionState, papers,
}) {
  const [contentTab, setContentTab] = useState("PDF");
  const [fullscreen, setFullscreen] = useState(false);
  const busy = actionState ? actionState.busy : false;

  const toggleFullscreen = useCallback(() => setFullscreen((f) => !f), []);

  if (!activePaper) return null;

  const a = activeArtifacts;
  const hasPdf = a && a.pdf.exists;
  const hasDocling = a && a.docling_md.exists;
  const hasOpenalex = a && a.openalex.exists;
  const hasGrobid = a && a.grobid && a.grobid.exists;

  return (
    <div className="paper-detail paper-detail-split">
      {/* Header */}
      <div className="panel paper-detail-header">
        <div className="paper-card-title">
          <h2>{activePaper.citekey}</h2>
          <span className="small">{activePaper.year || "n.d."}</span>
        </div>
        <div className="small">{activePaper.title}</div>
        <p>{(activePaper.authors || []).join(", ") || "Unknown authors"}</p>
        <div style={{ display: "flex", gap: "0.3rem", flexWrap: "wrap" }}>
          <ArtifactBadge
            exists={hasPdf}
            label="pdf"
            busy={busy}
            onAction={!hasPdf ? () => triggerAction("fetch-pdfs-oa", {}) : null}
            actionLabel="Fetch PDF from OpenAlex OA"
          />
          <ArtifactBadge
            exists={hasDocling}
            label="docling"
            busy={busy}
            onAction={!hasDocling ? () => triggerAction("docling-run", { citekey: activePaper.citekey }) : null}
            actionLabel="Run Docling on this paper"
          />
          <ArtifactBadge
            exists={hasOpenalex}
            label="openalex"
            busy={busy}
            onAction={!hasOpenalex ? () => triggerAction("openalex-resolve", {}) : null}
            actionLabel="Resolve OpenAlex metadata"
          />
          <ArtifactBadge
            exists={hasGrobid}
            label="grobid"
            busy={busy}
            onAction={!hasGrobid ? () => triggerAction("grobid-run", { citekey: activePaper.citekey }) : null}
            actionLabel="Run GROBID on this paper"
          />
          {hasOpenalex && (
            <button
              className="badge badge-action"
              disabled={busy}
              title="Expand citation graph for this paper (merges into shared candidates)"
              onClick={() => triggerAction("graph-expand", { citekey: activePaper.citekey, merge: true })}
            >
              expand graph ↻
            </button>
          )}
        </div>
      </div>

      {/* Two-column body */}
      <div className="paper-body-split">
        {/* Left: content subtabs */}
        <div className={`paper-content-col${fullscreen ? " paper-content-fullscreen" : ""}`}>
          <div className="subtab-bar">
            {CONTENT_SUBTABS.map((t) => (
              <button
                key={t}
                className={`subtab-btn${contentTab === t ? " active" : ""}`}
                onClick={() => setContentTab(t)}
              >
                {t}
              </button>
            ))}
            <button
              className="subtab-btn subtab-expand"
              title={fullscreen ? "Exit fullscreen" : "Expand to fullscreen"}
              onClick={toggleFullscreen}
              style={{ marginLeft: "auto" }}
            >
              {fullscreen ? "⊠" : "⛶"}
            </button>
          </div>

          {contentTab === "PDF" && (
            <div className="panel paper-content-panel">
              {hasPdf
                ? <iframe
                    className="pdf-frame"
                    src={`/api/files/pdf/${encodeURIComponent(activePaper.citekey)}`}
                    title={`${activePaper.citekey} PDF`}
                  />
                : <div className="small">No PDF available for this paper.</div>
              }
            </div>
          )}

          {contentTab === "Docling" && (
            <div className="panel paper-content-panel">
              {hasDocling && activePaper.docling && activePaper.docling.html
                ? <div className="docling-box docling-box-full" dangerouslySetInnerHTML={{ __html: activePaper.docling.html }} />
                : <div className="small">No Docling output available for this paper.</div>
              }
            </div>
          )}

          {contentTab === "Standardized" && (
            <div className="panel paper-content-panel">
              <StandardizedTab citekey={activePaper.citekey} papers={papers} />
            </div>
          )}

          {contentTab === "Figures" && (
            <div className="paper-content-panel figures-content-panel">
              <FiguresTab citekey={activePaper.citekey} />
            </div>
          )}

          {contentTab === "GROBID" && (
            <div className="panel paper-content-panel">
              {activePaper.grobid && activePaper.grobid.header && Object.keys(activePaper.grobid.header).length > 0 ? (
                <>
                  <div className="kv" style={{ marginBottom: "0.8rem" }}>
                    {activePaper.grobid.header.title && (
                      <>
                        <div className="small">Title</div>
                        <div>{activePaper.grobid.header.title}</div>
                      </>
                    )}
                    {activePaper.grobid.header.authors && activePaper.grobid.header.authors.length > 0 && (
                      <>
                        <div className="small">Authors</div>
                        <div>{activePaper.grobid.header.authors.join(", ")}</div>
                      </>
                    )}
                    {activePaper.grobid.header.year && (
                      <>
                        <div className="small">Year</div>
                        <div>{activePaper.grobid.header.year}</div>
                      </>
                    )}
                    {activePaper.grobid.header.doi && (
                      <>
                        <div className="small">DOI</div>
                        <code>{activePaper.grobid.header.doi}</code>
                      </>
                    )}
                    <div className="small">References</div>
                    <div>{activePaper.grobid.reference_count ?? 0}</div>
                  </div>
                  {activePaper.grobid.header.abstract && (
                    <div className="small" style={{ marginBottom: "1rem" }}>{activePaper.grobid.header.abstract}</div>
                  )}
                  <AbsentRefsPanel citekey={activePaper.citekey} triggerAction={triggerAction} />
                </>
              ) : (
                <div className="small">No GROBID data. Run GROBID on this paper first.</div>
              )}
            </div>
          )}
        </div>

        {/* Right: sidebar info */}
        <div className="paper-sidebar-col">
          <LibraryPanel activePaper={activePaper} updateLibraryEntry={updateLibraryEntry} />

          <div className="panel">
            <h3>Related local papers</h3>
            <ul className="list-clean">
              {((activePaper.related_local || []).length
                ? activePaper.related_local
                : [{ citekey: null }]
              ).map((item, idx) =>
                item.citekey
                  ? (
                    <li key={`${item.citekey}-${idx}`}>
                      <strong>{item.citekey}</strong>
                      <span className="small"> score {item.score}, shared out {item.shared_outgoing}, in {item.shared_incoming}</span>
                    </li>
                  )
                  : <li key="none" className="small">No related local papers yet.</li>
              )}
            </ul>
          </div>

          <div className="panel">
            <h3>Neighborhood</h3>
            <div className="small" style={{ marginBottom: "0.4rem" }}>
              {(activePaper.graph.outgoing || []).length} outgoing · {(activePaper.graph.incoming || []).length} incoming
            </div>
            <ul className="list-clean">
              {(activePaper.graph.outgoing || []).slice(0, 8).map((item, idx) => (
                <li key={`o-${idx}`} className="small">{item.citekey || item.openalex_id}</li>
              ))}
            </ul>
          </div>

          {hasGrobid && (
            <AbsentRefsPanel citekey={activePaper.citekey} triggerAction={triggerAction} />
          )}
        </div>
      </div>
    </div>
  );
}
