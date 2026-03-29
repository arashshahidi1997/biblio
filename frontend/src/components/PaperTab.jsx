import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { renderMarkdown } from "../utils/markdown.js";
import TagInput from "./TagInput.jsx";
import ActionProgress from "./ActionProgress.jsx";

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

const CONCEPT_GROUPS = ["methods", "datasets", "metrics", "domains", "techniques"];

function ConceptsPanel({ citekey, hasConcepts, triggerAction, busy, onConceptClick }) {
  const [concepts, setConcepts] = useState(null);
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const loadedFor = useRef(null);

  function fetchConcepts() {
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/concepts`)
      .then((r) => { if (!r.ok) throw new Error("not found"); return r.json(); })
      .then((data) => { setConcepts(data); setLoading(false); })
      .catch(() => { setConcepts(null); setLoading(false); });
  }

  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setConcepts(null);
    setExtracting(false);
    if (!hasConcepts) { setLoading(false); return; }
    fetchConcepts();
  }, [citekey, hasConcepts]);

  useEffect(() => { loadedFor.current = null; }, [citekey]);

  function handleComplete() {
    setExtracting(false);
    loadedFor.current = null;
    fetchConcepts();
  }

  if (loading) return <div className="panel"><h3>Concepts</h3><div className="small" style={{ opacity: 0.6 }}>Loading…</div></div>;

  if (extracting) {
    return (
      <div className="panel">
        <h3>Concepts</h3>
        <div style={{ textAlign: "center", padding: "0.5rem 0" }}>
          <ActionProgress
            endpoint="/api/actions/concepts-extract"
            body={{ citekey }}
            onComplete={handleComplete}
            onError={() => setExtracting(false)}
            label="Extracting concepts"
            autoTrigger
          />
        </div>
      </div>
    );
  }

  if (!concepts) {
    return (
      <div className="panel">
        <h3>Concepts</h3>
        <div style={{ textAlign: "center", padding: "0.5rem 0" }}>
          <p className="small" style={{ opacity: 0.6, marginBottom: "0.5rem" }}>No concepts extracted yet.</p>
          <button
            className="absent-refs-btn-small absent-refs-btn-primary"
            disabled={busy}
            onClick={() => setExtracting(true)}
          >Extract Concepts</button>
        </div>
      </div>
    );
  }

  const hasAny = CONCEPT_GROUPS.some((g) => concepts[g] && concepts[g].length > 0);
  if (!hasAny) {
    return (
      <div className="panel">
        <h3>Concepts</h3>
        <div className="small" style={{ opacity: 0.6 }}>No concepts found.</div>
      </div>
    );
  }

  return (
    <div className="panel concepts-panel">
      <h3>Concepts</h3>
      {CONCEPT_GROUPS.map((group) => {
        const items = concepts[group] || [];
        if (!items.length) return null;
        return (
          <div key={group} className="concepts-group">
            <div className="concepts-group-label">{group}</div>
            <div className="concepts-pills">
              {items.map((item) => (
                <button
                  key={item}
                  className={`concept-pill concept-pill--${group}`}
                  onClick={() => onConceptClick && onConceptClick(item)}
                  title={`Search papers with concept: ${item}`}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LibraryPanel({ activePaper, updateLibraryEntry, triggerAction, busy }) {
  const lib = activePaper.library || {};
  const [status, setStatus] = useState(lib.status || "");
  const [priority, setPriority] = useState(lib.priority || "");
  const [tags, setTags] = useState(lib.tags || []);
  const [saving, setSaving] = useState(false);
  const [autotagging, setAutotagging] = useState(false);

  useEffect(() => {
    const l = activePaper.library || {};
    setStatus(l.status || "");
    setPriority(l.priority || "");
    setTags(l.tags || []);
    setAutotagging(false);
  }, [activePaper.citekey]);

  async function save() {
    setSaving(true);
    await updateLibraryEntry(activePaper.citekey, { status: status || null, priority: priority || null, tags });
    setSaving(false);
  }

  function handleAutotagComplete(data) {
    setAutotagging(false);
    // Refresh library entry to get new tags
    fetch(`/api/library/${encodeURIComponent(activePaper.citekey)}`)
      .then((r) => r.json())
      .then((lib) => { setTags(lib.tags || []); })
      .catch(() => {});
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
        <TagInput tags={tags} onChange={setTags} placeholder="Add tags..." />
      </div>
      <div className="actions" style={{ marginTop: "0.6rem", display: "flex", gap: "0.4rem", alignItems: "center" }}>
        <button onClick={save} disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        {autotagging ? (
          <ActionProgress
            endpoint="/api/actions/autotag"
            body={{ citekey: activePaper.citekey }}
            onComplete={handleAutotagComplete}
            onError={() => setAutotagging(false)}
            label="Auto-tagging"
            autoTrigger
          />
        ) : (
          <button
            className="badge-action"
            disabled={busy}
            onClick={() => setAutotagging(true)}
            title="Auto-tag this paper using LLM"
          >
            Auto-tag
          </button>
        )}
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
  const saveTimer = useRef(null);
  const loadedFor = useRef(null);

  function fetchAll() {
    setLoading(true);
    Promise.all([
      fetch(`/api/papers/${encodeURIComponent(citekey)}/absent-refs`).then((r) => r.json()),
      fetch(`/api/papers/${encodeURIComponent(citekey)}/ref-resolutions`).then((r) => r.json()),
    ])
      .then(([absentData, cacheData]) => {
        setRefs(absentData.absent_refs || []);
        setResolved(cacheData.resolutions || {});
        setLoading(false);
      })
      .catch(() => { setRefs([]); setLoading(false); });
  }

  // Auto-load on mount / citekey change, also restore cached resolutions
  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setRefs(null);
    setResolved({});
    fetchAll();
  }, [citekey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist resolutions to backend (debounced 1s)
  useEffect(() => {
    if (!refs || Object.keys(resolved).length === 0) return;
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      fetch(`/api/papers/${encodeURIComponent(citekey)}/ref-resolutions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolutions: resolved }),
      }).catch(() => {});
    }, 1000);
    return () => clearTimeout(saveTimer.current);
  }, [resolved, citekey, refs]);

  function load() {
    loadedFor.current = null; // force reload
    setRefs(null);
    setResolved({});
    fetchAll();
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
    // Only resolve refs above/at threshold that are unresolved
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
  const pendingResolve = refs
    ? refs.filter((r, idx) => !r.doi && !resolved[idx] && !resolving[idx] && r.title).length
    : 0;
  const resolveInProgress = Object.values(resolving).filter(Boolean).length;
  const hasResolved = Object.keys(resolved).some((k) => resolved[k] && !resolved[k].error);

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
              title="Resolve DOIs via CrossRef for all unresolved refs"
            >
              {resolveInProgress > 0 ? `Resolving ${resolveInProgress}…` : `Resolve all (${pendingResolve})`}
            </button>
          )}
          {qualifiedDois.length > 0 && (
            <button className="absent-refs-btn-small" onClick={copyAll} title="Copy qualified DOIs to clipboard">
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
            {loading ? "Loading…" : "↺"}
          </button>
        </div>
      </div>

      {/* Threshold slider — always shown once refs are loaded */}
      {refs !== null && (
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
          {hasResolved && (
            <span style={{ fontSize: "0.72rem", opacity: 0.5, marginLeft: "0.3rem" }}>
              ({qualifiedDois.length} pass)
            </span>
          )}
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

function CitationTooltip({ paper, x, y, onOpen }) {
  if (!paper) return null;
  const left = Math.min(x + 12, window.innerWidth - 340);
  const top = Math.min(y + 16, window.innerHeight - 160);
  const oa = paper.openalex || {};
  const topics = oa.topics || [];
  const firstTopic = topics[0]?.display_name;
  const citedBy = oa.cited_by_count;
  const style = {
    position: "fixed",
    left,
    top,
    zIndex: 9999,
    maxWidth: 320,
    background: "var(--panel)",
    border: "1px solid var(--line)",
    borderRadius: 6,
    padding: "0.65rem 0.85rem",
    boxShadow: "0 4px 18px rgba(0,0,0,0.55)",
    pointerEvents: onOpen ? "auto" : "none",
    cursor: "default",
  };
  return (
    <div style={style}>
      <div style={{ fontWeight: 600, fontSize: "0.82rem", marginBottom: "0.2rem", lineHeight: 1.35 }}>
        {paper.title || paper.citekey}
      </div>
      <div style={{ fontSize: "0.76rem", opacity: 0.72, marginBottom: "0.2rem" }}>
        {(paper.authors || []).slice(0, 3).join(", ")}{(paper.authors || []).length > 3 ? " et al." : ""}
        {paper.year ? ` · ${paper.year}` : ""}
      </div>
      {(firstTopic || citedBy != null) && (
        <div style={{ fontSize: "0.72rem", opacity: 0.55, marginBottom: "0.25rem" }}>
          {firstTopic && <span>{firstTopic}</span>}
          {firstTopic && citedBy != null && <span> · </span>}
          {citedBy != null && <span>{citedBy.toLocaleString()} citations</span>}
        </div>
      )}
      {onOpen && (
        <button
          style={{
            fontSize: "0.72rem", marginTop: "0.3rem", padding: "0.15rem 0.5rem",
            background: "var(--accent-soft)", border: "1px solid var(--accent)",
            borderRadius: 4, color: "var(--accent)", cursor: "pointer",
          }}
          onClick={onOpen}
        >
          Open paper
        </button>
      )}
    </div>
  );
}

function StandardizedTab({ citekey, papers, openInPaperTab }) {
  const [text, setText] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isRawDocling, setIsRawDocling] = useState(false);
  const [tooltip, setTooltip] = useState(null); // { paper, x, y, key }
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
    setIsRawDocling(false);
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/ref-md`)
      .then((r) => {
        const raw = r.headers.get("X-Biblio-Ref-Md-Status") === "raw-docling";
        return r.text().then((t) => ({ t, raw }));
      })
      .then(({ t, raw }) => { setText(t); setIsRawDocling(raw); setLoading(false); })
      .catch(() => { setText(""); setIsRawDocling(false); setLoading(false); });
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
    if (tooltip?.key === key) return;
    const paper = paperMap[key] || null;
    setTooltip({ paper: paper || { citekey: key, title: key }, x: e.clientX, y: e.clientY, key });
  }

  function handleClick(e) {
    const a = e.target.closest(".cite-link");
    if (!a || !openInPaperTab) return;
    const key = a.dataset.key;
    if (paperMap[key]) openInPaperTab(key);
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
    <div
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setTooltip(null)}
      onClick={handleClick}
    >
      {isRawDocling && (
        <div className="small" style={{ padding: "0.4rem 1rem", opacity: 0.55, borderBottom: "1px solid #ddd" }}>
          Raw docling output — citations not yet resolved. Run: <code>biblio ref-md run --key {citekey}</code>
        </div>
      )}
      <div className="docling-box docling-box-full" dangerouslySetInnerHTML={{ __html: html }} />
      {tooltip && (
        <CitationTooltip
          paper={tooltip.paper}
          x={tooltip.x}
          y={tooltip.y}
          onOpen={tooltip.paper && paperMap[tooltip.key] && openInPaperTab
            ? () => { openInPaperTab(tooltip.key); setTooltip(null); }
            : null}
        />
      )}
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

const NOTES_VIEWS = ["split", "edit", "preview"];

function NotesTab({ citekey }) {
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState(""); // "" | "saving" | "saved" | "unsaved"
  const [view, setView] = useState("split");
  const loadedFor = useRef(null);
  const saveTimer = useRef(null);

  // Load notes on mount / citekey change
  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setLoading(true);
    setSaveStatus("");
    fetch(`/api/papers/${encodeURIComponent(citekey)}/notes`)
      .then((r) => r.text())
      .then((t) => { setContent(t); setSavedContent(t); setLoading(false); })
      .catch(() => { setContent(""); setSavedContent(""); setLoading(false); });
  }, [citekey]);

  // Reset cache when citekey changes
  useEffect(() => { loadedFor.current = null; }, [citekey]);

  // Auto-save with debounce
  const scheduleAutosave = useCallback((text) => {
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      doSave(text);
    }, 2000);
  }, [citekey]); // eslint-disable-line react-hooks/exhaustive-deps

  function doSave(text) {
    clearTimeout(saveTimer.current);
    setSaveStatus("saving");
    fetch(`/api/papers/${encodeURIComponent(citekey)}/notes`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text }),
    })
      .then((r) => { if (!r.ok) throw new Error("save failed"); return r.json(); })
      .then(() => { setSavedContent(text); setSaveStatus("saved"); })
      .catch(() => setSaveStatus("unsaved"));
  }

  function handleChange(ev) {
    const val = ev.target.value;
    setContent(val);
    setSaveStatus("unsaved");
    scheduleAutosave(val);
  }

  function handleBlur() {
    if (content !== savedContent) {
      clearTimeout(saveTimer.current);
      doSave(content);
    }
  }

  // Cleanup timer on unmount
  useEffect(() => () => clearTimeout(saveTimer.current), []);

  if (loading) {
    return <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>Loading notes…</div>;
  }

  const html = useMemo(() => renderMarkdown(content || ""), [content]);
  const showEditor = view === "split" || view === "edit";
  const showPreview = view === "split" || view === "preview";

  return (
    <div className="notes-tab">
      <div className="notes-toolbar">
        <div className="notes-view-toggle">
          {NOTES_VIEWS.map((v) => (
            <button
              key={v}
              className={`subtab-btn${view === v ? " active" : ""}`}
              onClick={() => setView(v)}
            >
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
        <span className="notes-save-status" style={{
          fontSize: "0.72rem",
          opacity: saveStatus ? 0.8 : 0.3,
          color: saveStatus === "saved" ? "var(--ok, #4caf7d)"
            : saveStatus === "unsaved" ? "var(--warn, #e0a84b)"
            : saveStatus === "saving" ? "var(--accent, #61afef)"
            : undefined,
        }}>
          {saveStatus === "saved" ? "Saved" : saveStatus === "unsaved" ? "Unsaved changes" : saveStatus === "saving" ? "Saving…" : ""}
        </span>
      </div>
      <div className={`notes-body${showEditor && showPreview ? " notes-body-split" : ""}`}>
        {showEditor && (
          <textarea
            className="notes-editor"
            value={content}
            onChange={handleChange}
            onBlur={handleBlur}
            placeholder="Start writing notes..."
            spellCheck
          />
        )}
        {showPreview && (
          <div
            className="notes-preview docling-box docling-box-full"
            dangerouslySetInnerHTML={{ __html: content.trim() ? html : '<p class="small" style="opacity:0.5">Preview will appear here…</p>' }}
          />
        )}
      </div>
    </div>
  );
}

const CONTENT_SUBTABS = ["PDF", "Markdown", "Summary", "Slides", "Figures", "Refs", "Notes"];

const SLIDE_TEMPLATES = [
  { value: "journal-club", label: "Journal Club", desc: "Background, methods, key results, discussion points, and open questions for group critique" },
  { value: "conference-talk", label: "Conference Talk", desc: "Motivation, contribution, methodology, results, and impact framed for a broad audience" },
  { value: "lab-meeting", label: "Lab Meeting", desc: "Quick overview, technical details, replication notes, and next steps for the research group" },
];

function SummaryTab({ citekey, hasSummary, triggerAction, busy }) {
  const [text, setText] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const loadedFor = useRef(null);

  function fetchSummary() {
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/summary`)
      .then((r) => {
        if (!r.ok) throw new Error("not found");
        return r.text();
      })
      .then((t) => { setText(t); setLoading(false); })
      .catch(() => { setText(null); setLoading(false); });
  }

  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setText(null);
    setGenerating(false);
    if (!hasSummary) { setLoading(false); return; }
    fetchSummary();
  }, [citekey, hasSummary]);

  useEffect(() => { loadedFor.current = null; }, [citekey]);

  function handleComplete() {
    setGenerating(false);
    loadedFor.current = null;
    fetchSummary();
  }

  if (loading) {
    return <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>Loading summary…</div>;
  }

  if (generating) {
    return (
      <div style={{ padding: "1.5rem", textAlign: "center" }}>
        <ActionProgress
          endpoint="/api/actions/summarize"
          body={{ citekey }}
          onComplete={handleComplete}
          onError={() => setGenerating(false)}
          label="Generating summary"
          autoTrigger
        />
      </div>
    );
  }

  if (text) {
    const html = renderMarkdown(text);
    return (
      <div>
        <div style={{ display: "flex", gap: "0.4rem", padding: "0.5rem 0.8rem", borderBottom: "1px solid var(--line, #ddd)" }}>
          <button
            className="absent-refs-btn-small"
            disabled={busy}
            onClick={() => { setGenerating(true); }}
          >
            Regenerate
          </button>
        </div>
        <div className="docling-box docling-box-full" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    );
  }

  return (
    <div style={{ padding: "1.5rem", textAlign: "center" }}>
      <p className="small" style={{ marginBottom: "0.8rem", opacity: 0.6 }}>No summary generated yet.</p>
      <button
        className="absent-refs-btn-small absent-refs-btn-primary"
        disabled={busy}
        onClick={() => setGenerating(true)}
      >
        Generate Summary
      </button>
    </div>
  );
}

