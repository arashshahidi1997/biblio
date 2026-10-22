"""Digests of one paper, stored by mode and context (backlog D02, D05; journal-club R06).

A digest is addressed by (citekey, mode, context, prompt version, model) and
stored under ``bib/derivatives/digest/<mode>/<context>/<citekey>.{json,md}``.

``claims`` mode reads the paper by section (``biblio.sections``) and returns
the paper's own claims, each with its evidence (figure, test, statistic, n as
reported), caveats, the section it comes from and one verbatim quote. Every
quote is checked against the full text with the wiki's exact-only checker;
claims whose quote is not exact get one repair pass that sees only their
section, and any quote still not exact stays flagged. The ``talk`` context
adds rigor notes and the role each figure would play in a talk (the shape of
journal-club's hand-written digest); ``wiki`` is the plain default.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import BiblioConfig
from .sections import Section, read_sections

MODES = ("claims",)
CONTEXTS = ("wiki", "talk")
PROMPT_VERSION = "claims-1"

SYSTEM = """You digest one scientific paper for a research group's knowledge base. You are careful and literal:
you report what the paper claims and on what evidence, you never add facts or numbers that are not in the text,
and every quote you give is copied character for character from the section you name."""

INSTRUCTIONS = """The paper is given below, split into sections with ids like [S12].

Return JSON only (no prose, no code fence) with this shape:
{{
  "question": "the question the paper asks, 1-3 sentences",
  "setup": ["one line each: data, subjects, recording or methods, task, analysis; numbers as written"],
  "claims": [
    {{
      "id": "C1",
      "claim": "one of the paper's own claims, in plain words, one sentence",
      "kind": "finding | method | interpretation",
      "evidence": "where and how it is shown: figure or table, test, statistic, n, exactly as reported",
      "caveats": "limits stated by the authors (prefix 'authors:') and methodological limits a careful reader would raise (prefix 'reader:'); empty if none",
      "section": "S12",
      "quote": "8-40 words copied exactly from that section that state or show the claim"
    }}
  ],
  "one_line": "the paper's story in one sentence"{talk_fields}
}}

Rules:
- 6 to 15 claims, in the order of the Results, then the main interpretations from the Discussion (kind "interpretation").
- Numbers, units and test statistics only as they appear in the text. Do not compute or round.
- The quote must be a contiguous span of the named section, copied exactly, including odd spellings or spacing
  produced by text extraction. Never paraphrase inside a quote, never join two sentences.
- Prefer quotes from the Results over the Abstract.{talk_rules}

Paper: {citekey}

