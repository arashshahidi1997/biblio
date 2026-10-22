"""Lint: detect deviations from the wiki principles. Detect only; never edits.

Every finding names the principle it serves and, for suggestions, the
refactor operation that would resolve it (wiki SPEC §8).
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import yaml

from .fidelity import QuoteChecker
from .hubs import stale_views
from .pages import Page, iter_page_paths, load_pages
from .sources import SourceIndex
from .schema import AUTHORS, REQUIRED_KEYS, REVIEWED_STATUSES, SCOPES, STATUSES, WikiConfig

SEVERITIES = ("error", "warning", "suggestion", "info")
CODE_ANCHOR_RE = re.compile(r"^(?P<path>[^:]+?)(?:::(?P<symbol>[\w.]+))?$")
BODY_ANCHOR_RE = re.compile(r"`([\w.\-]+(?:/[\w.\-]+)+::[\w.]+)`")  # `code/utils/x.py::fn` in prose
LEDE_PLACEHOLDER = "One-paragraph definition: what this is and why a reader would come here."
EXPERIENCE_SECTIONS = ("our experience", "observed in")  # SPEC §5: project findings live here (or on case pages)


@dataclass
class Finding:
    severity: str
    code: str
    page: str
    line: int | None
    message: str
    principle: str | None = None
    op: str | None = None




def _vocab_tags(path: Path | None) -> set[str] | None:
    """Known tags as ``facet/value`` (the vocabulary file uses biblio's ``namespace:value``)."""
    if not path or not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tags = set()
    for ns, spec in (data.get("namespaces") or {}).items():
        for value in (spec or {}).get("values") or []:
            tags.add(f"{ns}/{value}")
    for alias in (data.get("aliases") or {}):
        tags.add(str(alias).replace(":", "/"))
    return tags


def _check_embed(cfg, page: Page, link, add) -> bool:
    """Embedded files (W17): annex state and credit. True when the link check is done."""
    from .embeds import figure_citekey, file_state
    path = Path(os.path.normpath(page.path.parent / link.target))
    rel = os.path.relpath(path, cfg.repo_root)
    state = file_state(path)
    key = figure_citekey(cfg, path)
    if key and key not in {c.key for c in page.citations} | {s.lstrip("@") for s in page.list_field("sources")}:
        add(Finding("warning", "IMG003", page.rel, link.line,
                    f"figure from {key} without credit; cite [@{key}] on the page", "§6"))
    if state == "absent":
        add(Finding("warning", "IMG001", page.rel, link.line,
                    f"'{rel}' is annexed but not here (biblio wiki embeds --get)", "§6"))
        return True
    if state == "locked":
        add(Finding("info", "IMG002", page.rel, link.line,
                    f"'{rel}' is an annex symlink; Obsidian will not show it (biblio wiki embeds --unlock)", "§6"))
        return True
    return False


def _heading_slug(text: str) -> str:
    return re.sub(r"[^\w\- ]", "", text).strip().lower().replace(" ", "-")


class _Resolver:
    """Resolve wikilinks by basename and markdown links by path."""

    def __init__(self, cfg: WikiConfig, pages: list[Page]):
        self.by_name: dict[str, list[Path]] = defaultdict(list)
        self.headings: dict[Path, set[str]] = {}
        for page in pages:
            self.by_name[page.name].append(page.path)
            self.headings[page.path] = {h for _, h, _ in page.headings}
        self.page_by_path = {p.path: p for p in pages}
        roots = list(cfg.link_roots)
        if cfg.fulltext_root.is_dir():
            roots.append(cfg.fulltext_root)
        for root in roots:
            for path in root.rglob("*.md"):
                if path not in self.page_by_path:
                    self.by_name[path.stem].append(path)

    def wiki(self, name: str) -> list[Path]:
        return self.by_name.get(Path(name).name.removesuffix(".md"), [])

    def has_heading(self, path: Path, anchor: str) -> bool:
        heads = self.headings.get(path)
        if heads is None:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return True
            heads = {m.group(2).strip() for m in re.finditer(r"^(#{1,6})\s+(.+?)\s*#*\s*$", text, re.M)}
            self.headings[path] = heads
        wanted = anchor.strip()
        return wanted in heads or _heading_slug(wanted) in {_heading_slug(h) for h in heads}


def lint(cfg: WikiConfig, paths: list[Path] | None = None) -> list[Finding]:
    all_pages = load_pages(cfg.wiki_root)
    targets = {p.resolve() for p in paths} if paths else None
    pages = [p for p in all_pages if targets is None or p.path.resolve() in targets]
    findings: list[Finding] = []
    add = findings.append

    sources = SourceIndex(cfg)
    vocab = _vocab_tags(cfg.vocab)
    resolver = _Resolver(cfg, all_pages)
    checker = QuoteChecker(sources.fulltext)
    project_res = [re.compile(t) for t in cfg.project_tokens]

    if not sources.has_bibliography:
        add(Finding("info", "CIT000", "-", None, "no bibliography found; citekeys not checked"))
    elif not sources.bibliographies:
        add(Finding("warning", "CIT005", "-", None,
                    "no project bibliography (bib/srcbib/*.bib, merged.bib or compiled.bib); "
                    "only the pools are checked, so the project's own papers show as CIT001", "P8"))
    if vocab is None:
        add(Finding("info", "TAG000", "-", None, "no vocabulary found; tags not checked"))

    # global: duplicate basenames among wiki pages, ambiguity with full text
    names = Counter(p.name for p in all_pages)
    for page in pages:
        if names[page.name] > 1:
            add(Finding("error", "LNK002", page.rel, None,
                        f"basename '{page.name}' is used by {names[page.name]} pages", "P2", "relink"))
        elif len(resolver.wiki(page.name)) > 1:
            add(Finding("warning", "LNK002", page.rel, None,
                        f"basename '{page.name}' also names a full-text file; [[{page.name}]] is ambiguous",
                        "P2", "relink"))

    inbound: Counter = Counter()
    linked_from: dict[Path, set[str]] = defaultdict(set)
    wanted: dict[str, set[str]] = defaultdict(set)
    for page in all_pages:
        for link in page.links:
            if link.kind == "wiki":
                for target in resolver.wiki(link.target):
                    if target != page.path:
                        inbound[target] += 1
                        linked_from[target].add(page.rel)
                if not resolver.wiki(link.target):
                    wanted[link.target].add(page.rel)
            else:
                target = (page.path.parent / link.target).resolve()
                if target != page.path:
                    inbound[target] += 1
                    linked_from[target].add(page.rel)
        for key in cfg.relation_keys:
            for value in page.list_field(key):
                for target in resolver.wiki(_strip_link(value)):
                    inbound[target] += 1
                    linked_from[target].add(page.rel)
    hub_tag_set = {t for p in all_pages if p.type == "hub" for t in p.list_field("tags")}
    in_a_hub = {p.rel for p in all_pages if p.type == "hub" or hub_tag_set & set(p.list_field("tags"))}

    for page in pages:
        _check_page(cfg, page, add, sources, vocab, resolver, checker, project_res)
        if inbound[page.path] == 0 and page.type not in ("hub", "question"):
            add(Finding("info", "ORPH001", page.rel, None, "no page links here", "P5", "hub"))
        elif page.rel not in in_a_hub and page.type not in ("hub", "question"):
            linkers = sorted(linked_from[page.path] & in_a_hub)
            if linkers:
                add(Finding("suggestion", "SUG004", page.rel, None,
                            f"linked from {', '.join(linkers[:3])} but listed in no hub; "
                            "give it one of that hub's tags", "P12", "hub"))

    # views
    for path in stale_views(cfg, all_pages):
        rel = path.relative_to(cfg.wiki_root).as_posix()
        if targets is None or path.resolve() in targets:
            add(Finding("warning", "HUB001", rel, None,
                        "generated list is out of date; run `biblio wiki hubs`", "P12"))

    # suggestions across pages
    if targets is None:
        for target, referrers in sorted(wanted.items()):
            if len(referrers) >= 3:
                add(Finding("suggestion", "SUG002", "-", None,
                            f"'{target}' is linked from {len(referrers)} pages but has no page",
                            "P6", "stub"))
        hub_tags = {t for p in all_pages if p.type == "hub" for t in p.list_field("tags")}
        # pages already listed by some hub do not need another one for a narrower tag
        uncovered = [p for p in all_pages if p.type != "hub" and not hub_tags & set(p.list_field("tags"))]
        tag_counts = Counter(t for p in uncovered for t in set(p.list_field("tags")))
        for tag, count in sorted(tag_counts.items()):
            if count >= 5 and tag not in hub_tags:
                add(Finding("suggestion", "SUG003", "-", None,
                            f"{count} pages share tag '{tag}' and no hub covers it", "P6", "hub"))

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (f.page, order[f.severity], f.line or 0, f.code))
    return findings


