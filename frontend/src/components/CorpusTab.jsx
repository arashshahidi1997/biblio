const STATUS_COLORS = {
  unread: "#888",
  reading: "#e6a817",
  processed: "#3c9e3c",
  archived: "#555",
};

export default function CorpusTab({
  papers, actionState, setActiveKey, setActiveTab, triggerAction,
  statusFilter, setStatusFilter, tagFilter, setTagFilter, allTags,
  updateLibraryEntry,
}) {
  return (
    <div className="panel table-wrap">
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
      <table className="paper-table">
        <thead>
          <tr>
            <th>Citekey</th>
            <th>Title</th>
            <th>Year</th>
            <th>Status</th>
            <th>Tags</th>
            <th>Artifacts</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => {
            const lib = paper.library || {};
            const status = lib.status || "";
            const tags = lib.tags || [];
            const color = STATUS_COLORS[status] || "#aaa";
            return (
              <tr
                key={paper.citekey}
                onClick={() => { setActiveKey(paper.citekey); setActiveTab("paper"); }}
              >
                <td>{paper.citekey}</td>
                <td>{paper.title}</td>
                <td>{paper.year || "n.d."}</td>
                <td>
                  {status ? (
                    <span className="badge ok" style={{ background: color, border: `1px solid ${color}` }}>
                      {status}
                    </span>
                  ) : (
                    <span className="badge">—</span>
                  )}
                </td>
                <td>
                  <div style={{ display: "flex", gap: "0.25rem", flexWrap: "wrap" }}>
                    {tags.map((t) => (
                      <span key={t} className="badge ok" style={{ background: "#4a6fa5", border: "1px solid #4a6fa5", fontSize: "0.7rem" }}>
                        {t}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <span className={`badge ${paper.artifacts.pdf.exists ? "ok" : ""}`}>
                    {paper.artifacts.pdf.exists ? "pdf" : "no pdf"}
                  </span>
                  <span className={`badge ${paper.artifacts.docling_md.exists ? "ok" : ""}`}>
                    {paper.artifacts.docling_md.exists ? "docling" : "no docling"}
                  </span>
                  <span className={`badge ${paper.artifacts.openalex.exists ? "ok" : ""}`}>
                    {paper.artifacts.openalex.exists ? "openalex" : "no openalex"}
                  </span>
                  <span className={`badge ${paper.artifacts.grobid && paper.artifacts.grobid.exists ? "ok" : ""}`}>
                    {paper.artifacts.grobid && paper.artifacts.grobid.exists ? "grobid" : "no grobid"}
                  </span>
                </td>
                <td>
                  <div className="table-actions">
                    <button
                      onClick={(ev) => { ev.stopPropagation(); setActiveKey(paper.citekey); setActiveTab("paper"); }}
                    >
                      Open
                    </button>
                    <button
                      onClick={(ev) => { ev.stopPropagation(); setActiveKey(paper.citekey); setActiveTab("explore"); }}
                    >
                      Explore
                    </button>
                    <button
                      disabled={actionState.busy}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        setActiveKey(paper.citekey);
                        setActiveTab("actions");
                        triggerAction("docling-run", { citekey: paper.citekey });
                      }}
                    >
                      Docling
                    </button>
                    <button
                      disabled={actionState.busy}
                      onClick={(ev) => {
                        ev.stopPropagation();
                        setActiveKey(paper.citekey);
                        setActiveTab("actions");
                        triggerAction("grobid-run", { citekey: paper.citekey });
                      }}
                    >
                      GROBID
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
