"""Per-citekey pipeline completeness matrix."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import BiblioConfig

# Pipeline stages in order — used for next_action recommendation.
_STAGES = ("bib", "resolved", "pdf", "docling", "grobid", "enriched", "rag")

# Map stage → recommended MCP tool to advance it.
_STAGE_TOOLS = {
    "bib": "biblio_ingest",
    "resolved": "biblio_openalex_resolve",
    "pdf": "biblio_pdf_fetch_oa",
    "docling": "biblio_docling_batch",
    "grobid": "biblio_grobid",
    "enriched": "biblio_enrich",
    "rag": "biblio_rag_sync",
}


def _load_resolved_citekeys(resolved_path: Path) -> set[str]:
    """Load citekeys present in resolved.jsonl."""
    keys: set[str] = set()
    if not resolved_path.exists():
        return keys
    with resolved_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ck = str(rec.get("citekey") or "").strip()
            status = str(rec.get("resolution_status") or rec.get("status") or "")
            if ck and status != "error":
                keys.add(ck)
    return keys


def pipeline_status(
    cfg: BiblioConfig,
    *,
    citekeys: list[str] | None = None,
) -> dict[str, Any]:
    """Check derivative existence for each citekey.

    Returns a matrix with per-citekey stage booleans, summary counts,
    and recommended batch actions.
    """
    from .citekeys import load_active_citekeys

    all_keys = citekeys or load_active_citekeys(cfg)
    if not all_keys:
        return {"entries": [], "summary": {"total": 0}, "recommended_actions": []}

    root = cfg.repo_root

    # Pre-load resolved set (one pass)
    resolved_path = root / "bib" / "derivatives" / "openalex" / "resolved.jsonl"
    resolved_keys = _load_resolved_citekeys(resolved_path)

    entries: list[dict[str, Any]] = []
    by_stage: dict[str, int] = {s: 0 for s in _STAGES}
    complete_count = 0

    for ck in all_keys:
        row: dict[str, Any] = {"citekey": ck}

        # bib: always true if citekey comes from load_active_citekeys
        row["bib"] = True

        # resolved
        row["resolved"] = ck in resolved_keys

        # pdf
        pdf_path = root / "bib" / "articles" / ck / f"{ck}.pdf"
        row["pdf"] = pdf_path.exists()

        # docling
        docling_md = root / "bib" / "derivatives" / "docling" / ck / f"{ck}.md"
        row["docling"] = docling_md.exists()

        # grobid
        grobid_header = root / "bib" / "derivatives" / "grobid" / ck / "header.json"
        row["grobid"] = grobid_header.exists()

        # enriched
        enriched_yml = root / "bib" / "derivatives" / "openalex" / f"{ck}.yml"
        row["enriched"] = enriched_yml.exists()

        # rag (proxy: docling markdown exists → indexable)
        row["rag"] = row["docling"]

        # Compute completeness
        all_done = all(row[s] for s in _STAGES)
        row["complete"] = all_done
        if all_done:
            complete_count += 1

        # Next action: first missing stage in pipeline order
        row["next_action"] = None
        for stage in _STAGES:
            if not row[stage]:
                row["next_action"] = _STAGE_TOOLS[stage]
                break

        for stage in _STAGES:
            if row[stage]:
                by_stage[stage] += 1

        entries.append(row)

    total = len(all_keys)

    # Recommended batch actions: stages with missing coverage
    recommended: list[dict[str, str]] = []
    for stage in _STAGES:
        missing = total - by_stage[stage]
        if missing > 0:
            recommended.append({
                "action": _STAGE_TOOLS[stage],
                "reason": f"{missing} papers missing {stage}",
            })

    return {
        "entries": entries,
        "summary": {
            "total": total,
            "complete": complete_count,
            "by_stage": by_stage,
        },
        "recommended_actions": recommended,
    }
