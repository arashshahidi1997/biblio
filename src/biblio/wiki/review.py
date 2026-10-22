"""Human review of wiki pages (SPEC P11): packets for the reviewer, and recording their decisions.

Agents draft; people review. ``packet`` gathers what a reviewer needs to judge
one page (claims with their verification, open flags, lint findings). The
decision commands (``accept``, ``flag``, ``reopen``) only record what a person
decided: ``accept`` requires the reviewer's name and refuses pages with lint
errors or open review flags.
"""
from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .pages import Page, parse_page
from .schema import REVIEWED_STATUSES, WikiConfig
from .scaffold import append_log


class ReviewError(ValueError):
    pass


def resolve_page(cfg: WikiConfig, name: str) -> Path:
    """A page by path (absolute, from cwd, from the wiki root) or by basename."""
    for cand in (Path(name), cfg.repo_root / name, cfg.wiki_root / name):
        if cand.is_file():
            return cand.resolve()
    stem = Path(name).stem
    hits = [p for p in cfg.wiki_root.rglob(f"{stem}.md") if not p.name.startswith(".")]
    if len(hits) == 1:
        return hits[0].resolve()
    raise ReviewError(f"no single page matches '{name}'" + (f": {[str(h) for h in hits]}" if hits else ""))


# ---------------------------------------------------------------------------
# Frontmatter edits that keep the rest of the file as it is
# ---------------------------------------------------------------------------

def _dump(value: Any) -> str:
    if value is None:
        return "null"
    text = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=10_000).strip()
    return text[:-4].rstrip() if text.endswith("\n...") else text  # scalars end with a document marker


