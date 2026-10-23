"""Refactor operations across wiki pages (backlog W05-W07): relink, merge, extract.

Each operation first builds a :class:`Plan` (files to move, write and edit,
line by line) that is printed as a dry run; ``apply`` carries it out and
appends one line to ``log.md``. Pages are never deleted: a merged page stays
as a redirect stub (``redirect:`` in its frontmatter).

Links are rewritten wherever they point at a moved or merged page:
wikilinks by name (``[[old]]``, ``[[old#h|label]]``, ``![[old]]``, or with a
path ``[[concepts/old]]``) and markdown links by resolved path
(``[x](../concepts/old.md#h)``); a moved page's own relative links are
re-based. Links in fenced code are left alone. Files outside the wiki that
mention the old path (mkdocs nav, other docs) are listed, not edited.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .pages import FENCE_RE, HEADING_RE, MDLINK_RE, WIKILINK_RE, parse_page, split_frontmatter
from .review import _dump, resolve_page
from .schema import RELATION_KEYS, WikiConfig
from .scaffold import append_log, slugify, stub

LIST_KEYS = ("aliases", "tags", "sources", "evidence", "code", "review_flags") + RELATION_KEYS


class RefactorError(ValueError):
    pass


@dataclass
class Plan:
    op: str
    moves: list[tuple[Path, Path]] = field(default_factory=list)
    writes: dict[Path, str] = field(default_factory=dict)            # full new text per file
    edits: dict[Path, list[tuple[int, str, str]]] = field(default_factory=dict)   # line, before, after
    outside: list[tuple[Path, int, str]] = field(default_factory=list)            # mentions to fix by hand
    notes: list[str] = field(default_factory=list)
    log_pages: list[str] = field(default_factory=list)
    log_note: str = ""


# ---------------------------------------------------------------------------
# Link rewriting
# ---------------------------------------------------------------------------

def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _wikilink_path(target: str, wiki_root: Path, stems: dict[str, list[Path]]) -> Path | None:
    """The page a wikilink target names: by path when it has one, else by a unique basename."""
    t = target.strip().removesuffix(".md")
    if "/" in t:
        cand = (wiki_root / f"{t}.md").resolve()
        return cand if cand.is_file() else None
    hits = stems.get(Path(t).name, [])
    return hits[0] if len(hits) == 1 else None


def rewrite_links(text: str, src: Path, new_src: Path, mapping: dict[Path, Path], wiki_root: Path,
                  stems: dict[str, list[Path]]) -> tuple[str, list[tuple[int, str, str]]]:
    """``text`` of the file at ``src`` (moving to ``new_src``) with links to ``mapping`` keys redirected."""
    out_lines: list[str] = []
    changes: list[tuple[int, str, str]] = []
    in_fence = False
    moving = src.resolve() != new_src.resolve()

    def wiki_sub(m: re.Match) -> str:
        embed, target, anchor, label = m.group(1), m.group(2), m.group(3), m.group(4)
        if not target.strip():
            return m.group(0)                  # [[#heading]] on the same page
        dest = _wikilink_path(target, wiki_root, stems)
        if dest is None or dest not in mapping:
            return m.group(0)
        new = mapping[dest]
        new_target = _rel(new, wiki_root).removesuffix(".md") if "/" in target else new.stem
        return f"{embed}[[{new_target}" + (f"#{anchor}" if anchor is not None else "") + \
            (f"|{label}" if label is not None else "") + "]]"

    def md_sub(m: re.Match) -> str:
        embed, label, href = m.group(1), m.group(2), m.group(3)
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith(("#", "/")):
            return m.group(0)
        path_part, hash_, anchor = href.partition("#")
        if not path_part:
            return m.group(0)
        dest = (src.parent / path_part).resolve()
        target = mapping.get(dest, dest)
        if target == dest and not moving:
            return m.group(0)
        new_href = os.path.relpath(target, new_src.parent).replace(os.sep, "/") + (hash_ + anchor if hash_ else "")
        if new_href == href:
            return m.group(0)
        return m.group(0).replace(f"]({href}", f"]({new_href}", 1)

    for no, line in enumerate(text.split("\n"), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        new = WIKILINK_RE.sub(wiki_sub, line)
        new = MDLINK_RE.sub(md_sub, new)
        if new != line:
            changes.append((no, line, new))
        out_lines.append(new)
    return "\n".join(out_lines), changes


def rewrite_relations(text: str, mapping: dict[Path, Path], wiki_root: Path,
                      stems: dict[str, list[Path]]) -> tuple[str, list[tuple[int, str, str]]]:
    """Frontmatter relation values (``related: [old]``, ``- concepts/old``) pointed at the new pages."""
    if not text.startswith("---\n"):
        return text, []
    lines = text.split("\n")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() in ("---", "...")), None)
    if end is None:
        return text, []
    subs = []
    for old, new in mapping.items():
        unique = len(stems.get(old.stem, [])) == 1
        rel_old, rel_new = _rel(old, wiki_root).removesuffix(".md"), _rel(new, wiki_root).removesuffix(".md")
        subs.append((re.compile(rf"(?<![\w/.-]){re.escape(rel_old)}(?:\.md)?(?![\w/-])"), rel_new))
        if unique:
            subs.append((re.compile(rf"(?<![\w/.-]){re.escape(old.stem)}(?:\.md)?(?![\w/-])"), new.stem))
    changes = []
    key = None
    for i in range(1, end):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", lines[i])
        if m:
            key = m.group(1)
        if key not in RELATION_KEYS:
            continue
        line = lines[i]
        for rx, repl in subs:
            line = rx.sub(repl, line)
        if line != lines[i]:
            changes.append((i + 1, lines[i], line))
            lines[i] = line
    return "\n".join(lines), changes


def _wiki_files(cfg: WikiConfig) -> list[Path]:
    return sorted(p.resolve() for p in cfg.wiki_root.rglob("*.md") if not any(part.startswith(".") for part in
                                                                          p.relative_to(cfg.wiki_root).parts))


def _stems(files: list[Path]) -> dict[str, list[Path]]:
    out: dict[str, list[Path]] = {}
    for f in files:
        out.setdefault(f.stem, []).append(f)
    return out


def _outside_mentions(cfg: WikiConfig, olds: list[Path]) -> list[tuple[Path, int, str]]:
    """Lines in repo files outside the wiki (md, yml) that mention an old page path."""
    needles = [_rel(p, cfg.repo_root) for p in olds if p.is_relative_to(cfg.repo_root)]
    needles += [_rel(p, cfg.wiki_root) for p in olds]
    out = []
    for pattern in ("*.yml", "*.yaml", "docs/**/*.md", "*.md"):
        for f in cfg.repo_root.glob(pattern):
            if not f.is_file() or f.resolve().is_relative_to(cfg.wiki_root.resolve()):
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError:
                continue
            for no, line in enumerate(lines, 1):
                if any(n in line for n in needles):
                    out.append((f, no, line.strip()[:160]))
    return sorted(set(out))


def _link_edits(cfg: WikiConfig, plan: Plan, mapping: dict[Path, Path], moved: dict[Path, Path],
                skip: set[Path] = frozenset()) -> None:
    files = _wiki_files(cfg)
    stems = _stems(files)
    for f in files:
        if f in skip:
            continue
        text = plan.writes.get(f) or f.read_text(encoding="utf-8")
        new_text, changes = rewrite_links(text, f, moved.get(f, f), mapping, cfg.wiki_root, stems)
        new_text, rel_changes = rewrite_relations(new_text, mapping, cfg.wiki_root, stems)
        changes = sorted(changes + rel_changes)
        if changes:
            plan.edits[f] = changes
            plan.writes[f] = new_text
    ambiguous = [old.stem for old in mapping if len(stems.get(old.stem, [])) > 1]
    for stem in ambiguous:
        plan.notes.append(f"several pages are named '{stem}': only links with a path to it were rewritten")


# ---------------------------------------------------------------------------
# relink (W05)
# ---------------------------------------------------------------------------

def _new_path(cfg: WikiConfig, old: Path, new: str) -> Path:
    new = new.strip()
    if new.endswith("/"):
        return (cfg.wiki_root / new / old.name).resolve()
    if "/" in new:
        return (cfg.wiki_root / (new if new.endswith(".md") else f"{new}.md")).resolve()
    return (old.parent / (new if new.endswith(".md") else f"{slugify(new)}.md")).resolve()


def plan_relink(cfg: WikiConfig, old: str, new: str) -> Plan:
    """Rename or move a page and rewrite every link to it (P5)."""
    src = resolve_page(cfg, old)
    dst = _new_path(cfg, src, new)
    if dst == src:
        raise RefactorError("old and new are the same page")
    if dst.exists():
        raise RefactorError(f"{_rel(dst, cfg.wiki_root)} exists already")
    if not dst.is_relative_to(cfg.wiki_root.resolve()):
        raise RefactorError(f"{dst} is outside the wiki")
    plan = Plan("relink", moves=[(src, dst)])
    _link_edits(cfg, plan, {src: dst}, {src: dst})
    plan.outside = _outside_mentions(cfg, [src])
    plan.log_pages = [_rel(src, cfg.wiki_root), _rel(dst, cfg.wiki_root)]
    plan.log_note = f"{sum(len(c) for c in plan.edits.values())} link line(s) in {len(plan.edits)} file(s)"
    return plan


# ---------------------------------------------------------------------------
# merge (W06)
# ---------------------------------------------------------------------------

def _union(a: list, b: list) -> list:
    out = list(b)
    for x in a:
        if x not in out:
            out.append(x)
    return out


def _set_frontmatter(text: str, updates: dict) -> str:
    """Replace or add top-level frontmatter keys in ``text``; other lines stay as they are."""
    if not text.startswith("---\n"):
        raise RefactorError("page has no frontmatter")
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
    return "---\n" + "\n".join(lines) + text[end:]


def _drop_self_relations(text: str, path: Path, wiki_root: Path) -> str:
    """A page never relates to itself (after a merge, A's ``related: [B]`` would)."""
    import yaml
    fm_text, _, _ = split_frontmatter(text)
    data = (yaml.safe_load(fm_text or "") or {}) if fm_text else {}
    own = {path.stem, _rel(path, wiki_root), _rel(path, wiki_root).removesuffix(".md")}
    updates = {}
    for key in RELATION_KEYS:
        values = data.get(key)
        if isinstance(values, list):
            kept = [v for v in values if str(v).strip("[]") not in own]
            if kept != values:
                updates[key] = kept
    return _set_frontmatter(text, updates) if updates else text


def plan_merge(cfg: WikiConfig, a: str, b: str) -> Plan:
    """Merge page A into B: frontmatter union, A's aliases, A's body appended to B for folding in,
    A left as a redirect stub, links to A pointed at B (P2). Nothing is deleted."""
    pa, pb = resolve_page(cfg, a), resolve_page(cfg, b)
    if pa == pb:
        raise RefactorError("a page cannot be merged into itself")
    A, B = parse_page(pa, cfg.wiki_root), parse_page(pb, cfg.wiki_root)
    if A.frontmatter.get("redirect"):
        raise RefactorError(f"{A.rel} is already a redirect to {A.frontmatter['redirect']}")
    plan = Plan("merge")
    updates: dict = {}
    for key in LIST_KEYS:
        av, bv = A.list_field(key), B.list_field(key)
        if av:
            merged = _union(av, bv)
            if merged != bv:
                updates[key] = merged
    aliases = _union([x for x in (A.title, A.name) if x not in (B.title, B.name)], B.list_field("aliases"))
    aliases = _union(A.list_field("aliases"), aliases)
    if aliases != B.list_field("aliases"):
        updates["aliases"] = aliases
    for key in ("type", "scope"):
        if A.frontmatter.get(key) != B.frontmatter.get(key):
            plan.notes.append(f"{key} differs ({A.frontmatter.get(key)} vs {B.frontmatter.get(key)}): "
                              f"{B.rel} keeps {B.frontmatter.get(key)}")
    today = date.today().isoformat()
    if B.status in ("reviewed", "stable", "promoted"):
        updates["status"] = "draft"
        updates["reviewed"] = None
        plan.notes.append(f"{B.rel} was {B.status}; back to draft, its content changed")
    updates["updated"] = date.today()
    if str(B.frontmatter.get("author") or "") != str(A.frontmatter.get("author") or ""):
        updates["author"] = "mixed"

    _, a_body, _ = split_frontmatter(A.text)
    a_lines = a_body.strip("\n").split("\n")
    if a_lines and HEADING_RE.match(a_lines[0]) and a_lines[0].startswith("# "):
        a_lines = a_lines[1:]
    demoted = [("#" + ln) if HEADING_RE.match(ln) and not ln.startswith("######") else ln for ln in a_lines]
    files = _wiki_files(cfg)
    a_moved, _ = rewrite_links("\n".join(demoted), pa, pb, {}, cfg.wiki_root, _stems(files))   # re-base A's links
    b_text = _set_frontmatter(B.text, updates)
    b_text = (b_text.rstrip("\n") + f"\n\n## Merged from {A.title}\n\n"
              f"<!-- merged from {A.rel} on {today}: fold this into the sections above, then delete this "
              f"section -->\n\n" + a_moved.strip("\n") + "\n")
    plan.writes[pb] = b_text

    link = os.path.relpath(pb, pa.parent).replace(os.sep, "/")
    target = f"[[{pb.stem}]]" if cfg.link_style != "markdown" else f"[{B.title}]({link})"
    stub_text = (f"---\ntitle: {_dump(A.title)}\ntype: {A.type or 'concept'}\n"
                 f"scope: {A.frontmatter.get('scope') or 'general'}\nstatus: stub\nauthor: "
                 f"{A.frontmatter.get('author') or 'human'}\nupdated: {today}\nredirect: {_dump(B.rel)}\n"
                 f"aliases: []\ntags: []\nsources: []\n---\n\n# {A.title}\n\nMerged into {target} on {today}.\n")
    plan.writes[pa] = stub_text
    _link_edits(cfg, plan, {pa: pb}, {}, skip={pa})
    plan.writes[pb] = _drop_self_relations(plan.writes[pb], pb, cfg.wiki_root)
    plan.outside = _outside_mentions(cfg, [pa])
    plan.log_pages = [A.rel, B.rel]
    plan.log_note = f"{A.rel} into {B.rel}; {A.rel} is a redirect"
    return plan


# ---------------------------------------------------------------------------
# extract (W07)
# ---------------------------------------------------------------------------

def plan_extract(cfg: WikiConfig, page: str, section: str, name: str, ptype: str | None = None) -> Plan:
    """Move one H2 section of a page to a new page; the section keeps its first paragraph and a link (P1)."""
    src = resolve_page(cfg, page)
    P = parse_page(src, cfg.wiki_root)
    ptype = ptype or P.type or "concept"
    if ptype not in cfg.page_types:
        raise RefactorError(f"unknown page type '{ptype}'")
    lines = P.text.split("\n")
    want = section.strip().lower().lstrip("#").strip()
    h2 = [(i, text) for i, (lvl, text, line) in enumerate(P.headings) if lvl == 2]
    idx = next((line - 1 for lvl, text, line in P.headings if lvl == 2 and text.strip().lower() == want), None)
    if idx is None:
        raise RefactorError(f"no '## {section}' in {P.rel}; sections: {', '.join(t for _, t in h2)}")
    end = next((line - 1 for lvl, text, line in P.headings if lvl <= 2 and line - 1 > idx), len(lines))
    heading = lines[idx]
    content = lines[idx + 1:end]
    while content and not content[-1].strip():
        content.pop()
    paras: list[list[str]] = [[]]
    for ln in content:
        if ln.strip():
            paras[-1].append(ln)
        elif paras[-1]:
            paras.append([])
    paras = [p for p in paras if p]
    if not paras:
        raise RefactorError(f"'## {section}' is empty")
    lede = paras[0] if not paras[0][0].lstrip().startswith(("#", ">", "-", "*", "|", "!")) else []

    folder = cfg.wiki_root / cfg.page_types[ptype][0]
    dst = (folder / f"{slugify(name)}.md").resolve()
    if dst.exists():
        raise RefactorError(f"{_rel(dst, cfg.wiki_root)} exists already")
    title = name.replace("-", " ").strip()
    title = title[0].upper() + title[1:] if title else title
    cited = sorted({c.key for c in P.citations if idx + 1 < c.line <= end})     # file lines of the section
    new_text = _extracted_page(cfg, ptype, title, P, content, cited, heading.lstrip("#").strip())
    link = f"[[{dst.stem}]]" if cfg.link_style != "markdown" else \
        f"[{title}]({os.path.relpath(dst, src.parent).replace(os.sep, '/')})"
    kept = lede + ([""] if lede else []) + [f"See {link}."]
    new_src = lines[:idx + 1] + [""] + kept + ([""] if end < len(lines) else []) + lines[end:]
    plan = Plan("extract", writes={src: "\n".join(new_src), dst: new_text})
    plan.edits[src] = [(idx + 2, "(section body, %d lines)" % len(content), "\n".join(kept))]
    plan.notes.append(f"new page {_rel(dst, cfg.wiki_root)} ({ptype}, draft): fill its required sections")
    if P.status in ("reviewed", "stable", "promoted"):
        plan.writes[src] = _set_frontmatter(plan.writes[src], {"status": "draft", "reviewed": None})
        plan.notes.append(f"{P.rel} was {P.status}; back to draft, its content changed")
    plan.log_pages = [P.rel, _rel(dst, cfg.wiki_root)]
    plan.log_note = f"section '{heading.lstrip('#').strip()}' extracted"
    return plan


def _extracted_page(cfg: WikiConfig, ptype: str, title: str, P, content: list[str], cited: list[str],
                    section: str = "") -> str:
    """The new page from its type's template: the content goes under the section of the same name
    when the type has one ("Key facts" to "Key facts"), else in place of the lede."""
    from .scaffold import page_template
    text = page_template(cfg, ptype, title, P.list_field("tags"), str(P.frontmatter.get("scope") or "general"),
                         str(P.frontmatter.get("author") or "human"), status="draft")
    text = _set_frontmatter(text, {"sources": cited, "related": [P.name]})
    placeholder = "One-paragraph definition: what this is and why a reader would come here.\n"
    note = f"<!-- extracted from {P.rel} on {date.today().isoformat()} -->\n\n"
    names = {alt.strip().lower(): sec.split("|")[0] for sec in cfg.page_types[ptype][1] for alt in sec.split("|")}
    same = names.get(section.lower())
    if same and f"## {same}\n" in text:
        body = "\n".join(content).strip("\n") + "\n"
        return text.replace(f"## {same}\n", f"## {same}\n\n{note}{body}", 1)
    moved = [("#" + ln) if ln.startswith("### ") else ln for ln in content]   # H3 under the section -> H2
    body = "\n".join(moved).strip("\n") + "\n"
    if placeholder in text:
        return text.replace(placeholder, f"<!-- extracted from {P.rel} on {date.today().isoformat()} -->\n\n"
                            + body, 1)
    return text.rstrip("\n") + "\n\n" + body


# ---------------------------------------------------------------------------
# Showing and applying a plan
# ---------------------------------------------------------------------------

def describe(cfg: WikiConfig, plan: Plan) -> str:
    out = [f"{plan.op}: " + " -> ".join(plan.log_pages)]
    for a, b in plan.moves:
        out.append(f"  move {_rel(a, cfg.wiki_root)} -> {_rel(b, cfg.wiki_root)}")
    created = [p for p in plan.writes if not p.exists() and p not in {b for _, b in plan.moves}]
    for p in created:
        out.append(f"  create {_rel(p, cfg.wiki_root)}")
    rewritten = [p for p in plan.writes if p.exists() and p not in plan.edits]
    for p in rewritten:
        out.append(f"  rewrite {_rel(p, cfg.wiki_root)}")
    for f, changes in sorted(plan.edits.items()):
        out.append(f"  edit {_rel(f, cfg.wiki_root)}:")
        for no, before, after in changes:
            out.append(f"    {no}: {before.strip()[:110]}\n     -> {after.strip()[:110]}")
    for f, no, line in plan.outside:
        out.append(f"  check by hand {f.relative_to(cfg.repo_root).as_posix()}:{no}: {line}")
    for n in plan.notes:
        out.append(f"  note: {n}")
    return "\n".join(out)


def apply(cfg: WikiConfig, plan: Plan) -> None:
    moved = dict(plan.moves)
    for path, text in plan.writes.items():
        target = moved.get(path, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    for src, dst in plan.moves:
        if src not in plan.writes:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        src.unlink()          # the page lives on at dst; relink is a move, not a deletion
    append_log(cfg, plan.op, plan.log_pages, plan.log_note)
