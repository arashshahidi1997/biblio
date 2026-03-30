"""Concept extraction from paper summaries/abstracts.

Extracts structured concepts (methods, datasets, metrics, domains, techniques)
from a paper and builds a cross-paper concept index.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .config import BiblioConfig, default_config_path, load_biblio_config

CONCEPT_DIR_REL = Path("bib/derivatives/concepts")
CONCEPT_INDEX_REL = Path("bib/derivatives/concepts/_index.yml")

CONCEPT_CATEGORIES = ("methods", "datasets", "metrics", "domains", "techniques")

SYSTEM_PROMPT = """\
You are a research paper concept extractor. Given a paper's title, abstract, \
and/or summary, extract key concepts into exactly these categories:

- methods: algorithms, models, architectures, or methodological approaches
- datasets: named datasets or benchmarks used or introduced
- metrics: evaluation metrics or measures reported
- domains: research areas or application domains
- techniques: specific techniques, tricks, or procedures (distinct from high-level methods)

Return a JSON object with these five keys, each mapping to a list of short \
strings (1-5 words each). Include 0-8 items per category. Be precise and use \
standard terminology.

Example:
{"methods": ["transformer", "attention mechanism"], "datasets": ["ImageNet", "COCO"], \
"metrics": ["top-1 accuracy", "F1 score"], "domains": ["computer vision", "object detection"], \
"techniques": ["data augmentation", "label smoothing"]}

Respond ONLY with the JSON object, no other text.\
"""

DEFAULT_MODEL = "haiku"


def _concepts_dir(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / CONCEPT_DIR_REL).resolve()


def _concepts_path(cfg: BiblioConfig, citekey: str) -> Path:
    return _concepts_dir(cfg) / f"{citekey}.yml"


def _index_path(cfg: BiblioConfig) -> Path:
    return (cfg.repo_root / CONCEPT_INDEX_REL).resolve()


def load_concepts(cfg: BiblioConfig, citekey: str) -> dict[str, list[str]] | None:
    """Load cached concepts for a citekey, or None if not extracted."""
    path = _concepts_path(cfg, citekey)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {cat: data.get(cat, []) for cat in CONCEPT_CATEGORIES}


def save_concepts(
    cfg: BiblioConfig, citekey: str, concepts: dict[str, list[str]]
) -> Path:
    """Write concept extraction results for a citekey."""
    path = _concepts_path(cfg, citekey)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {"citekey": citekey, "date_extracted": now}
    for cat in CONCEPT_CATEGORIES:
        data[cat] = concepts.get(cat, [])
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def _assemble_input(citekey: str, root: Path) -> str:
    """Gather title/abstract/summary for concept extraction."""
    from .mcp import paper_context

    ctx = paper_context(citekey, root=root)
    parts: list[str] = []

    bib = ctx.get("bib") or {}
    if bib.get("title"):
        parts.append(f"**Title:** {bib['title']}")
    if bib.get("abstract"):
        parts.append(f"**Abstract:** {bib['abstract']}")

    grobid_header = ctx.get("grobid_header") or {}
    if not bib.get("abstract") and grobid_header.get("abstract"):
        parts.append(f"**Abstract:** {grobid_header['abstract']}")

    # Check for existing summary
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    from .summarize import summary_path_for_key

    summary_path = summary_path_for_key(cfg, citekey)
    if summary_path.exists():
        text = summary_path.read_text(encoding="utf-8")
        # Strip frontmatter
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end + 3:].strip()
        parts.append(f"**Summary:**\n{text[:2000]}")

    return "\n\n".join(parts)


def validate_concepts(concepts: dict[str, Any]) -> dict[str, list[str]]:
    """Validate and normalize extracted concepts to the expected schema."""
    result: dict[str, list[str]] = {}
    for cat in CONCEPT_CATEGORIES:
        raw = concepts.get(cat, [])
        if not isinstance(raw, list):
            raw = []
        result[cat] = [str(item).strip() for item in raw if item and str(item).strip()]
    return result


def extract_concepts(
    citekey: str,
    root: Path,
    *,
    prompt_only: bool = False,
    force: bool = False,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Extract key concepts from a paper.

    Returns a dict with keys: citekey, prompt, concepts, concepts_path, skipped.
    """
    key = citekey.lstrip("@")
    cfg = load_biblio_config(default_config_path(root=root), root=root)

    # Check cache
    if not force and not prompt_only:
        existing = load_concepts(cfg, key)
        if existing is not None:
            return {
                "citekey": key,
                "prompt": None,
                "concepts": existing,
                "concepts_path": str(_concepts_path(cfg, key)),
                "skipped": True,
            }

    prompt_text = _assemble_input(key, root)

    if prompt_only:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "concepts": None,
            "concepts_path": None,
            "skipped": False,
        }

    # Call LLM
    from .llm import call_llm
    import json

    result = call_llm(system=SYSTEM_PROMPT, prompt=prompt_text, model=model, max_tokens=1000)
    if result["error"]:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "concepts": None,
            "concepts_path": None,
            "skipped": False,
            "error": result["error"],
        }
    raw_text = result["text"].strip()
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "citekey": key,
            "prompt": prompt_text,
            "concepts": None,
            "concepts_path": None,
            "skipped": False,
            "error": f"LLM returned invalid JSON: {raw_text[:200]}",
        }

    concepts = validate_concepts(raw)
    out_path = save_concepts(cfg, key, concepts)

    return {
        "citekey": key,
        "prompt": prompt_text,
        "concepts": concepts,
        "concepts_path": str(out_path),
        "skipped": False,
    }


