const STATUS_COLORS = {
  unread: "#888",
  reading: "#e6a817",
  processed: "#3c9e3c",
  archived: "#555",
};

function ArtifactBadge({ exists, label, onAction, busy, actionLabel }) {
  if (exists) {
    return <span className="badge ok">{label}</span>;
  }
  if (onAction) {
    return (
      <button
        className="badge badge-action"
        disabled={busy}
        onClick={(ev) => { ev.stopPropagation(); onAction(); }}
        title={actionLabel || `Run ${label}`}
      >
        {`no ${label}`} ↻
      </button>
    );
  }
  return <span className="badge">{`no ${label}`}</span>;
}

export default function CorpusTab({
  papers, actionState, setActiveKey, setActiveTab, openInPaperTab,
  setLibraryMode, triggerAction,
  statusFilter, setStatusFilter, tagFilter, setTagFilter, allTags,
  updateLibraryEntry, compact,
}) {
  const busy = actionState.busy;
  return (
    <div className="panel table-wrap">
      {!compact && (
        <div className="controls" style={{ marginBottom: "0.6rem" }}>
          <div className="field">
            <label>Status filter</label>
            <select value={statusFilter} onChange={(ev) => setStatusFilter(ev.target.value)}>
              <option value="">All statuses</option>
              <option value="unread">Unread</option>
              <option value="reading">Reading</option>
              <option value="processed">Processed</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div className="field">
            <label>Tag filter</label>
            <select value={tagFilter} onChange={(ev) => setTagFilter(ev.target.value)}>
              <option value="">All tags</option>
              {allTags.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="field" style={{ alignSelf: "flex-end" }}>
            <span className="small">{papers.length} papers</span>
          </div>
        </div>
      )}
      <table className={`paper-table${compact ? " paper-table-compact" : ""}`}>
        <thead>
          <tr>
            <th>Citekey</th>
            {!compact && <th>Title</th>}
            {compact && <th>Title</th>}
            {!compact && <th>Year</th>}
            {!compact && <th>Status</th>}
            {!compact && <th>Tags</th>}
            {!compact && <th>Artifacts</th>}
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => {
            const lib = paper.library || {};
            const status = lib.status || "";
            const tags = lib.tags || [];
            const color = STATUS_COLORS[status] || "#aaa";
            const a = paper.artifacts;
            return (
              <tr
                key={paper.citekey}
                onClick={() => setActiveKey(paper.citekey)}
                onDoubleClick={() => openInPaperTab(paper.citekey)}
                title="Double-click to open in new tab"
              >
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    {!compact && <span>{paper.citekey}</span>}
                    {!compact && (
                      <button
                        className="open-btn"
                        onClick={(ev) => { ev.stopPropagation(); openInPaperTab(paper.citekey); }}
                        title="Open paper"
                      >
                        ↗
                      </button>
                    )}
                    {!compact && (
                      <button
                        className="open-btn"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          setActiveKey(paper.citekey);
                          setLibraryMode("split");
                          setActiveTab("library");
                        }}
                        title="Show in network"
                      >
                        ◎
                      </button>
                    )}
                    {compact && (
                      <span
                        className="small"
                        style={{ fontFamily: "monospace", fontSize: "0.72rem", opacity: 0.6, whiteSpace: "nowrap" }}
                      >
                        {paper.citekey}
                      </span>
                    )}
                  </div>
                </td>
                <td>{paper.title}</td>
                {!compact && <td>{paper.year || "n.d."}</td>}
                {!compact && (
                  <td>
                    {status ? (
                      <span className="badge ok" style={{ background: color, border: `1px solid ${color}` }}>
                        {status}
                      </span>
                    ) : (
                      <span className="badge">—</span>
                    )}
                  </td>
                )}
                {!compact && (
                  <td>
                    <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                      {tags.map((t) => (
                        <span key={t} className="badge ok" style={{ background: "#4a6fa5", border: "1px solid #4a6fa5", fontSize: "0.7rem" }}>
                          {t}
                        </span>
                      ))}
                    </div>
                  </td>
                )}
                {!compact && (
                  <td>
                    <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                      <ArtifactBadge
                        exists={a.pdf.exists}
                        label="pdf"
                        busy={busy}
                        onAction={!a.pdf.exists ? () => triggerAction("fetch-pdfs-oa", {}) : null}
                        actionLabel="Fetch PDF from OpenAlex OA"
                      />
                      <ArtifactBadge
                        exists={a.docling_md.exists}
                        label="docling"
                        busy={busy}
                        onAction={!a.docling_md.exists ? () => { setActiveKey(paper.citekey); triggerAction("docling-run", { citekey: paper.citekey }); } : null}
                        actionLabel="Run Docling on this paper"
                      />
                      <ArtifactBadge
                        exists={a.openalex.exists}
                        label="openalex"
                        busy={busy}
                        onAction={!a.openalex.exists ? () => triggerAction("openalex-resolve", {}) : null}
                        actionLabel="Resolve OpenAlex metadata"
                      />
                      <ArtifactBadge
                        exists={a.grobid && a.grobid.exists}
                        label="grobid"
                        busy={busy}
                        onAction={!(a.grobid && a.grobid.exists) ? () => { setActiveKey(paper.citekey); triggerAction("grobid-run", { citekey: paper.citekey }); } : null}
                        actionLabel="Run GROBID on this paper"
                      />
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
