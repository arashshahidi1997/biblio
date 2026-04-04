import { useState } from "react";
import TagInput from "./TagInput.jsx";

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

async function exportBibtex(citekeys) {
  const res = await fetch("/api/export/bibtex", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ citekeys }),
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.text();
}

function BulkToolbar({ count, bulkSelection, bulkUpdateLibrary, setBulkSelection, loadModel }) {
  const [bulkAddTags, setBulkAddTags] = useState([]);
  const [bulkRemoveTags, setBulkRemoveTags] = useState([]);

  return (
    <div className="bulk-toolbar">
      <span className="bulk-toolbar-count">{count} selected</span>

      <select
        defaultValue=""
        onChange={(ev) => {
          if (ev.target.value) {
            bulkUpdateLibrary({ status: ev.target.value });
            ev.target.value = "";
          }
        }}
      >
        <option value="" disabled>Set status...</option>
        <option value="unread">Unread</option>
        <option value="reading">Reading</option>
        <option value="processed">Processed</option>
        <option value="archived">Archived</option>
      </select>

      <select
        defaultValue=""
        onChange={(ev) => {
          if (ev.target.value) {
            bulkUpdateLibrary({ priority: ev.target.value });
            ev.target.value = "";
          }
        }}
      >
        <option value="" disabled>Set priority...</option>
        <option value="low">Low</option>
        <option value="normal">Normal</option>
        <option value="high">High</option>
      </select>

      <div className="bulk-toolbar-tags">
        <TagInput
          tags={bulkAddTags}
          onChange={(tags) => setBulkAddTags(tags)}
          placeholder="Add tags..."
        />
        <button
          className="bulk-toolbar-btn"
          disabled={bulkAddTags.length === 0}
          onClick={() => {
            bulkUpdateLibrary({ add_tags: bulkAddTags });
            setBulkAddTags([]);
          }}
        >
          + Add
        </button>
      </div>

      <div className="bulk-toolbar-tags">
        <TagInput
          tags={bulkRemoveTags}
          onChange={(tags) => setBulkRemoveTags(tags)}
          placeholder="Remove tags..."
        />
        <button
          className="bulk-toolbar-btn bulk-toolbar-btn-danger"
          disabled={bulkRemoveTags.length === 0}
          onClick={() => {
            bulkUpdateLibrary({ remove_tags: bulkRemoveTags });
            setBulkRemoveTags([]);
          }}
        >
          - Remove
        </button>
      </div>

      <button
        className="bulk-toolbar-btn"
        onClick={async () => {
          try {
            const bib = await exportBibtex(bulkSelection);
            const blob = new Blob([bib], { type: "application/x-bibtex" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "export.bib";
            a.click();
            URL.revokeObjectURL(url);
          } catch (e) {
            console.error("BibTeX export failed", e);
          }
        }}
      >
        Export BibTeX
      </button>

      <button
        className="bulk-toolbar-btn"
        onClick={async () => {
          try {
            const bib = await exportBibtex(bulkSelection);
            await navigator.clipboard.writeText(bib);
          } catch (e) {
            console.error("BibTeX copy failed", e);
          }
        }}
      >
        Copy BibTeX
      </button>

      <button
        className="bulk-toolbar-btn"
        onClick={() => setBulkSelection([])}
      >
        Clear
      </button>
    </div>
  );
}

const ENTRY_TYPE_LABELS = {
  book: "book",
  proceedings: "proceedings",
  phdthesis: "PhD thesis",
  mastersthesis: "MSc thesis",
  techreport: "tech report",
  misc: "misc",
  manual: "manual",
  booklet: "booklet",
  online: "online",
};

export default function CorpusTab({
  papers, actionState, setActiveKey, setActiveTab, openInPaperTab,
  setLibraryMode, triggerAction,
  statusFilter, setStatusFilter, tagFilter, setTagFilter, allTags,
  updateLibraryEntry, compact, onRowContextMenu,
  bulkSelection, setBulkSelection, toggleBulkSelect, bulkUpdateLibrary, loadModel,
  papersOnly, setPapersOnly,
}) {
  const busy = actionState.busy;
  const allVisibleKeys = papers.map((p) => p.citekey);
  const allSelected = allVisibleKeys.length > 0 && allVisibleKeys.every((ck) => bulkSelection.includes(ck));

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
            <TagInput
              tags={tagFilter ? [tagFilter] : []}
              onChange={(tags) => setTagFilter(tags[0] || "")}
              placeholder="Filter by tag..."
              mode="filter"
            />
          </div>
          <div className="field" style={{ alignSelf: "flex-end" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer", fontSize: "0.8rem" }}>
              <input
                type="checkbox"
                checked={papersOnly}
                onChange={(ev) => setPapersOnly(ev.target.checked)}
              />
              Papers only
            </label>
          </div>
          <div className="field" style={{ alignSelf: "flex-end" }}>
            <span className="small">{papers.length} {papersOnly ? "papers" : "entries"}</span>
          </div>
        </div>
      )}

      {bulkSelection.length > 0 && !compact && (
        <BulkToolbar
          count={bulkSelection.length}
          bulkSelection={bulkSelection}
          bulkUpdateLibrary={bulkUpdateLibrary}
          setBulkSelection={setBulkSelection}
          loadModel={loadModel}
        />
      )}

      <table className={`paper-table${compact ? " paper-table-compact" : ""}`}>
        <thead>
          <tr>
            {!compact && (
              <th style={{ width: "2rem", textAlign: "center" }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() => {
                    if (allSelected) {
                      setBulkSelection((prev) => prev.filter((ck) => !allVisibleKeys.includes(ck)));
                    } else {
                      setBulkSelection((prev) => {
                        const set = new Set(prev);
                        allVisibleKeys.forEach((ck) => set.add(ck));
                        return [...set];
                      });
                    }
                  }}
                  title={allSelected ? "Deselect all" : "Select all visible"}
                />
              </th>
            )}
            <th>Citekey</th>
            <th>Title</th>
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
            const isSelected = bulkSelection.includes(paper.citekey);
            return (
              <tr
                key={paper.citekey}
                className={isSelected ? "bulk-selected" : ""}
                onClick={() => setActiveKey(paper.citekey)}
                onDoubleClick={() => openInPaperTab(paper.citekey)}
                onContextMenu={onRowContextMenu ? (e) => onRowContextMenu(e, paper.citekey) : undefined}
                title="Double-click to open in new tab"
              >
                {!compact && (
                  <td style={{ textAlign: "center" }} onClick={(ev) => ev.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={(ev) => toggleBulkSelect(paper.citekey, ev.nativeEvent)}
                    />
                  </td>
                )}
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
                    {!compact && paper.doi && (
                      <a
                        href={`https://doi.org/${paper.doi}`}
                        target="_blank"
                        rel="noreferrer"
                        className="open-btn"
                        title="View on publisher site"
                        onClick={(ev) => ev.stopPropagation()}
                        style={{ textDecoration: "none", fontSize: "0.65rem", opacity: 0.7 }}
                      >
                        DOI
                      </a>
                    )}
                    {!compact && (paper.graph || {}).seed_openalex_id && (
                      <a
                        href={`https://openalex.org/works/${paper.graph.seed_openalex_id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="open-btn"
                        title="View on OpenAlex"
                        onClick={(ev) => ev.stopPropagation()}
                        style={{ textDecoration: "none", fontSize: "0.65rem", opacity: 0.7 }}
                      >
                        OA
                      </a>
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
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <span>{paper.title}</span>
                    {!paper.is_paper && (
                      <span
                        className="badge"
                        style={{ background: "#6a5acd", color: "#fff", border: "1px solid #6a5acd", fontSize: "0.65rem", padding: "0.05rem 0.35rem", whiteSpace: "nowrap" }}
                        title={`Entry type: ${paper.entry_type}`}
                      >
                        {ENTRY_TYPE_LABELS[paper.entry_type] || paper.entry_type}
                      </span>
                    )}
                  </div>
                </td>
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