function SlidesTab({ citekey, hasSlides, triggerAction, busy }) {
  const [text, setText] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [template, setTemplate] = useState("journal-club");
  const [generating, setGenerating] = useState(false);
  const loadedFor = useRef(null);

  function fetchSlides() {
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/slides`)
      .then((r) => {
        if (!r.ok) throw new Error("not found");
        return r.text();
      })
      .then((t) => { setText(t); setLoading(false); })
      .catch(() => { setText(null); setLoading(false); });
  }

  useEffect(() => {
    if (loadedFor.current === citekey) return;
    loadedFor.current = citekey;
    setText(null);
    setGenerating(false);
    if (!hasSlides) { setLoading(false); return; }
    fetchSlides();
  }, [citekey, hasSlides]);

  useEffect(() => { loadedFor.current = null; }, [citekey]);

  function handleComplete() {
    setGenerating(false);
    loadedFor.current = null;
    fetchSlides();
  }

  function copyToClipboard() {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  if (loading) {
    return <div className="small" style={{ padding: "1rem", opacity: 0.6 }}>Loading slides…</div>;
  }

  // Split Marp slides into cards at "---" separators
  function renderSlideCards(raw) {
    const slides = raw.split(/\n---\n/).map((s) => s.trim()).filter(Boolean);
    return slides.map((slide, idx) => (
      <div key={idx} className="slides-card">
        <div className="slides-card-number">{idx + 1}</div>
        <pre className="slides-card-content">{slide}</pre>
      </div>
    ));
  }

  if (generating) {
    return (
      <div style={{ padding: "1.5rem", textAlign: "center" }}>
        <ActionProgress
          endpoint="/api/actions/present"
          body={{ citekey, template }}
          onComplete={handleComplete}
          onError={() => setGenerating(false)}
          label={`Generating ${template} slides`}
          autoTrigger
        />
      </div>
    );
  }

  if (text) {
    return (
      <div>
        <div style={{ display: "flex", gap: "0.4rem", padding: "0.5rem 0.8rem", borderBottom: "1px solid var(--line, #ddd)", flexWrap: "wrap", alignItems: "center" }}>
          <button className="absent-refs-btn-small" onClick={copyToClipboard}>
            {copied ? "Copied!" : "Copy to Clipboard"}
          </button>
          <select value={template} onChange={(ev) => setTemplate(ev.target.value)} style={{ fontSize: "0.75rem" }}>
            {SLIDE_TEMPLATES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <button
            className="absent-refs-btn-small"
            disabled={busy}
            onClick={() => setGenerating(true)}
          >
            Regenerate
          </button>
        </div>
        <div className="slides-preview-grid">
          {renderSlideCards(text)}
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "1.5rem" }}>
      <p className="small" style={{ marginBottom: "0.8rem", opacity: 0.6, textAlign: "center" }}>No slides generated yet. Choose a template to get started.</p>
      <div className="slides-template-picker">
        {SLIDE_TEMPLATES.map((t) => (
          <div
            key={t.value}
            className={`slides-template-card${template === t.value ? " active" : ""}`}
            onClick={() => setTemplate(t.value)}
          >
            <div className="slides-template-card-label">{t.label}</div>
            <div className="slides-template-card-desc">{t.desc}</div>
          </div>
        ))}
      </div>
      <div style={{ textAlign: "center", marginTop: "0.8rem" }}>
        <button
          className="absent-refs-btn-small absent-refs-btn-primary"
          disabled={busy}
          onClick={() => setGenerating(true)}
        >
          Generate Slides
        </button>
      </div>
    </div>
  );
}

export default function PaperTab({
  activePaper, activeArtifacts,
  updateLibraryEntry, triggerAction, actionState, papers, openInPaperTab,
  onConceptClick,
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
  const hasSummary = !!activePaper.has_summary;
  const hasConcepts = !!activePaper.has_concepts;
  const hasSlides = !!activePaper.has_slides;
  const hasAutotag = !!activePaper.has_autotag;
  const hasNotes = !!activePaper.has_notes;

  return (
    <div className="paper-detail paper-detail-split">
      {/* Header */}
      <div className="panel paper-detail-header">
        <div className="paper-card-title">
          <h2>{activePaper.citekey}</h2>
          <span className="small">{activePaper.year || "n.d."}</span>
          {!activePaper.is_paper && (
            <span
              className="badge"
              style={{ background: "#6a5acd", color: "#fff", border: "1px solid #6a5acd", fontSize: "0.72rem", padding: "0.1rem 0.45rem", marginLeft: "0.4rem" }}
            >
              {activePaper.entry_type === "phdthesis" ? "PhD thesis"
                : activePaper.entry_type === "mastersthesis" ? "MSc thesis"
                : activePaper.entry_type || "misc"}
            </span>
          )}
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
          <ArtifactBadge
            exists={hasSummary}
            label="summary"
            busy={busy}
            onAction={!hasSummary ? () => triggerAction("summarize", { citekey: activePaper.citekey }) : null}
            actionLabel="Generate summary"
          />
          <ArtifactBadge
            exists={hasConcepts}
            label="concepts"
            busy={busy}
            onAction={!hasConcepts ? () => triggerAction("concepts-extract", { citekey: activePaper.citekey }) : null}
            actionLabel="Extract concepts"
          />
          <ArtifactBadge
            exists={hasSlides}
            label="slides"
            busy={busy}
            onAction={!hasSlides ? () => triggerAction("present", { citekey: activePaper.citekey }) : null}
            actionLabel="Generate slides"
          />
          <ArtifactBadge
            exists={hasAutotag}
            label="autotag"
            busy={busy}
            onAction={!hasAutotag ? () => triggerAction("autotag", { citekey: activePaper.citekey }) : null}
            actionLabel="Auto-tag this paper"
          />
          <ArtifactBadge
            exists={hasNotes}
            label="notes"
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

          {contentTab === "Markdown" && (
            <div className="panel paper-content-panel">
              {!hasDocling && actionState && actionState.action === "docling-run" && actionState.busy ? (
                <div style={{ padding: "1.5rem", textAlign: "center" }}>
                  <div className="action-progress-status">
                    <span className="action-spinner">&#x27F3;</span>
                    <span className="action-progress-label">{actionState.message || "Running Docling..."}</span>
                  </div>
                  {actionState.progressTotal > 0 && (
                    <div className="progress-bar" style={{ marginTop: "0.5rem", height: "4px", maxWidth: "300px", margin: "0.5rem auto 0" }}>
                      <div className="progress-fill" style={{ width: `${actionState.progressPercent || 0}%` }} />
                    </div>
                  )}
                  {actionState.logs && (
                    <pre style={{ marginTop: "0.5rem", fontSize: "0.72rem", opacity: 0.6, maxHeight: "8rem", overflowY: "auto", textAlign: "left", whiteSpace: "pre-wrap" }}>
                      {actionState.logs}
                    </pre>
                  )}
                </div>
              ) : (
                <StandardizedTab citekey={activePaper.citekey} papers={papers} openInPaperTab={openInPaperTab} />
              )}
            </div>
          )}

          {contentTab === "Summary" && (
            <div className="panel paper-content-panel">
              <SummaryTab citekey={activePaper.citekey} hasSummary={hasSummary} triggerAction={triggerAction} busy={busy} />
            </div>
          )}

          {contentTab === "Slides" && (
            <div className="panel paper-content-panel">
              <SlidesTab citekey={activePaper.citekey} hasSlides={hasSlides} triggerAction={triggerAction} busy={busy} />
            </div>
          )}

          {contentTab === "Figures" && (
            <div className="paper-content-panel figures-content-panel">
              <FiguresTab citekey={activePaper.citekey} />
            </div>
          )}

          {contentTab === "Refs" && (
            <div className="panel paper-content-panel">
              {!hasGrobid && actionState && actionState.action === "grobid-run" && actionState.busy ? (
                <div style={{ padding: "1.5rem", textAlign: "center" }}>
                  <div className="action-progress-status">
                    <span className="action-spinner">&#x27F3;</span>
                    <span className="action-progress-label">{actionState.message || "Running GROBID..."}</span>
                  </div>
                  {actionState.progressTotal > 0 && (
                    <div className="progress-bar" style={{ marginTop: "0.5rem", height: "4px", maxWidth: "300px", margin: "0.5rem auto 0" }}>
                      <div className="progress-fill" style={{ width: `${actionState.progressPercent || 0}%` }} />
                    </div>
                  )}
                </div>
              ) : activePaper.grobid && activePaper.grobid.header && Object.keys(activePaper.grobid.header).length > 0 ? (
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

          {contentTab === "Notes" && (
            <div className="panel paper-content-panel">
              <NotesTab citekey={activePaper.citekey} />
            </div>
          )}
        </div>

        {/* Right: sidebar info */}
        <div className="paper-sidebar-col">
          <LibraryPanel activePaper={activePaper} updateLibraryEntry={updateLibraryEntry} triggerAction={triggerAction} busy={busy} />

          <ConceptsPanel
            citekey={activePaper.citekey}
            hasConcepts={hasConcepts}
            triggerAction={triggerAction}
            busy={busy}
            onConceptClick={onConceptClick}
          />

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
            <div className="panel small" style={{ opacity: 0.65 }}>
              {activePaper.grobid?.reference_count ?? 0} refs extracted — see Refs tab to resolve absent references.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
