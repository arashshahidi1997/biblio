import { useState, useRef, useEffect } from "react";

function buildTree(collections, parentId = null) {
  return collections
    .filter((c) => (c.parent ?? null) === parentId)
    .map((c) => ({ ...c, children: buildTree(collections, c.id) }));
}

function CollectionNode({
  col, depth,
  activeId, setActiveId,
  onCreateChild, onRename, onDelete,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(col.name);
  const [expanded, setExpanded] = useState(true);
  const inputRef = useRef(null);
  const hasChildren = col.children && col.children.length > 0;
  const isActive = activeId === col.id;

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

        <span className="col-tree-icon">▤</span>

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

        <span className="col-tree-count">{col.citekeys?.length ?? 0}</span>

        <span className="col-tree-actions">
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
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export default function CollectionTree({
  collections,
  activeCollectionId,
  setActiveCollectionId,
  onCreateCollection,
  onRenameCollection,
  onDeleteCollection,
}) {
  const tree = buildTree(collections ?? []);
  const totalPapers = null; // shown in My Library row by parent

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

  return (
    <div className="col-tree-panel">
      <div className="col-tree-header">
        <span className="col-tree-header-label">Collections</span>
        <button
          className="col-tree-new-btn"
          title="New collection"
          onClick={() => handleCreate(null)}
        >+</button>
      </div>

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
          />
        ))}
      </ul>
    </div>
  );
}
