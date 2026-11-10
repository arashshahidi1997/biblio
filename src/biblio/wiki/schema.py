"""Wiki schema defaults (wiki SPEC v0.2, docs/reference/wiki-spec.md) and the per-wiki configuration.

The defaults encode the page types, required sections, statuses and relation
keys of the wiki specification. A wiki can extend them in ``<wiki>/wiki.yml``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

STATUSES = ("stub", "draft", "reviewed", "stable", "promoted")
REVIEWED_STATUSES = ("reviewed", "stable", "promoted")
SCOPES = ("general", "project")
AUTHORS = ("human", "llm", "mixed")
# SPEC §9: knowledge moves one tier up, never sideways
TIERS = ("project", "personal", "lab")
ORIGIN_FIELDS = ("project", "path", "commit", "date")

# type -> (folder, required H2 sections). "A|B" accepts either heading.
PAGE_TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "concept": ("concepts", ("Why it matters", "Key facts", "Related")),
    "anatomy": ("anatomy", ("Structure", "Expected geometry", "Signatures", "Related")),
    "marker": ("markers", ("Signature", "Computation", "What it localizes|What it measures",
                           "Failure modes", "Evidence", "Our experience", "Implementation")),
    "method": ("methods", ("Goal", "Procedure", "Assumptions", "Outputs", "Failure modes", "Implementation")),
    "pitfall": ("pitfalls", ("Symptom", "Cause", "How to detect", "Mitigation", "Observed in")),
    "tool": ("tools", ("What and where|What/where", "Implements", "Inputs and outputs|Inputs/outputs",
                       "Tests", "Status")),
    "source": ("sources", ("Citation", "Contribution", "Key claims", "Figures", "Links")),
    "howto": ("howto", ("Goal", "Steps", "Done when")),
    "hub": ("hubs", ("Scope", "Reading order", "Pages")),
    "question": ("questions", ("Question", "Answer", "Fold into|Fold-into")),
    "case": ("cases", ("Data", "What it shows", "Figures", "Links")),
    # a question answered across papers: built from claims digests by wiki-synthesize
    "synthesis": ("syntheses", ("Question", "Definitions compared", "Agreement", "Disagreement|Contested",
                                "Open problems", "Related")),
}

RELATION_KEYS = (
    "related", "depends_on", "part_of", "localizes", "measured_by", "fails_by",
    "detected_by", "implemented_by", "example_of", "contradicts",
    "affects", "implements",  # inverses: pitfall -> markers it affects, tool -> what it implements
)

KNOWN_KEYS = (
    "title", "type", "scope", "status", "reviewed", "author", "updated", "aliases",
    "tags", "sources", "evidence", "code", "review_flags", "promoted_to",
    "match", "exclude_tags",       # hubs: which pages they list (match: any | all)
    "redirect",                    # a page merged into another (biblio wiki merge): the surviving page
    "origin",                      # a page moved up a tier: [{project, path, commit, date}] (SPEC §5, §9)
)

REQUIRED_KEYS = ("title", "type", "status", "scope")

# Files at the wiki root that are not pages
META_FILES = ("index.md", "log.md", "README.md", "SPEC.md", "SCHEMA.md", "RESOURCES.md",
              "BACKLOG.md", "skill-spec.md")

DEFAULT_PROJECT_TOKENS = (r"\bsub-\d+", r"\bses-\d+")


@dataclass
class WikiConfig:
    repo_root: Path
    wiki_root: Path
    bibliography: Path | None
    vocab: Path | None
    fulltext_root: Path
    link_roots: tuple[Path, ...]
    page_types: dict[str, tuple[str, tuple[str, ...]]] = field(default_factory=lambda: dict(PAGE_TYPES))
    relation_keys: tuple[str, ...] = RELATION_KEYS
    extra_keys: tuple[str, ...] = ()
    project_tokens: tuple[str, ...] = DEFAULT_PROJECT_TOKENS
    max_words: int = 800
    bibliography_explicit: bool = False      # set in wiki.yml; otherwise project defaults are merged
    vocab_explicit: bool = False             # set in wiki.yml; otherwise the wiki's own vocab.yml wins
    link_style: str = "markdown"        # "markdown" | "wikilink" (used when biblio writes links)
    tier: str = "project"               # SPEC §9: project | personal | lab
    name: str = ""                      # this wiki's name, the prefix in another wiki's promoted_to
    project_facets: tuple[str, ...] = ()  # tag facets stripped when a page moves up (SPEC §3)
    meta_files: tuple[str, ...] = META_FILES  # wiki-relative files that are not pages (+ wiki.yml meta_files)
    severity_overrides: dict[str, str] = field(default_factory=dict)  # lint code -> severity or "off"

    @property
    def known_keys(self) -> set[str]:
        return set(KNOWN_KEYS) | set(self.relation_keys) | set(self.extra_keys)

    def fulltext_path(self, citekey: str) -> Path:
        return self.fulltext_root / citekey / f"{citekey}.md"


def _first_existing(root: Path, candidates: tuple[str, ...]) -> Path | None:
    for rel in candidates:
        path = root / rel
        if path.is_file():
            return path
    return None


def wiki_vocab_path(repo_root: Path, wiki_root: Path | None = None) -> Path | None:
    """The wiki's tag vocabulary: ``vocab:`` in ``wiki.yml``, else ``<wiki>/vocab.yml``; None without one.

    When a project has a wiki this file is the project's one tag vocabulary (SPEC §3, W14).
    """
    wiki_root = wiki_root or repo_root / "docs" / "wiki"
    cfg_path = wiki_root / "wiki.yml"
    if cfg_path.is_file():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        if isinstance(data, dict) and data.get("vocab"):
            return (repo_root / str(data["vocab"])).resolve()
    own = wiki_root / "vocab.yml"
    return own.resolve() if own.is_file() else None


def load_wiki_config(repo_root: Path, wiki_root: Path | None = None) -> WikiConfig:
    """Load ``<wiki>/wiki.yml`` over the defaults. Paths in the file are repo-relative."""
    repo_root = repo_root.resolve()
    wiki_root = (wiki_root or repo_root / "docs" / "wiki").resolve()
    data: dict[str, Any] = {}
    cfg_path = wiki_root / "wiki.yml"
    if cfg_path.is_file():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    def rel(value: str | None) -> Path | None:
        return (repo_root / value).resolve() if value else None

    bibliography = rel(data.get("bibliography")) or _first_existing(
        repo_root, (".projio/render/compiled.bib", ".projio/biblio/merged.bib", "bib/main.bib"))
    vocab = wiki_vocab_path(repo_root, wiki_root)
    if vocab is None:
        legacy = repo_root / ".projio" / "biblio" / "tag_vocab.yml"
        vocab = legacy if legacy.is_file() else None
    fulltext_root = rel(data.get("fulltext_root")) or (repo_root / "bib" / "derivatives" / "docling")
    link_roots = tuple(rel(p) for p in data.get("link_roots", []) if p) or ()

    page_types = dict(PAGE_TYPES)
    for name, spec in (data.get("page_types") or {}).items():
        page_types[name] = (spec.get("folder", name + "s"), tuple(spec.get("sections", ())))

    return WikiConfig(
        repo_root=repo_root,
        wiki_root=wiki_root,
        bibliography=bibliography,
        vocab=vocab,
        fulltext_root=fulltext_root,
        link_roots=tuple(p for p in link_roots if p),
        page_types=page_types,
        relation_keys=RELATION_KEYS + tuple(data.get("relation_keys", ())),
        extra_keys=tuple(data.get("extra_keys", ())),
        project_tokens=tuple(data.get("project_tokens", DEFAULT_PROJECT_TOKENS)),
        max_words=int(data.get("max_words", 800)),
        link_style=str(data.get("link_style", "markdown")),
        tier=str(data.get("tier", "project")),
        name=str(data.get("name") or repo_root.name),
        project_facets=tuple(str(f).rstrip("/") for f in data.get("project_facets", ())),
        bibliography_explicit=bool(data.get("bibliography")),
        vocab_explicit=bool(data.get("vocab")),
        meta_files=META_FILES + tuple(str(f).strip("/") for f in data.get("meta_files") or () if f),
        severity_overrides=_severity_overrides(data.get("severity_overrides"), cfg_path),
    )


SEVERITY_LEVELS = ("error", "warning", "suggestion", "info", "off")


def _severity_overrides(value: Any, cfg_path: Path) -> dict[str, str]:
    """``severity_overrides: {TAG001: warning}``; "off" drops the finding."""
    out: dict[str, str] = {}
    for code, level in (value or {}).items():
        level = "off" if level is False else str(level).strip().lower()   # YAML reads a bare off as false
        if level not in SEVERITY_LEVELS:
            raise ValueError(f"{cfg_path}: severity_overrides.{code}: '{level}' is not one of "
                             f"{', '.join(SEVERITY_LEVELS)}")
        out[str(code).strip().upper()] = level
    return out