def _strip_link(value: str) -> str:
    value = value.strip()
    m = re.match(r"^\[\[([^\]|#]+)", value)
    return m.group(1) if m else value


def _check_page(cfg, page: Page, add, sources: SourceIndex, vocab, resolver: _Resolver, checker: QuoteChecker,
                project_res):
    fm = page.frontmatter
    reviewed = page.status in REVIEWED_STATUSES
    strict = "error" if reviewed else "warning"

    # frontmatter
    if not page.has_frontmatter:
        add(Finding("error", "FM001", page.rel, 1, "no frontmatter", "P7"))
        return
    if page.fm_error:
        add(Finding("error", "FM001", page.rel, 1, page.fm_error, "P7"))
        return
    for key in REQUIRED_KEYS:
        if fm.get(key) in (None, ""):
            add(Finding("error", "FM002", page.rel, 1, f"missing required key '{key}'", "P7"))
    for key, allowed in (("type", tuple(cfg.page_types)), ("status", STATUSES), ("scope", SCOPES), ("author", AUTHORS)):
        value = fm.get(key)
        if value is not None and str(value) not in allowed:
            add(Finding("error", "FM003", page.rel, 1, f"{key} '{value}' not in {list(allowed)}", "P7"))
    rev = fm.get("reviewed")
    if reviewed and not (isinstance(rev, dict) and rev.get("by") and rev.get("date")):
        add(Finding("error", "FM004", page.rel, 1,
                    f"status '{page.status}' needs reviewed: {{by, date}} set by a person", "P11"))
    elif not reviewed and rev:
        add(Finding("warning", "FM004", page.rel, 1,
                    f"reviewed is set but status is '{page.status}'", "P11"))
    for key in fm:
        if key not in cfg.known_keys:
            add(Finding("warning", "FM005", page.rel, 1, f"unknown frontmatter key '{key}'", "P7"))
    for key in cfg.relation_keys:
        for value in page.list_field(key):
            if not resolver.wiki(_strip_link(value)):
                add(Finding(strict, "FM006", page.rel, 1, f"{key}: '{value}' does not resolve", "P5", "relink"))
    updated = fm.get("updated")
    if updated is not None and not isinstance(updated, date) and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(updated)):
        add(Finding("warning", "FM007", page.rel, 1, f"updated '{updated}' is not YYYY-MM-DD"))
    ptype = page.type
    if ptype in cfg.page_types:
        folder = cfg.page_types[ptype][0]
        parts = Path(page.rel).parts
        if len(parts) < 2 or parts[0] != folder:
            add(Finding("warning", "FM008", page.rel, 1,
                        f"type '{ptype}' pages belong in '{folder}/'", "P5", "relink"))

    # tags
    if vocab is not None:
        for tag in page.list_field("tags"):
            if tag.lstrip("#") not in vocab:
                add(Finding("error", "TAG001", page.rel, 1, f"tag '{tag}' is not in the vocabulary", "§3"))

    # structure
    if page.status != "stub" and ptype in cfg.page_types:
        if ptype != "hub" and not page.lede:
            add(Finding(strict, "STR001", page.rel, page.body_offset,
                        "no lede paragraph before the first section", "P3"))
        elif page.lede and page.lede.strip() == LEDE_PLACEHOLDER:
            add(Finding(strict, "STR003", page.rel, page.body_offset,
                        "lede is still the template placeholder", "P3"))
        present = [h.lower() for h, _ in page.h2()]
        for required in cfg.page_types[ptype][1]:
            options = [o.strip().lower() for o in required.split("|")]
            if not any(h.startswith(o) for h in present for o in options):
                add(Finding(strict, "STR002", page.rel, None, f"missing section '## {required.split('|')[0]}'", "P4"))
    if page.words > cfg.max_words:
        add(Finding("suggestion", "SUG001", page.rel, None,
                    f"{page.words} words (limit {cfg.max_words}); a second idea may belong on its own page",
                    "P1", "extract"))

    # links
    for link in page.links:
        if link.embed and link.kind == "wiki":
            add(Finding("warning", "LNK003", page.rel, link.line, f"embed ![[{link.target}]]; link instead", "§6"))
        if link.kind == "wiki":
            found = resolver.wiki(link.target)
            if not found:
                add(Finding(strict, "LNK001", page.rel, link.line, f"[[{link.target}]] does not resolve",
                            "P6", "stub"))
            elif link.anchor and not resolver.has_heading(found[0], link.anchor):
                add(Finding("warning", "LNK005", page.rel, link.line,
                            f"[[{link.target}#{link.anchor}]]: no such heading"))
        else:
            if link.embed and _check_embed(cfg, page, link, add):
                continue
            target = (page.path.parent / link.target).resolve()
            if not target.exists():
                add(Finding(strict, "LNK004", page.rel, link.line, f"link target '{link.target}' does not exist",
                            "P5", "relink"))
            elif link.anchor and target.suffix == ".md" and not resolver.has_heading(target, link.anchor):
                add(Finding("warning", "LNK005", page.rel, link.line, f"'{link.target}#{link.anchor}': no such heading"))

    # citations
    listed = {s.lstrip("@") for s in page.list_field("sources")}
    cited = {c.key for c in page.citations}
    if sources.has_bibliography:
        for key in sorted(cited | listed):
            line = next((c.line for c in page.citations if c.key == key), 1)
            where = sources.locate(key)
            if where is None:
                add(Finding("error", "CIT001", page.rel, line, f"@{key} is not in the bibliography or any pool", "P8"))
            elif where != "project":
                add(Finding("info", "CIT003", page.rel, line,
                            f"@{key} is in a pool ({where}) but not in the project bibliography; "
                            "add it before rendering", "P8"))
    for key in sorted(cited - listed):
        line = next(c.line for c in page.citations if c.key == key)
        add(Finding("warning", "CIT002", page.rel, line, f"@{key} is cited but not listed in sources:", "P8"))
    for key in sorted(listed - cited):
        add(Finding("info", "CIT004", page.rel, 1, f"@{key} is in sources: but never cited in the text", "P8"))

    # fidelity
    rank = {"exact": 0, "approximate": 1, "changed": 2, "missing": 3, "no-text": 4}
    for quote in page.quotes:
        if not quote.keys:
            continue
        matches = {key: checker.match(key, quote.text) for key in quote.keys}
        key, best = min(matches.items(), key=lambda kv: rank[kv[1].status])
        short = quote.text if len(quote.text) <= 70 else quote.text[:67] + "..."
        if best.status == "exact":
            continue
        if best.status == "approximate":
            add(Finding("warning", "FID003", page.rel, quote.line,
                        f"quote matches @{key} only approximately ({best.diff}); copy it verbatim", "P8"))
        elif best.status == "changed":
            add(Finding("error", "FID004", page.rel, quote.line,
                        f"quote changes a word that carries meaning in @{key} ({best.diff}): \"{short}\"", "P8"))
        elif best.status == "no-text":
            add(Finding("info", "FID002", page.rel, quote.line,
                        f"cannot verify quote: no full text for {', '.join('@' + k for k in quote.keys)}", "P8"))
        else:
            add(Finding("error", "FID001", page.rel, quote.line,
                        f"quote not found in {', '.join('@' + k for k in quote.keys)}: \"{short}\"", "P8"))

    # code anchors: the frontmatter `code:` list and `path::symbol` in backticks in the body
    anchors = [(a.strip(), 1) for a in page.list_field("code")]
    seen = {a for a, _ in anchors}
    for idx, raw in enumerate(page.body_lines):
        for m in BODY_ANCHOR_RE.finditer(raw):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                anchors.append((m.group(1), page.body_offset + idx))
    for anchor, line in anchors:
        m = CODE_ANCHOR_RE.match(anchor)
        if not m:
            continue
        path = cfg.repo_root / m.group("path")
        if not path.exists():
            add(Finding("warning", "CODE001", page.rel, line, f"code anchor '{anchor}': file not found"))
        elif m.group("symbol") and path.is_file():
            name = m.group("symbol").split(".")[-1]
            text = path.read_text(encoding="utf-8", errors="replace")
            if not re.search(rf"^\s*(def|class)\s+{re.escape(name)}\b|^{re.escape(name)}\s*=|"
                             rf"^(rule|checkpoint)\s+{re.escape(name)}\s*:", text, re.M):
                add(Finding("warning", "CODE002", page.rel, line, f"code anchor '{anchor}': '{name}' not defined"))

    # scope: project tokens on general pages
    if fm.get("scope") == "general":
        for idx, raw in enumerate(page.body_lines):
            lineno = page.body_offset + idx
            section = (page.section_of(lineno) or "").lower()
            if section.startswith(EXPERIENCE_SECTIONS):
                continue
            for rx in project_res:
                m = rx.search(raw)
                if m:
                    add(Finding("warning", "SCOPE001", page.rel, lineno,
                                f"project token '{m.group(0)}' on a general page; move to 'Our experience' ('Observed in' on pitfalls) or a case page",
                                "P10", "extract"))
                    break


