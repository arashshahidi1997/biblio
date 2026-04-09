"""LLM-driven extraction of paper relevance against research questions."""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from .config import BiblioConfig

EXTRACT_DIR_REL = Path("bib") / "derivatives" / "claude"

_SYSTEM_PROMPT = """\
You are a research assistant extracting structured information from an academic
paper in the context of a set of research questions / hypotheses.

Given the paper's full text and the research questions, produce **only** a YAML
document (no markdown fences, no prose) with exactly this schema:

```
citekey: <citekey>
relevance:
  - question_id: <id>
    relevance: high | medium | low | none
    summary: <1-2 sentences>
    supports: true | false | null
methods:
  - <method>
dataset_opportunities:
  - <dataset or resource>
species:
  - <species if biological>
regions:
  - <brain region / geographic region if applicable>
key_findings:
  - <finding>
```

Rules:
- If a question is not addressed, set relevance to "none" and omit summary.
- Only include fields that have actual content — omit empty lists.
- Be precise and concise.
"""


def extract_for_citekey(
    cfg: BiblioConfig,
    citekey: str,
    *,
    questions_path: Path | None = None,
    force: bool = False,
    model: str = "sonnet",
) -> dict[str, Any]:
    """Run LLM extraction for a single citekey against research questions.

    Returns ``{"citekey": str, "output_path": str, "status": "extracted"|"skipped"|"error"}``.
    """
    key = citekey.lstrip("@")
    out_dir = (cfg.repo_root / EXTRACT_DIR_REL / key).resolve()
    out_path = out_dir / "extract.yml"

    if out_path.exists() and not force:
        return {"citekey": key, "output_path": str(out_path), "status": "skipped"}

    # Load docling markdown
    from .docling import resolve_docling_outputs

    docling_out, docling_src = resolve_docling_outputs(cfg, key)
    if docling_src == "missing" or not docling_out.md_path.exists():
        return {
            "citekey": key,
            "status": "error",
            "error": "No docling markdown available. Run biblio_docling first.",
        }

    full_text = docling_out.md_path.read_text(encoding="utf-8", errors="replace")
    text_excerpt = full_text[:15000]

    # Load questions
    q_path = questions_path or (cfg.repo_root / "plan" / "questions.yml")
    if not q_path.exists():
        return {"citekey": key, "status": "error", "error": f"questions.yml not found at {q_path}"}

    questions_raw = yaml.safe_load(q_path.read_text(encoding="utf-8"))
    questions: dict[str, dict] = (questions_raw or {}).get("questions", {})
    if not questions:
        return {"citekey": key, "status": "error", "error": "No questions defined in questions.yml"}

    questions_text = "\n".join(
        f"- {qid}: {qdata.get('text', '')} (type: {qdata.get('type', '')})"
        for qid, qdata in questions.items()
    )

    prompt = (
        f"# Paper: {key}\n\n"
        f"## Research Questions\n{questions_text}\n\n"
        f"## Paper Full Text (excerpt)\n{text_excerpt}\n\n"
        "Extract structured YAML as specified in the system prompt."
    )

    from .llm import call_llm

    result = call_llm(system=_SYSTEM_PROMPT, prompt=prompt, model=model, max_tokens=3000)

    if result["error"]:
        return {"citekey": key, "status": "error", "error": result["error"]}

    raw_text = (result["text"] or "").strip()
    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        raw_text = "\n".join(lines)

    try:
        extraction = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        return {"citekey": key, "status": "error", "error": f"Failed to parse LLM YAML: {e}"}

    if not isinstance(extraction, dict):
        return {"citekey": key, "status": "error", "error": "LLM output is not a YAML mapping"}

    # Ensure citekey is set
    extraction.setdefault("citekey", key)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(extraction, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    return {"citekey": key, "output_path": str(out_path), "status": "extracted"}
