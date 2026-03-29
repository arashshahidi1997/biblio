import { useState, useEffect, useCallback } from "react";

function coverageColor(pct) {
  if (pct >= 80) return "var(--accent, #98c379)";
  if (pct >= 20) return "var(--warning, #e5c07b)";
  return "var(--error, #e06c75)";
}

export default function StatsBar({ triggerAction, cancelAction, actionState }) {
  const [stats, setStats] = useState(null);
  const [dismissed, setDismissed] = useState(new Set());

  const loadStats = useCallback(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then(setStats)
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 10000);
    return () => clearInterval(interval);
  }, [loadStats]);

  // Reload stats when an action finishes
  useEffect(() => {
    if (!actionState.busy && actionState.message) loadStats();
  }, [actionState.busy, actionState.message, loadStats]);

  if (!stats) return null;

  const cov = stats.coverage || {};
  const total = stats.total || 0;
  const papersCount = stats.papers_count ?? total;
  const nonPapers = stats.non_papers ?? 0;

  const items = [
    { key: "papers", label: "papers", count: papersCount },
    ...(nonPapers > 0 ? [{ key: "other", label: "other entries", count: nonPapers }] : []),
    { key: "pdf", label: "pdf", count: cov.pdf?.count ?? 0, pct: cov.pdf?.pct ?? 0 },
    { key: "docling", label: "docling", count: cov.docling?.count ?? 0, pct: cov.docling?.pct ?? 0 },
    { key: "openalex", label: "openalex", count: cov.openalex?.count ?? 0, pct: cov.openalex?.pct ?? 0 },
    { key: "grobid", label: "grobid", count: cov.grobid?.count ?? 0, pct: cov.grobid?.pct ?? 0 },
    { key: "summary", label: "summary", count: cov.summary?.count ?? 0, pct: cov.summary?.pct ?? 0 },
  ];

  // Smart tips
  const tips = [];
  const pdfCount = cov.pdf?.count ?? 0;
  const doclingCount = cov.docling?.count ?? 0;
  const grobidCount = cov.grobid?.count ?? 0;
  const openalexCount = cov.openalex?.count ?? 0;
  const missingPdf = stats.missing_pdf ?? (total - pdfCount);

  if (pdfCount > 0 && doclingCount < pdfCount && !dismissed.has("docling")) {
    const n = pdfCount - doclingCount;
    tips.push({
      id: "docling",
      text: `${n} papers have PDFs but no text extraction`,
      action: () => triggerAction("docling-run", { all: true }),
      label: "Run Docling For All",
    });
  }
  if (missingPdf > 10 && !dismissed.has("pdf")) {
    tips.push({
      id: "pdf",
      text: `${missingPdf} papers missing PDFs`,
      action: () => triggerAction("fetch-pdfs-oa"),
      label: "Fetch OA PDFs",
    });
  }
  if (doclingCount > 0 && grobidCount < doclingCount && !dismissed.has("grobid")) {
    const n = pdfCount - grobidCount;
    tips.push({
      id: "grobid",
      text: `Run GROBID to extract references for ${n > 0 ? n : "remaining"} papers`,
      action: () => triggerAction("grobid-run", { all: true }),
      label: "Run GROBID For All",
    });
  }
  if (openalexCount < papersCount * 0.5 && !dismissed.has("openalex")) {
    tips.push({
      id: "openalex",
      text: "Resolve OpenAlex for metadata enrichment",
      action: () => triggerAction("openalex-resolve"),
      label: "Resolve OpenAlex",
    });
  }

  // Show at most 2 tips
  const visibleTips = tips.slice(0, 2);

  return (
    <div className="stats-bar">
      <div className="stats-bar-counts">
        {items.map((item, idx) => (
          <span key={item.key}>
            {idx > 0 && <span className="stats-sep"> · </span>}
            <span
              className="stats-bar-item"
              style={item.pct !== undefined ? { color: coverageColor(item.pct) } : undefined}
              title={item.pct !== undefined ? `${item.pct}% coverage` : undefined}
            >
              {item.count} {item.label}
            </span>
          </span>
        ))}
      </div>
      {visibleTips.length > 0 && (
        <div className="stats-bar-tips">
          {visibleTips.map((tip) => (
            <div key={tip.id} className="stats-bar-tip">
              <span className="stats-bar-tip-icon">&#x1F4A1;</span>
              <span className="stats-bar-tip-text">{tip.text}</span>
              <button
                className="stats-bar-tip-btn"
                disabled={actionState.busy}
                onClick={tip.action}
              >
                {tip.label}
              </button>
              <button
                className="stats-bar-tip-dismiss"
                onClick={() => setDismissed((s) => new Set([...s, tip.id]))}
                title="Dismiss"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
