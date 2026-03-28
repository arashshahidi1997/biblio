"""Literature review workflow.

Provides query-driven review synthesis and review planning for
seed-expand-synthesize workflows.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import default_config_path, load_biblio_config
from .rag import default_rag_config_path

REVIEW_SYSTEM_PROMPT = """\
You are a research literature review assistant. Given a research question and \
a set of relevant passages from academic papers (with citekeys), synthesize a \
concise literature review section.

Requirements:
- Organize the synthesis thematically, not paper-by-paper
- Use {cite_fmt} citation format
- Only cite papers whose passages are provided — do not fabricate references
- Identify areas of consensus and disagreement
- Note methodological trends
- Conclude with identified gaps in the literature

Write in formal academic style.\
"""

PLAN_SYSTEM_PROMPT = """\
You are a research planning assistant. Given a set of seed papers and a research \
question, analyze the coverage and produce a structured review plan.

Return a JSON object with these keys:
- "scope": one-sentence description of the review scope
- "themes": list of 3-7 thematic categories the review should cover
- "coverage": object mapping each theme to list of citekeys that address it
- "gaps": list of identified gaps (themes with few or no papers)
- "expansion_directions": list of suggested search directions to fill gaps \
  (each with "direction" and "rationale" keys)
- "estimated_additional_papers": integer estimate of papers needed to fill gaps

Respond ONLY with the JSON object, no other text.\
"""

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _query_rag_multi(root: Path, queries: list[str], k: int = 4) -> list[dict[str, Any]]:
    """Query the RAG index with multiple queries, deduplicating by citekey."""
    rag_cfg_path = default_rag_config_path(root)
    if not rag_cfg_path.exists():
        return []

    try:
        from indexio.query import query_index_multi
    except ImportError:
        return []

    try:
        data = query_index_multi(
            config_path=rag_cfg_path,
            root=root,
            queries=queries,
            k=k,
            corpus="bib",
        )
    except FileNotFoundError:
        return []

    # Deduplicate by citekey
    from .cite_draft import _extract_citekey_from_source

    seen_keys: set[str] = set()
    passages: list[dict[str, Any]] = []
    for item in data.get("results") or []:
        source_path = item.get("source_path") or ""
        citekey = _extract_citekey_from_source(source_path)
        if not citekey or citekey in seen_keys:
            continue
        seen_keys.add(citekey)
        passages.append({
            "citekey": citekey,
            "snippet": item.get("snippet", ""),
            "source_path": source_path,
        })

    return passages


def _format_passages(passages: list[dict[str, Any]]) -> str:
    """Format retrieved passages for the LLM prompt."""
    parts: list[str] = []
    for p in passages:
        parts.append(f"## @{p['citekey']}\n{p['snippet']}")
    return "\n\n---\n\n".join(parts)


def _cite_format_hint(style: str) -> str:
    if style == "pandoc":
        return "[@citekey]"
    return "\\cite{citekey}"


def assemble_review_prompt(
    question: str,
    passages: list[dict[str, Any]],
    style: str = "latex",
) -> str:
    """Build the user prompt for literature review synthesis."""
    passages_text = _format_passages(passages)
    citekeys = [p["citekey"] for p in passages]
    cite_fmt = _cite_format_hint(style)
    return (
        f"Research question: {question}\n\n"
        f"Citation format: {cite_fmt}\n"
        f"Available citekeys: {', '.join(citekeys)}\n\n"
        f"# Retrieved Passages\n\n{passages_text}"
    )


def review_query(
    question: str,
    root: Path,
    *,
    style: str = "latex",
    prompt_only: bool = False,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Query-driven literature review — find relevant passages and synthesize.

    Returns dict with keys: question, passages, prompt, system_prompt,
    synthesis, model_used, error.
    """
    # Generate sub-queries from the question for broader coverage
    queries = [question]
    # Add the question as-is plus a methodological variant
    if len(question.split()) > 3:
        queries.append(f"methods approaches {question}")
        queries.append(f"limitations challenges {question}")

    passages = _query_rag_multi(root, queries, k=6)

    if not passages:
        return {
            "question": question,
            "passages": [],
            "prompt": None,
            "synthesis": None,
            "model_used": None,
            "error": "No relevant passages found in the RAG index. Build the index first.",
        }

    cite_fmt = _cite_format_hint(style)
    system = REVIEW_SYSTEM_PROMPT.format(cite_fmt=cite_fmt)
    prompt_text = assemble_review_prompt(question, passages, style=style)

    if prompt_only:
        return {
            "question": question,
            "passages": passages,
            "prompt": prompt_text,
            "system_prompt": system,
            "synthesis": None,
            "model_used": None,
        }

    # Call LLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "question": question,
            "passages": passages,
            "prompt": prompt_text,
            "synthesis": None,
            "model_used": None,
            "error": "ANTHROPIC_API_KEY not set",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "question": question,
            "passages": passages,
            "prompt": prompt_text,
            "synthesis": None,
            "model_used": None,
            "error": "anthropic package not installed",
        }

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": prompt_text}],
    )
    synthesis_text = message.content[0].text

    return {
        "question": question,
        "passages": passages,
        "prompt": prompt_text,
        "synthesis": synthesis_text,
        "model_used": model,
    }


