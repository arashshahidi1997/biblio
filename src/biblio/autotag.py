"""LLM auto-tagging and reference-propagation pipeline.

Provides two tagging tiers:
- **llm**: Classify a paper using an LLM constrained to the tag vocabulary.
- **propagate**: Inherit tags from frequently-cited papers in the local corpus.

Results are cached under ``bib/derivatives/autotag/{citekey}.yml``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig, default_config_path, load_biblio_config

AUTOTAG_DIR_REL = Path("bib/derivatives/autotag")

DEFAULT_MODEL = "haiku"

SYSTEM_PROMPT_TEMPLATE = """\
You are a research paper classifier. Given a paper's title and abstract, assign \
3-5 tags from the controlled vocabulary below. Each tag uses the format \
namespace:value. Only use tags from this vocabulary — do not invent new ones.

Return a JSON object with a single key "tags", whose value is a list of objects \
each with "tag" (string) and "confidence" (float 0-1). Order by confidence \
descending. Example:

{{"tags": [{{"tag": "domain:nlp", "confidence": 0.95}}, {{"tag": "method:transformer", "confidence": 0.8}}]}}

## Tag Vocabulary
{vocab_block}

Respond ONLY with the JSON object, no other text.\
"""


def _autotag_dir(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / AUTOTAG_DIR_REL).resolve()


def _cache_path(cfg: BiblioConfig, citekey: str) -> Path:
    return _autotag_dir(cfg) / f"{citekey}.yml"


def load_cache(cfg: BiblioConfig, citekey: str) -> dict[str, Any] | None:
    """Load cached autotag result, or None if not cached."""
    path = _cache_path(cfg, citekey)
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or None


def save_cache(cfg: BiblioConfig, citekey: str, data: dict[str, Any]) -> Path:
    """Write autotag cache for a citekey."""
    path = _cache_path(cfg, citekey)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=True, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def _format_vocab_block(vocab: dict[str, Any]) -> str:
    """Format the tag vocabulary as a compact text block for the LLM prompt."""
    lines: list[str] = []
    for ns, ns_data in (vocab.get("namespaces") or {}).items():
        if not isinstance(ns_data, dict):
            continue
        desc = ns_data.get("description", "")
        values = ns_data.get("values") or []
        tag_list = ", ".join(f"{ns}:{v}" for v in values)
        lines.append(f"- **{ns}** ({desc}): {tag_list}")
    return "\n".join(lines)


def _get_abstract(citekey: str, root: Path) -> tuple[str, str]:
    """Return (title, abstract) for a paper from BibTeX/GROBID data."""
    from .mcp import paper_context

    ctx = paper_context(citekey, root=root)
    bib = ctx.get("bib") or {}
    grobid = ctx.get("grobid_header") or {}

    title = bib.get("title") or grobid.get("title") or ""
    abstract = bib.get("abstract") or grobid.get("abstract") or ""
    return str(title), str(abstract)


def _format_openalex_context(enrichment: dict[str, Any] | None) -> str:
    """Format OpenAlex enrichment data as additional context for the LLM prompt."""
    if not enrichment:
        return ""
    parts: list[str] = []
    pt = enrichment.get("primary_topic")
    if pt and isinstance(pt, dict):
        parts.append(
            f"- Primary topic: {pt.get('name', '')} "
            f"(field: {pt.get('field', '')}, domain: {pt.get('domain', '')})"
        )
    keywords = enrichment.get("keywords")
    if keywords:
        kw_list = ", ".join(
            k.get("keyword", "") for k in keywords if isinstance(k, dict)
        )
        if kw_list:
            parts.append(f"- Keywords: {kw_list}")
    if not parts:
        return ""
    return "\n\n## OpenAlex Classification (use as context, not as direct tags)\n" + "\n".join(parts)


def build_llm_prompt(
    title: str, abstract: str, vocab: dict[str, Any],
    openalex_enrichment: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for the LLM classification call.

    If *openalex_enrichment* is provided, the paper's OpenAlex topic and keyword
    data is appended to the user prompt as additional context for more accurate
    classification.

    Returns (system_prompt, user_prompt).
    """
    vocab_block = _format_vocab_block(vocab)
    system = SYSTEM_PROMPT_TEMPLATE.format(vocab_block=vocab_block)
    user = f"**Title:** {title}\n\n**Abstract:** {abstract}"
    oa_ctx = _format_openalex_context(openalex_enrichment)
    if oa_ctx:
        user += oa_ctx
    return system, user


