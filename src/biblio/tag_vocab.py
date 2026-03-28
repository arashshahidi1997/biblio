"""Controlled tag vocabulary: load, validate, normalize, and suggest corrections."""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig


def default_tag_vocab_path(repo_root: Path) -> Path:
    return (repo_root / "bib" / "config" / "tag_vocab.yml").resolve()


def load_tag_vocab(path: Path) -> dict[str, Any]:
    """Load the tag vocabulary YAML. Returns raw dict with 'namespaces' and 'aliases'."""
    if not path.exists():
        return {"namespaces": {}, "aliases": {}}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {"namespaces": {}, "aliases": {}}
    return payload


def load_tag_vocab_from_config(cfg: BiblioConfig) -> dict[str, Any]:
    return load_tag_vocab(default_tag_vocab_path(cfg.repo_root))


def known_tags(vocab: dict[str, Any]) -> set[str]:
    """Return the full set of namespace:value tags defined in the vocabulary."""
    tags: set[str] = set()
    for ns, ns_data in (vocab.get("namespaces") or {}).items():
        if not isinstance(ns_data, dict):
            continue
        for val in ns_data.get("values") or []:
            tags.add(f"{ns}:{val}")
    return tags


def normalize_tag(tag: str) -> str:
    """Lowercase, strip whitespace, collapse internal whitespace to hyphens."""
    return tag.strip().lower().replace(" ", "-")


def is_namespaced(tag: str) -> bool:
    """Return True if tag has a namespace prefix (contains ':')."""
    return ":" in tag


def validate_tag(tag: str, vocab: dict[str, Any]) -> dict[str, Any]:
    """Validate a single tag against the vocabulary.

    Returns {"tag": str, "valid": bool, "namespace": str|None,
             "suggestion": str|None}.
    """
    normed = normalize_tag(tag)
    kt = known_tags(vocab)

    if normed in kt:
        ns = normed.split(":", 1)[0]
        return {"tag": normed, "valid": True, "namespace": ns, "suggestion": None}

    if is_namespaced(normed):
        ns, val = normed.split(":", 1)
        ns_data = (vocab.get("namespaces") or {}).get(ns)
        if isinstance(ns_data, dict):
            values = [str(v) for v in (ns_data.get("values") or [])]
            close = difflib.get_close_matches(val, values, n=1, cutoff=0.6)
            suggestion = f"{ns}:{close[0]}" if close else None
            return {"tag": normed, "valid": False, "namespace": ns, "suggestion": suggestion}
        # Unknown namespace — try all values
        suggestion = _suggest_from_all(normed, kt)
        return {"tag": normed, "valid": False, "namespace": None, "suggestion": suggestion}

    # Unnamespaced — check if it closely matches any known value
    suggestion = _suggest_from_all(normed, kt)
    return {"tag": normed, "valid": False, "namespace": None, "suggestion": suggestion}


def _suggest_from_all(tag: str, known: set[str]) -> str | None:
    """Find the closest match among all known tags."""
    matches = difflib.get_close_matches(tag, sorted(known), n=1, cutoff=0.5)
    return matches[0] if matches else None


def map_keyword_to_tag(keyword: str, vocab: dict[str, Any]) -> str:
    """Map a BibTeX keyword string to a vocabulary tag.

    Checks aliases first, then tries to match against known namespace values.
    Returns the mapped tag or the normalized keyword as an unnamespaced tag.
    """
    normed = normalize_tag(keyword)
    # Strip hyphens for alias lookup (aliases use spaces, normed uses hyphens)
    alias_key = normed.replace("-", " ")

    aliases = vocab.get("aliases") or {}
    # Case-insensitive alias lookup
    alias_lookup = {k.lower().strip(): v for k, v in aliases.items()}
    if alias_key in alias_lookup:
        return alias_lookup[alias_key]

    # Check if normed directly matches a known tag
    kt = known_tags(vocab)
    if normed in kt:
        return normed

    # Check if it matches a value in any namespace
    for ns, ns_data in (vocab.get("namespaces") or {}).items():
        if not isinstance(ns_data, dict):
            continue
        values = [str(v).lower() for v in (ns_data.get("values") or [])]
        if normed in values:
            return f"{ns}:{normed}"

    # Return as unnamespaced tag
    return normed


def extract_bibtex_keywords(entry_fields: dict[str, str]) -> list[str]:
    """Extract and split the 'keywords' field from a BibTeX entry's fields dict.

    Handles comma-separated and semicolon-separated keywords.
    """
    raw = entry_fields.get("keywords") or entry_fields.get("keyword") or ""
    if not raw:
        return []
    # Split on comma or semicolon
    parts = []
    for sep in (";", ","):
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep) if p.strip()]
            break
    if not parts:
        parts = [raw.strip()] if raw.strip() else []
    return parts


def keywords_to_tags(keywords: list[str], vocab: dict[str, Any]) -> list[str]:
    """Convert a list of BibTeX keywords to normalized, deduplicated tags."""
    seen: set[str] = set()
    tags: list[str] = []
    for kw in keywords:
        tag = map_keyword_to_tag(kw, vocab)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def lint_library_tags(
    library: dict[str, dict[str, Any]], vocab: dict[str, Any]
) -> dict[str, Any]:
    """Scan all library tags and report issues.

    Returns {"non_vocab": [...], "duplicates": [...], "suggestions": [...]}.
    """
    kt = known_tags(vocab)
    non_vocab: list[dict[str, str]] = []
    duplicates: list[dict[str, Any]] = []
    suggestions: list[dict[str, str]] = []

    # Track normalized forms across all citekeys for duplicate detection
    global_normed: dict[str, list[str]] = {}  # normed -> [original forms]

    for ck, entry in sorted(library.items()):
        tags = entry.get("tags") or []
        if not isinstance(tags, list):
            continue

        local_normed: dict[str, list[str]] = {}
        for tag in tags:
            n = normalize_tag(tag)
            local_normed.setdefault(n, []).append(tag)
            global_normed.setdefault(n, []).append(tag)

            if is_namespaced(n) and n not in kt:
                result = validate_tag(n, vocab)
                entry_info = {"citekey": ck, "tag": tag}
                if result.get("suggestion"):
                    entry_info["suggestion"] = result["suggestion"]
                    suggestions.append(entry_info)
                non_vocab.append(entry_info)

        # Check for local duplicates (same citekey, different casing)
        for normed, forms in local_normed.items():
            if len(forms) > 1:
                duplicates.append({"citekey": ck, "normalized": normed, "forms": forms})

    # Check for global inconsistencies (same concept, different forms across papers)
    for normed, forms in global_normed.items():
        unique_forms = set(forms)
        if len(unique_forms) > 1:
            duplicates.append(
                {"citekey": "(global)", "normalized": normed, "forms": sorted(unique_forms)}
            )

    return {
        "non_vocab": non_vocab,
        "duplicates": duplicates,
        "suggestions": suggestions,
    }
