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
PROMPT_VERSION = "claims-2"   # claims-2: quoted author caveats, terms, inconsistencies, quoted rigor notes

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
      "caveats": [
        {{"by": "authors", "text": "a limit the authors state", "section": "S20", "quote": "their words, 8-40 words"}},
        {{"by": "reader", "text": "a methodological limit a careful reader would raise (no quote)"}}
      ],
      "section": "S12",
      "quote": "8-40 words copied exactly from that section that state or show the claim"
    }}
  ],
  "terms": [
    {{"term": "Ripple", "layer": "measured | derived | interpreted",
      "definition": "how this paper operationally defines it (thresholds, bands, windows), as written",
      "differs": "how it differs from the field's usual meaning, or empty",
      "section": "S18", "quote": "the defining words, 8-40 words"}}
  ],
  "inconsistencies": [
    {{"what": "two passages of the paper that disagree (e.g. abstract vs discussion), one sentence",
      "passages": [{{"section": "S4", "quote": "..."}}, {{"section": "S38", "quote": "..."}}]}}
  ],
  "one_line": "the paper's story in one sentence"{talk_fields}
}}

Rules:
- 8 to 18 claims: every Results claim backed by a test statistic or a figure, in the order of the Results,
  then the main interpretations from the Discussion (kind "interpretation").
- Numbers, units and test statistics only as they appear in the text. Do not compute or round.
- Every quote (claims, author caveats, terms, inconsistencies{talk_quote}) must be a contiguous span of the named
  section, copied exactly, including odd spellings or spacing produced by text extraction. Never paraphrase inside
  a quote, never join two sentences. A reader caveat has no quote: it is your own reasoning.