{sections}
"""

TALK_FIELDS = """,
  "rigor_notes": ["points a journal club should discuss: statistics (events vs animals as samples), sample sizes,
                   single channels, thresholds set by eye, causal language, alternative explanations"],
  "figure_roles": [{"figure": "Figure 1", "role": "what this figure would show in a talk, one line"}]"""
TALK_RULES = """
- Rigor notes are your own critical reading; tie each to a claim id where it applies.
- figure_roles: one entry per main figure listed below, in order."""

REPAIR = """For each claim below, give a quote of 8-40 words copied exactly, as a contiguous span, from the section text
shown under it, that states or shows the claim. Return JSON only: {{"quotes": {{"C1": "...", ...}}}}.
If no span supports the claim, give an empty string.

{items}"""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def digest_dir(cfg: BiblioConfig, mode: str, context: str) -> Path:
    return cfg.repo_root / "bib" / "derivatives" / "digest" / mode / context


def digest_paths(cfg: BiblioConfig, citekey: str, mode: str, context: str) -> tuple[Path, Path]:
    d = digest_dir(cfg, mode, context)
    return d / f"{citekey}.json", d / f"{citekey}.md"


def list_digests(cfg: BiblioConfig) -> list[dict[str, Any]]:
    root = cfg.repo_root / "bib" / "derivatives" / "digest"
    out = []
    for path in sorted(root.glob("*/*/*.json")) if root.is_dir() else []:
        try:
            meta = json.loads(path.read_text(encoding="utf-8")).get("meta", {})
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"citekey": path.stem, "mode": path.parent.parent.name, "context": path.parent.name,
                    "prompt_version": meta.get("prompt_version"), "model": meta.get("model"),
                    "created": meta.get("created"), "quotes": meta.get("quotes"), "path": str(path)})
    return out


# ---------------------------------------------------------------------------
# Claims mode
# ---------------------------------------------------------------------------

def _parse_json(text: str | None) -> dict[str, Any]:
    if not text:
        raise ValueError("empty LLM response")
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the LLM response")
    return json.loads(text[start:end + 1])


def _sections_block(sections: list[Section]) -> str:
    return "\n\n".join(f"### [{s.id}] {s.title}\n{s.text}" for s in sections)


def _main_figures(cfg: BiblioConfig, citekey: str) -> list[str]:
    manifest = cfg.repo_root / "bib" / "derivatives" / "figures" / citekey / "manifest.yml"
    if not manifest.is_file():
        return []
    import yaml
    figures = (yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}).get("figures") or []
    return [f"{f.get('number')}: {str(f.get('caption') or '')[:160]}" for f in figures
            if f.get("kind", "figure") == "figure" and f.get("number")]


def _verify(cfg: BiblioConfig, citekey: str, source: Path, claims: list[dict[str, Any]]) -> None:
    from .wiki.fidelity import QuoteChecker
    checker = QuoteChecker(lambda key: source)
    for c in claims:
        quote = (c.get("quote") or "").strip()
        m = checker.match(citekey, quote) if quote else None
        c["quote_status"] = m.status if m else "none"
        c["quote_diff"] = m.diff if m and m.diff else ""


def digest_claims(
    cfg: BiblioConfig,
    citekey: str,
    *,
    context: str = "wiki",
    model: str | None = None,
    force: bool = False,
    llm=None,
) -> dict[str, Any]:
    """Run claims mode for one paper and store it; returns the digest (with ``meta``)."""
    from .llm import DEFAULT_MODEL, call_llm
    key = citekey.lstrip("@")
    if context not in CONTEXTS:
        raise ValueError(f"unknown context {context!r}; known: {', '.join(CONTEXTS)}")
    json_path, md_path = digest_paths(cfg, key, "claims", context)
    if json_path.exists() and not force:
        return json.loads(json_path.read_text(encoding="utf-8"))
    llm = llm or call_llm
    model = model or DEFAULT_MODEL

    sections, source, source_kind = read_sections(cfg, key)
    by_id = {s.id: s for s in sections}
    talk = context == "talk"
    figures = _main_figures(cfg, key) if talk else []
    prompt = INSTRUCTIONS.format(
        talk_fields=TALK_FIELDS if talk else "", talk_rules=TALK_RULES if talk else "", citekey=key,
        sections=_sections_block(sections) + (("\n\nMain figures:\n" + "\n".join(figures)) if figures else ""))
    result = llm(system=SYSTEM, prompt=prompt, model=model, max_tokens=8000)
    if result.get("error"):
        raise RuntimeError(f"LLM call failed: {result['error']}")
    data = _parse_json(result.get("text"))
    claims = [c for c in data.get("claims") or [] if isinstance(c, dict) and c.get("claim")]
    _verify(cfg, key, source, claims)

    # one repair pass: only the claim's own section, asked for an exact span
    bad = [c for c in claims if c["quote_status"] != "exact" and c.get("section") in by_id]
    repaired = 0
    if bad:
        items = "\n\n".join(f"{c['id']}: {c['claim']}\nSection [{c['section']}] {by_id[c['section']].title}:\n"
                            f"{by_id[c['section']].text}" for c in bad)
        fix = llm(system=SYSTEM, prompt=REPAIR.format(items=items), model=model, max_tokens=3000)
        if not fix.get("error"):
            try:
                quotes = _parse_json(fix.get("text")).get("quotes") or {}
            except (ValueError, json.JSONDecodeError):
                quotes = {}
            for c in bad:
                new = (quotes.get(c["id"]) or "").strip()
                if new:
                    old = dict(c)
                    c["quote"] = new
                    _verify(cfg, key, source, [c])
                    if c["quote_status"] == "exact":
                        repaired += 1
                    elif old["quote_status"] in ("approximate",) and c["quote_status"] != "approximate":
                        c.update({k: old[k] for k in ("quote", "quote_status", "quote_diff")})
    for c in claims:
        sec = by_id.get(c.get("section") or "")
        c["section_title"] = sec.title if sec else ""
        c["section_line"] = sec.line if sec else 0

    counts = {s: sum(1 for c in claims if c["quote_status"] == s)
              for s in ("exact", "approximate", "changed", "missing", "none")}
    digest = {
        "meta": {"citekey": key, "mode": "claims", "context": context, "prompt_version": PROMPT_VERSION,
                 "model": model, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "source": str(source), "source_kind": source_kind, "sections": len(sections),
                 "quotes": counts, "repaired": repaired},
        "question": data.get("question", ""),
        "setup": data.get("setup") or [],
        "claims": claims,
        "one_line": data.get("one_line", ""),
    }
    if talk:
        digest["rigor_notes"] = data.get("rigor_notes") or []
        digest["figure_roles"] = data.get("figure_roles") or []
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(digest), encoding="utf-8")
    return digest


def to_markdown(digest: dict[str, Any]) -> str:
    """The digest as markdown; claims carry their quote as `> "..." [@key]`, the form wiki lint checks."""
    meta = digest["meta"]
    key = meta["citekey"]
    q = meta.get("quotes") or {}
    lines = [
        "---",
        f"citekey: {key}",
        f"mode: {meta['mode']}",
        f"context: {meta['context']}",
        f"prompt_version: {meta['prompt_version']}",
        f"model: {meta['model']}",
        f"created: {meta['created']}",
        f"source: {meta['source_kind']}",
        f"quotes: {{exact: {q.get('exact', 0)}, approximate: {q.get('approximate', 0)}, "
        f"changed: {q.get('changed', 0)}, missing: {q.get('missing', 0) + q.get('none', 0)}}}",
        "---", "",
        f"# Claims digest: {key}", "",
        "Generated by `biblio digest claims`. Each quote was checked against the full text: only quotes marked",
        "exact are verified; review the rest before using them.", "",
        "## Question", "", digest.get("question", ""), "",
        "## Setup", "",
    ]
    lines += [f"- {s}" for s in digest.get("setup") or []] or ["-"]
    lines += ["", "## Claims and evidence", ""]
    for c in digest.get("claims") or []:
        lines.append(f"### {c.get('id', '')}. {c.get('claim', '')}")
        lines.append("")
        lines.append(f"- **Kind:** {c.get('kind', '')}")
        lines.append(f"- **Evidence:** {c.get('evidence', '')}")
        if c.get("caveats"):
            lines.append(f"- **Caveats:** {c['caveats']}")
        where = f"{c.get('section_title', '')} ({c.get('section', '')})".strip()
        status = c.get("quote_status", "none")
        lines.append(f"- **Source:** {where}; quote {status}"
                     + (f" ({c['quote_diff']})" if c.get("quote_diff") else ""))
        lines.append("")
        if c.get("quote"):
            lines.append(f'> "{c["quote"]}" [@{key}]')
            lines.append("")
    lines += ["## In one line", "", digest.get("one_line", ""), ""]
    if "rigor_notes" in digest:
        lines += ["## Rigor notes for discussion", ""]
        lines += [f"- {n}" for n in digest["rigor_notes"]] or ["-"]
        lines += ["", "## Figure roles", ""]
        lines += [f"- **{f.get('figure', '')}**: {f.get('role', '')}" for f in digest.get("figure_roles") or []] or ["-"]
        lines.append("")
    return "\n".join(lines)
