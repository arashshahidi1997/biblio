"""Map OpenAlex topic hierarchy to biblio tag vocabulary.

Generates tags like ``domain:neuroscience``, ``field:behavioral-neuroscience``,
``topic:sharp-wave-ripples`` from OpenAlex enrichment data.  Tags are derived
deterministically from the topic hierarchy — no API or LLM calls needed.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _slugify(name: str) -> str:
    """Convert a display name to a tag-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s).strip("-")
    return s


def tags_from_enrichment(enrichment: dict[str, Any]) -> list[str]:
    """Derive biblio-style tags from per-citekey OpenAlex enrichment data.

    Generates hierarchical tags from the primary topic and all topics:
    - ``oa:domain:<slug>``
    - ``oa:field:<slug>``
    - ``oa:subfield:<slug>``
    - ``oa:topic:<slug>``
    - ``oa:keyword:<slug>``

    Tags use the ``oa:`` prefix to distinguish from human-assigned or
    LLM-generated tags.

    Returns a deduplicated, sorted list of tags.
    """
    seen: set[str] = set()
    tags: list[str] = []

    def _add(tag: str) -> None:
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)

    # Extract from primary_topic and all topics
    all_topics = list(enrichment.get("topics") or [])
    pt = enrichment.get("primary_topic")
    if pt and isinstance(pt, dict):
        all_topics.insert(0, pt)

    for topic in all_topics:
        if not isinstance(topic, dict):
            continue
        domain = topic.get("domain") or ""
        field = topic.get("field") or ""
        subfield = topic.get("subfield") or ""
        name = topic.get("name") or ""

        if domain:
            _add(f"oa:domain:{_slugify(domain)}")
        if field:
            _add(f"oa:field:{_slugify(field)}")
        if subfield:
            _add(f"oa:subfield:{_slugify(subfield)}")
        if name:
            _add(f"oa:topic:{_slugify(name)}")

    # Keywords
    for kw in enrichment.get("keywords") or []:
        if isinstance(kw, dict):
            word = kw.get("keyword") or ""
            if word:
                _add(f"oa:keyword:{_slugify(word)}")

    return sorted(tags)


def apply_topic_tags(
    enrichment: dict[str, Any],
    library_tags: list[str] | None = None,
) -> list[str]:
    """Generate OpenAlex-derived tags, merging with existing library tags.

    Only adds new tags — never removes existing ones (union merge).

    Args:
        enrichment: Per-citekey enrichment dict (from ``load_enrichment``).
        library_tags: Existing tags from library.yml for this citekey.

    Returns:
        Merged tag list (existing + new OpenAlex-derived tags).
    """
    existing = set(library_tags or [])
    new_tags = tags_from_enrichment(enrichment)
    merged = list(library_tags or [])
    for tag in new_tags:
        if tag not in existing:
            merged.append(tag)
    return merged


def populate_library_tags(
    root: Path,
    *,
    citekeys: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Auto-populate library.yml tags from OpenAlex enrichment data.

    Args:
        root: Project root.
        citekeys: If given, only process these citekeys.
        dry_run: Report changes without writing.

    Returns:
        ``{"updated": N, "unchanged": N, "missing": N, "changes": [...]}``
    """
    from ..config import default_config_path, load_biblio_config
    from ..library import get_entry, load_library, update_entry
    from .openalex_enrich import load_enrichment

    cfg = load_biblio_config(default_config_path(root=root), root=root)
    library = load_library(cfg)

    keys = citekeys if citekeys else sorted(library.keys())
    updated = 0
    unchanged = 0
    missing = 0
    changes: list[dict[str, Any]] = []

    for ck in keys:
        enrichment = load_enrichment(root, ck)
        if enrichment is None:
            missing += 1
            continue

        entry = get_entry(cfg, ck) or {}
        existing_tags = entry.get("tags") or []
        merged = apply_topic_tags(enrichment, existing_tags)

        new_tags = [t for t in merged if t not in set(existing_tags)]
        if not new_tags:
            unchanged += 1
            continue

        changes.append({"citekey": ck, "added_tags": new_tags})
        if not dry_run:
            update_entry(cfg, ck, tags=merged)
        updated += 1

    return {
        "updated": updated,
        "unchanged": unchanged,
        "missing_enrichment": missing,
        "changes": changes[:50],
        "dry_run": dry_run,
    }
