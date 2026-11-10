"""Gate check and plan for moving pages one tier up (wiki SPEC §9, backlog W12).

Knowledge moves project -> personal -> lab, one step at a time and never
sideways. ``plan_promote`` checks each page against the gate of its step and
describes the move: where the page lands, the ``origin:`` entry it gets, the
tags and keys that stay behind, links that would not resolve in the receiving
wiki, and what the page left behind becomes. It writes nothing: only the
receiving tier writes the moved page (``integrate``).
"""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .pages import Page, load_pages, parse_page
from .schema import TIERS, WikiConfig
from .sources import SourceIndex, bib_keys_and_dois

NEVER_MOVED = ("case", "question")
GATE_SEVERITIES = ("error", "warning")      # "lint-clean": no errors and no warnings


class PromoteError(ValueError):
    pass


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class PagePlan:
    page: str                                 # path from the source wiki root
    checks: list[Check] = field(default_factory=list)
    dest: str = ""                            # <wiki>:<path> in the receiving wiki
    dest_exists: bool = False
    origin: dict = field(default_factory=dict)
    tags_kept: list[str] = field(default_factory=list)
    tags_stripped: list[str] = field(default_factory=list)
    stays_behind: list[str] = field(default_factory=list)
    links_unresolved: list[str] = field(default_factory=list)   # in the receiving wiki
    left_behind: str = ""

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


@dataclass
class PromotePlan:
    source_tier: str
    target_tier: str
    target_name: str
    pages: list[PagePlan] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.pages) and all(p.ok for p in self.pages)

    def to_dict(self) -> dict:
        out = asdict(self)
        for page, plan in zip(out["pages"], self.pages):
            page["ok"] = plan.ok
        out["ok"] = self.ok
        return out


def next_tier(tier: str) -> str:
    if tier not in TIERS:
        raise PromoteError(f"tier '{tier}' is not one of {list(TIERS)} (set tier: in wiki.yml)")
    i = TIERS.index(tier)
    if i == len(TIERS) - 1:
        raise PromoteError(f"a '{tier}' wiki is the top tier; its pages do not move up")
    return TIERS[i + 1]


