import { useEffect, useState } from 'react';

const STATUS_COLORS = {
  unread: '#6b7280',
  reading: '#3b82f6',
  processed: '#10b981',
  archived: '#8b5cf6',
  unset: '#d1d5db',
};

const COVERAGE_LABELS = {
  pdf: 'PDF',
  docling: 'Docling',
  grobid: 'GROBID',
  summary: 'Summary',
  concepts: 'Concepts',
};

export default function StatsPanel({ onFilterStatus, onFilterTag, collapsed, onToggle }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/stats')
      .then((r) => r.json())
      .then(setStats)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  if (error) return <div className="stats-panel panel"><span className="small">Stats: {error}</span></div>;
  if (!stats) return null;

  const statusEntries = Object.entries(stats.by_status || {});
  const statusTotal = statusEntries.reduce((s, [, c]) => s + c, 0) || 1;

  // Year histogram
  const yearEntries = Object.entries(stats.by_year || {});
  const maxYearCount = Math.max(1, ...yearEntries.map(([, c]) => c));

  return (
    <div className={`stats-panel panel${collapsed ? ' stats-collapsed' : ''}`}>
      <div className="stats-header" onClick={onToggle}>
        <span className="stats-title">Library Stats</span>
        <span className="stats-total">{stats.total} papers</span>
        <span className="stats-toggle">{collapsed ? '+' : '\u2212'}</span>
      </div>

      {!collapsed && (
        <div className="stats-body">
          {/* Status donut */}
          <div className="stats-section">
            <div className="stats-section-title">Status</div>
            <div className="stats-donut-row">
              <svg className="stats-donut" viewBox="0 0 36 36">
                {(() => {
                  let offset = 0;
                  return statusEntries.map(([status, count]) => {
                    const pct = (count / statusTotal) * 100;
                    const seg = (
                      <circle
                        key={status}
                        className="stats-donut-seg"
                        cx="18" cy="18" r="15.915"
                        fill="none"
                        stroke={STATUS_COLORS[status] || '#9ca3af'}
                        strokeWidth="3.5"
                        strokeDasharray={`${pct} ${100 - pct}`}
                        strokeDashoffset={-offset}
                        onClick={() => onFilterStatus && onFilterStatus(status === 'unset' ? '' : status)}
                        style={{ cursor: 'pointer' }}
                      />
                    );
                    offset += pct;
                    return seg;
                  });
                })()}
                <text x="18" y="19.5" className="stats-donut-text">{stats.total}</text>
              </svg>
              <div className="stats-legend">
                {statusEntries.map(([status, count]) => (
                  <div
                    key={status}
                    className="stats-legend-item"
                    onClick={() => onFilterStatus && onFilterStatus(status === 'unset' ? '' : status)}
                  >
                    <span className="stats-legend-dot" style={{ background: STATUS_COLORS[status] || '#9ca3af' }} />
                    <span className="stats-legend-label">{status}</span>
                    <span className="stats-legend-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Year histogram */}
          {yearEntries.length > 0 && (
            <div className="stats-section">
              <div className="stats-section-title">Years</div>
              <div className="stats-year-hist">
                {yearEntries.map(([year, count]) => (
                  <div key={year} className="stats-year-bar-wrap" title={`${year}: ${count}`}>
                    <div
                      className="stats-year-bar"
                      style={{ height: `${Math.max(4, (count / maxYearCount) * 100)}%` }}
                    />
                    <span className="stats-year-label">{year}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Coverage bars */}
          <div className="stats-section">
            <div className="stats-section-title">Coverage</div>
            <div className="stats-coverage">
              {Object.entries(stats.coverage || {}).map(([key, val]) => (
                <div key={key} className="stats-coverage-row">
                  <span className="stats-coverage-label">{COVERAGE_LABELS[key] || key}</span>
                  <div className="stats-coverage-track">
                    <div className="stats-coverage-fill" style={{ width: `${val.pct}%` }} />
                  </div>
                  <span className="stats-coverage-pct">{val.pct}%</span>
                </div>
              ))}
            </div>
            <div className="stats-coverage-extra">
              {stats.missing_pdf > 0 && (
                <span className="stats-chip">{stats.missing_pdf} missing PDF</span>
              )}
              {stats.fetch_queue > 0 && (
                <span className="stats-chip">{stats.fetch_queue} in fetch queue</span>
              )}
            </div>
          </div>

          {/* Top tags */}
          {(stats.top_tags || []).length > 0 && (
            <div className="stats-section">
              <div className="stats-section-title">Top Tags</div>
              <div className="stats-tag-cloud">
                {stats.top_tags.map(({ tag, count }) => (
                  <span
                    key={tag}
                    className="stats-tag"
                    onClick={() => onFilterTag && onFilterTag(tag)}
                    title={`${tag}: ${count}`}
                  >
                    {tag} <span className="stats-tag-count">{count}</span>
                  </span>
                ))}
              </div>
              {Object.keys(stats.tag_namespaces || {}).length > 1 && (
                <div className="stats-ns-row">
                  {Object.entries(stats.tag_namespaces).map(([ns, count]) => (
                    <span key={ns} className="stats-ns-chip">{ns === '_unnamespaced' ? 'other' : `${ns}:`} {count}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
