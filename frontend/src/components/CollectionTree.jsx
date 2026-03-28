import { useState, useRef, useEffect } from "react";

function buildTree(collections, parentId = null) {
  return collections
    .filter((c) => (c.parent ?? null) === parentId)
    .map((c) => ({ ...c, children: buildTree(collections, c.id) }));
}

/* ── Inline query editor (shared by create-smart and edit-query) ───────── */

function QueryEditor({ initial, onSave, onCancel, placeholder }) {
  const [value, setValue] = useState(initial || "");
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); }, []);

  return (
    <div className="col-tree-query-editor" onClick={(e) => e.stopPropagation()}>
      <input
        ref={ref}
        className="col-tree-edit-input col-tree-query-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder || 'tag:method:transformer AND status:unread'}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) onSave(value.trim());
          if (e.key === "Escape") onCancel();
        }}
      />
      <div className="col-tree-query-help" title="Predicates: tag:, status:, priority:, author:, year:, has:, type:, keyword:  —  Operators: AND, OR, NOT">
        ?
      </div>
      <button className="col-tree-action-btn" onClick={() => value.trim() && onSave(value.trim())}>✓</button>
      <button className="col-tree-action-btn" onClick={onCancel}>✕</button>
    </div>
  );
}

/* ── Single collection node ───────────────────────────────────────────── */