def set_fields(path: Path, updates: dict[str, Any]) -> None:
    """Replace or add top-level frontmatter keys; other lines stay byte for byte."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ReviewError(f"{path} has no frontmatter")
    end = text.index("\n---", 3)
    lines = text[4:end].split("\n")
    for key, value in updates.items():
        new = f"{key}: {_dump(value)}"
        idx = next((i for i, line in enumerate(lines) if re.match(rf"^{re.escape(key)}\s*:", line)), None)
        if idx is None:
            lines.append(new)
            continue
        stop = idx + 1
        while stop < len(lines) and (lines[stop].startswith((" ", "\t", "- ")) or not lines[stop].strip()):
            stop += 1
        lines[idx:stop] = [new]
    path.write_text("---\n" + "\n".join(lines) + text[end:], encoding="utf-8")


# ---------------------------------------------------------------------------
# Packet
# ---------------------------------------------------------------------------

def _last_commit(cfg: WikiConfig, path: Path) -> str:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs %h %s", "--", str(path)], cwd=cfg.repo_root,
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return out or "not committed"


def packet(cfg: WikiConfig, path: Path) -> str:
    """Markdown review packet for one page."""
    from .lint import lint
    from .sources import SourceIndex

    page = parse_page(path, cfg.wiki_root)
    fm = page.frontmatter
    findings = lint(cfg, [path])
    fid_lines = {f.line for f in findings if f.code.startswith("FID")}
    sources = SourceIndex(cfg)
    out = [f"## {page.title}  (`{page.rel}`)", ""]
    rev = fm.get("reviewed")
    out.append(f"- type **{page.type}**, status **{page.status}**, author **{fm.get('author')}**, "
               f"scope {fm.get('scope')}, updated {fm.get('updated')}")
    if isinstance(rev, dict):
        out.append(f"- reviewed by {rev.get('by')} on {rev.get('date')}")
    out.append(f"- last commit: {_last_commit(cfg, path)}")
    if page.lede:
        out += ["", f"> {page.lede}"]

    flags = page.list_field("review_flags")
    out += ["", f"### Open review flags ({len(flags)})", ""]
    out += [f"- [ ] {f}" for f in flags] or ["none"]

    shown = [f for f in findings if f.severity in ("error", "warning")]
    out += ["", f"### Lint ({len(shown)} errors or warnings)", ""]
    out += [f"- {f.severity} {f.code} line {f.line or '-'}: {f.message}" for f in shown] or ["clean"]

    out += ["", f"### Quotes ({len(page.quotes)})", ""]
    for q in page.quotes:
        mark = "NOT FOUND in source" if q.line in fid_lines else ("verified" if q.keys else "no citation")
        text = q.text if len(q.text) <= 160 else q.text[:157] + "..."
        out.append(f"- line {q.line}, {mark}: \"{text}\" " + " ".join(f"[@{k}]" for k in q.keys))
    if not page.quotes:
        out.append("none")

    keys = sorted({c.key for c in page.citations} | {s.lstrip("@") for s in page.list_field("sources")})
    out += ["", f"### Citations ({len(keys)})", ""]
    for key in keys:
        where = sources.locate(key)
        out.append(f"- @{key}: {'project' if where == 'project' else ('pool ' + where) if where else 'NOT FOUND'}")
    if not keys:
        out.append("none")

    evidence, code = page.list_field("evidence"), page.list_field("code")
    if evidence or code:
        out += ["", "### Project evidence and code", ""]
        out += [f"- evidence: {', '.join(evidence)}"] if evidence else []
        out += [f"- code: {', '.join(code)}"] if code else []

    marked = [(n, ln.strip()) for n, ln in enumerate(page.body_lines, page.body_offset)
              if re.match(r"^>\s*\*\*(Contested|Outdated|Disputed)\.?\*\*", ln.strip())]
    if marked:
        out += ["", "### Contested or outdated blocks", ""]
        out += [f"- line {n}: {t[:160]}" for n, t in marked]

    out += ["", "### Decision", "",
            f"- accept: `biblio wiki review accept {page.rel} --by <your name>`",
            f"- request changes: `biblio wiki review flag {page.rel} \"<what to change>\"`", ""]
    return "\n".join(out)


def queue(cfg: WikiConfig) -> list[Path]:
    """Draft pages written by an agent, waiting for a person."""
    from .status import status
    return [cfg.wiki_root / rel for rel in status(cfg)["review_queue"]]


# ---------------------------------------------------------------------------
# Decisions (recorded for a person; agents never review their own pages)
# ---------------------------------------------------------------------------

def accept(cfg: WikiConfig, path: Path, by: str, *, stable: bool = False, resolve_flags: bool = False,
           on: str | None = None) -> str:
    from .lint import lint

    by = (by or "").strip()
    if not by:
        raise ReviewError("accept needs the reviewer's name (--by); agents never review pages")
    page = parse_page(path, cfg.wiki_root)
    target = "stable" if stable else "reviewed"
    if stable and page.status not in REVIEWED_STATUSES:
        raise ReviewError(f"{page.rel} is '{page.status}'; review it before marking it stable")
    if page.status in ("stub",):
        raise ReviewError(f"{page.rel} is a stub; write it up to a draft first")
    errors = [f for f in lint(cfg, [path]) if f.severity == "error" and f.page == page.rel]
    if errors:
        raise ReviewError(f"{page.rel} has {len(errors)} lint error(s): "
                          + "; ".join(f"{f.code} {f.message}" for f in errors[:3]))
    flags = page.list_field("review_flags")
    if flags and not resolve_flags:
        raise ReviewError(f"{page.rel} has {len(flags)} open review flag(s); resolve them, or pass "
                          "--resolve-flags to record that you settled them")
    updates: dict[str, Any] = {"status": target, "reviewed": {"by": by, "date": on or date.today().isoformat()}}
    if flags:
        updates["review_flags"] = []
    set_fields(path, updates)
    note = f"{target} by {by}" + (f"; {len(flags)} flag(s) resolved" if flags else "")
    append_log(cfg, "review", [page.rel], note)
    return note


def flag(cfg: WikiConfig, path: Path, text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        raise ReviewError("a review flag needs text")
    page = parse_page(path, cfg.wiki_root)
    set_fields(path, {"review_flags": [*page.list_field("review_flags"), text]})
    append_log(cfg, "review", [page.rel], f"flag: {text}")
    return text


def reopen(cfg: WikiConfig, path: Path, reason: str = "") -> str:
    page = parse_page(path, cfg.wiki_root)
    set_fields(path, {"status": "draft", "reviewed": None})
    append_log(cfg, "review", [page.rel], "reopened" + (f": {reason}" if reason else ""))
    return f"{page.rel} back to draft"