def build_concept_index(root: Path) -> dict[str, Any]:
    """Aggregate all per-paper concept files into a cross-paper index.

    Returns {concept_to_citekeys: {concept: [citekeys]}, total_papers, total_concepts}.
    """
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    concepts_dir = _concepts_dir(cfg)

    concept_to_citekeys: dict[str, list[str]] = {}
    total_papers = 0

    if not concepts_dir.exists():
        return {
            "concept_to_citekeys": {},
            "total_papers": 0,
            "total_concepts": 0,
            "index_path": str(_index_path(cfg)),
        }

    for yml_file in sorted(concepts_dir.glob("*.yml")):
        if yml_file.name.startswith("_"):
            continue
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8")) or {}
        ck = data.get("citekey") or yml_file.stem
        total_papers += 1
        for cat in CONCEPT_CATEGORIES:
            for concept in data.get(cat, []):
                concept_lower = concept.lower().strip()
                if concept_lower:
                    concept_to_citekeys.setdefault(concept_lower, [])
                    if ck not in concept_to_citekeys[concept_lower]:
                        concept_to_citekeys[concept_lower].append(ck)

    # Write index
    index_path = _index_path(cfg)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        yaml.safe_dump(
            {"concept_to_citekeys": concept_to_citekeys},
            sort_keys=True,
            allow_unicode=True,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    return {
        "concept_to_citekeys": concept_to_citekeys,
        "total_papers": total_papers,
        "total_concepts": len(concept_to_citekeys),
        "index_path": str(index_path),
    }


def search_concepts(query: str, root: Path) -> dict[str, Any]:
    """Search the concept index for papers matching a concept query.

    Returns {query, matches: [{concept, citekeys}], total_matches}.
    """
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    index_path = _index_path(cfg)

    if not index_path.exists():
        return {"query": query, "matches": [], "total_matches": 0, "hint": "Run 'biblio concepts index' first."}

    data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    c2ck = data.get("concept_to_citekeys", {})

    query_lower = query.lower().strip()
    matches: list[dict[str, Any]] = []
    for concept, citekeys in sorted(c2ck.items()):
        if query_lower in concept:
            matches.append({"concept": concept, "citekeys": citekeys})

    return {"query": query, "matches": matches, "total_matches": len(matches)}
