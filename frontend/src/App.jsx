import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import ExploreTab from './components/ExploreTab';
import CorpusTab from './components/CorpusTab';
import PaperTab from './components/PaperTab';
import SetupTab from './components/SetupTab';
import SearchTab from './components/SearchTab';
import GraphInspector from './components/GraphInspector';
import CollectionTree from './components/CollectionTree';
import ResearchTab from './components/ResearchTab';
import { renderMarkdown } from './utils/markdown.js';

export default function App() {
  const urlCitekey = new URLSearchParams(window.location.search).get("paper") || "";
  const [payload, setPayload] = useState(null);
  const [query, setQuery] = useState("");
  const [activeKey, setActiveKey] = useState(urlCitekey);
  const [localOnly, setLocalOnly] = useState(false);
  const [graphMode, setGraphMode] = useState("all");
  const [graphDirection, setGraphDirection] = useState("both");
  const [sizeBy, setSizeBy] = useState("cited_by");
  const [colorBy, setColorBy] = useState("year");
  const [activeTab, setActiveTab] = useState(urlCitekey ? "paper" : "library");
  const [openPaperKeys, setOpenPaperKeys] = useState(urlCitekey ? [urlCitekey] : []);
  const [activePaperKey, setActivePaperKey] = useState(urlCitekey);
  const [showSearch, setShowSearch] = useState(false);
  const [libraryMode, setLibraryMode] = useState("list"); // "list" | "split" | "graph"
  const [showInspector, setShowInspector] = useState(false);
  const [showSetup, setShowSetup] = useState(false);
  const [actionState, setActionState] = useState({ busy: false, message: "", error: false });
  const [setup, setSetup] = useState(null);
  const [setupError, setSetupError] = useState(null);
  const [setupCommand, setSetupCommand] = useState("");
  const [setupCondaEnv, setSetupCondaEnv] = useState("docling");
  const [ragConfig, setRagConfig] = useState({
    embedding_model: "",
    chunk_size_chars: "1000",
    chunk_overlap_chars: "200",
    default_store: "local",
    local_persist_directory: ".cache/rag/chroma_db",
  });
  const [activeExternalNode, setActiveExternalNode] = useState(null);
  const [selectedGraphNode, setSelectedGraphNode] = useState(null); // { kind: "local"|"external", citekey?, node? }
  const cyInstanceRef = useRef(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [collections, setCollections] = useState([]);
  const [activeCollectionId, setActiveCollectionId] = useState(null);
  const [contextMenu, setContextMenu] = useState(null); // {x, y, citekey}
  // Comparison selection
  const [compareSelection, setCompareSelection] = useState([]); // array of citekeys
  const [compareResult, setCompareResult] = useState(null); // {markdown, loading, error}
  const [showCompareModal, setShowCompareModal] = useState(false);
  // Reading list
  const [showReadingList, setShowReadingList] = useState(false);
  const [readingListQuestion, setReadingListQuestion] = useState("");
  const [readingListResult, setReadingListResult] = useState(null); // {recommendations, loading, error}
  // Concept search
  const [conceptSearchQuery, setConceptSearchQuery] = useState("");
  const [conceptSearchResult, setConceptSearchResult] = useState(null);
  const [conceptSearchLoading, setConceptSearchLoading] = useState(false);
  // Bulk selection
  const [bulkSelection, setBulkSelection] = useState([]); // array of citekeys
  const lastBulkClickRef = useRef(null); // for shift-click range select
  // Navigation history: stack of {activeTab, activePaperKey}
  const navHistoryRef = useRef([]);
  const navFutureRef = useRef([]);
  const navSkipRef = useRef(false); // skip recording when navigating via back/forward
  const [navCanBack, setNavCanBack] = useState(false);
  const [navCanForward, setNavCanForward] = useState(false);
  // DOI paste detection
  const [doiToast, setDoiToast] = useState(null); // { dois: string[], timer: number }
  const [doiReviewModal, setDoiReviewModal] = useState(null); // { dois: string[], checked: Set }
  const doiToastTimerRef = useRef(null);

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

  const loadCollections = useCallback(() => {
    fetch("/api/collections").then((r) => r.json()).then((d) => setCollections(d.collections || []));
  }, []);

  useEffect(() => { loadCollections(); }, [loadCollections]);

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [contextMenu]);

  // ── DOI paste detection ────────────────────────────────────
  useEffect(() => {
    function extractDois(text) {
      // Strip common DOI URL prefixes first, then match DOI pattern
      const cleaned = text.replace(/https?:\/\/(?:dx\.)?doi\.org\//g, "");
      const re = /10\.\d{4,}\/\S+/g;
      const matches = [];
      const seen = new Set();
      let m;
      while ((m = re.exec(cleaned)) !== null) {
        // Strip trailing punctuation that's likely not part of the DOI
        let doi = m[0].replace(/[.,;:)\]}>]+$/, "");
        if (!seen.has(doi)) { seen.add(doi); matches.push(doi); }
      }
      // Also extract DOIs from full URLs that weren't cleaned (e.g. mixed content)
      const urlRe = /https?:\/\/(?:dx\.)?doi\.org\/(10\.\d{4,}\/\S+)/g;
      while ((m = urlRe.exec(text)) !== null) {
        let doi = m[1].replace(/[.,;:)\]}>]+$/, "");
        if (!seen.has(doi)) { seen.add(doi); matches.push(doi); }
      }
      return matches;
    }

    function handlePaste(ev) {
      // Don't trigger when pasting into DOI input fields
      const target = ev.target;
      if (target && (target.classList.contains("absent-refs-doi-input") ||
          target.closest?.(".absent-refs-add-row"))) {
        return;
      }
      const text = ev.clipboardData?.getData("text") || "";
      if (!text) return;
      const dois = extractDois(text);
      if (!dois.length) return;

      // Filter out DOIs already in the library
      const knownDois = new Set(
        (payload?.papers || [])
          .map((p) => p.doi)
          .filter(Boolean)
          .map((d) => d.toLowerCase())
      );
      const newDois = dois.filter((d) => !knownDois.has(d.toLowerCase()));
      if (!newDois.length) return;

      // Clear any existing timer
      if (doiToastTimerRef.current) clearTimeout(doiToastTimerRef.current);

      setDoiToast({ dois: newDois });
      doiToastTimerRef.current = setTimeout(() => setDoiToast(null), 8000);
    }

    document.addEventListener("paste", handlePaste);
    return () => document.removeEventListener("paste", handlePaste);
  }, [payload]);

  function doiToastAddAll(dois) {
    dois.forEach((doi) => triggerAction("add-paper", { doi }));
    if (doiToastTimerRef.current) clearTimeout(doiToastTimerRef.current);
    setDoiToast(null);
  }

  function doiToastDismiss() {
    if (doiToastTimerRef.current) clearTimeout(doiToastTimerRef.current);
    setDoiToast(null);
  }

  function doiToastReview(dois) {
    if (doiToastTimerRef.current) clearTimeout(doiToastTimerRef.current);
    setDoiToast(null);
    setDoiReviewModal({ dois, checked: new Set(dois) });
  }

  function doiReviewToggle(doi) {
    setDoiReviewModal((prev) => {
      if (!prev) return prev;
      const next = new Set(prev.checked);
      if (next.has(doi)) next.delete(doi); else next.add(doi);
      return { ...prev, checked: next };
    });
  }

  function doiReviewSubmit() {
    if (!doiReviewModal) return;
    [...doiReviewModal.checked].forEach((doi) => triggerAction("add-paper", { doi }));
    setDoiReviewModal(null);
  }

  const papers = useMemo(() => {
    if (!payload) return [];
    const q = query.trim().toLowerCase();
    const activeCol = activeCollectionId ? collections.find((c) => c.id === activeCollectionId) : null;
    const colCitekeys = activeCol
      ? (activeCol.smart ? activeCol.resolved_citekeys : activeCol.citekeys) || []
      : null;
    return (payload.papers || []).filter((paper) => {
      if (q && !`${paper.citekey} ${paper.title}`.toLowerCase().includes(q)) return false;
      if (statusFilter && (paper.library || {}).status !== statusFilter) return false;
      if (tagFilter && !((paper.library || {}).tags || []).includes(tagFilter)) return false;
      if (colCitekeys && !colCitekeys.includes(paper.citekey)) return false;
      return true;
    });
  }, [payload, query, statusFilter, tagFilter, activeCollectionId, collections]);

  const allTags = useMemo(() => {
    if (!payload) return [];
    const tags = new Set();
    (payload.papers || []).forEach((p) => ((p.library || {}).tags || []).forEach((t) => tags.add(t)));
    return [...tags].sort();
  }, [payload]);

  // Paper focused in the graph/inspector
  const activePaper = useMemo(() => {
    if (!payload) return null;
    return (payload.papers || []).find((paper) => paper.citekey === activeKey) || papers[0] || null;
  }, [payload, papers, activeKey]);

  // Paper shown in the paper tab strip
  const activePaperItem = useMemo(() => {
    if (!payload || !activePaperKey) return null;
    return (payload.papers || []).find((p) => p.citekey === activePaperKey) || null;
  }, [payload, activePaperKey]);



  // Record a navigation step (tab + optional paperKey) into history
  function navPush(tab, paperKey) {
    if (navSkipRef.current) return;
    const entry = { tab, paperKey: paperKey || "" };
    navHistoryRef.current = [...navHistoryRef.current, entry];
    navFutureRef.current = [];
    setNavCanBack(navHistoryRef.current.length > 1);
    setNavCanForward(false);
  }

  function navApply(entry) {
    navSkipRef.current = true;
    setActiveTab(entry.tab);
    if (entry.paperKey) {
      setActivePaperKey(entry.paperKey);
      setOpenPaperKeys((prev) => prev.includes(entry.paperKey) ? prev : [...prev, entry.paperKey]);
    }
    navSkipRef.current = false;
  }

  function navBack() {
    if (navHistoryRef.current.length <= 1) return;
    const current = navHistoryRef.current[navHistoryRef.current.length - 1];
    navFutureRef.current = [current, ...navFutureRef.current];
    navHistoryRef.current = navHistoryRef.current.slice(0, -1);
    const entry = navHistoryRef.current[navHistoryRef.current.length - 1];
    setNavCanBack(navHistoryRef.current.length > 1);
    setNavCanForward(true);
    navApply(entry);
  }

  function navForward() {
    if (navFutureRef.current.length === 0) return;
    const entry = navFutureRef.current[0];
    navFutureRef.current = navFutureRef.current.slice(1);
    navHistoryRef.current = [...navHistoryRef.current, entry];
    setNavCanBack(true);
    setNavCanForward(navFutureRef.current.length > 0);
    navApply(entry);
  }

  function openInPaperTab(citekey) {
    setOpenPaperKeys((prev) => prev.includes(citekey) ? prev : [...prev, citekey]);
    setActivePaperKey(citekey);
    setActiveTab("paper");
    navPush("paper", citekey);
  }

  function closePaperTab(citekey) {
    setOpenPaperKeys((prev) => {
      const next = prev.filter((k) => k !== citekey);
      if (activePaperKey === citekey) {
        const idx = prev.indexOf(citekey);
        const nextKey = next[idx] ?? next[idx - 1] ?? "";
        setActivePaperKey(nextKey);
        if (!nextKey) setActiveTab("library");
      }
      return next;
    });
  }

  async function updateLibraryEntry(citekey, updates) {
    try {
      await fetch(`/api/library/${encodeURIComponent(citekey)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      loadModel();
    } catch (err) {
      console.error("library update failed", err);
    }
  }

  async function bulkUpdateLibrary(updates) {
    try {
      await fetch("/api/library/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ citekeys: bulkSelection, ...updates }),
      });
      loadModel();
    } catch (err) {
      console.error("bulk library update failed", err);
    }
  }

  function toggleBulkSelect(citekey, event) {
    if (event && event.shiftKey && lastBulkClickRef.current) {
      // Range select
      const paperKeys = papers.map((p) => p.citekey);
      const lastIdx = paperKeys.indexOf(lastBulkClickRef.current);
      const curIdx = paperKeys.indexOf(citekey);
      if (lastIdx >= 0 && curIdx >= 0) {
        const start = Math.min(lastIdx, curIdx);
        const end = Math.max(lastIdx, curIdx);
        const range = paperKeys.slice(start, end + 1);
        setBulkSelection((prev) => {
          const set = new Set(prev);
          range.forEach((ck) => set.add(ck));
          return [...set];
        });
        return;
      }
    }
    lastBulkClickRef.current = citekey;
    setBulkSelection((prev) =>
      prev.includes(citekey) ? prev.filter((ck) => ck !== citekey) : [...prev, citekey]
    );
  }

  async function createCollection(name, parentId, query) {
    const body = { name, parent: parentId || null };
    if (query) body.query = query;
    await fetch("/api/collections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    loadCollections();
  }

  async function renameCollection(id, name) {
    await fetch(`/api/collections/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    loadCollections();
  }

  async function deleteCollection(id) {
    await fetch(`/api/collections/${id}`, { method: "DELETE" });
    loadCollections();
  }

  async function editCollectionQuery(id, query) {
    await fetch(`/api/collections/${id}/query`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    loadCollections();
  }

  async function convertToSmartCollection(id, query) {
    await fetch(`/api/collections/${id}/convert-smart`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    loadCollections();
  }

  async function togglePaperInCollection(colId, citekey) {
    const col = collections.find((c) => c.id === colId);
    if (!col) return;
    const method = col.citekeys.includes(citekey) ? "DELETE" : "POST";
    await fetch(`/api/collections/${colId}/papers`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ citekeys: [citekey] }),
    });
    loadCollections();
  }

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
        logs: data.logs || "",
        progressCompleted: completed,
        progressTotal: total,
        progressPercent: pct,
        action,
      });
      if (data.running) {
        window.setTimeout(() => pollJobStatus(action), 400);
      } else if (!data.error) {
        loadModel();
        if (action === "docling-run" || action === "rag-build") loadSetup();
      }
    } catch (err) {
      setActionState({
        busy: false,
        message: String(err.message || err),
        error: true,
        logs: "",
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
      if (data.async && (action === "graph-expand" || action === "docling-run" || action === "grobid-run" || action === "grobid-match" || action === "rag-build" || action === "fetch-pdfs-oa" || action === "autotag" || action === "summarize" || action === "present" || action === "concepts-extract")) {
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

  async function cancelAction(action) {
    if (!action) return;
    try {
      await fetch(`/api/actions/${action}/cancel`, { method: "POST" });
    } catch (_) {}
  }

  function toggleCompareSelection(citekey) {
    setCompareSelection((prev) =>
      prev.includes(citekey) ? prev.filter((k) => k !== citekey) : [...prev, citekey]
    );
  }

  async function runComparison(dimensions) {
    if (compareSelection.length < 2) return;
    setShowCompareModal(true);
    setCompareResult({ markdown: null, loading: true, error: null });
    try {
      const resp = await fetch("/api/actions/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ citekeys: compareSelection, dimensions: dimensions || null }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      // Poll for result
      pollCompareResult();
    } catch (err) {
      setCompareResult({ markdown: null, loading: false, error: String(err.message || err) });
    }
  }

  async function pollCompareResult() {
    try {
      const resp = await fetch("/api/actions/compare/status");
      const data = await resp.json();
      if (data.running) {
        setCompareResult({ markdown: null, loading: true, error: null, message: data.message });
        window.setTimeout(pollCompareResult, 500);
      } else if (data.error) {
        setCompareResult({ markdown: null, loading: false, error: data.error });
      } else {
        // Load the comparison file
        const path = data.comparison_path;
        if (path) {
          const fileResp = await fetch(`/api/comparisons/latest`);
          const text = await fileResp.text();
          setCompareResult({ markdown: text, loading: false, error: null });
        } else {
          setCompareResult({ markdown: "Comparison complete (no file generated).", loading: false, error: null });
        }
      }
    } catch (err) {
      setCompareResult({ markdown: null, loading: false, error: String(err.message || err) });
    }
  }

  async function runReadingList() {
    if (!readingListQuestion.trim()) return;
    setReadingListResult({ recommendations: null, loading: true, error: null });
    try {
      const resp = await fetch("/api/reading-list", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: readingListQuestion.trim() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      // Poll for result
      pollReadingListResult();
    } catch (err) {
      setReadingListResult({ recommendations: null, loading: false, error: String(err.message || err) });
    }
  }

  async function pollReadingListResult() {
    try {
      const resp = await fetch("/api/actions/reading-list/status");
      const data = await resp.json();
      if (data.running) {
        setReadingListResult({ recommendations: null, loading: true, error: null, message: data.message });
        window.setTimeout(pollReadingListResult, 500);
      } else if (data.error) {
        setReadingListResult({ recommendations: null, loading: false, error: data.error });
      } else {
        setReadingListResult({ recommendations: data.recommendations || [], loading: false, error: null });
      }
    } catch (err) {
      setReadingListResult({ recommendations: null, loading: false, error: String(err.message || err) });
    }
  }

  async function runConceptSearch(query) {
    const q = (query || conceptSearchQuery).trim();
    if (!q) return;
    setConceptSearchQuery(q);
    setConceptSearchLoading(true);
    setConceptSearchResult(null);
    try {
      const resp = await fetch("/api/concepts/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      setConceptSearchResult(data);
    } catch (err) {
      setConceptSearchResult({ error: String(err.message || err) });
    } finally {
      setConceptSearchLoading(false);
    }
  }

  function handleConceptClick(concept) {
    setShowSearch(true);
    runConceptSearch(concept);
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
      if (endpoint === "/api/setup/grobid-check") {
        setSetup((prev) => prev ? { ...prev, grobid: { ...prev.grobid, ...data } } : prev);
        setActionState({ busy: false, message: data.message || "GROBID checked", error: !data.ok });
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

  const activeArtifacts = activePaperItem ? activePaperItem.artifacts : null;
  const docsUrl = "https://arashshahidi1997.github.io/biblio/";
  const githubUrl = "https://github.com/arashshahidi1997/biblio";
  const tabs = [
    ["library", "Library"],
    ["paper", "Paper"],
  ];

  return (
    <div className="app">
      {/* DOI paste toast */}
      {doiToast && (
        <div className="doi-toast">
          {doiToast.dois.length === 1 ? (
            <>
              <span className="doi-toast-text">DOI detected: <code>{doiToast.dois[0]}</code></span>
              <button className="doi-toast-btn primary" onClick={() => doiToastAddAll(doiToast.dois)}>Add to library</button>
              <button className="doi-toast-btn" onClick={doiToastDismiss}>Dismiss</button>
            </>
          ) : (
            <>
              <span className="doi-toast-text">{doiToast.dois.length} DOIs detected</span>
              <button className="doi-toast-btn primary" onClick={() => doiToastAddAll(doiToast.dois)}>Add all</button>
              <button className="doi-toast-btn" onClick={() => doiToastReview(doiToast.dois)}>Review</button>
              <button className="doi-toast-btn" onClick={doiToastDismiss}>Dismiss</button>
            </>
          )}
        </div>
      )}

      {/* DOI review modal */}
      {doiReviewModal && (
        <div className="doi-review-overlay" onClick={() => setDoiReviewModal(null)}>
          <div className="doi-review-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Review DOIs to add</h3>
            <div className="doi-review-list">
              {doiReviewModal.dois.map((doi) => (
                <label key={doi} className="doi-review-item">
                  <input
                    type="checkbox"
                    checked={doiReviewModal.checked.has(doi)}
                    onChange={() => doiReviewToggle(doi)}
                  />
                  <code>{doi}</code>
                </label>
              ))}
            </div>
            <div className="doi-review-actions">
              <button className="doi-toast-btn primary" onClick={doiReviewSubmit} disabled={doiReviewModal.checked.size === 0}>
                Add {doiReviewModal.checked.size} selected
              </button>
              <button className="doi-toast-btn" onClick={() => setDoiReviewModal(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="header">
        <div className="header-bar">
          <div>
            <div className="small">Local FastAPI bibliography explorer</div>
            <h1>BiBlio</h1>
          </div>
          <div className="header-links">
            <a href={docsUrl} target="_blank" rel="noreferrer">Docs</a>
            <a href={githubUrl} target="_blank" rel="noreferrer">GitHub</a>
          </div>
        </div>
      </div>

      {/* App body: icon sidebar + main */}
      <div className="app-layout">

        {/* Vertical icon sidebar */}
        <nav className="icon-sidebar">
          <div className="sidebar-divider" />

          {/* Panel toggles */}
          <div className="sidebar-section">
            <button
              className={`sidebar-icon${showSearch ? " active" : ""}`}
              onClick={() => setShowSearch((s) => !s)}
              title="Search"
            >
              ⌕
            </button>
            {activeTab === "library" && (
              <button
                className={`sidebar-icon${showInspector ? " active" : ""}`}
                onClick={() => setShowInspector((s) => !s)}
                title="Inspector"
              >
                ⓘ
              </button>
            )}
            <button
              className={`sidebar-icon${showReadingList ? " active" : ""}`}
              onClick={() => setShowReadingList((s) => !s)}
              title="Reading List"
            >
              ☰
            </button>
          </div>

          {/* Spacer pushes settings to bottom */}
          <div className="sidebar-spacer" />

          <div className="sidebar-section">
            <button
              className={`sidebar-icon${showSetup ? " active" : ""}`}
              onClick={() => setShowSetup((s) => !s)}
              title="Settings"
            >
              ⚙
            </button>
          </div>
        </nav>

        {/* Main content */}
        <div className="main-content">

          {/* Settings full view */}
          {showSetup && (
            <div className="settings-view">
              <div className="settings-view-header">
                <h2 style={{ margin: 0 }}>Settings</h2>
                <button className="icon-btn" onClick={() => setShowSetup(false)} title="Close">✕</button>
              </div>
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
                triggerAction={triggerAction}
              />
            </div>
          )}

          {!showSetup && (<>
          {/* Global tab strip: nav buttons + Library (fixed) + open paper tabs */}
          <div className="global-tabstrip">
            {/* Back / Forward */}
            <button
              className="global-tabstrip-nav-btn"
              disabled={!navCanBack}
              onClick={navBack}
              title="Navigate back"
            >‹</button>
            <button
              className="global-tabstrip-nav-btn"
              disabled={!navCanForward}
              onClick={navForward}
              title="Navigate forward"
            >›</button>
            <div className="global-tabstrip-sep" />
            <div
              className={`global-tabstrip-tab global-tabstrip-tab--library${activeTab === "library" ? " active" : ""}`}
              onClick={() => { setActiveTab("library"); navPush("library", ""); }}
              title="Library"
            >
              <span className="global-tabstrip-label">▤ Library</span>
            </div>
            <div
              className={`global-tabstrip-tab global-tabstrip-tab--research${activeTab === "research" ? " active" : ""}`}
              onClick={() => { setActiveTab("research"); navPush("research", ""); }}
              title="Research"
            >
              <span className="global-tabstrip-label">&#x270E; Research</span>
            </div>
            <div className="global-tabstrip-sep" />
            {openPaperKeys.map((ck) => (
              <div
                key={ck}
                className={`global-tabstrip-tab${activeTab === "paper" && ck === activePaperKey ? " active" : ""}`}
                onClick={() => { setActiveTab("paper"); setActivePaperKey(ck); navPush("paper", ck); }}
              >
                <span className="global-tabstrip-label">{ck}</span>
                <button
                  className="global-tabstrip-close"
                  onClick={(e) => { e.stopPropagation(); closePaperTab(ck); }}
                >×</button>
              </div>
            ))}
          </div>

          {/* Paper/graph controls */}
          <div className="controls">
            {activeTab !== "paper" && (
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
                      if (exact) setActiveKey(exact.citekey);
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
            )}
            <div className="field">
              <label>Focus paper</label>
              <select value={activePaper ? activePaper.citekey : ""} onChange={(ev) => setActiveKey(ev.target.value)}>
                {papers.map((paper) => (
                  <option key={paper.citekey} value={paper.citekey}>{`${paper.citekey} — ${paper.title}`}</option>
                ))}
              </select>
            </div>
            {activeTab === "library" && (
              <div className="view-mode-bar">
                <button
                  className={`view-mode-btn${libraryMode === "list" ? " active" : ""}`}
                  onClick={() => setLibraryMode("list")}
                  title="List only"
                >
                  <span className="vm-bars" />
                </button>
                <button
                  className={`view-mode-btn${libraryMode === "split" ? " active" : ""}`}
                  onClick={() => setLibraryMode("split")}
                  title="List + Graph"
                >
                  <span className="vm-bars" /><span className="vm-dot" />
                </button>
                <button
                  className={`view-mode-btn${libraryMode === "graph" ? " active" : ""}`}
                  onClick={() => setLibraryMode("graph")}
                  title="Graph only"
                >
                  <span className="vm-dot" />
                </button>
              </div>
            )}
          </div>

          {/* Multicolumn panels */}
          <div className="multicolumn-layout">
        {/* Semantic search column */}
        {showSearch && (
          <div className="col col-search">
            <SearchTab
              setActiveKey={setActiveKey}
              setActiveTab={(t) => setActiveTab(t === "corpus" ? "library" : t)}
            />
          </div>
        )}

        {/* Collections tree column */}
        {activeTab === "library" && (
          <div className="col col-collections">
            <CollectionTree
              collections={collections}
              activeCollectionId={activeCollectionId}
              setActiveCollectionId={setActiveCollectionId}
              onCreateCollection={createCollection}
              onRenameCollection={renameCollection}
              onDeleteCollection={deleteCollection}
              onEditQuery={editCollectionQuery}
              onConvertToSmart={convertToSmartCollection}
            />
          </div>
        )}

        {/* Library list column */}
        {activeTab === "library" && libraryMode !== "graph" && (
          <div className="col col-library">
            <CorpusTab
              papers={papers}
              actionState={actionState}
              setActiveKey={setActiveKey}
              setActiveTab={setActiveTab}
              openInPaperTab={openInPaperTab}
              setLibraryMode={setLibraryMode}
              triggerAction={triggerAction}
              statusFilter={statusFilter}
              setStatusFilter={setStatusFilter}
              tagFilter={tagFilter}
              setTagFilter={setTagFilter}
              allTags={allTags}
              updateLibraryEntry={updateLibraryEntry}
              compact={libraryMode === "split"}
              onRowContextMenu={(e, citekey) => { e.preventDefault(); setContextMenu({ x: e.clientX, y: e.clientY, citekey }); }}
              bulkSelection={bulkSelection}
              setBulkSelection={setBulkSelection}
              toggleBulkSelect={toggleBulkSelect}
              bulkUpdateLibrary={bulkUpdateLibrary}
              loadModel={loadModel}
            />
          </div>
        )}

        {/* Network graph column */}
        {activeTab === "library" && libraryMode !== "list" && (
          <div className="col col-network">
            <div className="graph-column-layout">
              <div className="graph-controls-bar">
                <select value={localOnly ? "local" : "all"} onChange={(ev) => setLocalOnly(ev.target.value === "local")} title="Graph filter">
                  <option value="all">Local + external</option>
                  <option value="local">Local only</option>
                </select>
                <select value={graphMode} onChange={(ev) => setGraphMode(ev.target.value)} title="Explore mode">
                  <option value="focused">Focused</option>
                  <option value="all">All papers</option>
                </select>
                <select value={graphDirection} onChange={(ev) => setGraphDirection(ev.target.value)} title="Direction">
                  <option value="both">Past + future</option>
                  <option value="past">Past works</option>
                  <option value="future">Future works</option>
                </select>
                <select value={sizeBy} onChange={(ev) => setSizeBy(ev.target.value)} title="Size by">
                  <option value="cited_by">Size: citations</option>
                  <option value="uniform">Size: uniform</option>
                </select>
                <select value={colorBy} onChange={(ev) => setColorBy(ev.target.value)} title="Color by">
                  <option value="year">Color: year</option>
                  <option value="type">Color: type</option>
                </select>
              </div>
              <div className="graph-body-row">
              <ExploreTab
                payload={payload}
                activePaper={activePaper}
                localOnly={localOnly}
                graphMode={graphMode}
                graphDirection={graphDirection}
                setActiveKey={setActiveKey}
                setActiveExternalNode={setActiveExternalNode}
                openInPaperTab={openInPaperTab}
                onSelectNode={setSelectedGraphNode}
                onCyInit={(cy) => { cyInstanceRef.current = cy; }}
                sizeBy={sizeBy}
                colorBy={colorBy}
                setGraphDirection={setGraphDirection}
                setGraphMode={setGraphMode}
              />
              <nav className="graph-actions-bar">
                <button
                  className="sidebar-icon"
                  title="Zoom in"
                  onClick={() => cyInstanceRef.current && cyInstanceRef.current.zoom({ level: cyInstanceRef.current.zoom() * 1.25, renderedPosition: { x: cyInstanceRef.current.width() / 2, y: cyInstanceRef.current.height() / 2 } })}
                >
                  +
                </button>
                <button
                  className="sidebar-icon"
                  title="Zoom out"
                  onClick={() => cyInstanceRef.current && cyInstanceRef.current.zoom({ level: cyInstanceRef.current.zoom() * 0.8, renderedPosition: { x: cyInstanceRef.current.width() / 2, y: cyInstanceRef.current.height() / 2 } })}
                >
                  −
                </button>
                <button
                  className="sidebar-icon"
                  title="Fit all"
                  onClick={() => cyInstanceRef.current && cyInstanceRef.current.fit(undefined, 30)}
                >
                  ⤢
                </button>
                <div className="sidebar-divider" />
                <button
                  className="sidebar-icon"
                  title="Expand graph for all papers"
                  disabled={actionState.busy}
                  onClick={() => triggerAction("graph-expand", {})}
                >
                  ⊕
                </button>
                <button
                  className={`sidebar-icon${selectedGraphNode && selectedGraphNode.kind === "local" ? "" : " disabled-look"}`}
                  title={selectedGraphNode && selectedGraphNode.kind === "local"
                    ? `Expand graph for ${selectedGraphNode.citekey}`
                    : "Select a local paper node first"}
                  disabled={actionState.busy || !selectedGraphNode || selectedGraphNode.kind !== "local"}
                  onClick={() => selectedGraphNode && triggerAction("graph-expand", { citekey: selectedGraphNode.citekey })}
                >
                  ⊕₁
                </button>
              </nav>
              </div>
            </div>
          </div>
        )}

        {/* Paper detail column */}
        {activeTab === "paper" && (
          <div className="col col-paper">
            {activePaperItem
              ? <PaperTab
                  activePaper={activePaperItem}
                  activeArtifacts={activeArtifacts}
                  updateLibraryEntry={updateLibraryEntry}
                  triggerAction={triggerAction}
                  actionState={actionState}
                  papers={payload ? payload.papers : []}
                  openInPaperTab={openInPaperTab}
                  onConceptClick={handleConceptClick}
                />
              : <div className="small" style={{ padding: "1rem" }}>
                  No paper selected — double-click a row in the Library tab to open one.
                </div>
            }
          </div>
        )}

        {/* Research tab */}
        {activeTab === "research" && (
          <ResearchTab openInPaperTab={openInPaperTab} />
        )}

        {/* Inspector column */}
        {(activeTab === "library") && showInspector && (
          <div className="col col-inspector">
            <GraphInspector
              activePaper={activePaper}
              activeExternalNode={activeExternalNode}
              status={payload ? payload.status : null}
              actionState={actionState}
              triggerAction={triggerAction}
            />
          </div>
        )}
        {/* Paper context menu */}
        {contextMenu && (
          <div
            className="col-context-menu"
            style={{ position: "fixed", top: contextMenu.y, left: contextMenu.x }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="col-context-menu-header">{contextMenu.citekey}</div>

            {/* Paper actions */}
            <div
              className="col-context-menu-item"
              onClick={() => {
                fetch(`/api/papers/${encodeURIComponent(contextMenu.citekey)}/refresh-metadata`, { method: "POST" })
                  .then((r) => r.json())
                  .then(() => loadModel())
                  .catch(() => {});
                setContextMenu(null);
              }}
            >
              ↻ Refresh metadata from DOI
            </div>
            <div
              className="col-context-menu-item col-context-menu-danger"
              onClick={() => {
                if (!window.confirm(`Remove "${contextMenu.citekey}" from library? (Files are kept, only removes from citekeys list)`)) return;
                fetch(`/api/papers/${encodeURIComponent(contextMenu.citekey)}`, { method: "DELETE" })
                  .then((r) => r.json())
                  .then(() => { loadModel(); closePaperTab(contextMenu.citekey); })
                  .catch(() => {});
                setContextMenu(null);
              }}
            >
              ✕ Drop from library
            </div>

            <div
              className="col-context-menu-item"
              onClick={() => {
                toggleCompareSelection(contextMenu.citekey);
                setContextMenu(null);
              }}
            >
              {compareSelection.includes(contextMenu.citekey) ? "✓ In comparison set" : "⊕ Add to comparison"}
            </div>

            <div className="col-context-menu-sep" />
            <div className="col-context-menu-header" style={{ fontSize: "0.7rem" }}>Add to collection</div>
            {collections.length === 0 && (
              <div className="col-context-menu-empty">No collections yet</div>
            )}
            {collections.filter((c) => !c.smart).map((col) => (
              <div
                key={col.id}
                className="col-context-menu-item"
                onClick={() => { togglePaperInCollection(col.id, contextMenu.citekey); setContextMenu(null); }}
              >
                <span className="col-context-check">{(col.citekeys || []).includes(contextMenu.citekey) ? "✓" : "\u00a0"}</span>
                {col.name}
              </div>
            ))}
          </div>
        )}
        </div>{/* end multicolumn-layout */}

          {/* Comparison selection bar */}
          {compareSelection.length > 0 && (
            <div className="compare-bar">
              <span className="small"><strong>{compareSelection.length}</strong> papers selected for comparison:</span>
              <div className="compare-bar-pills">
                {compareSelection.map((ck) => (
                  <span key={ck} className="compare-bar-pill">
                    {ck}
                    <button className="compare-bar-pill-x" onClick={() => toggleCompareSelection(ck)}>×</button>
                  </span>
                ))}
              </div>
              <button
                className="absent-refs-btn-small absent-refs-btn-primary"
                disabled={compareSelection.length < 2}
                onClick={() => runComparison()}
              >
                Compare Selected ({compareSelection.length})
              </button>
              <button className="absent-refs-btn-small" onClick={() => setCompareSelection([])}>Clear</button>
            </div>
          )}

          {/* Reading list panel */}
          {showReadingList && (
            <div className="reading-list-panel">
              <div className="reading-list-header">
                <h3 style={{ margin: 0 }}>Reading List</h3>
                <button className="icon-btn" onClick={() => setShowReadingList(false)} title="Close">✕</button>
              </div>
              <div className="reading-list-input-row">
                <input
                  value={readingListQuestion}
                  onChange={(ev) => setReadingListQuestion(ev.target.value)}
                  placeholder="Enter your research question..."
                  style={{ flex: 1 }}
                  onKeyDown={(ev) => { if (ev.key === "Enter") runReadingList(); }}
                />
                <button
                  className="absent-refs-btn-small absent-refs-btn-primary"
                  disabled={!readingListQuestion.trim() || (readingListResult && readingListResult.loading)}
                  onClick={runReadingList}
                >
                  {readingListResult && readingListResult.loading ? "Generating..." : "Generate Reading List"}
                </button>
              </div>
              {readingListResult && readingListResult.loading && (
                <div className="small" style={{ padding: "0.6rem 0", opacity: 0.6 }}>
                  <span className="action-spinner">⟳</span> {readingListResult.message || "Generating reading list..."}
                </div>
              )}
              {readingListResult && readingListResult.error && (
                <div className="action-status error" style={{ margin: "0.5rem 0" }}>{readingListResult.error}</div>
              )}
              {readingListResult && readingListResult.recommendations && (
                <div className="reading-list-results">
                  {readingListResult.recommendations.length === 0 ? (
                    <div className="small" style={{ opacity: 0.6 }}>No recommendations generated.</div>
                  ) : (
                    readingListResult.recommendations.map((rec, idx) => (
                      <div key={rec.citekey || idx} className="reading-list-item" onClick={() => openInPaperTab(rec.citekey)}>
                        <div className="reading-list-item-header">
                          <strong>{rec.citekey}</strong>
                          <span className="reading-list-score-bar">
                            <span className="reading-list-score-fill" style={{ width: `${Math.round((rec.score || 0) * 100)}%` }} />
                            <span className="reading-list-score-label">{Math.round((rec.score || 0) * 100)}%</span>
                          </span>
                          <button
                            className="absent-refs-btn-small"
                            onClick={(e) => { e.stopPropagation(); updateLibraryEntry(rec.citekey, { priority: "high" }); }}
                            title="Set priority to high"
                          >
                            ★ High
                          </button>
                        </div>
                        <div className="small" style={{ opacity: 0.75, marginTop: "0.2rem" }}>{rec.justification}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          )}

          {/* Concept search panel (in search column) */}
          {showSearch && conceptSearchQuery && (
            <div className="concept-search-panel">
              <div className="concept-search-header">
                <h3 style={{ margin: 0 }}>Concept Search: "{conceptSearchQuery}"</h3>
                <button className="icon-btn" onClick={() => { setConceptSearchQuery(""); setConceptSearchResult(null); }} title="Close">✕</button>
              </div>
              {conceptSearchLoading && <div className="small" style={{ padding: "0.5rem 0", opacity: 0.6 }}>Searching concepts...</div>}
              {conceptSearchResult && conceptSearchResult.error && (
                <div className="action-status error">{conceptSearchResult.error}</div>
              )}
              {conceptSearchResult && !conceptSearchResult.error && (
                <div className="concept-search-results">
                  {(conceptSearchResult.matches || []).length === 0 && (
                    <div className="small" style={{ opacity: 0.6 }}>No matching concepts found.</div>
                  )}
                  {(conceptSearchResult.matches || []).map((m) => (
                    <div key={m.concept} className="concept-search-group">
                      <div className="concepts-group-label">{m.concept}</div>
                      <div className="concept-search-papers">
                        {(m.citekeys || []).map((ck) => (
                          <div
                            key={ck}
                            className="concept-search-paper-item"
                            onClick={() => openInPaperTab(ck)}
                          >
                            {ck}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Compare modal */}
          {showCompareModal && (
            <div className="compare-modal-overlay" onClick={() => setShowCompareModal(false)}>
              <div className="compare-modal" onClick={(e) => e.stopPropagation()}>
                <div className="compare-modal-header">
                  <h2 style={{ margin: 0 }}>Paper Comparison</h2>
                  <button className="icon-btn" onClick={() => setShowCompareModal(false)} title="Close">✕</button>
                </div>
                <div className="compare-modal-body">
                  {compareResult && compareResult.loading && (
                    <div className="small" style={{ padding: "2rem", textAlign: "center", opacity: 0.6 }}>
                      <span className="action-spinner">⟳</span> {compareResult.message || "Generating comparison..."}
                    </div>
                  )}
                  {compareResult && compareResult.error && (
                    <div className="action-status error">{compareResult.error}</div>
                  )}
                  {compareResult && compareResult.markdown && (
                    <div className="docling-box docling-box-full" dangerouslySetInnerHTML={{ __html: renderMarkdown(compareResult.markdown) }} />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Action status bar */}
          {actionState.message && (
            <div className={`action-status-bar${actionState.error ? " error" : actionState.busy ? " busy" : ""}`}>
              {actionState.busy && actionState.action && (
                <button
                  className="action-cancel-btn"
                  onClick={() => cancelAction(actionState.action)}
                  title="Cancel operation"
                >✕</button>
              )}
              {actionState.busy && <span className="action-spinner">⟳</span>}
              {actionState.message}
            </div>
          )}

          {/* Stats footer */}
          {payload && payload.status && (
            <div className="stats-footer">
              <span>{payload.status.papers_total} papers</span>
              <span className="stats-sep">·</span>
              <span>{payload.status.papers_with_pdf ?? 0} pdf</span>
              <span className="stats-sep">·</span>
              <span>{payload.status.papers_with_docling ?? 0} docling</span>
              <span className="stats-sep">·</span>
              <span>{payload.status.papers_with_openalex ?? 0} openalex</span>
              <span className="stats-sep">·</span>
              <span>{payload.status.papers_with_grobid ?? 0} grobid</span>
            </div>
          )}

          </>)}{/* end !showSetup */}
        </div>{/* end main-content */}
      </div>{/* end app-layout */}
    </div>
  );
}
