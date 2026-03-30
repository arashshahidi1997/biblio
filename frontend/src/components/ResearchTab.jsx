import { useState, useRef } from "react";
import { renderMarkdown } from "../utils/markdown.js";

// ── Citation Drafting Section ──────────────────────────────────────────────

function CiteDraftSection() {
  const [text, setText] = useState("");
  const [style, setStyle] = useState("latex");
  const [maxRefs, setMaxRefs] = useState(5);
  const [result, setResult] = useState(null); // {draft, loading, error}

  async function draftParagraph() {
    if (!text.trim()) return;
    if (!window.confirm("Draft a citation paragraph using a Claude session?")) return;
    setResult({ draft: null, loading: true, error: null });
    try {
      const resp = await fetch("/api/cite-draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text.trim(), style, max_refs: maxRefs }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      // Poll for result
      pollCiteDraft();
    } catch (err) {
      setResult({ draft: null, loading: false, error: String(err.message || err) });
    }
  }

  async function pollCiteDraft() {
    try {
      const resp = await fetch("/api/actions/cite-draft/status");
      const data = await resp.json();
      if (data.running) {
        setResult({ draft: null, loading: true, error: null, message: data.message });
        window.setTimeout(pollCiteDraft, 500);
      } else if (data.error) {
        setResult({ draft: null, loading: false, error: data.error });
      } else {
        setResult({ draft: data.draft || "", loading: false, error: null });
      }
    } catch (err) {
      setResult({ draft: null, loading: false, error: String(err.message || err) });
    }
  }

  function copyToClipboard(asMarkdown) {
    if (!result || !result.draft) return;
    const content = asMarkdown ? result.draft : result.draft;
    navigator.clipboard.writeText(content).catch(() => {});
  }

  // Highlight citation keys in the draft text
  function highlightCitations(draft) {
    if (!draft) return "";
    // Highlight \cite{...} and [@...]
    let html = renderMarkdown(draft);
    html = html.replace(/\\cite\{([^}]+)\}/g, '<span class="research-cite-highlight">\\cite{$1}</span>');
    html = html.replace(/\[@([^\]]+)\]/g, '<span class="research-cite-highlight">[@$1]</span>');
    return html;
  }

  return (
    <div className="research-section">
      <h3>Citation Drafting</h3>
      <div className="small" style={{ marginBottom: "0.6rem", opacity: 0.7 }}>
        Enter a claim, section heading, or topic sentence. The system will draft a paragraph
        with inline citations from your library.
      </div>
      <div className="research-input-group">
        <textarea
          value={text}
          onChange={(ev) => setText(ev.target.value)}
          placeholder="e.g. Hippocampal replay during sleep consolidates spatial memories..."
          rows={4}
          className="research-textarea"
        />
        <div className="research-controls-row">
          <div className="field">
            <label>Citation style</label>
            <select value={style} onChange={(ev) => setStyle(ev.target.value)}>
              <option value="latex">LaTeX (\cite{"{}"})</option>
              <option value="pandoc">Pandoc ([@])</option>
            </select>
          </div>
          <div className="field">
            <label>Max references: {maxRefs}</label>
            <input
              type="range"
              min={1}
              max={10}
              value={maxRefs}
              onChange={(ev) => setMaxRefs(Number(ev.target.value))}
            />
          </div>
          <div className="field" style={{ alignSelf: "flex-end" }}>
            <button
              className="primary"
              disabled={!text.trim() || (result && result.loading)}
              onClick={draftParagraph}
            >
              {result && result.loading ? "Drafting..." : "Draft Paragraph"}
            </button>
          </div>
        </div>
      </div>

      {result && result.loading && (
        <div className="small" style={{ padding: "0.6rem 0", opacity: 0.6 }}>
          <span className="action-spinner">&#x27F3;</span> {result.message || "Generating citation draft..."}
        </div>
      )}
      {result && result.error && (
        <div className="action-status error">{result.error}</div>
      )}
      {result && result.draft && (
        <div className="research-result">
          <div className="research-result-toolbar">
            <button className="absent-refs-btn-small" onClick={() => copyToClipboard(false)}>
              Copy to Clipboard
            </button>
            <button className="absent-refs-btn-small" onClick={() => copyToClipboard(true)}>
              Copy as Markdown
            </button>
          </div>
          <div
            className="docling-box docling-box-full research-draft-output"
            dangerouslySetInnerHTML={{ __html: highlightCitations(result.draft) }}
          />
        </div>
      )}
    </div>
  );
}

// ── Literature Review Section ──────────────────────────────────────────────

