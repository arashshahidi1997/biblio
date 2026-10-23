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
# link_style: markdown                        # how biblio writes links: markdown (relative paths) | wikilink
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
  task: {description: Behavioral task or paradigm, values: []}

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


def yaml_scalar(value: str) -> str:
    """A YAML scalar for one frontmatter value, quoted only when needed ("A: b", "#x", "yes")."""
    import yaml
    text = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=10_000).strip()
    return text[:-4].rstrip() if text.endswith("\n...") else text


def page_template(cfg: WikiConfig, ptype: str, title: str, tags: list[str], scope: str, author: str,
                  status: str = "stub") -> str:
    sections = cfg.page_types[ptype][1]
    tag_list = ", ".join(yaml_scalar(t) for t in tags)
    fm = (
        "---\n"
        f"title: {yaml_scalar(title)}\n"
        f"type: {ptype}\n"
        f"scope: {scope}\n"
        f"status: {status}\n"
        "reviewed: null\n"
        f"author: {author}\n"
        f"updated: {date.today().isoformat()}\n"
        "aliases: []\n"
        f"tags: [{tag_list}]\n"
        "sources: []\n"
        "evidence: []\n"
        "code: []\n"
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


def ensure_tags(cfg: WikiConfig, tags: list[str]) -> list[str]:
    """Add ``facet/value`` tags to the vocabulary; return the ones added.

    The value goes into its facet's ``values: [...]`` list, edited as text so
    comments and layout stay. An unknown facet is refused (likely a typo); add
    the facet to the vocabulary by hand first.
    """
    import yaml

    path = cfg.vocab
    if not tags or path is None or not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    namespaces = (yaml.safe_load(text) or {}).get("namespaces") or {}
    added = []
    for tag in tags:
        facet, sep, value = tag.lstrip("#").partition("/")
        if not sep or not facet or not value:
            raise ValueError(f"tag '{tag}' must be facet/value, e.g. event/ripple")
        if facet not in namespaces:
            raise ValueError(f"unknown facet '{facet}' in tag '{tag}'; known: {sorted(namespaces)}. "
                             f"Add it to {path.name} first.")
        if value in ((namespaces[facet] or {}).get("values") or []):
            continue
        text = _add_vocab_value(text, facet, value, path)
        namespaces[facet] = {**(namespaces[facet] or {}),
                             "values": [*((namespaces[facet] or {}).get("values") or []), value]}
        added.append(f"{facet}/{value}")
    if added:
        path.write_text(text, encoding="utf-8")
    return added


def _add_vocab_value(text: str, facet: str, value: str, path: Path) -> str:
    # the facet's block: its header line up to the next line at the same or a lower indent
    header = re.search(rf"^([ \t]*){re.escape(facet)}:.*$", text, re.M)
    if header:
        indent = len(header.group(1))
        end = len(text)
        for m in re.finditer(r"^([ \t]*)\S.*$", text[header.end():], re.M):
            if len(m.group(1)) <= indent:
                end = header.end() + m.start()
                break
        block = text[header.start():end]
        values = re.search(r"values:\s*\[([^\]]*)\]", block)
        if values:
            items = [v.strip() for v in values.group(1).split(",") if v.strip()]
            new_block = block[:values.start(1)] + ", ".join([*items, value]) + block[values.end(1):]
            return text[:header.start()] + new_block + text[end:]
    raise ValueError(f"cannot add '{facet}/{value}' to {path} automatically (values are not a [..] list); "
                     "add it by hand")


def stub(cfg: WikiConfig, name: str, ptype: str, *, title: str | None = None, tags: list[str] | None = None,
         scope: str = "general", author: str = "human", status: str = "stub", log: bool = True) -> Path:
    if ptype not in cfg.page_types:
        raise ValueError(f"unknown page type '{ptype}'; known: {sorted(cfg.page_types)}")
    slug = slugify(name)
    if ptype == "hub" and not slug.startswith("hub-"):
        slug = f"hub-{slug}"
    folder = cfg.wiki_root / cfg.page_types[ptype][0]
    path = folder / f"{slug}.md"
    if path.exists():
        raise FileExistsError(path)
    added = ensure_tags(cfg, tags or [])
    if added and log:
        append_log(cfg, "vocab", [cfg.vocab.name], "added " + ", ".join(added))
    folder.mkdir(parents=True, exist_ok=True)
    title = title or name.replace("-", " ").strip().capitalize()
    path.write_text(page_template(cfg, ptype, title, tags or [], scope, author, status), encoding="utf-8")
    if log:
        append_log(cfg, "stub", [path.relative_to(cfg.wiki_root).as_posix()], f"type {ptype}")
    return path


def init(cfg: WikiConfig, subject: str | None = None, tags: list[str] | None = None, *,
         title: str | None = None, author: str = "human") -> list[Path]:
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
    if not cfg.vocab_explicit:  # the config was loaded before this skeleton's vocab.yml existed
        cfg.vocab = root / "vocab.yml"
    if subject:
        created.append(stub(cfg, subject, "hub", title=title or subject.replace("-", " ").capitalize(),
                            tags=tags or [], author=author))
    return created
