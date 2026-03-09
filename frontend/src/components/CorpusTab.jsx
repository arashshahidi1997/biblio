export default function CorpusTab({ papers, actionState, setActiveKey, setActiveTab, triggerAction }) {
  return (
    <div className="panel table-wrap">
      <table className="paper-table">
        <thead>
          <tr>
            <th>Citekey</th>
            <th>Title</th>
            <th>Year</th>
            <th>Artifacts</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => (
            <tr
              key={paper.citekey}
              onClick={() => { setActiveKey(paper.citekey); setActiveTab("paper"); }}
            >
              <td>{paper.citekey}</td>
              <td>{paper.title}</td>
              <td>{paper.year || "n.d."}</td>
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
          ))}
        </tbody>
      </table>
    </div>
  );
}