def autotag_llm(
    citekey: str,
    root: Path,
    *,
    model: str = DEFAULT_MODEL,
    force: bool = False,
) -> dict[str, Any]:
    """Classify a paper using an LLM constrained to the tag vocabulary.

    Returns {"citekey", "tags": [{"tag", "confidence"}], "model", "tier": "llm",
             "cached": bool} or {"error": ...}.
    """
    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)

    # Check cache
    if not force:
        cached = load_cache(cfg, key)
        if cached and "llm" in (cached.get("tiers") or {}):
            return {
                "citekey": key,
                "tags": cached["tiers"]["llm"].get("tags", []),
                "model": cached["tiers"]["llm"].get("model"),
                "tier": "llm",
                "cached": True,
            }

    # Get paper data
    title, abstract = _get_abstract(key, root)
    if not abstract and not title:
        return {"citekey": key, "error": "No title or abstract available", "tier": "llm"}

    # Load vocabulary
    from .tag_vocab import default_tag_vocab_path, load_tag_vocab

    vocab = load_tag_vocab(default_tag_vocab_path(root))

    # Load OpenAlex enrichment (if available) as context for the LLM
    oa_enrichment = None
    try:
        from .openalex.openalex_enrich import load_enrichment
        oa_enrichment = load_enrichment(root, key)
    except Exception:
        pass

    system_prompt, user_prompt = build_llm_prompt(title, abstract, vocab, openalex_enrichment=oa_enrichment)

    # Call LLM
    from .llm import call_llm

    result = call_llm(system=system_prompt, prompt=user_prompt, model=model, max_tokens=500)
    if result["error"]:
        return {"citekey": key, "error": result["error"], "tier": "llm"}
    raw_text = result["text"].strip()

    # Parse JSON response
    try:
        parsed = json.loads(raw_text)
        tags = parsed.get("tags", [])
    except json.JSONDecodeError:
        return {"citekey": key, "error": f"Failed to parse LLM response: {raw_text[:200]}", "tier": "llm"}

    # Validate tags against vocabulary
    from .tag_vocab import known_tags

    kt = known_tags(vocab)
    validated = [t for t in tags if t.get("tag") in kt]

    # Update cache
    cached = load_cache(cfg, key) or {"citekey": key, "tiers": {}}
    cached.setdefault("tiers", {})["llm"] = {
        "tags": validated,
        "model": model,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_cache(cfg, key, cached)

    return {
        "citekey": key,
        "tags": validated,
        "model": model,
        "tier": "llm",
        "cached": False,
    }


def autotag_propagate(
    citekey: str,
    root: Path,
    *,
    threshold: int = 3,
    force: bool = False,
) -> dict[str, Any]:
    """Propagate tags from frequently-cited papers in the local corpus.

    Reads GROBID local reference matches, checks what tags cited papers have
    in library.yml, and propagates tags appearing in >= threshold cited papers.

    Returns {"citekey", "tags": [...], "tier": "propagate", "cited_count": N,
             "cached": bool}.
    """
    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)

    # Check cache
    if not force:
        cached = load_cache(cfg, key)
        if cached and "propagate" in (cached.get("tiers") or {}):
            return {
                "citekey": key,
                "tags": cached["tiers"]["propagate"].get("tags", []),
                "tier": "propagate",
                "cited_count": cached["tiers"]["propagate"].get("cited_count", 0),
                "cached": True,
            }

    # Load local reference matches
    from .grobid import local_refs_path

    refs_file = local_refs_path(cfg)
    if not refs_file.exists():
        # Try individual references.json for this paper
        from .grobid import grobid_outputs_for_key

        grobid_out = grobid_outputs_for_key(cfg, key)
        if not grobid_out.references_path.exists():
            return {
                "citekey": key,
                "tags": [],
                "tier": "propagate",
                "cited_count": 0,
                "cached": False,
                "note": "No GROBID references found. Run biblio grobid and biblio grobid match first.",
            }
        # Fall back: no local_refs.json but we have references — can't do propagation
        return {
            "citekey": key,
            "tags": [],
            "tier": "propagate",
            "cited_count": 0,
            "cached": False,
            "note": "No local_refs.json. Run biblio grobid match to build reference graph.",
        }

    local_refs: dict[str, list[dict[str, Any]]] = json.loads(
        refs_file.read_text(encoding="utf-8")
    )

    # Get cited citekeys for this paper
    cited_entries = local_refs.get(key, [])
    cited_keys = [e["target_citekey"] for e in cited_entries if "target_citekey" in e]

    if not cited_keys:
        result_data = {
            "citekey": key,
            "tags": [],
            "tier": "propagate",
            "cited_count": 0,
            "cached": False,
        }
        # Still cache the empty result
        cached_data = load_cache(cfg, key) or {"citekey": key, "tiers": {}}
        cached_data.setdefault("tiers", {})["propagate"] = {
            "tags": [],
            "cited_count": 0,
            "threshold": threshold,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        save_cache(cfg, key, cached_data)
        return result_data

    # Load library to get tags of cited papers
    from .library import load_library

    library = load_library(cfg)

    # Count tag frequency across cited papers
    tag_counts: dict[str, int] = {}
    for ck in cited_keys:
        entry = library.get(ck, {})
        for tag in entry.get("tags") or []:
            # Only propagate namespaced tags, skip auto: prefixed ones
            if ":" in tag and not tag.startswith("auto:"):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Filter by threshold
    propagated = sorted(
        [tag for tag, count in tag_counts.items() if count >= threshold]
    )

    # Prefix with auto:
    auto_tags = [f"auto:{tag}" for tag in propagated]

    # Update cache
    cached_data = load_cache(cfg, key) or {"citekey": key, "tiers": {}}
    cached_data.setdefault("tiers", {})["propagate"] = {
        "tags": auto_tags,
        "cited_count": len(cited_keys),
        "threshold": threshold,
        "tag_counts": {k: v for k, v in tag_counts.items() if v >= threshold},
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_cache(cfg, key, cached_data)

    return {
        "citekey": key,
        "tags": auto_tags,
        "tier": "propagate",
        "cited_count": len(cited_keys),
        "cached": False,
    }


def autotag(
    citekey: str,
    root: Path,
    *,
    tiers: list[str] | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    threshold: int = 3,
) -> dict[str, Any]:
    """Orchestrator: run requested tiers in order and merge results.

    Args:
        tiers: List of tier names to run. Default ["llm", "propagate"].
        force: Re-run even if cached.
        model: Anthropic model for LLM tier.
        threshold: Minimum citation count for propagation tier.

    Returns {"citekey", "tiers": {tier_name: result}, "all_tags": [...]}.
    """
    key = citekey.lstrip("@")
    if tiers is None:
        tiers = ["llm", "propagate"]

    tier_results: dict[str, Any] = {}
    all_tags: list[str] = []

    for tier in tiers:
        if tier == "llm":
            result = autotag_llm(key, root, model=model, force=force)
            tier_results["llm"] = result
            if not result.get("error"):
                for t in result.get("tags", []):
                    tag_str = t["tag"] if isinstance(t, dict) else t
                    auto_tag = f"auto:{tag_str}"
                    if auto_tag not in all_tags:
                        all_tags.append(auto_tag)
        elif tier == "propagate":
            result = autotag_propagate(key, root, threshold=threshold, force=force)
            tier_results["propagate"] = result
            for t in result.get("tags", []):
                if t not in all_tags:
                    all_tags.append(t)

    return {
        "citekey": key,
        "tiers": tier_results,
        "all_tags": all_tags,
    }
