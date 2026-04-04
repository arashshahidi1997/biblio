"""Persist OpenAlex topic/keyword/type/retraction enrichments per citekey.

Reads ``resolved.jsonl`` and writes per-citekey YAML files to
``bib/derivatives/openalex/{citekey}.yml``.  Also builds a cross-paper
topic index at ``bib/derivatives/openalex/_topic_index.yml``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

OPENALEX_DERIVATIVES_REL = Path("bib/derivatives/openalex")
RESOLVED_JSONL_REL = Path("bib/derivatives/openalex/resolved.jsonl")


def _derivatives_dir(root: Path) -> Path:
    return (root / OPENALEX_DERIVATIVES_REL).resolve()


def _resolved_jsonl(root: Path) -> Path:
    return (root / RESOLVED_JSONL_REL).resolve()


def _extract_topic(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single OpenAlex topic dict."""
    return {
        "id": raw.get("id") or "",
        "name": raw.get("display_name") or "",
        "score": float(raw.get("score") or 0),
        "subfield": (raw.get("subfield") or {}).get("display_name") or "",
        "field": (raw.get("field") or {}).get("display_name") or "",
        "domain": (raw.get("domain") or {}).get("display_name") or "",
    }


def _extract_primary_topic(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw or not isinstance(raw, dict):
        return None
    return {
        "id": raw.get("id") or "",
        "name": raw.get("display_name") or "",
        "score": float(raw.get("score") or 0),
        "subfield": (raw.get("subfield") or {}).get("display_name") or "",
        "field": (raw.get("field") or {}).get("display_name") or "",
        "domain": (raw.get("domain") or {}).get("display_name") or "",
    }


def _extract_keyword(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": raw.get("keyword") or raw.get("display_name") or "",
        "score": float(raw.get("score") or 0),
    }


def _extract_counts_by_year(raw: list[dict[str, Any]] | None) -> dict[int, int] | None:
    """Convert OpenAlex counts_by_year list to {year: cited_by_count} dict."""
    if not raw or not isinstance(raw, list):
        return None
    result: dict[int, int] = {}
    for entry in raw:
        if isinstance(entry, dict):
            try:
                year = int(entry["year"])
                count = int(entry.get("cited_by_count", 0))
                result[year] = count
            except (KeyError, ValueError, TypeError):
                continue
    return result if result else None


def enrich_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Extract enrichment data from a single resolved.jsonl record.

    Returns a dict suitable for writing as per-citekey YAML, or None if
    the record is unresolved.
    """
    citekey = record.get("citekey")
    if not citekey:
        return None
    if record.get("resolution_method") == "unresolved":
        return None

    topics_raw = record.get("topics")
    topics = [_extract_topic(t) for t in (topics_raw or []) if isinstance(t, dict)]

    primary_topic = _extract_primary_topic(record.get("primary_topic"))

    keywords_raw = record.get("keywords")
    keywords = [_extract_keyword(k) for k in (keywords_raw or []) if isinstance(k, dict)]

    counts_by_year = _extract_counts_by_year(record.get("counts_by_year"))

    enrichment: dict[str, Any] = {"citekey": citekey}

    work_type = record.get("type")
    if work_type:
        enrichment["type"] = work_type

    is_retracted = record.get("is_retracted")
    if is_retracted is not None:
        enrichment["is_retracted"] = bool(is_retracted)

    if primary_topic:
        enrichment["primary_topic"] = primary_topic

    if topics:
        enrichment["topics"] = topics

    if keywords:
        enrichment["keywords"] = keywords

    if counts_by_year:
        enrichment["counts_by_year"] = counts_by_year

    return enrichment


def enrich_resolved(
    root: Path,
    *,
    citekeys: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Read resolved.jsonl and write per-citekey enrichment YAML files.

    Args:
        root: Project root.
        citekeys: If given, only enrich these citekeys.
        force: Overwrite existing enrichment files.

    Returns:
        ``{"enriched": N, "skipped": N, "errors": [...], "output_dir": str}``
    """
    resolved_path = _resolved_jsonl(root)
    if not resolved_path.exists():
        return {
            "error": f"resolved.jsonl not found at {resolved_path}",
            "hint": "Run OpenAlex resolution first (biblio openalex resolve).",
        }

    out_dir = _derivatives_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)

    citekey_set = set(citekeys) if citekeys else None
    enriched = 0
    skipped = 0
    errors: list[str] = []
    topic_index: dict[str, list[str]] = {}

    with resolved_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_no}: JSON parse error: {e}")
                continue

            ck = record.get("citekey")
            if not ck:
                continue
            if citekey_set is not None and ck not in citekey_set:
                continue

            out_path = out_dir / f"{ck}.yml"
            if out_path.exists() and not force:
                skipped += 1
                # Still index topics from existing file
                try:
                    existing = yaml.safe_load(out_path.read_text(encoding="utf-8")) or {}
                    for t in existing.get("topics") or []:
                        tid = t.get("id", "")
                        if tid:
                            topic_index.setdefault(tid, [])
                            if ck not in topic_index[tid]:
                                topic_index[tid].append(ck)
                except Exception:
                    pass
                continue

            enrichment = enrich_record(record)
            if enrichment is None:
                skipped += 1
                continue

            try:
                out_path.write_text(
                    yaml.safe_dump(
                        enrichment,
                        sort_keys=False,
                        allow_unicode=True,
                        default_flow_style=False,
                    ),
                    encoding="utf-8",
                )
                enriched += 1
            except Exception as e:
                errors.append(f"{ck}: write error: {e}")
                continue

            # Build topic index
            for t in enrichment.get("topics") or []:
                tid = t.get("id", "")
                if tid:
                    topic_index.setdefault(tid, [])
                    if ck not in topic_index[tid]:
                        topic_index[tid].append(ck)

    # Write topic index
    if topic_index:
        idx_path = out_dir / "_topic_index.yml"
        sorted_index = {k: sorted(v) for k, v in sorted(topic_index.items())}
        idx_path.write_text(
            yaml.safe_dump(
                sorted_index,
                sort_keys=True,
                allow_unicode=True,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

    return {
        "enriched": enriched,
        "skipped": skipped,
        "errors": errors[:20] if errors else [],
        "error_count": len(errors),
        "output_dir": str(out_dir),
    }


def load_enrichment(root: Path, citekey: str) -> dict[str, Any] | None:
    """Load per-citekey enrichment YAML, or None if missing."""
    path = _derivatives_dir(root) / f"{citekey}.yml"
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or None
    except Exception:
        return None


def load_topic_index(root: Path) -> dict[str, list[str]]:
    """Load the cross-paper topic index."""
    path = _derivatives_dir(root) / "_topic_index.yml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
