"""Duplicate paper detection: DOI, title similarity, and OpenAlex ID matching."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from ._pybtex_utils import parse_bibtex_file, require_pybtex
from .config import BiblioConfig


def _normalize_title(title: str) -> str:
    """Lowercase, strip accents, remove punctuation, collapse whitespace."""
    title = title.strip().lower()
    # Strip accents
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))
    # Remove punctuation
    title = re.sub(r"[^\w\s]", "", title)
    # Collapse whitespace
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _title_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two normalized titles (0.0–1.0)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Use SequenceMatcher for similarity
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    # Strip URL prefixes
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/"):
        if d.startswith(prefix):
            d = d[len(prefix):]
            break
    return d or None


def _load_openalex_records(cfg: BiblioConfig) -> dict[str, str]:
    """Load citekey -> openalex_id mapping from the resolve output."""
    path = cfg.openalex.out_jsonl
    mapping: dict[str, str] = {}
    if not path.exists():
        return mapping
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ck = rec.get("citekey")
            oa_id = rec.get("openalex_id")
            if ck and oa_id:
                mapping[str(ck)] = str(oa_id)
    return mapping


def _count_derivatives(repo_root: Path, citekey: str) -> int:
    """Count derivative artifacts for a citekey (docling outputs, notes, etc.)."""
    count = 0
    docling_dir = repo_root / "bib" / "derivatives" / "docling" / citekey
    if docling_dir.exists():
        count += sum(1 for _ in docling_dir.iterdir())
    notes_path = repo_root / "bib" / "notes" / f"{citekey}.md"
    if notes_path.exists():
        count += 1
    grobid_dir = repo_root / "bib" / "derivatives" / "grobid" / citekey
    if grobid_dir.exists():
        count += sum(1 for _ in grobid_dir.iterdir())
    return count


def find_duplicates(
    repo_root: str | Path,
    *,
    cfg: BiblioConfig | None = None,
    title_threshold: float = 0.90,
) -> list[dict[str, Any]]:
    """Scan all BibTeX entries and return groups of likely duplicates.

    Detection methods:
    - Exact DOI match (different citekeys, same DOI)
    - Normalized title similarity (>= *title_threshold*)
    - Same OpenAlex ID

    Each returned group::

        {
            "citekeys": [...],
            "reason": "doi" | "title" | "openalex",
            "confidence": float,
            "suggested_keep": str,
            "detail": str,
        }
    """
    require_pybtex("duplicate detection")
    repo_root = Path(repo_root).expanduser().resolve()

    main_bib = repo_root / "bib" / "main.bib"
    if not main_bib.exists():
        return []

    db = parse_bibtex_file(main_bib)

    # Build per-entry metadata
    entries: dict[str, dict[str, Any]] = {}
    for key, entry in db.entries.items():
        doi = _normalize_doi(entry.fields.get("doi"))
        raw_title = entry.fields.get("title", "")
        norm_title = _normalize_title(raw_title)
        entries[key] = {
            "doi": doi,
            "raw_title": raw_title,
            "norm_title": norm_title,
        }

    # Load OpenAlex IDs if available
    if cfg is not None:
        oa_map = _load_openalex_records(cfg)
        for key in entries:
            entries[key]["openalex_id"] = oa_map.get(key)
    else:
        for key in entries:
            entries[key]["openalex_id"] = None

    # Track which pairs we've already grouped
    grouped_pairs: set[tuple[str, str]] = set()
    raw_groups: list[dict[str, Any]] = []

    keys = sorted(entries.keys())

    # 1. DOI duplicates
    doi_to_keys: dict[str, list[str]] = {}
    for key in keys:
        doi = entries[key]["doi"]
        if doi:
            doi_to_keys.setdefault(doi, []).append(key)
    for doi, dup_keys in doi_to_keys.items():
        if len(dup_keys) > 1:
            pair = (dup_keys[0], dup_keys[-1])
            grouped_pairs.add(pair)
            raw_groups.append({
                "citekeys": list(dup_keys),
                "reason": "doi",
                "confidence": 1.0,
                "detail": f"DOI: {doi}",
            })

    # 2. OpenAlex ID duplicates
    oa_to_keys: dict[str, list[str]] = {}
    for key in keys:
        oa_id = entries[key].get("openalex_id")
        if oa_id:
            oa_to_keys.setdefault(oa_id, []).append(key)
    for oa_id, dup_keys in oa_to_keys.items():
        if len(dup_keys) > 1:
            pair = (dup_keys[0], dup_keys[-1])
            if pair not in grouped_pairs:
                grouped_pairs.add(pair)
                raw_groups.append({
                    "citekeys": list(dup_keys),
                    "reason": "openalex",
                    "confidence": 1.0,
                    "detail": f"OpenAlex: {oa_id}",
                })

    # 3. Title similarity
    for i, k1 in enumerate(keys):
        t1 = entries[k1]["norm_title"]
        if not t1:
            continue
        for k2 in keys[i + 1:]:
            t2 = entries[k2]["norm_title"]
            if not t2:
                continue
            pair = (k1, k2)
            if pair in grouped_pairs:
                continue
            sim = _title_similarity(t1, t2)
            if sim >= title_threshold:
                grouped_pairs.add(pair)
                raw_groups.append({
                    "citekeys": [k1, k2],
                    "reason": "title",
                    "confidence": round(sim, 3),
                    "detail": f"Title similarity: {sim:.1%}",
                })

    # Pick suggested_keep for each group
    from .library import load_library

    if cfg is not None:
        library = load_library(cfg)
    else:
        library = {}

    groups: list[dict[str, Any]] = []
    for g in raw_groups:
        cks = g["citekeys"]
        # Score each citekey: derivatives + library metadata richness
        scores: dict[str, int] = {}
        for ck in cks:
            score = _count_derivatives(repo_root, ck)
            lib_entry = library.get(ck, {})
            if lib_entry.get("tags"):
                score += len(lib_entry["tags"])
            if lib_entry.get("status"):
                score += 1
            if lib_entry.get("notes"):
                score += 1
            scores[ck] = score
        suggested = max(cks, key=lambda ck: scores[ck])
        groups.append({
            "citekeys": cks,
            "reason": g["reason"],
            "confidence": g["confidence"],
            "suggested_keep": suggested,
            "detail": g["detail"],
        })

    return groups
