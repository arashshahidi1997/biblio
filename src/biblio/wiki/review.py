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


_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")
_STRIP_FOR_NUMBERS = re.compile(
    r"`[^`]*`"                                   # code spans and anchors
    r"|\[[^\]]*@[^\]]*\]"                        # citation groups
    r"|\]\([^)]*\)"                              # link targets
    r"|https?://\S+"
    r"|\b[A-Za-z]+(?:-[A-Za-z]*\d[\w]*)+"        # IDs: result-20260614-125644, DEN-R10, sub-03
    r"|[\"“][^\"”]{20,}?[\"”]")                  # inline quotes (checked separately)
_PROJECT_SECTIONS = ("our experience", "observed in")
_REFERENCE_SECTIONS = ("citation", "links", "related", "sources")  # references, not claims


_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")


def _claim_for(page: Page, quote_line: int) -> tuple[list[int], str]:
    """The sentence, paragraph or list item a quote backs, as (its lines, its text).

    An inline quote backs its own line. A blockquote backs the nearest preceding paragraph or
    list item (wrapped lines included) in the same section.
    """
    idx = quote_line - page.body_offset
    lines = page.body_lines
    if 0 <= idx < len(lines) and not lines[idx].lstrip().startswith(">"):
        return [quote_line], lines[idx].strip()
    section = page.section_of(quote_line)
    j = idx - 1
    while j >= 0 and (not lines[j].strip() or lines[j].lstrip().startswith(">")):
        j -= 1                                   # skip blank lines and other quotes of the same claim
    block: list[int] = []
    while j >= 0:
        raw = lines[j]
        if not raw.strip() or raw.lstrip().startswith((">", "#")) \
                or page.section_of(page.body_offset + j) != section:
            break
        block.insert(0, j)
        if _LIST_ITEM.match(raw):
            break                                # the start of this list item
        j -= 1
    if not block:
        return [], ""
    return [page.body_offset + k for k in block], " ".join(lines[k].strip() for k in block)


def _is_figure_line(page: Page, idx: int) -> bool:
    raw = page.body_lines[idx].strip()
    prev = next((page.body_lines[k].strip() for k in range(idx - 1, -1, -1) if page.body_lines[k].strip()), "")
    return raw.startswith("![") or prev.startswith("![") or bool(re.match(r"^\*+\s*(Figure|Fig\.)", raw))


def _short(text: str, n: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 3] + "..."


