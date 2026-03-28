import { useState, useEffect, useRef, useCallback } from "react";

let _vocabCache = null;
let _vocabPromise = null;

function fetchVocab() {
  if (_vocabCache) return Promise.resolve(_vocabCache);
  if (_vocabPromise) return _vocabPromise;
  _vocabPromise = fetch("/api/tag-vocab")
    .then((r) => r.json())
    .then((data) => {
      _vocabCache = data;
      return data;
    })
    .catch(() => ({ namespaces: {}, aliases: {} }));
  return _vocabPromise;
}

/** Build flat list of namespace:value tags from vocab */
function buildSuggestions(vocab) {
  const tags = [];
  const namespaces = vocab.namespaces || {};
  for (const [ns, nsData] of Object.entries(namespaces)) {
    if (!nsData || !nsData.values) continue;
    for (const val of nsData.values) {
      tags.push(`${ns}:${val}`);
    }
  }
  return tags.sort();
}

/** Filter suggestions by query */
function matchSuggestions(allTags, query) {
  if (!query) return [];
  const q = query.toLowerCase();
  // If query ends with ":", show all values in that namespace
  if (q.endsWith(":")) {
    const ns = q.slice(0, -1);
    return allTags.filter((t) => t.toLowerCase().startsWith(ns + ":"));
  }
  // Otherwise match anywhere
  return allTags.filter((t) => t.toLowerCase().includes(q));
}

/**
 * TagInput — reusable tag autocomplete with chips.
 *
 * Props:
 *   tags: string[]          — current tags
 *   onChange: (string[])=>   — called when tags change
 *   placeholder?: string
 *   mode?: "edit" | "filter" — "filter" shows single-select behavior
 */
export default function TagInput({ tags, onChange, placeholder, mode }) {
  const [vocab, setVocab] = useState(null);
  const [allSuggestions, setAllSuggestions] = useState([]);
  const [inputValue, setInputValue] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    fetchVocab().then((v) => {
      setVocab(v);
      setAllSuggestions(buildSuggestions(v));
    });
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filtered = matchSuggestions(allSuggestions, inputValue)
    .filter((t) => !tags.includes(t))
    .slice(0, 20);

  function addTag(tag) {
    if (mode === "filter") {
      onChange([tag]);
      setInputValue("");
      setShowDropdown(false);
      return;
    }
    if (!tags.includes(tag)) {
      onChange([...tags, tag]);
    }
    setInputValue("");
    setShowDropdown(false);
    setHighlightIdx(-1);
  }

  function removeTag(tag) {
    onChange(tags.filter((t) => t !== tag));
  }

  function handleKeyDown(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Tab" || e.key === "Enter") {
      if (showDropdown && highlightIdx >= 0 && filtered[highlightIdx]) {
        e.preventDefault();
        addTag(filtered[highlightIdx]);
      } else if (e.key === "Enter" && inputValue.trim()) {
        e.preventDefault();
        addTag(inputValue.trim());
      }
    } else if (e.key === "Backspace" && !inputValue && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  }

  function handleInputChange(e) {
    const val = e.target.value;
    setInputValue(val);
    setShowDropdown(val.length > 0);
    setHighlightIdx(val.length > 0 && filtered.length > 0 ? 0 : -1);
  }

  return (
    <div className="tag-input-wrapper" ref={wrapperRef}>
      <div className="tag-input-chips" onClick={() => inputRef.current?.focus()}>
        {tags.map((tag) => (
          <span key={tag} className="tag-chip">
            {tag}
            <button
              className="tag-chip-remove"
              onClick={(e) => { e.stopPropagation(); removeTag(tag); }}
            >×</button>
          </span>
        ))}
        <input
          ref={inputRef}
          className="tag-input-field"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (inputValue) setShowDropdown(true); }}
          placeholder={tags.length === 0 ? (placeholder || "Add tags...") : ""}
        />
      </div>
      {showDropdown && filtered.length > 0 && (
        <div className="tag-dropdown">
          {filtered.map((tag, idx) => (
            <div
              key={tag}
              className={`tag-dropdown-item${idx === highlightIdx ? " highlighted" : ""}`}
              onMouseDown={(e) => { e.preventDefault(); addTag(tag); }}
              onMouseEnter={() => setHighlightIdx(idx)}
            >
              <span className="tag-dropdown-ns">{tag.split(":")[0]}:</span>
              <span>{tag.split(":").slice(1).join(":")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