function LitReviewSection() {
  const [mode, setMode] = useState("query"); // "query" | "plan"
  // Query mode
  const [question, setQuestion] = useState("");
  // Plan mode
  const [seedCitekeys, setSeedCitekeys] = useState("");
  const [planQuestion, setPlanQuestion] = useState("");
  // Shared result
  const [result, setResult] = useState(null); // {content, loading, error, action}

  async function runReviewQuery() {
    if (!question.trim()) return;
    if (!window.confirm("Synthesize a literature review using a Claude session?")) return;
    setResult({ content: null, loading: true, error: null, action: "review-query" });
    try {
      const resp = await fetch("/api/actions/review-query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      pollReviewStatus();
    } catch (err) {
      setResult({ content: null, loading: false, error: String(err.message || err), action: "review-query" });
    }
  }

  async function runReviewPlan() {
    const keys = seedCitekeys.split(",").map((s) => s.trim()).filter(Boolean);
    if (keys.length === 0) return;
    if (!window.confirm("Generate a review plan using a Claude session?")) return;
    setResult({ content: null, loading: true, error: null, action: "review-plan" });
    try {
      const resp = await fetch("/api/actions/review-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seed_citekeys: keys,
          question: planQuestion.trim() || undefined,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      pollReviewStatus();
    } catch (err) {
      setResult({ content: null, loading: false, error: String(err.message || err), action: "review-plan" });
    }
  }

  async function pollReviewStatus() {
    try {
      const resp = await fetch("/api/actions/review/status");
      const data = await resp.json();
      if (data.running) {
        setResult((prev) => ({ ...prev, loading: true, message: data.message }));
        window.setTimeout(pollReviewStatus, 500);
      } else if (data.error) {
        setResult((prev) => ({ ...prev, loading: false, error: data.error }));
      } else {
        const res = data.result || {};
        // review-query returns {synthesis}, review-plan returns structured plan
        const content = res.synthesis || res.plan || JSON.stringify(res, null, 2);
        setResult((prev) => ({ ...prev, content, loading: false, error: null }));
      }
    } catch (err) {
      setResult((prev) => ({ ...prev, loading: false, error: String(err.message || err) }));
    }
  }

  function copyResult() {
    if (result && result.content) {
      navigator.clipboard.writeText(result.content).catch(() => {});
    }
  }

  return (
    <div className="research-section">
      <h3>Literature Review</h3>
      <div className="research-mode-tabs">
        <button
          className={`research-mode-tab${mode === "query" ? " active" : ""}`}
          onClick={() => setMode("query")}
        >
          Query Mode
        </button>
        <button
          className={`research-mode-tab${mode === "plan" ? " active" : ""}`}
          onClick={() => setMode("plan")}
        >
          Plan Mode
        </button>
      </div>

      {mode === "query" && (
        <div className="research-input-group">
          <div className="small" style={{ marginBottom: "0.4rem", opacity: 0.7 }}>
            Enter a research question to synthesize a literature review from your library.
          </div>
          <textarea
            value={question}
            onChange={(ev) => setQuestion(ev.target.value)}
            placeholder="e.g. What are the neural mechanisms of memory consolidation during sleep?"
            rows={3}
            className="research-textarea"
          />
          <div className="research-controls-row">
            <div className="field" style={{ alignSelf: "flex-end" }}>
              <button
                className="primary"
                disabled={!question.trim() || (result && result.loading)}
                onClick={runReviewQuery}
              >
                {result && result.loading && result.action === "review-query" ? "Synthesizing..." : "Synthesize"}
              </button>
            </div>
          </div>
        </div>
      )}

      {mode === "plan" && (
        <div className="research-input-group">
          <div className="small" style={{ marginBottom: "0.4rem", opacity: 0.7 }}>
            Provide seed papers (comma-separated citekeys) to generate a structured review plan
            with scope, themes, gaps, and expansion directions.
          </div>
          <div className="field" style={{ marginBottom: "0.5rem" }}>
            <label>Seed citekeys</label>
            <input
              value={seedCitekeys}
              onChange={(ev) => setSeedCitekeys(ev.target.value)}
              placeholder="e.g. smith2020, jones2021, lee2022"
              style={{ width: "100%" }}
            />
          </div>
          <div className="field" style={{ marginBottom: "0.5rem" }}>
            <label>Research question (optional)</label>
            <input
              value={planQuestion}
              onChange={(ev) => setPlanQuestion(ev.target.value)}
              placeholder="e.g. How do these papers relate to memory consolidation?"
              style={{ width: "100%" }}
            />
          </div>
          <div className="research-controls-row">
            <div className="field" style={{ alignSelf: "flex-end" }}>
              <button
                className="primary"
                disabled={!seedCitekeys.trim() || (result && result.loading)}
                onClick={runReviewPlan}
              >
                {result && result.loading && result.action === "review-plan" ? "Planning..." : "Plan Review"}
              </button>
            </div>
          </div>
        </div>
      )}

      {result && result.loading && (
        <div className="small" style={{ padding: "0.6rem 0", opacity: 0.6 }}>
          <span className="action-spinner">&#x27F3;</span> {result.message || "Processing..."}
        </div>
      )}
      {result && result.error && (
        <div className="action-status error">{result.error}</div>
      )}
      {result && result.content && (
        <div className="research-result">
          <div className="research-result-toolbar">
            <button className="absent-refs-btn-small" onClick={copyResult}>
              Copy to Clipboard
            </button>
          </div>
          <div
            className="docling-box docling-box-full"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(result.content) }}
          />
        </div>
      )}
    </div>
  );
}

