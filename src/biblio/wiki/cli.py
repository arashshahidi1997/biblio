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
        created = init(cfg, subject=args.subject, tags=args.tag)
        for path in created:
            print(f"created {rel(path)}")
        if not created:
            print(f"{rel(cfg.wiki_root)}: skeleton already present")
        return

    if args.wiki_cmd == "stub":
        from .scaffold import stub
        try:
            path = stub(cfg, args.name, args.type, title=args.title, tags=args.tag,
                        scope=args.scope, author=args.author)
        except (ValueError, FileExistsError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print(f"created {rel(path)}")
        return

    if args.wiki_cmd == "lint":
        from .lint import SEVERITIES, format_findings, lint, page_count
        if not cfg.wiki_root.is_dir():
            print(f"error: no wiki at {rel(cfg.wiki_root)} (run `biblio wiki init`)", file=sys.stderr)
            raise SystemExit(2)
        paths = [p.resolve() for p in args.paths] if args.paths else None
        findings = lint(cfg, paths)
        keep = SEVERITIES[: SEVERITIES.index(args.min_severity) + 1]
        shown = [f for f in findings if f.severity in keep]
        print(format_findings(shown, args.format, None if paths else page_count(cfg)))
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