- terms: the 6-12 terms a reader must pin down to follow the paper (places, signals, events, derived categories,
  the authors' own constructs). layer: measured (detected or recorded), derived (built from measurements),
  interpreted (the authors' reading).
- inconsistencies: only real disagreements between two passages of this paper, each side quoted; an empty list
  is a good answer. Check counts and group sizes against every place they are stated before calling them
  inconsistent (e.g. "8 animals, 4 per group, one excluded" is consistent with "3 vehicle animals").
- Prefer quotes from the Results over the Abstract.{talk_rules}

Paper: {citekey}

{sections}
"""

TALK_FIELDS = """,
  "rigor_notes": [{{"note": "a point a journal club should discuss: statistics (events vs animals as samples),
                    sample sizes, single channels, thresholds set by eye, causal language, alternative
                    explanations", "claims": ["C3"], "section": "S24", "quote": "the passage the note rests on"}}],
  "figure_roles": [{{"figure": "Figure 1", "role": "what this figure would show in a talk, one line"}}]"""
TALK_RULES = """
- Rigor notes are your own critical reading, but each rests on a passage: quote it (the method, the statistic,
  the wording) so the note can be checked; tie it to claim ids.
- figure_roles: one entry per main figure listed below, in order."""
TALK_QUOTE = ", rigor notes"

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
        talk_fields=TALK_FIELDS.replace("{{", "{").replace("}}", "}") if talk else "",
        talk_rules=TALK_RULES if talk else "", talk_quote=TALK_QUOTE if talk else "", citekey=key,
        sections=_sections_block(sections) + (("\n\nMain figures:\n" + "\n".join(figures)) if figures else ""))
    result = llm(system=SYSTEM, prompt=prompt, model=model, max_tokens=8000)
    if result.get("error"):
        raise RuntimeError(f"LLM call failed: {result['error']}")
    data = _parse_json(result.get("text"))
    claims = [c for c in data.get("claims") or [] if isinstance(c, dict) and c.get("claim")]
    _verify(cfg, key, source, claims)
    for c in claims:                                     # author caveats carry their own quote
        if isinstance(c.get("caveats"), list):
            _verify(cfg, key, source, [x for x in c["caveats"] if isinstance(x, dict) and x.get("quote")])
    terms = [t for t in data.get("terms") or [] if isinstance(t, dict) and t.get("term")]
    _verify(cfg, key, source, terms)
    inconsistencies = [x for x in data.get("inconsistencies") or [] if isinstance(x, dict) and x.get("what")]
    for x in inconsistencies:
        _verify(cfg, key, source, [q for q in x.get("passages") or [] if isinstance(q, dict)])

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
        "terms": terms,
        "inconsistencies": inconsistencies,
        "one_line": data.get("one_line", ""),
    }
    if talk:
        notes = [n if isinstance(n, dict) else {"note": str(n)} for n in data.get("rigor_notes") or []]
        _verify(cfg, key, source, [n for n in notes if n.get("quote")])
        digest["rigor_notes"] = notes
        digest["figure_roles"] = data.get("figure_roles") or []
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(digest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(digest), encoding="utf-8")
    return digest


def _status(item: dict[str, Any]) -> str:
    status = item.get("quote_status", "none")
    return "exact" if status == "exact" else f"quote {status.upper()}" + (
        f": {item['quote_diff']}" if item.get("quote_diff") else "")


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
        cav = c.get("caveats")
        if isinstance(cav, str) and cav:                      # claims-1 digests
            lines.append(f"- **Caveats:** {cav}")
        elif isinstance(cav, list) and cav:
            lines.append("- **Caveats:**")
            for x in cav:
                if not isinstance(x, dict):
                    continue
                if x.get("quote"):
                    lines.append(f"  - {x.get('by', '')}: {x.get('text', '')} ({_status(x)}) "
                                 f"\"{x['quote']}\"")
                else:
                    lines.append(f"  - {x.get('by', '')}: {x.get('text', '')}")
        where = f"{c.get('section_title', '')} ({c.get('section', '')})".strip()
        status = c.get("quote_status", "none")
        lines.append(f"- **Source:** {where}; quote {status}"
                     + (f" ({c['quote_diff']})" if c.get("quote_diff") else ""))
        lines.append("")
        if c.get("quote"):
            lines.append(f'> "{c["quote"]}" [@{key}]')
            lines.append("")
    terms = digest.get("terms") or []
    if terms:
        lines += ["## Terms", "", "| Term | Layer | In this paper | Differs from the field | Source |",
                  "|---|---|---|---|---|"]
        for t in terms:
            cell = lambda v: str(v or "").replace("|", "\\|")  # noqa: E731
            lines.append(f"| **{cell(t.get('term'))}** | {cell(t.get('layer'))} | {cell(t.get('definition'))} | "
                         f"{cell(t.get('differs'))} | {cell(t.get('section'))}, quote {_status(t)} |")
        lines.append("")
    inc = digest.get("inconsistencies")
    if inc is not None:
        lines += ["## Internal inconsistencies", ""]
        for x in inc:
            lines.append(f"- {x.get('what', '')}")
            for q in x.get("passages") or []:
                lines.append(f"  - {q.get('section', '')} ({_status(q)}): \"{q.get('quote', '')}\"")
        if not inc:
            lines.append("None found.")
        lines.append("")
    lines += ["## In one line", "", digest.get("one_line", ""), ""]
    if "rigor_notes" in digest:
        lines += ["## Rigor notes for discussion", ""]
        for n in digest["rigor_notes"]:
            if isinstance(n, str):                            # claims-1 digests
                lines.append(f"- {n}")
                continue
            ids = f" ({', '.join(n.get('claims') or [])})" if n.get("claims") else ""
            lines.append(f"- {n.get('note', '')}{ids}")
            if n.get("quote"):
                lines.append(f"  - rests on {n.get('section', '')} ({_status(n)}): \"{n['quote']}\"")
            else:
                lines.append("  - rests on: no passage given (unchecked)")
        if not digest["rigor_notes"]:
            lines.append("-")
        lines += ["", "## Figure roles", ""]
        lines += [f"- **{f.get('figure', '')}**: {f.get('role', '')}" for f in digest.get("figure_roles") or []] or ["-"]
        lines.append("")
    return "\n".join(lines)


def _quote_totals(digest: dict[str, Any]) -> dict[str, int]:
    """Quote checks over everything in a digest that carries a quote (claims, caveats, terms, ...)."""
    items: list[dict[str, Any]] = list(digest.get("claims") or [])
    for c in digest.get("claims") or []:
        items += [x for x in c.get("caveats") or [] if isinstance(x, dict) and x.get("quote")]
    items += list(digest.get("terms") or [])
    for x in digest.get("inconsistencies") or []:
        items += [q for q in x.get("passages") or [] if isinstance(q, dict)]
    items += [n for n in digest.get("rigor_notes") or [] if isinstance(n, dict) and n.get("quote")]
    out: dict[str, int] = {}
    for it in items:
        s = it.get("quote_status") or "none"
        out[s] = out.get(s, 0) + 1
    return out


def digest_claims_batch(
    cfg: BiblioConfig,
    keys: list[str],
    *,
    context: str = "wiki",
    model: str | None = None,
    force: bool = False,
    stale: bool = False,
    concurrency: int = 1,
    progress=None,
    llm=None,
) -> dict[str, Any]:
    """Claims digests for a list of papers (journal-club R31), with a summary stored beside them.

    A paper with a digest is skipped unless ``force``, or ``stale`` and its
    digest was made with an older prompt. ``progress(row)`` is called after
    each paper. The summary goes to ``bib/derivatives/digest/_runs/``.
    """
    from concurrent.futures import ThreadPoolExecutor

    started = datetime.now(timezone.utc)

    def one(key: str) -> dict[str, Any]:
        key = key.lstrip("@")
        json_path, md_path = digest_paths(cfg, key, "claims", context)
        redo = force
        if json_path.exists() and not force and stale:
            try:
                old = json.loads(json_path.read_text(encoding="utf-8")).get("meta", {})
            except (OSError, json.JSONDecodeError):
                old = {}
            redo = old.get("prompt_version") != PROMPT_VERSION
        if json_path.exists() and not redo:
            d = json.loads(json_path.read_text(encoding="utf-8"))
            status = "skipped (exists)"
        else:
            try:
                d = digest_claims(cfg, key, context=context, model=model, force=True, llm=llm)
            except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                return {"citekey": key, "status": "failed", "error": str(exc)}
            status = "done"
        q = _quote_totals(d)
        return {"citekey": key, "status": status, "claims": len(d.get("claims") or []),
                "prompt_version": d.get("meta", {}).get("prompt_version"),
                "claim_quotes": d.get("meta", {}).get("quotes") or {}, "all_quotes": q,
                "md": str(md_path)}

    rows: list[dict[str, Any]] = []
    if concurrency <= 1:
        for k in keys:
            rows.append(one(k))
            if progress:
                progress(rows[-1])
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            for row in ex.map(one, keys):
                rows.append(row)
                if progress:
                    progress(row)

    def total(field: str, status: str | None = None) -> int:
        return sum((r.get(field) or {}).get(status, 0) if status else sum((r.get(field) or {}).values())
                   for r in rows)

    summary = {
        "context": context, "model": model, "prompt_version": PROMPT_VERSION,
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "papers": len(rows),
        "done": sum(r["status"] == "done" for r in rows),
        "skipped": sum(r["status"].startswith("skipped") for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "claims": sum(r.get("claims", 0) for r in rows),
        "quotes": total("all_quotes"), "quotes_exact": total("all_quotes", "exact"),
        "rows": rows,
    }
    run_dir = cfg.repo_root / "bib" / "derivatives" / "digest" / "_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    stem = f"claims-{context}-{started.strftime('%Y%m%dT%H%M%SZ')}"
    (run_dir / f"{stem}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / f"{stem}.md").write_text(batch_summary_markdown(summary), encoding="utf-8")
    summary["path"] = str(run_dir / f"{stem}.md")
    return summary


def batch_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [f"# Claims digests ({summary['context']}), {summary['started']}", "",
             f"{summary['papers']} papers: {summary['done']} digested, {summary['skipped']} skipped, "
             f"{summary['failed']} failed; {summary['claims']} claims; quotes exact "
             f"{summary['quotes_exact']}/{summary['quotes']}.", "",
             "| citekey | status | claims | quotes exact | not exact |", "|---|---|---|---|---|"]
    for r in summary["rows"]:
        q = r.get("all_quotes") or {}
        other = ", ".join(f"{n} {s}" for s, n in sorted(q.items()) if s != "exact")
        lines.append(f"| {r['citekey']} | {r['status']}{(': ' + r['error']) if r.get('error') else ''} | "
                     f"{r.get('claims', '')} | {q.get('exact', '')}{'/' + str(sum(q.values())) if q else ''} | {other} |")
    return "\n".join(lines) + "\n"


def claims_table(
    cfg: BiblioConfig,
    keys: list[str] | None = None,
    *,
    context: str | None = None,
    grep: str | None = None,
    kind: str | None = None,
    section: str | None = None,
    exact_only: bool = False,
) -> list[dict[str, Any]]:
    """Claims from several stored digests side by side (D13), filtered.

    ``keys`` None means every stored claims digest. ``grep`` is a
    case-insensitive regex over claim, evidence, caveats and quote; ``kind``
    is finding / interpretation / method (comma-separated for several);
    ``section`` a substring of the section title. A paper with digests in both
    contexts contributes the talk digest only when ``context`` says so
    (``wiki`` first otherwise).
    """
    import re
    rx = re.compile(grep, re.I) if grep else None
    kinds = {k.strip().lower() for k in kind.split(",")} if kind else None
    contexts = [context] if context else ["wiki", "talk"]
    wanted = [k.lstrip("@") for k in keys] if keys else None
    picked: dict[str, Path] = {}
    for ctx in contexts:
        d = digest_dir(cfg, "claims", ctx)
        for path in sorted(d.glob("*.json")) if d.is_dir() else []:
            if (wanted is None or path.stem in wanted) and path.stem not in picked:
                picked[path.stem] = path
    rows: list[dict[str, Any]] = []
    order = wanted or sorted(picked)
    for key in order:
        path = picked.get(key)
        if path is None:
            rows.append({"citekey": key, "missing": True})
            continue
        digest = json.loads(path.read_text(encoding="utf-8"))
        for c in digest.get("claims") or []:
            caveats = c.get("caveats")
            if isinstance(caveats, list):
                caveats = "; ".join(str(x.get("text") or x.get("caveat") or x.get("quote") or x)
                                    if isinstance(x, dict) else str(x) for x in caveats)
            text = " ".join(str(c.get(f) or "") for f in ("claim", "evidence", "quote")) + " " + str(caveats or "")
            if rx and not rx.search(text):
                continue
            if kinds and str(c.get("kind") or "").lower() not in kinds:
                continue
            if section and section.lower() not in str(c.get("section_title") or "").lower():
                continue
            if exact_only and c.get("quote_status") != "exact":
                continue
            rows.append({"citekey": key, "context": path.parent.name, "id": c.get("id"), "kind": c.get("kind"),
                         "claim": c.get("claim"), "evidence": c.get("evidence"), "caveats": caveats or "",
                         "section": c.get("section_title") or c.get("section"), "line": c.get("section_line"),
                         "quote": c.get("quote"), "quote_status": c.get("quote_status")})
    return rows


def claims_table_markdown(rows: list[dict[str, Any]], *, quotes: bool = False) -> str:
    def cell(v: Any) -> str:
        return " ".join(str(v or "").split()).replace("|", "/")

    head = "| paper | id | kind | claim | section | quote |" if quotes else "| paper | id | kind | claim | section | check |"
    lines = [head, "|---|---|---|---|---|---|"]
    missing = []
    for r in rows:
        if r.get("missing"):
            missing.append(r["citekey"])
            continue
        last = (f'"{cell(r["quote"])}" ({r["quote_status"]})' if quotes else cell(r["quote_status"]))
        where = cell(r["section"]) + (f" (L{r['line']})" if r.get("line") else "")
        lines.append(f"| {r['citekey']} | {r['id']} | {cell(r['kind'])} | {cell(r['claim'])} | {where} | {last} |")
    n = len(rows) - len(missing)
    papers = len({r["citekey"] for r in rows if not r.get("missing")})
    out = "\n".join(lines) + f"\n\n{n} claims from {papers} papers."
    if missing:
        out += f" No claims digest: {', '.join(missing)}."
    return out + "\n"
