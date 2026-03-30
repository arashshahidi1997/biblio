"""Reading list curation based on research questions.

Scores unread/queued papers by relevance to a given question using
summaries, concepts, and metadata, then returns a ranked list with
per-paper justifications.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import default_config_path, load_biblio_config

SYSTEM_PROMPT = """\
You are a research reading list curator. Given a research question and a list of \
candidate papers (with metadata, abstracts, and summaries), select and rank the \
top papers most relevant to the question.

For each selected paper, provide:
1. The citekey
2. A relevance score (0.0-1.0)
3. A one-sentence justification

Return a JSON array of objects, each with keys: "citekey", "score", "justification".
Order by score descending. Select up to {count} papers.

Example:
[{{"citekey": "smith_2024_Example", "score": 0.95, "justification": "Directly addresses the question with novel methodology."}}]

Respond ONLY with the JSON array, no other text.\
"""

DEFAULT_MODEL = "haiku"


def _gather_candidates(root: Path) -> list[dict[str, Any]]:
    """Gather unread/queued papers with their metadata, summaries, and concepts."""
    cfg = load_biblio_config(default_config_path(root=root), root=root)

    from .library import load_library

    library = load_library(cfg)

    # Include papers that are unread, reading, or have no status
    candidates: list[dict[str, Any]] = []
    for ck, entry in library.items():
        status = entry.get("status", "unread")
        if status in ("unread", "reading", ""):
            candidates.append({"citekey": ck, "library": entry})

    # Also include papers in library with no status set
    # Enrich with bib metadata
    from .mcp import _load_bib_database, _load_cfg, _bib_entry_to_dict

    bib_cfg = _load_cfg(root)
    bib_db = _load_bib_database(bib_cfg)

    for cand in candidates:
        ck = cand["citekey"]
        if bib_db and ck in bib_db.entries:
            bib_data = _bib_entry_to_dict(bib_db.entries[ck])
            cand["title"] = bib_data.get("title", "")
            cand["abstract"] = bib_data.get("abstract", "")
            cand["authors"] = bib_data.get("authors", [])
            cand["year"] = bib_data.get("year", "")

        # Summary
        from .summarize import summary_path_for_key

        summary_path = summary_path_for_key(bib_cfg, ck)
        if summary_path.exists():
            text = summary_path.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            cand["summary"] = text[:800]

        # Concepts
        from .concepts import load_concepts

        concepts = load_concepts(bib_cfg, ck)
        if concepts:
            cand["concepts"] = concepts

    return candidates


def _format_candidates(candidates: list[dict[str, Any]]) -> str:
    """Format candidates into a prompt-friendly string."""
    parts: list[str] = []
    for cand in candidates:
        lines = [f"## {cand['citekey']}"]
        if cand.get("title"):
            lines.append(f"**Title:** {cand['title']}")
        if cand.get("authors"):
            lines.append(f"**Authors:** {', '.join(cand['authors'][:5])}")
        if cand.get("year"):
            lines.append(f"**Year:** {cand['year']}")
        if cand.get("abstract"):
            lines.append(f"**Abstract:** {cand['abstract'][:500]}")
        tags = (cand.get("library") or {}).get("tags", [])
        if tags:
            lines.append(f"**Tags:** {', '.join(tags)}")
        if cand.get("summary"):
            lines.append(f"**Summary:** {cand['summary']}")
        if cand.get("concepts"):
            concepts = cand["concepts"]
            flat = []
            for cat, items in concepts.items():
                if items:
                    flat.extend(items)
            if flat:
                lines.append(f"**Concepts:** {', '.join(flat)}")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def reading_list(
    question: str,
    root: Path,
    *,
    count: int = 5,
    prompt_only: bool = False,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Curate a reading list based on a research question.

    Returns dict with keys: question, candidates_count, recommendations, prompt.
    """
    candidates = _gather_candidates(root)

    if not candidates:
        return {
            "question": question,
            "candidates_count": 0,
            "recommendations": [],
            "hint": "No unread/reading papers found in the library.",
        }

    candidates_text = _format_candidates(candidates)
    system = SYSTEM_PROMPT.format(count=count)
    prompt_text = f"Research question: {question}\n\n# Candidate Papers\n\n{candidates_text}"

    if prompt_only:
        return {
            "question": question,
            "candidates_count": len(candidates),
            "prompt": prompt_text,
            "system_prompt": system,
            "recommendations": None,
        }

    # Call LLM
    from .llm import call_llm
    import json

    result = call_llm(system=system, prompt=prompt_text, model=model, max_tokens=2000)
    if result["error"]:
        return {
            "question": question,
            "candidates_count": len(candidates),
            "prompt": prompt_text,
            "recommendations": None,
            "error": result["error"],
        }
    raw_text = result["text"].strip()
    try:
        recommendations = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "question": question,
            "candidates_count": len(candidates),
            "prompt": prompt_text,
            "recommendations": None,
            "error": f"LLM returned invalid JSON: {raw_text[:200]}",
        }

    if not isinstance(recommendations, list):
        recommendations = []

    return {
        "question": question,
        "candidates_count": len(candidates),
        "recommendations": recommendations[:count],
        "model_used": model,
    }
