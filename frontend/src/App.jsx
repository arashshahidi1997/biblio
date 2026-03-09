import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { renderMarkdown } from './utils/markdown';
import ExploreTab from './components/ExploreTab';
import CorpusTab from './components/CorpusTab';
import PaperTab from './components/PaperTab';
import ActionsTab from './components/ActionsTab';
import SetupTab from './components/SetupTab';

export default function App() {
  const [payload, setPayload] = useState(null);
  const [query, setQuery] = useState("");
  const [activeKey, setActiveKey] = useState("");
  const [localOnly, setLocalOnly] = useState(false);
  const [graphMode, setGraphMode] = useState("focused");
  const [graphDirection, setGraphDirection] = useState("both");
  const [activeTab, setActiveTab] = useState("explore");
  const [actionState, setActionState] = useState({ busy: false, message: "", error: false });
  const [setup, setSetup] = useState(null);
  const [setupError, setSetupError] = useState(null);
  const [setupCommand, setSetupCommand] = useState("");
  const [setupCondaEnv, setSetupCondaEnv] = useState("docling");
  const [showPdf, setShowPdf] = useState(false);
  const [ragConfig, setRagConfig] = useState({
    embedding_model: "",
    chunk_size_chars: "1000",
    chunk_overlap_chars: "200",
    default_store: "local",
    local_persist_directory: ".cache/rag/chroma_db",
  });
  const [activeExternalNode, setActiveExternalNode] = useState(null);
  const [addDoi, setAddDoi] = useState("");

  const loadModel = useCallback(() => {
    fetch("/api/model").then((resp) => resp.json()).then((data) => {
      setPayload(data);
      if (data.papers && data.papers.length) {
        setActiveKey((prev) => prev && data.papers.some((paper) => paper.citekey === prev) ? prev : data.papers[0].citekey);
      }
    });
  }, []);

  useEffect(() => {
    loadModel();
  }, [loadModel]);

  const loadSetup = useCallback(() => {
    setSetupError(null);
    fetch("/api/setup")
      .then((resp) => {
        if (!resp.ok) return resp.json().then((e) => { throw new Error(e.detail || `HTTP ${resp.status}`); });
        return resp.json();
      })
      .then((data) => {
        setSetup(data);
        setSetupCommand(data.docling_command_text || "");
        const cmd = data.docling && Array.isArray(data.docling.command) ? data.docling.command : [];
        const envIdx = cmd.findIndex((item) => item === "-n");
        setSetupCondaEnv(envIdx >= 0 && cmd[envIdx + 1] ? cmd[envIdx + 1] : "docling");
        setRagConfig({
          embedding_model: data.rag && data.rag.embedding_model ? data.rag.embedding_model : "",
          chunk_size_chars: String(data.rag && data.rag.chunk_size_chars ? data.rag.chunk_size_chars : 1000),
          chunk_overlap_chars: String(data.rag && data.rag.chunk_overlap_chars ? data.rag.chunk_overlap_chars : 200),
          default_store: data.rag && data.rag.default_store ? data.rag.default_store : "local",
          local_persist_directory: data.rag && data.rag.local_persist_directory ? data.rag.local_persist_directory : ".cache/rag/chroma_db",
        });
      })
      .catch((err) => setSetupError(String(err.message || err)));
  }, []);

  useEffect(() => {
    loadSetup();
  }, [loadSetup]);

  const papers = useMemo(() => {
    if (!payload) return [];
    const q = query.trim().toLowerCase();
    return (payload.papers || []).filter((paper) => {
      if (!q) return true;
      return `${paper.citekey} ${paper.title}`.toLowerCase().includes(q);
    });
  }, [payload, query]);

  const activePaper = useMemo(() => {
    if (!payload) return null;
    return (payload.papers || []).find((paper) => paper.citekey === activeKey) || papers[0] || null;
  }, [payload, papers, activeKey]);

  const doclingHtml = useMemo(
    () => renderMarkdown((activePaper && activePaper.docling && activePaper.docling.excerpt) || ""),
    [activePaper]
  );

  useEffect(() => {
    setShowPdf(false);
  }, [activeKey]);

  async function pollOpenAlexProgress() {
    try {
      const resp = await fetch("/api/actions/openalex-resolve/status");
      const data = await resp.json();
      const total = Number(data.total || 0);
      const completed = Number(data.completed || 0);
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
      setActionState({
        busy: !!data.running,
        message: data.message || "Resolving OpenAlex metadata...",
        error: !!data.error,
        progressCompleted: completed,
        progressTotal: total,
        progressPercent: pct,
        action: "openalex-resolve",
      });
      if (data.running) {
        window.setTimeout(pollOpenAlexProgress, 400);
      } else if (!data.error) {
        loadModel();
      }
    } catch (err) {
      setActionState({
        busy: false,
        message: String(err.message || err),
        error: true,
        progressCompleted: 0,
        progressTotal: 0,
        progressPercent: 0,
        action: "openalex-resolve",
      });
    }
  }

  async function pollJobStatus(action) {
    const endpoint = `/api/actions/${action}/status`;
    try {
      const resp = await fetch(endpoint);
      const data = await resp.json();
      const total = Number(data.total || 0);
      const completed = Number(data.completed || 0);
      const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
      setActionState({
        busy: !!data.running,
        message: data.message || `${action} running...`,
        error: !!data.error,
        progressCompleted: completed,
        progressTotal: total,
        progressPercent: pct,
        action,
      });
      if (data.running) {
        window.setTimeout(() => pollJobStatus(action), 400);
      } else if (!data.error) {
        loadModel();
        if (loadSetup) loadSetup();
      }
    } catch (err) {
      setActionState({
        busy: false,
        message: String(err.message || err),
        error: true,
        progressCompleted: 0,
        progressTotal: 0,
        progressPercent: 0,
        action,
      });
    }
  }

  async function triggerAction(action, body) {
    setActionState({ busy: true, message: `Running ${action}...`, error: false });
    try {
      const resp = await fetch(`/api/actions/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `Request failed: ${resp.status}`);
      }
      if (data.async && action === "openalex-resolve") {
        const total = Number(data.total || 0);
        const completed = Number(data.completed || 0);
        setActionState({
          busy: true,
          message: data.message || "Resolving OpenAlex metadata...",
          error: false,
          progressCompleted: completed,
          progressTotal: total,
          progressPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
          action,
        });
        window.setTimeout(pollOpenAlexProgress, 150);
        return;
      }
      if (data.async && (action === "graph-expand" || action === "docling-run")) {
        const total = Number(data.total || 0);
        const completed = Number(data.completed || 0);
        setActionState({
          busy: true,
          message: data.message || `${action} running...`,
          error: false,
          progressCompleted: completed,
          progressTotal: total,
          progressPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
          action,
        });
        window.setTimeout(() => pollJobStatus(action), 150);
        return;
      }
      setActionState({
        busy: false,
        message: data.message || `${action} finished`,
        error: false,
        progressCompleted: 0,
        progressTotal: 0,
        progressPercent: 0,
        action,
      });
      loadModel();
    } catch (err) {
      setActionState({
        busy: false,
        message: String(err.message || err),
        error: true,
        progressCompleted: 0,
        progressTotal: 0,
        progressPercent: 0,
        action,
      });
    }
  }

  async function triggerSetupAction(endpoint, body) {
    setActionState({ busy: true, message: `Running ${endpoint}...`, error: false });
    try {
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `Request failed: ${resp.status}`);
      }
      if (endpoint === "/api/setup/docling-check") {
        setSetup((prev) => prev ? { ...prev, docling: data } : prev);
        setActionState({ busy: false, message: data.message || "Docling checked", error: !data.ok });
        return;
      }
      setActionState({ busy: false, message: data.message || "Setup updated", error: false });
      loadSetup();
      loadModel();
    } catch (err) {
      setActionState({ busy: false, message: String(err.message || err), error: true });
    }
  }

  if (!payload) {
    return (
      <div className="app">
        <div className="header">Loading bibliography UI...</div>
      </div>
    );
  }

  const activeArtifacts = activePaper ? activePaper.artifacts : null;
  const docsUrl = "https://arashshahidi1997.github.io/biblio/";
  const githubUrl = "https://github.com/arashshahidi1997/biblio";
  const tabs = [
    ["explore", "Explore"],
    ["corpus", "Corpus"],
    ["paper", "Paper"],
    ["actions", "Actions"],
    ["setup", "Setup"],
  ];

  return (
    <div className="app">
      <div className="header">
        <div className="header-bar">
          <div>
            <div className="small">Local FastAPI bibliography explorer</div>
            <h1>biblio ui</h1>
            <div className="legend small">
              <span className="legend-seed">active seed</span>
              <span className="legend-local">local paper</span>
              <span className="legend-external">external neighbor</span>
            </div>
          </div>
          <div className="header-links">
            <a href={docsUrl} target="_blank" rel="noreferrer">Docs</a>
            <a href={githubUrl} target="_blank" rel="noreferrer">GitHub</a>
          </div>
        </div>
      </div>
      <div className="small" style={{ marginBottom: "0.9rem" }}>
        {activePaper ? `Focused paper: ${activePaper.citekey}` : "No active paper"}
      </div>
      <div className="tabs">
        {tabs.map(([value, label]) => (
          <button
            key={value}
            className={`tab ${activeTab === value ? "active" : ""}`}
            onClick={() => setActiveTab(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="controls">
        <div className="field">
          <label>Search papers</label>
          <>
            <input
              list="paper-search-options"
              value={query}
              onChange={(ev) => {
                const value = ev.target.value;
                setQuery(value);
                const exact = (payload.papers || []).find((paper) => paper.citekey === value);
                if (exact) {
                  setActiveKey(exact.citekey);
                }
              }}
              placeholder="citekey or title"
            />
            <datalist id="paper-search-options">
              {papers.slice(0, 50).map((paper) => (
                <option key={paper.citekey} value={paper.citekey} label={`${paper.citekey} — ${paper.title}`} />
              ))}
            </datalist>
          </>
        </div>
        <div className="field">
          <label>Focus paper</label>
          <select value={activePaper ? activePaper.citekey : ""} onChange={(ev) => setActiveKey(ev.target.value)}>
            {papers.map((paper) => (
              <option key={paper.citekey} value={paper.citekey}>{`${paper.citekey} — ${paper.title}`}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Graph filter</label>
          <select value={localOnly ? "local" : "all"} onChange={(ev) => setLocalOnly(ev.target.value === "local")}>
            <option value="all">Local + external</option>
            <option value="local">Local only</option>
          </select>
        </div>
        <div className="field">
          <label>Explore mode</label>
          <select value={graphMode} onChange={(ev) => setGraphMode(ev.target.value)}>
            <option value="focused">Focused neighborhood</option>
            <option value="all">All papers in graph</option>
          </select>
        </div>
        <div className="field">
          <label>Direction</label>
          <select value={graphDirection} onChange={(ev) => setGraphDirection(ev.target.value)}>
            <option value="both">Past + future</option>
            <option value="past">Past works</option>
            <option value="future">Future works</option>
          </select>
        </div>
      </div>
      {activeTab === "explore" && (
        <ExploreTab
          payload={payload}
          activePaper={activePaper}
          activeExternalNode={activeExternalNode}
          localOnly={localOnly}
          graphMode={graphMode}
          graphDirection={graphDirection}
          actionState={actionState}
          triggerAction={triggerAction}
          setActiveKey={setActiveKey}
          setActiveExternalNode={setActiveExternalNode}
          activeTab={activeTab}
        />
      )}
      {activeTab === "corpus" && (
        <CorpusTab
          papers={papers}
          activePaper={activePaper}
          actionState={actionState}
          setActiveKey={setActiveKey}
          setActiveTab={setActiveTab}
          triggerAction={triggerAction}
        />
      )}
      {activeTab === "paper" && activePaper && (
        <PaperTab
          activePaper={activePaper}
          activeArtifacts={activeArtifacts}
          showPdf={showPdf}
          setShowPdf={setShowPdf}
          doclingHtml={doclingHtml}
        />
      )}
      {activeTab === "actions" && (
        <ActionsTab
          activePaper={activePaper}
          actionState={actionState}
          triggerAction={triggerAction}
          addDoi={addDoi}
          setAddDoi={setAddDoi}
        />
      )}
      {activeTab === "setup" && (
        <SetupTab
          setup={setup}
          setupError={setupError}
          modelStatus={payload ? payload.status : null}
          setupCommand={setupCommand}
          setSetupCommand={setSetupCommand}
          setupCondaEnv={setupCondaEnv}
          setSetupCondaEnv={setSetupCondaEnv}
          ragConfig={ragConfig}
          setRagConfig={setRagConfig}
          actionState={actionState}
          triggerSetupAction={triggerSetupAction}
        />
      )}
    </div>
  );
}