def _git(cfg: WikiConfig, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cfg.repo_root, capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _select(cfg: WikiConfig, names: list[str], tag: str | None) -> list[Page]:
    from .review import ReviewError, resolve_page
    pages: list[Page] = []
    try:
        for name in names:
            pages.append(parse_page(resolve_page(cfg, name), cfg.wiki_root))
    except ReviewError as exc:
        raise PromoteError(str(exc)) from exc
    if tag:
        tag = tag.lstrip("#").replace(":", "/")
        seen = {p.path.resolve() for p in pages}
        pages += [p for p in load_pages(cfg.wiki_root, meta_files=cfg.meta_files)
                  if tag in p.list_field("tags") and p.path.resolve() not in seen]
    if not pages:
        raise PromoteError("no pages to promote: name pages or give --tag")
    return pages


def _section_ranges(page: Page) -> dict[str, tuple[int, int]]:
    """H2 heading (lower case) -> (first, last) body line number."""
    h2 = page.h2()
    end = page.body_offset + len(page.body_lines)
    return {text.strip().lower(): (line, (h2[i + 1][1] - 1) if i + 1 < len(h2) else end)
            for i, (text, line) in enumerate(h2)}


def _outbound(page: Page, cfg: WikiConfig) -> list[Path]:
    """Wiki pages this page links to (markdown links by path, wikilinks by unique basename)."""
    out: list[Path] = []
    stems: dict[str, list[Path]] = {}
    for p in cfg.wiki_root.rglob("*.md"):
        stems.setdefault(p.stem, []).append(p.resolve())
    for link in page.links:
        if link.embed or not link.target or "://" in link.target:
            continue
        if link.kind == "md":
            target = (page.path.parent / link.target).resolve()
        else:
            hits = stems.get(Path(link.target.removesuffix(".md")).name, [])
            target = hits[0] if len(hits) == 1 else None
        if target and target.suffix == ".md" and target.is_relative_to(cfg.wiki_root) \
                and target != page.path.resolve() and target not in out:
            out.append(target)
    return out


def plan_promote(cfg: WikiConfig, names: list[str] | None = None, tag: str | None = None,
                 target: WikiConfig | None = None, today: date | None = None) -> PromotePlan:
    """Check each page against its step's gate and plan the move; writes nothing."""
    from .lint import lint

    step_to = next_tier(cfg.tier)
    if target is not None:
        if target.wiki_root.resolve() == cfg.wiki_root.resolve():
            raise PromoteError("the target is this wiki")
        if target.tier != step_to:
            kind = "sideways" if target.tier == cfg.tier else "not the next tier"
            raise PromoteError(f"target '{target.name}' is a '{target.tier}' wiki ({kind}); "
                               f"a '{cfg.tier}' wiki moves pages to a '{step_to}' wiki")
    target_name = target.name if target is not None else step_to
    pages = _select(cfg, names or [], tag)
    sources = SourceIndex(cfg)
    target_keys: set[str] | None = None
    if target is not None and step_to == "lab":
        target_keys = set()
        for bib in SourceIndex(target).bibliographies:
            target_keys |= bib_keys_and_dois(bib)[0]
    findings = lint(cfg, [p.path for p in pages])
    when = (today or date.today()).isoformat()

    plan = PromotePlan(source_tier=cfg.tier, target_tier=step_to, target_name=target_name)
    for page in pages:
        pp = PagePlan(page=page.rel)
        plan.pages.append(pp)
        add = pp.checks.append
        fm = page.frontmatter
        ptype = page.type or ""
        add(Check("type", ptype not in NEVER_MOVED and not fm.get("redirect"),
                  f"'{ptype}' pages never move" if ptype in NEVER_MOVED else
                  ("a redirect stub" if fm.get("redirect") else ptype)))
        add(Check("scope", fm.get("scope") == "general", str(fm.get("scope"))))
        if step_to == "lab":
            add(Check("reviewed", page.status in ("reviewed", "stable"),
                      f"status: {page.status} (needs reviewed or stable)"))
        own = [f for f in findings if f.page == page.rel and f.severity in GATE_SEVERITIES]
        add(Check("lint", not own, "clean" if not own else
                  "; ".join(f"{f.code} {f.message}" for f in own[:3]) + (" ..." if len(own) > 3 else "")))
        keys = sorted(set(page.list_field("sources")) | {c.key for c in page.citations})
        if step_to == "personal":
            unheld = [k for k in keys if sources.locate(k) is None]
            add(Check("sources", bool(page.list_field("sources")) and not unheld,
                      "sources: [] (not movable yet)" if not page.list_field("sources") else
                      (f"not held: {', '.join(unheld)}" if unheld else f"{len(keys)} held")))
        elif target_keys is not None:
            absent = [k for k in keys if k not in target_keys]
            add(Check("lab bibliography", not absent,
                      f"not in {target_name}'s bibliography: {', '.join(absent)}" if absent else
                      f"{len(keys)} in {target_name}'s bibliography"))
        rel_repo = page.path.resolve().relative_to(cfg.repo_root).as_posix()
        uncommitted = bool(_git(cfg, "status", "--porcelain", "--", rel_repo))
        commit = _git(cfg, "log", "-1", "--format=%h", "--", rel_repo)
        add(Check("committed", bool(commit) and not uncommitted,
                  commit if commit and not uncommitted else
                  ("uncommitted changes" if commit else "not committed")))

        # the move
        types = target.page_types if target is not None else cfg.page_types
        folder = types[ptype][0] if ptype in types else Path(page.rel).parent.as_posix()
        dest_rel = f"{folder}/{page.name}.md"
        pp.dest = f"{target_name}:{dest_rel}"
        if target is not None:
            pp.dest_exists = (target.wiki_root / dest_rel).is_file()
        pp.origin = {"project": cfg.name, "path": rel_repo, "commit": commit or "<commit>", "date": when}
        for t in page.list_field("tags"):
            facet = t.lstrip("#").split("/", 1)[0]
            (pp.tags_stripped if facet in cfg.project_facets else pp.tags_kept).append(t)
        sections = _section_ranges(page)
        if "our experience" in sections:
            pp.stays_behind.append("section 'Our experience'")
        if page.list_field("evidence"):
            pp.stays_behind.append(f"evidence: {', '.join(page.list_field('evidence'))}")
        if pp.tags_stripped:
            pp.stays_behind.append(f"project facets: {', '.join(pp.tags_stripped)}")
        for linked in _outbound(page, cfg):
            linked_rel = linked.relative_to(cfg.wiki_root).as_posix()
            if target is None or not (target.wiki_root / linked_rel).is_file():
                pp.links_unresolved.append(linked_rel)
        pp.left_behind = (f"lede, a link to {pp.dest}, 'Our experience' and the project facets; "
                          f"status: promoted, promoted_to: {pp.dest}")
    return plan


def describe(plan: PromotePlan) -> str:
    lines = [f"promote: {plan.source_tier} -> {plan.target_tier} ({plan.target_name}); "
             f"{sum(p.ok for p in plan.pages)}/{len(plan.pages)} page(s) pass the gate", ""]
    for pp in plan.pages:
        lines.append(f"{pp.page}  {'PASS' if pp.ok else 'BLOCKED'}")
        for c in pp.checks:
            lines.append(f"  [{'x' if c.ok else ' '}] {c.name}: {c.detail}")
        lines.append(f"  -> {pp.dest}" + ("  (exists there: merge, do not overwrite)" if pp.dest_exists else ""))
        o = pp.origin
        lines.append(f"  origin: {{project: {o['project']}, path: {o['path']}, commit: {o['commit']}, "
                     f"date: {o['date']}}}")
        if pp.tags_kept or pp.tags_stripped:
            lines.append(f"  tags: {', '.join(pp.tags_kept) or '-'}"
                         + (f"  (stripped: {', '.join(pp.tags_stripped)})" if pp.tags_stripped else ""))
        if pp.stays_behind:
            lines.append(f"  stays behind: {'; '.join(pp.stays_behind)}")
        if pp.links_unresolved:
            lines.append(f"  links to move first or unlink: {', '.join(pp.links_unresolved)}")
        lines.append(f"  left behind: {pp.left_behind}")
        lines.append("")
    lines.append("Nothing written. The receiving wiki writes the page (with origin:) and both log.md files "
                 "get an integrate entry (SPEC §9).")
    return "\n".join(lines)
