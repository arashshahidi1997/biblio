"""`biblio wiki ...` and `biblio skills ...` subcommands."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..paths import find_repo_root
from .schema import load_wiki_config


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p.add_argument("--wiki", type=Path, help="Wiki folder, relative to the root (default: docs/wiki).")


def add_parsers(sub) -> None:
    p_wiki = sub.add_parser("wiki", help="Build and maintain the project knowledge wiki.")
    wsub = p_wiki.add_subparsers(dest="wiki_cmd", required=True)

    p = wsub.add_parser("init", help="Create the wiki skeleton (idempotent) and optionally a first hub.")
    _common(p)
    p.add_argument("--subject", help="Create a hub for this subject, e.g. layer-identification.")
    p.add_argument("--tag", action="append", default=[], help="Hub tag (facet/value); repeatable.")

    p = wsub.add_parser("stub", help="Create a page from its type's template.")
    _common(p)
    p.add_argument("name", help="Page name; turned into a kebab-case basename.")
    p.add_argument("--type", required=True, help="Page type (concept, method, marker, pitfall, source, hub, ...).")
    p.add_argument("--title", help="Page title (default: from the name).")
    p.add_argument("--tag", action="append", default=[], help="Tag (facet/value); repeatable.")
    p.add_argument("--scope", default="general", choices=["general", "project"])
    p.add_argument("--author", default="human", choices=["human", "llm", "mixed"])
    p.add_argument("--status", default="stub", choices=["stub", "draft"],
                   help="Initial status (draft pages get the full structure checks).")

    p = wsub.add_parser("lint", help="Detect deviations from the wiki principles (exit 1 on errors).")
    _common(p)
    p.add_argument("paths", nargs="*", type=Path, help="Limit page checks to these files.")
    p.add_argument("--format", default="text", choices=["text", "json", "tsv"])
    p.add_argument("--min-severity", default="info", choices=["error", "warning", "suggestion", "info"],
                   help="Hide findings below this severity.")

    p = wsub.add_parser("hubs", help="Regenerate hub page lists and the hub index.")
    _common(p)
    p.add_argument("--check", action="store_true", help="Only report stale views (exit 1 if any).")

    p = wsub.add_parser("status", help="Pages by type and status, review queue, open flags.")
    _common(p)
    p.add_argument("--format", default="text", choices=["text", "json"])

    p = wsub.add_parser("embeds", help="Files pages embed and their annex state; fetch or unlock them.")
    _common(p)
    p.add_argument("--get", action="store_true", help="Fetch annexed files whose content is not here.")
    p.add_argument("--unlock", action="store_true",
                   help="Unlock annexed files so Obsidian shows them (it ignores symlinks).")

    p = wsub.add_parser("figure", help="Markdown that embeds a paper's figure with caption and citation.")
    _common(p)
    p.add_argument("citekey")
    p.add_argument("number", help="Figure number, or a file stem such as pic-02 (see the figures manifest).")
    p.add_argument("--page", type=Path, help="The page it goes on, for the relative path (default: sources/).")

    p = wsub.add_parser("review", help="Human review: packets for the reviewer, and recording decisions.")
    rsub = p.add_subparsers(dest="review_cmd", required=True)
    r = rsub.add_parser("packet", help="What a reviewer needs to judge pages (default: the review queue).")
    _common(r)
    r.add_argument("pages", nargs="*", help="Pages (path or basename); default: every draft written by an agent.")
    r.add_argument("--out", type=Path, help="Write the packets to this markdown file.")
    r = rsub.add_parser("accept", help="Record a person's acceptance: status reviewed and reviewed: {by, date}.")
    _common(r)
    r.add_argument("page")
    r.add_argument("--by", required=True, help="The reviewer's name (a person; agents never review).")
    r.add_argument("--stable", action="store_true", help="Advance a reviewed page to stable.")
    r.add_argument("--resolve-flags", action="store_true", help="The reviewer settled the open review flags.")
    r.add_argument("--date", help="Review date (default: today).")
    r = rsub.add_parser("flag", help="Record a change the reviewer asks for (adds to review_flags).")
    _common(r)
    r.add_argument("page")
    r.add_argument("text")
    r = rsub.add_parser("reopen", help="Send a reviewed page back to draft (e.g. after a material change).")
    _common(r)
    r.add_argument("page")
    r.add_argument("--reason", default="")

    p_sk = sub.add_parser("skills", help="Agent skills shipped with biblio.")
    sksub = p_sk.add_subparsers(dest="skills_cmd", required=True)
    sksub.add_parser("list", help="List bundled skills.")
    p = sksub.add_parser("install", help="Copy bundled skills into a project.")
    p.add_argument("names", nargs="*", help="Skills to install (default: all).")
    p.add_argument("--root", type=Path, help="Repository root (default: auto-detect from cwd).")
    p.add_argument("--dest", type=Path, help="Target folder (default: <root>/.claude/skills).")
    p.add_argument("--force", action="store_true", help="Overwrite existing copies.")


def _cfg(args):
    repo_root = args.root.expanduser().resolve() if args.root else find_repo_root()
    wiki_root = (repo_root / args.wiki).resolve() if args.wiki else None
    return load_wiki_config(repo_root, wiki_root)


def run(args) -> None:
    if args.command == "skills":
        from ..skills_bundle import install, list_skills
        if args.skills_cmd == "list":
            for name, desc in list_skills():
                print(f"{name}\n    {desc}")
            return
        repo_root = args.root.expanduser().resolve() if args.root else find_repo_root()
        dest = (args.dest or repo_root / ".claude" / "skills").resolve()
        dest.mkdir(parents=True, exist_ok=True)
        for name, action in install(dest, args.names or None, force=args.force):
            print(f"{name}: {action} -> {dest / name}")
        return

    cfg = _cfg(args)
    rel = lambda p: p.relative_to(cfg.repo_root).as_posix() if p.is_relative_to(cfg.repo_root) else str(p)  # noqa: E731

    if args.wiki_cmd == "init":
        from .scaffold import init
        try:
            created = init(cfg, subject=args.subject, tags=args.tag)
        except (ValueError, FileExistsError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        for path in created:
            print(f"created {rel(path)}")
        if not created:
            print(f"{rel(cfg.wiki_root)}: skeleton already present")
        return

    if args.wiki_cmd == "stub":
        from .scaffold import stub
        try:
            path = stub(cfg, args.name, args.type, title=args.title, tags=args.tag,
                        scope=args.scope, author=args.author, status=args.status)
        except (ValueError, FileExistsError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print(f"created {rel(path)}")
        return

    if args.wiki_cmd == "embeds":
        from .embeds import apply, find_embeds
        embeds = find_embeds(cfg)
        for action, paths, code in apply(cfg, embeds, get=args.get, unlock=args.unlock):
            print(f"{action}: {len(paths)} file(s)" + ("" if code == 0 else f" (exit {code})"))
        for e in embeds:
            print(f"{e.state:8} {rel(e.path)}  <- {e.page.rel}:{e.line}")
        if not embeds:
            print("no embedded files")
        counts = {s: sum(e.state == s for e in embeds) for s in ("file", "locked", "absent", "missing")}
        print(", ".join(f"{v} {k}" for k, v in counts.items() if v) or "")
        raise SystemExit(1 if counts["absent"] or counts["missing"] else 0)

    if args.wiki_cmd == "figure":
        from .embeds import figure_embed
        page = args.page.expanduser().resolve() if args.page else None
        try:
            print(figure_embed(cfg, args.citekey, args.number, page), end="")
        except (FileNotFoundError, LookupError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        return

    if args.wiki_cmd == "review":
        from . import review as rv
        try:
            if args.review_cmd == "packet":
                paths = [rv.resolve_page(cfg, n) for n in args.pages] or rv.queue(cfg)
                text = "\n".join(rv.packet(cfg, p) for p in paths) or "review queue is empty\n"
                if args.out:
                    args.out.write_text(f"# Review packets ({len(paths)} pages)\n\n" + text, encoding="utf-8")
                    print(f"{len(paths)} packet(s) -> {args.out}")
                else:
                    print(text)
                return
            path = rv.resolve_page(cfg, args.page)
            if args.review_cmd == "accept":
                print(rv.accept(cfg, path, args.by, stable=args.stable, resolve_flags=args.resolve_flags,
                                on=args.date))
            elif args.review_cmd == "flag":
                print("flagged: " + rv.flag(cfg, path, args.text))
            else:
                print(rv.reopen(cfg, path, args.reason))
        except rv.ReviewError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        return

    if args.wiki_cmd == "lint":
        from .lint import SEVERITIES, format_findings, lint, page_count
        if not cfg.wiki_root.is_dir():
            print(f"error: no wiki at {rel(cfg.wiki_root)} (run `biblio wiki init`)", file=sys.stderr)
            raise SystemExit(2)
        from .lint import resolve_page_args
        paths = None
        if args.paths:
            paths, unmatched = resolve_page_args(cfg, args.paths)
            if unmatched:
                print(f"error: no wiki page matches {', '.join(unmatched)}", file=sys.stderr)
                raise SystemExit(2)
        findings = lint(cfg, paths)
        keep = SEVERITIES[: SEVERITIES.index(args.min_severity) + 1]
        shown = [f for f in findings if f.severity in keep]
        print(format_findings(shown, args.format, len(paths) if paths else page_count(cfg)))
        raise SystemExit(1 if any(f.severity == "error" for f in findings) else 0)

    if args.wiki_cmd == "hubs":
        from .hubs import regenerate, stale_views
        if args.check:
            stale = stale_views(cfg)
            for path in stale:
                print(f"stale {rel(path)}")
            raise SystemExit(1 if stale else 0)
        written = regenerate(cfg)
        for path in written:
            print(f"updated {rel(path)}")
        if not written:
            print("all generated views are current")
        return

    if args.wiki_cmd == "status":
        from .status import format_status, status
        print(format_status(status(cfg), args.format))
        return

    raise SystemExit(2)