function CollectionNode({
  col, depth,
  activeId, setActiveId,
  onCreateChild, onRename, onDelete,
  onEditQuery, onConvertToSmart,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(col.name);
  const [expanded, setExpanded] = useState(true);
  const [editingQuery, setEditingQuery] = useState(false);
  const [showConvert, setShowConvert] = useState(false);
  const inputRef = useRef(null);
  const hasChildren = col.children && col.children.length > 0;
  const isActive = activeId === col.id;
  const isSmart = !!col.smart;

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  function commit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== col.name) onRename(col.id, trimmed);
    setEditing(false);
  }

  const memberCount = isSmart ? (col.resolved_count ?? 0) : (col.citekeys?.length ?? 0);

  return (
    <li className="col-tree-li">
      <div
        className={`col-tree-row${isActive ? " active" : ""}`}
        style={{ paddingLeft: `${0.4 + depth * 1.1}rem` }}
        onClick={() => !editing && setActiveId(col.id)}
      >
        <button
          className={`col-tree-toggle${hasChildren ? "" : " invisible"}`}
          onClick={(e) => { e.stopPropagation(); setExpanded((x) => !x); }}
          tabIndex={-1}
        >
          {expanded ? "▾" : "▸"}
        </button>

        <span
          className="col-tree-icon"
          title={isSmart ? `Smart: ${col.query}` : "Manual collection"}
        >
          {isSmart ? "⚡" : "▤"}
        </span>

        {editing ? (
          <input
            ref={inputRef}
            className="col-tree-edit-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") { setDraft(col.name); setEditing(false); }
            }}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span
            className="col-tree-label"
            onDoubleClick={(e) => { e.stopPropagation(); setDraft(col.name); setEditing(true); }}
            title={col.name}
          >
            {col.name}
          </span>
        )}

        <span className="col-tree-count">{memberCount}</span>

        <span className="col-tree-actions">
          {isSmart && (
            <button
              className="col-tree-action-btn"
              title="Edit query"
              onClick={(e) => { e.stopPropagation(); setEditingQuery(true); }}
            >✎</button>
          )}
          {!isSmart && (
            <button
              className="col-tree-action-btn"
              title="Convert to smart collection"
              onClick={(e) => { e.stopPropagation(); setShowConvert(true); }}
            >⚡</button>
          )}
          <button
            className="col-tree-action-btn"
            title="New subcollection"
            onClick={(e) => { e.stopPropagation(); onCreateChild(col.id); }}
          >+</button>
          <button
            className="col-tree-action-btn col-tree-action-del"
            title="Delete collection"
            onClick={(e) => { e.stopPropagation(); onDelete(col.id, col.name); }}
          >✕</button>
        </span>
      </div>

      {/* Inline query editor for smart collections */}
      {editingQuery && (
        <div style={{ paddingLeft: `${0.4 + (depth + 1) * 1.1}rem` }}>
          <QueryEditor
            initial={col.query || ""}
            onSave={(q) => { onEditQuery(col.id, q); setEditingQuery(false); }}
            onCancel={() => setEditingQuery(false)}
            placeholder="tag:method:transformer AND status:unread"
          />
        </div>
      )}

      {/* Inline convert-to-smart form */}
      {showConvert && (
        <div style={{ paddingLeft: `${0.4 + (depth + 1) * 1.1}rem` }}>
          <QueryEditor
            initial=""
            onSave={(q) => { onConvertToSmart(col.id, q); setShowConvert(false); }}
            onCancel={() => setShowConvert(false)}
            placeholder="Enter query to convert to smart collection"
          />
        </div>
      )}

      {hasChildren && expanded && (
        <ul className="col-tree-ul">
          {col.children.map((child) => (
            <CollectionNode
              key={child.id}
              col={child}
              depth={depth + 1}
              activeId={activeId}
              setActiveId={setActiveId}
              onCreateChild={onCreateChild}
              onRename={onRename}
              onDelete={onDelete}
              onEditQuery={onEditQuery}
              onConvertToSmart={onConvertToSmart}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/* ── Collection tree panel ────────────────────────────────────────────── */

export default function CollectionTree({
  collections,
  activeCollectionId,
  setActiveCollectionId,
  onCreateCollection,
  onRenameCollection,
  onDeleteCollection,
  onEditQuery,
  onConvertToSmart,
}) {
  const tree = buildTree(collections ?? []);
  const [showSmartForm, setShowSmartForm] = useState(false);
  const [smartName, setSmartName] = useState("");
  const [smartQuery, setSmartQuery] = useState("");
  const nameRef = useRef(null);

  useEffect(() => {
    if (showSmartForm && nameRef.current) nameRef.current.focus();
  }, [showSmartForm]);

  function handleCreate(parentId) {
    const name = prompt("Collection name:");
    if (name?.trim()) onCreateCollection(name.trim(), parentId);
  }

  function handleDelete(id, name) {
    if (window.confirm(`Delete "${name}"? Its papers won't be removed, but subcollections will move up.`)) {
      onDeleteCollection(id);
      if (activeCollectionId === id) setActiveCollectionId(null);
    }
  }

  function handleCreateSmart() {
    const n = smartName.trim();
    const q = smartQuery.trim();
    if (n && q) {
      onCreateCollection(n, null, q);
      setSmartName("");
      setSmartQuery("");
      setShowSmartForm(false);
    }
  }

  return (
    <div className="col-tree-panel">
      <div className="col-tree-header">
        <span className="col-tree-header-label">Collections</span>
        <button
          className="col-tree-new-btn"
          title="New smart collection"
          onClick={() => setShowSmartForm((s) => !s)}
        >⚡</button>
        <button
          className="col-tree-new-btn"
          title="New collection"
          onClick={() => handleCreate(null)}
        >+</button>
      </div>

      {/* Inline smart collection creation form */}
      {showSmartForm && (
        <div className="col-tree-smart-form">
          <input
            ref={nameRef}
            className="col-tree-edit-input"
            value={smartName}
            onChange={(e) => setSmartName(e.target.value)}
            placeholder="Collection name"
            onKeyDown={(e) => { if (e.key === "Enter") handleCreateSmart(); if (e.key === "Escape") setShowSmartForm(false); }}
          />
          <div className="col-tree-query-row">
            <input
              className="col-tree-edit-input col-tree-query-input"
              value={smartQuery}
              onChange={(e) => setSmartQuery(e.target.value)}
              placeholder="tag:method:transformer AND status:unread"
              onKeyDown={(e) => { if (e.key === "Enter") handleCreateSmart(); if (e.key === "Escape") setShowSmartForm(false); }}
            />
            <div
              className="col-tree-query-help"
              title={"Predicates: tag:, status:, priority:, author:, year:, has:, type:, keyword:\nOperators: AND, OR, NOT\nExample: status:unread AND year:>2023"}
            >?</div>
          </div>
          <div className="col-tree-smart-form-actions">
            <button className="col-tree-action-btn" onClick={handleCreateSmart}>Create</button>
            <button className="col-tree-action-btn" onClick={() => setShowSmartForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      <ul className="col-tree-ul col-tree-root">
        {/* My Library — always first */}
        <li className="col-tree-li">
          <div
            className={`col-tree-row col-tree-row-library${!activeCollectionId ? " active" : ""}`}
            onClick={() => setActiveCollectionId(null)}
          >
            <span className="col-tree-icon">▤</span>
            <span className="col-tree-label">My Library</span>
          </div>
        </li>

        {tree.map((col) => (
          <CollectionNode
            key={col.id}
            col={col}
            depth={0}
            activeId={activeCollectionId}
            setActiveId={setActiveCollectionId}
            onCreateChild={handleCreate}
            onRename={onRenameCollection}
            onDelete={handleDelete}
            onEditQuery={onEditQuery}
            onConvertToSmart={onConvertToSmart}
          />
        ))}
      </ul>
    </div>
  );
}
