import { useState, useEffect } from "react";

const STATUSES = ["", "unread", "reading", "processed", "archived"];
const PRIORITIES = ["", "low", "normal", "high"];

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

function AbsentRefsPanel({ citekey, triggerAction }) {
  const [refs, setRefs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [addDoi, setAddDoi] = useState("");

  function load() {
    setLoading(true);
    fetch(`/api/papers/${encodeURIComponent(citekey)}/absent-refs`)
      .then((r) => r.json())
      .then((data) => { setRefs(data.absent_refs || []); setLoading(false); })
      .catch(() => { setRefs([]); setLoading(false); });
  }

  if (refs === null) {
    return (
      <div className="panel">
        <h3>Absent References</h3>
        <div className="actions">
          <button onClick={load} disabled={loading}>{loading ? "Loading..." : "Load absent refs"}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <h3>Absent References ({refs.length})</h3>
      <div className="small" style={{ marginBottom: "0.5rem" }}>
        GROBID references not matched to local corpus
      </div>
      {refs.length === 0 && <div className="small">All references matched locally.</div>}
      <ul className="list-clean">
        {refs.map((ref, idx) => (
          <li key={idx} style={{ marginBottom: "0.4rem" }}>
            <div>{ref.title || <em>No title</em>}</div>
            {ref.doi && (
              <div className="small">
                DOI: <code>{ref.doi}</code>{" "}
                <button
                  style={{ fontSize: "0.75rem", padding: "0.1rem 0.4rem" }}
                  onClick={() => triggerAction("add-paper", { doi: ref.doi })}
                >
                  Add
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <div className="actions" style={{ marginTop: "0.5rem", display: "flex", gap: "0.4rem" }}>
        <input
          value={addDoi}
          onChange={(ev) => setAddDoi(ev.target.value)}
          placeholder="Add by DOI..."
          style={{ flexGrow: 1 }}
        />
        <button
          disabled={!addDoi.trim()}
          onClick={() => { triggerAction("add-paper", { doi: addDoi.trim() }); setAddDoi(""); }}
        >
          Add
        </button>
      </div>
    </div>
  );
}

export default function PaperTab({
  activePaper, activeArtifacts, showPdf, setShowPdf, doclingHtml,
  updateLibraryEntry, triggerAction,
}) {
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
          <span className={`badge ${activeArtifacts && activeArtifacts.grobid && activeArtifacts.grobid.exists ? "ok" : ""}`}>
            {activeArtifacts && activeArtifacts.grobid && activeArtifacts.grobid.exists ? "grobid" : "no grobid"}
          </span>
        </div>
      </div>
      <LibraryPanel activePaper={activePaper} updateLibraryEntry={updateLibraryEntry} />
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
      {activePaper.grobid && activePaper.grobid.header && Object.keys(activePaper.grobid.header).length > 0 && (
        <div className="panel">
          <h3>GROBID</h3>
          <div className="kv">
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
            <div className="small" style={{ marginTop: "0.6rem" }}>{activePaper.grobid.header.abstract}</div>
          )}
        </div>
      )}
      {activePaper.artifacts && activePaper.artifacts.grobid && activePaper.artifacts.grobid.exists && (
        <AbsentRefsPanel citekey={activePaper.citekey} triggerAction={triggerAction} />
      )}
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
