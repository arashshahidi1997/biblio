"""Create the wiki skeleton and new pages from templates; append to log.md."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .hubs import HUBS_END, HUBS_START, PAGES_END, PAGES_START
from .schema import WikiConfig

WIKI_YML = """\
# Machine-readable part of this project's wiki binding (see SCHEMA.md / wiki SPEC §11).
# Paths are relative to the repository root. Every key is optional.

# bibliography: .projio/render/compiled.bib   # citekey checks (default: compiled.bib, then bib/main.bib)
# vocab: {vocab}                       # faceted tags (biblio tag_vocab format)
# fulltext_root: bib/derivatives/docling      # <root>/<citekey>/<citekey>.md, for quote checks
# link_roots: []                              # extra folders whose .md files links may point to
# link_style: wikilink                        # how biblio writes links: wikilink | markdown
# relation_keys: []                           # extra typed relations, e.g. [supports, opposes]
# extra_keys: []                              # extra frontmatter keys allowed
# project_tokens: ['\\bsub-\\d+', '\\bses-\\d+']   # flagged on scope: general pages
# max_words: 800
"""

VOCAB_YML = """\
# Faceted tag vocabulary (biblio tag_vocab format: namespace -> values).
# Pages write tags as facet/value (e.g. region/ca1); lint rejects unknown tags.
# Keep it small (about 50-80 values). Project facets carry a project prefix.

namespaces:
  region: {description: Anatomical region, values: []}
  signal: {description: Signal type or band, values: []}
  event: {description: Physiological event, values: []}
  state: {description: Brain or behavioral state, values: []}
  technique: {description: Method or analysis technique, values: []}
  device: {description: Recording device, values: []}
  species: {description: Species, values: []}

aliases: {}
"""

INDEX_MD = f"""\
---
title: Wiki index
type: meta
---

# Wiki index

Start from a hub. Pages are organized by type (folders) and by subject (tags and hubs).

## Hubs

{HUBS_START}
{HUBS_END}
"""

LOG_MD = """\
---
title: Wiki log
type: meta
---

# Wiki log

Append-only: date · operation · pages · note.
"""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def append_log(cfg: WikiConfig, op: str, pages: list[str], note: str = "") -> None:
    log = cfg.wiki_root / "log.md"
    if not log.exists():
        log.write_text(LOG_MD, encoding="utf-8")
    line = f"- {date.today().isoformat()} · {op} · {', '.join(pages) or '-'}{' · ' + note if note else ''}\n"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(line)


def page_template(cfg: WikiConfig, ptype: str, title: str, tags: list[str], scope: str, author: str) -> str:
    sections = cfg.page_types[ptype][1]
    tag_list = ", ".join(tags)
    fm = (
        "---\n"
        f"title: {title}\n"
        f"type: {ptype}\n"
        f"scope: {scope}\n"
        "status: stub\n"
        "reviewed: null\n"
        f"author: {author}\n"
        f"updated: {date.today().isoformat()}\n"
        "aliases: []\n"
        f"tags: [{tag_list}]\n"
        "sources: []\n"
        "review_flags: []\n"
        "related: []\n"
        "---\n\n"
    )
    body = [f"# {title}\n"]
    if ptype != "hub":
        body.append("One-paragraph definition: what this is and why a reader would come here.\n")
    for section in sections:
        name = section.split("|")[0]
        body.append(f"## {name}\n")
        if ptype == "hub" and name == "Pages":
            body.append(f"{PAGES_START}\n{PAGES_END}\n")
    return fm + "\n".join(body)


def stub(cfg: WikiConfig, name: str, ptype: str, *, title: str | None = None, tags: list[str] | None = None,
         scope: str = "general", author: str = "human", log: bool = True) -> Path:
    if ptype not in cfg.page_types:
        raise ValueError(f"unknown page type '{ptype}'; known: {sorted(cfg.page_types)}")
    slug = slugify(name)
    if ptype == "hub" and not slug.startswith("hub-"):
        slug = f"hub-{slug}"
    folder = cfg.wiki_root / cfg.page_types[ptype][0]
    path = folder / f"{slug}.md"
    if path.exists():
        raise FileExistsError(path)
    folder.mkdir(parents=True, exist_ok=True)
    title = title or name.replace("-", " ").strip().capitalize()
    path.write_text(page_template(cfg, ptype, title, tags or [], scope, author), encoding="utf-8")
    if log:
        append_log(cfg, "stub", [path.relative_to(cfg.wiki_root).as_posix()], f"type {ptype}")
    return path


def init(cfg: WikiConfig, subject: str | None = None, tags: list[str] | None = None) -> list[Path]:
    """Create the skeleton (idempotent: existing files are kept) and an optional first hub."""
    root = cfg.wiki_root
    root.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for folder, _ in cfg.page_types.values():
        (root / folder).mkdir(exist_ok=True)
    try:
        vocab_rel = (root / "vocab.yml").relative_to(cfg.repo_root).as_posix()
    except ValueError:
        vocab_rel = "vocab.yml"
    files = {
        "wiki.yml": WIKI_YML.format(vocab=vocab_rel),
        "vocab.yml": VOCAB_YML,
        "index.md": INDEX_MD,
        "log.md": LOG_MD,
    }
    for name, content in files.items():
        path = root / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(path)
    if created:
        append_log(cfg, "init", [p.name for p in created], "skeleton")
    if subject:
        created.append(stub(cfg, subject, "hub", title=subject.replace("-", " ").capitalize(), tags=tags or []))
    return created