def packet(cfg: WikiConfig, path: Path) -> str:
    """Markdown review packet for one page (what a reviewer needs to judge it fast and safely)."""
    from .embeds import find_embeds
    from .fidelity import QuoteChecker
    from .lint import lint
    from .pages import load_pages
    from .sources import SourceIndex

    page = parse_page(path, cfg.wiki_root)
    fm = page.frontmatter
    findings = lint(cfg, [path])
    sources = SourceIndex(cfg)
    checker = QuoteChecker(sources.fulltext)
    label = {"exact": "verified exact", "approximate": "APPROXIMATE", "changed": "MEANING CHANGED",
             "missing": "NOT FOUND in source", "no-text": "no full text"}
    rank = {"exact": 0, "approximate": 1, "changed": 2, "missing": 3, "no-text": 4}
    out = [f"## {page.title}  (`{page.rel}`)", ""]
    rev = fm.get("reviewed")
    out.append(f"- type **{page.type}**, status **{page.status}**, author **{fm.get('author')}**, "
               f"scope {fm.get('scope')}, updated {fm.get('updated')}")
    if isinstance(rev, dict):
        out.append(f"- reviewed by {rev.get('by')} on {rev.get('date')}")
    if page.lede:
        out += ["", f"> {page.lede}"]

    flags = page.list_field("review_flags")
    out += ["", f"### Open review flags ({len(flags)})", ""]
    out += [f"- [ ] {f}" for f in flags] or ["none"]

    shown = [f for f in findings if f.severity in ("error", "warning")]
    out += ["", f"### Lint ({len(shown)} errors or warnings)", ""]
    out += [f"- {f.severity} {f.code} line {f.line or '-'}: {f.message}" for f in shown] or ["clean"]

    # 1-3: each claim beside its quote, where the quote is in the paper, exact or not
    out += ["", f"### Claims and their quotes ({len(page.quotes)})", ""]
    backed: set[int] = set()
    for q in page.quotes:
        claim_lines, claim = _claim_for(page, q.line)
        backed.update(claim_lines)
        first = claim_lines[0] if claim_lines else q.line
        out.append(f"- **line {first}** claim: {_short(claim, 400) if claim else '(no claim text found)'}")
        if not q.keys:
            out.append(f"  - quote (no citation): \"{_short(q.text)}\"")
            continue
        m = min(((k, checker.match(k, q.text)) for k in q.keys), key=lambda km: rank[km[1].status])
        key, match = m
        where = checker.locate(key, q.text) if match.status in ("exact", "approximate", "changed") else None
        loc = ""
        if where:
            line_no, heading = where
            ft = sources.fulltext(key)
            try:
                ft = ft.relative_to(cfg.repo_root)
            except ValueError:
                pass
            loc = f" in {heading + ', ' if heading else ''}`{ft}:{line_no}`"
        diff = f" ({match.diff})" if match.diff else ""
        out.append(f"  - quote, {label[match.status]}{diff}{loc}: \"{_short(q.text)}\" [@{key}]")
    if not page.quotes:
        out.append("none")

    # 4: sentences that cite a paper without a quote backing them
    quote_lines = {q.line for q in page.quotes}
    unbacked = sorted({c.line for c in page.citations} - backed - quote_lines)
    unbacked = [ln for ln in unbacked
                if not page.body_lines[ln - page.body_offset].lstrip().startswith(">")
                and not _is_figure_line(page, ln - page.body_offset)
                and (page.section_of(ln) or "").lower() not in _REFERENCE_SECTIONS]
    out += ["", f"### Citations without a quote ({len(unbacked)})", ""]
    out += [f"- line {ln}: {_short(page.body_lines[ln - page.body_offset].strip())}" for ln in unbacked] or ["none"]

    # 5: numbers on the page and whether the cited papers contain them
    cited = sorted({c.key for c in page.citations} | {s.lstrip("@") for s in page.list_field("sources")})
    with_text = [k for k in cited if checker.has_text(k)]
    missing_rows, project_rows, found_lines = [], [], []
    for idx, raw in enumerate(page.body_lines):
        line_no = page.body_offset + idx
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", ">", "<!--")) or _is_figure_line(page, idx):
            continue
        nums = [n for n in _NUMBER_RE.findall(_STRIP_FOR_NUMBERS.sub(" ", raw))
                if not re.fullmatch(r"(19|20)\d\d", n)]          # years say little
        if not nums:
            continue
        section = (page.section_of(line_no) or "").lower()
        if section.startswith(_PROJECT_SECTIONS):
            project_rows.append(f"- line {line_no}: {', '.join(nums)} (project result: check the evidence IDs)")
            continue
        absent = [n for n in nums if not any(checker.number_in(k, n) for k in with_text)]
        if absent and with_text:
            missing_rows.append(f"- line {line_no}: **{', '.join(absent)}** not in the cited papers: "
                                f"{_short(stripped, 160)}")
        elif absent:
            missing_rows.append(f"- line {line_no}: {', '.join(absent)} unchecked (no full text cited)")
        else:
            found_lines.append(str(line_no))
    out += ["", "### Numbers", ""]
    out += missing_rows + project_rows
    if found_lines:
        out.append(f"- line{'s' if len(found_lines) > 1 else ''} {', '.join(found_lines)}: "
                   "every number found in the cited papers")
    if not (missing_rows or project_rows or found_lines):
        out.append("none")

    # 9: where each citation resolves; pool-only keys must join the project bibliography
    out += ["", f"### Citations ({len(cited)})", ""]
    for key in cited:
        where = sources.locate(key)
        if where == "project":
            state = "project"
        elif where:
            state = f"pool only ({where}): add to the project bibliography before rendering"
        else:
            state = "NOT FOUND"
        out.append(f"- @{key}: {state}{'' if checker.has_text(key) else '; no full text'}")
    if not cited:
        out.append("none")

    # 6: embedded figures
    embeds = [e for e in find_embeds(cfg) if e.page.path.resolve() == path.resolve()]
    if embeds:
        out += ["", f"### Figures ({len(embeds)})", ""]
        for e in embeds:
            try:
                shown_path = e.path.relative_to(cfg.repo_root)
            except ValueError:
                shown_path = e.path
            out.append(f"- line {e.line}: `{shown_path}` ({e.state})")

    # 7: placement: links out and the hubs that list the page
    targets = sorted({ln.target for ln in page.links if not ln.embed})
    tags = set(page.list_field("tags"))
    hubs = [p.rel for p in load_pages(cfg.wiki_root) if p.type == "hub" and tags & set(p.list_field("tags"))]
    out += ["", "### Placement", "",
            f"- hubs: {', '.join(hubs) if hubs else 'none (no hub shares a tag with this page)'}",
            f"- links out ({len(targets)}): {', '.join(targets) if targets else 'none'}"]

    evidence, code = page.list_field("evidence"), page.list_field("code")
    if evidence or code:
        out += ["", "### Project evidence and code", ""]
        out += [f"- evidence: {', '.join(evidence)}"] if evidence else []
        out += [f"- code: {', '.join(code)}"] if code else []

    marked = [(n, ln.strip()) for n, ln in enumerate(page.body_lines, page.body_offset)
              if re.match(r"^>\s*\*\*(Contested|Outdated|Disputed)\.?\*\*", ln.strip())]
    if marked:
        out += ["", "### Contested or outdated blocks", ""]
        out += [f"- line {n}: {_short(t, 160)}" for n, t in marked]

    # 8: history from the wiki log (more telling than a blanket commit message)
    log = cfg.wiki_root / "log.md"
    history = [ln.strip() for ln in log.read_text(encoding="utf-8").splitlines()
               if page.rel in ln] if log.is_file() else []
    out += ["", "### History", ""]
    out += [f"- {h.lstrip('- ')}" for h in history[-6:]] or ["no log entries"]
    out.append(f"- last commit: {_last_commit(cfg, path)}")

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