// ── Reading List Section ───────────────────────────────────────────────────

function ReadingListSection({ openInPaperTab }) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);

  async function generate() {
    if (!question.trim()) return;
    if (!window.confirm("Generate a reading list using a Claude session?")) return;
    setResult({ recommendations: null, loading: true, error: null });
    try {
      const resp = await fetch("/api/reading-list", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      pollResult();
    } catch (err) {
      setResult({ recommendations: null, loading: false, error: String(err.message || err) });
    }
  }

  async function pollResult() {
    try {
      const resp = await fetch("/api/actions/reading-list/status");
      const data = await resp.json();
      if (data.running) {
        setResult({ recommendations: null, loading: true, error: null, message: data.message });
        window.setTimeout(pollResult, 500);
      } else if (data.error) {
        setResult({ recommendations: null, loading: false, error: data.error });
      } else {
        setResult({ recommendations: data.recommendations || [], loading: false, error: null });
      }
    } catch (err) {
      setResult({ recommendations: null, loading: false, error: String(err.message || err) });
    }
  }

  return (
    <div className="research-section">
      <h3>Reading List</h3>
      <div className="small" style={{ marginBottom: "0.6rem", opacity: 0.7 }}>
        Generate a prioritized reading list from your library based on a research question.
      </div>
      <div className="research-input-group">
        <div className="research-controls-row" style={{ gap: "0.5rem" }}>
          <input
            value={question}
            onChange={(ev) => setQuestion(ev.target.value)}
            placeholder="Enter your research question..."
            style={{ flex: 1 }}
            onKeyDown={(ev) => { if (ev.key === "Enter") generate(); }}
          />
          <button
            className="primary"
            disabled={!question.trim() || (result && result.loading)}
            onClick={generate}
          >
            {result && result.loading ? "Generating..." : "Generate"}
          </button>
        </div>
      </div>

      {result && result.loading && (
        <div className="small" style={{ padding: "0.6rem 0", opacity: 0.6 }}>
          <span className="action-spinner">&#x27F3;</span> {result.message || "Generating reading list..."}
        </div>
      )}
      {result && result.error && (
        <div className="action-status error">{result.error}</div>
      )}
      {result && result.recommendations && (
        <div className="reading-list-results">
          {result.recommendations.length === 0 ? (
            <div className="small" style={{ opacity: 0.6 }}>No recommendations generated.</div>
          ) : (
            result.recommendations.map((rec, idx) => (
              <div
                key={rec.citekey || idx}
                className="reading-list-item"
                onClick={() => openInPaperTab && openInPaperTab(rec.citekey)}
                style={{ cursor: openInPaperTab ? "pointer" : "default" }}
              >
                <div className="reading-list-item-header">
                  <strong>{rec.citekey}</strong>
                  <span className="reading-list-score-bar">
                    <span className="reading-list-score-fill" style={{ width: `${Math.round((rec.score || 0) * 100)}%` }} />
                    <span className="reading-list-score-label">{Math.round((rec.score || 0) * 100)}%</span>
                  </span>
                </div>
                <div className="small" style={{ opacity: 0.75, marginTop: "0.2rem" }}>{rec.justification}</div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Main ResearchTab ───────────────────────────────────────────────────────

export default function ResearchTab({ openInPaperTab }) {
  const [subtab, setSubtab] = useState("cite-draft");

  return (
    <div className="col col-research">
      <div className="panel" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <div className="research-tab-header">
          <h2 style={{ margin: 0 }}>Research</h2>
          <div className="research-subtab-bar">
            <button
              className={`research-subtab${subtab === "cite-draft" ? " active" : ""}`}
              onClick={() => setSubtab("cite-draft")}
            >
              Cite Draft
            </button>
            <button
              className={`research-subtab${subtab === "lit-review" ? " active" : ""}`}
              onClick={() => setSubtab("lit-review")}
            >
              Literature Review
            </button>
            <button
              className={`research-subtab${subtab === "reading-list" ? " active" : ""}`}
              onClick={() => setSubtab("reading-list")}
            >
              Reading List
            </button>
          </div>
        </div>
        <div className="research-body">
          {subtab === "cite-draft" && <CiteDraftSection />}
          {subtab === "lit-review" && <LitReviewSection />}
          {subtab === "reading-list" && <ReadingListSection openInPaperTab={openInPaperTab} />}
        </div>
      </div>
    </div>
  );
}