def summarize(findings: list[Finding]) -> dict[str, int]:
    counts = Counter(f.severity for f in findings)
    return {s: counts.get(s, 0) for s in SEVERITIES}


def format_findings(findings: list[Finding], fmt: str = "text", n_pages: int | None = None) -> str:
    if fmt == "json":
        return json.dumps({"summary": summarize(findings), "findings": [asdict(f) for f in findings]}, indent=1)
    if fmt == "tsv":
        rows = ["severity\tcode\tpage\tline\tprinciple\top\tmessage"]
        rows += [f"{f.severity}\t{f.code}\t{f.page}\t{f.line or ''}\t{f.principle or ''}\t{f.op or ''}\t{f.message}"
                 for f in findings]
        return "\n".join(rows)
    out, current = [], None
    for f in findings:
        if f.page != current:
            current = f.page
            out.append(f"\n{f.page if f.page != '-' else '(wiki)'}")
        hint = f"  [{f.principle}{' -> ' + f.op if f.op else ''}]" if f.principle else ""
        out.append(f"  {str(f.line or ''):>4}  {f.severity:<10} {f.code:<8} {f.message}{hint}")
    s = summarize(findings)
    pages = f"{n_pages} pages: " if n_pages is not None else ""
    out.append(f"\n{pages}{s['error']} errors, {s['warning']} warnings, "
               f"{s['suggestion']} suggestions, {s['info']} notes")
    return "\n".join(out).lstrip("\n")


def resolve_page_args(cfg: WikiConfig, args: list[Path]) -> tuple[list[Path], list[str]]:
    """Pages named by CLI arguments: files or folders, relative to the cwd, the repo or the wiki root.

    Returns (pages, arguments that matched no page). Folders expand to the pages inside them.
    """
    pages_all = {p.resolve() for p in iter_page_paths(cfg.wiki_root)}
    found: list[Path] = []
    unmatched: list[str] = []
    for arg in args:
        cands = [arg] if arg.is_absolute() else [Path.cwd() / arg, cfg.repo_root / arg, cfg.wiki_root / arg]
        target = next((c.resolve() for c in cands if c.exists()), None)
        if target is None:
            unmatched.append(str(arg))
            continue
        hits = sorted(p for p in pages_all if p == target or target in p.parents) if target.is_dir() else (
            [target] if target in pages_all else [])
        if not hits:
            unmatched.append(str(arg))
        found.extend(h for h in hits if h not in found)
    return found, unmatched


def page_count(cfg: WikiConfig) -> int:
    return len(iter_page_paths(cfg.wiki_root))