def _gather_seed_context(
    seed_citekeys: list[str],
    root: Path,
) -> list[dict[str, Any]]:
    """Gather metadata and summaries for seed papers."""
    from .mcp import paper_context

    seeds: list[dict[str, Any]] = []
    for ck in seed_citekeys:
        ctx = paper_context(ck, root=root)
        bib = ctx.get("bib") or {}
        entry: dict[str, Any] = {
            "citekey": ctx["citekey"],
            "title": bib.get("title", ""),
            "authors": bib.get("authors", []),
            "year": bib.get("year", ""),
        }
        # Include summary if available
        cfg = load_biblio_config(default_config_path(root=root), root=root)
        from .summarize import summary_path_for_key

        summary_path = summary_path_for_key(cfg, ctx["citekey"])
        if summary_path.exists():
            text = summary_path.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].strip()
            entry["summary"] = text[:600]

        # Include tags
        lib = ctx.get("library") or {}
        if lib.get("tags"):
            entry["tags"] = lib["tags"]

        seeds.append(entry)

    return seeds


def _format_seeds(seeds: list[dict[str, Any]]) -> str:
    """Format seed papers for the planning prompt."""
    parts: list[str] = []
    for s in seeds:
        lines = [f"## @{s['citekey']}"]
        if s.get("title"):
            lines.append(f"**Title:** {s['title']}")
        if s.get("authors"):
            lines.append(f"**Authors:** {', '.join(s['authors'][:5])}")
        if s.get("year"):
            lines.append(f"**Year:** {s['year']}")
        if s.get("tags"):
            lines.append(f"**Tags:** {', '.join(s['tags'])}")
        if s.get("summary"):
            lines.append(f"**Summary:** {s['summary']}")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def assemble_plan_prompt(
    question: str,
    seeds: list[dict[str, Any]],
) -> str:
    """Build the user prompt for review planning."""
    seeds_text = _format_seeds(seeds)
    citekeys = [s["citekey"] for s in seeds]
    return (
        f"Research question: {question}\n\n"
        f"Seed papers ({len(seeds)}): {', '.join(citekeys)}\n\n"
        f"# Seed Paper Details\n\n{seeds_text}"
    )


def review_plan(
    seed_citekeys: list[str],
    question: str,
    root: Path,
    *,
    prompt_only: bool = False,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Generate a review plan: identify gaps, suggest expansion directions.

    Returns dict with keys: question, seeds, prompt, system_prompt, plan,
    model_used, error.
    """
    seeds = _gather_seed_context(seed_citekeys, root)

    if not seeds:
        return {
            "question": question,
            "seeds": [],
            "prompt": None,
            "plan": None,
            "model_used": None,
            "error": "No seed papers found for the given citekeys.",
        }

    system = PLAN_SYSTEM_PROMPT
    prompt_text = assemble_plan_prompt(question, seeds)

    if prompt_only:
        return {
            "question": question,
            "seeds": seeds,
            "prompt": prompt_text,
            "system_prompt": system,
            "plan": None,
            "model_used": None,
        }

    # Call LLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "question": question,
            "seeds": seeds,
            "prompt": prompt_text,
            "plan": None,
            "model_used": None,
            "error": "ANTHROPIC_API_KEY not set",
        }

    try:
        import anthropic
    except ImportError:
        return {
            "question": question,
            "seeds": seeds,
            "prompt": prompt_text,
            "plan": None,
            "model_used": None,
            "error": "anthropic package not installed",
        }

    import json

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw_text = message.content[0].text.strip()
    try:
        plan = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "question": question,
            "seeds": seeds,
            "prompt": prompt_text,
            "plan": None,
            "model_used": model,
            "error": f"LLM returned invalid JSON: {raw_text[:200]}",
        }

    return {
        "question": question,
        "seeds": seeds,
        "prompt": prompt_text,
        "plan": plan,
        "model_used": model,
    }
