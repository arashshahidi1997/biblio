---
title: LLM-maintained knowledge wiki — specification
type: meta
status: draft
version: 0.2-draft
updated: 2026-11-06
---

# LLM-maintained knowledge wiki — specification (v0.2-draft)

This is the canonical copy (biblio W13). It was first written for pixecog
(`docs/wiki/SPEC.md` there, v0.1-draft, 2026-10-22), which now points here, so
the method and the tools that apply it ([wiki toolkit](../explanation/wiki.md),
`biblio wiki`) version together. v0.2 adds the three-tier lifecycle (§9), the
`origin` key and tier prefixes (§5), relative markdown links as the link style
(§6, §10, §12) and the `synthesis` page type (§4) (lit-studio R44, D23, D28).

A portable method for a research project (or lab) to build a **knowledge wiki** that an LLM agent
helps write and maintain and humans review. Project-neutral: each adopting project adds a short
**binding file** (its `SCHEMA.md`) with paths, tools and vocabulary extensions (§11).
Background and prior art: pixecog `docs/wiki/RESOURCES.md`.

## 1. Idea

- The wiki holds **durable knowledge** — concepts, anatomy/structures, measurable markers, methods,
  pitfalls, tools, sources — that does not depend on when or where it was learned. It is *not* a
  diary (notes/logs), a results record (analysis docs), or API documentation (code docs).
- Three layers (Karpathy LLM-wiki pattern):
  1. **Raw sources — immutable.** Literature full text (e.g. docling markdown), paper digests,
     the project record (notes, analysis state docs), code. The wiki cites them, never edits them.
  2. **The wiki — maintained.** Small, linked markdown pages, compiled from sources by the agent,
     reviewed by humans.
  3. **The schema — rules.** This spec + the project binding. Agents follow; humans amend.
- **Lifecycle:** projects *develop* knowledge; a personal knowledge base and then a lab hub
  *integrate* it (§9).

## 2. Principles

Every lint signal and refactor operation (§7–8) serves one of these.

| ID | Principle | Meaning | Origin |
|---|---|---|---|
| P1 | **Atomicity** | one idea per page; split when a second idea appears | Zettelkasten; Matuschak |
| P2 | **Single source of truth** | each fact lives in one page; others link (DRY) | software DRY; Matuschak |
| P3 | **Title + lede = interface** | concept-oriented title and a one-paragraph definition; linking pages quote at most the lede | Matuschak |
| P4 | **One mode per page** | tutorial / how-to / reference / explanation are not mixed | Diataxis |
| P5 | **Associative over hierarchical** | folders only for page type; subject via tags and links | Matuschak |
| P6 | **Grow, don't pre-build** | pages start as stubs; structure emerges; hubs appear at the "squeeze point" | Appleton; Milo (LYT) |
| P7 | **Explicit epistemic status** | growth stage, human review, contested/outdated marks are visible | Appleton |
| P8 | **Source fidelity** | every claim traceable; numbers and quotes verbatim from their source | Karpathy; Astro-Han |
| P9 | **Never silently rewrite history** | contradictions recorded side by side; superseded content marked, not deleted | Astro-Han |
| P10 | **Knowledge ≠ findings** | general knowledge separated from the project's own results | this spec |
| P11 | **Humans own judgment** | agents draft and propose; humans review, accept, promote | this spec |
| P12 | **Derived views are caches** | hub listings and indexes are generated, never hand-maintained | nvk/llm-wiki |

## 3. Organization — two axes plus views

1. **Folders = page type** (single-valued; maps to Diataxis):
   `concepts/ anatomy/ markers/ methods/ pitfalls/ tools/ sources/ howto/ cases/ questions/ syntheses/ hubs/ tutorial/ assets/`
   (rename `anatomy/`/`markers/` to fit the domain, e.g. `structures/`/`signatures/`). No topic folders.
2. **Tags = subject** (multi-valued) from one **controlled, faceted vocabulary**
   (`vocab.yml` in biblio's `tag_vocab` format, `namespace:value`; written `namespace/value` in
   pages because Obsidian nested tags cannot contain `:`).
   - **One file per project.** When the project has a wiki, its `vocab.yml` (or the file `vocab:`
     names in `wiki.yml`) is the project's tag vocabulary: biblio's library tagging
     (`library.yml` tags, autotag, `library lint`) reads the same file. Without a wiki, biblio
     uses `.projio/biblio/tag_vocab.yml`.
   - General facets (movable), e.g. `region/ signal/ event/ state/ technique/ device/ species/`.
   - Project facets prefixed with the project (e.g. `px-analysis/`, `px-hypothesis/`), declared in
     `wiki.yml` as `project_facets`; stripped when a page moves up a tier (§9).
   - Keep it small (~50–80 values); lint reports unknown tags (`TAG001`, an error unless the
     wiki sets `severity_overrides: {TAG001: warning}` in `wiki.yml`, for a vocabulary that is
     linted rather than enforced). `biblio wiki lint --tag-candidates` lists them with page counts.
3. **Hubs = views** (`hubs/hub-<name>.md`): a curated reading order + a **generated** list of pages
   carrying the hub's tag(s) (P12). A page appears in every hub it is relevant to. Tutorials are
   ordered paths through pages.
4. **Typed relations** in frontmatter give the fine graph (§5).

## 4. Page types

| type | Diataxis | Required sections |
|---|---|---|
| `concept` | explanation | Definition (lede) · Why it matters · Key facts (cited) · Related |
| `anatomy` | explanation / reference | Structure · Expected geometry (species, cited) · Signatures · Related |
| `marker` | explanation + reference | Signature (physics) · Computation · What it localizes/measures · Failure modes (→ pitfalls) · Evidence · Our experience · Implementation (→ tools) |
| `method` | explanation / how-to | Goal · Procedure · Assumptions · Outputs · Failure modes · Implementation |
| `pitfall` | explanation | Symptom · Cause · How to detect · Mitigation · Observed in (→ cases) |
| `tool` | reference | What/where (path, function) · Implements · Inputs/outputs · Tests · Status — link code, don't re-document APIs |
| `source` | reference | Citation · Contribution to the subject · Key claims (with source section) · Figures · Links (full text, digest) |
| `synthesis` | explanation | Question · Definitions compared · Agreement · Disagreement (or Contested) · Open problems · Related — a question answered across papers, built from claims digests; own reasoning marked **Synthesis:** |
| `howto` | how-to | Goal · Steps · Done when |
| `hub` | — (navigation) | Scope · Reading order · Pages (generated) |
| `question` | — (folded, never moved) | Question · Answer (cited) · Date · Fold-into target |
| `case` | — (project only) | Data · What it shows · Figures · Links to project record |
| `tutorial` | tutorial | Quarto `.qmd` learning path built on pages |

## 5. Frontmatter

```yaml
---
title: Ripple-band kurtosis peak
type: marker
scope: general            # general (movable) | project
status: draft             # stub | draft | reviewed | stable | promoted
reviewed: null            # {by: <human>, date: YYYY-MM-DD} — humans only
author: llm               # human | llm | mixed
updated: 2026-10-22
aliases: []
tags: [region/ca1, event/ripple, technique/layer-identification]
sources: [buzsaki_2015_HippocampalSharp]     # citekeys
evidence: []              # project record IDs (analysis IDs, note ids)
code: [path/to/module.py::function]           # code anchors
review_flags: []          # open issues for the reviewer
# typed relations — lists of links (relative paths, or wikilinks where bound); closed vocabulary:
related: []
depends_on: []
part_of: []
localizes: []
measured_by: []
fails_by: []
detected_by: []
implemented_by: []
example_of: []
contradicts: []
# moves between tiers (§9)
promoted_to: null         # on the page left behind: <tier-wiki>:<path>, e.g. lit-studio:concepts/x.md
origin: []                # on the receiving page: [{project, path, commit, date}], one entry per move
---
```

- `promoted_to` carries the receiving wiki's name as a prefix (`lit-studio:…`, `sirocampus:…`),
  so a reader of the project page knows which tier holds the general text.
- `origin` is provenance on the receiving page: the wiki it came from (`project`), its path there,
  the commit that held it, and the date of the move. A page moved twice (project → personal → lab)
  keeps both entries, oldest first.

## 6. Writing rules

1. **Names**: unique, descriptive kebab-case basenames across the docs tree; hub/topic index pages
   are not linked as content.
2. **Links**: relative markdown links, `[label](../markers/ripple-band-kurtosis.md)`, the tooling
   default (`link_style: markdown`): they render unchanged in Obsidian, VS Code, mkdocs, Quarto and
   GitHub, and `biblio wiki relink` keeps them resolvable on moves. `[[basename]]` wikilinks are an
   optional binding (`link_style: wikilink` in `wiki.yml`); lint accepts both. No page embeds
   (`![[…]]`).
3. **Citations**: pandoc `[@citekey]`; every literature claim cites; source pages give the section.
4. **Knowledge vs findings (P10)**: project results only in an "Our experience" section or a
   `case` page, cited by stable ID; never stated as general fact.
5. **Status marks (P7, P9)**: `> **Contested.** …`, `> **Outdated.** …`, `> **Unverified.** …` blockquotes.
6. **Portable markdown**: `$…$` math, fenced mermaid, plain tables, relative images and links;
   nothing tool-specific.
7. **Neutral, audience-facing language**; state species/system scope.
8. **No code bodies**; link code anchors.
9. **Protected pages (P11)**: agents edit `stub`/`draft` pages; for `reviewed`/`stable` pages they
   propose a diff.

## 7. Operations

| Op | Does | Key rules |
|---|---|---|
| **init** | add a hub + tags for a new subject (and the wiki skeleton on first use) | no content pages |
| **ingest** `<source>` | read a source (paper full text, note, analysis doc, code module) → update/create the pages it touches, atomic from the start | show the plan when > 3 pages change; cite locations; log |
| **query** `<question>` | answer from the wiki; fall back to full-text search over sources, marked *not yet in wiki* | optionally file as `question` page |
| **lint** | **detect only**: structure, provenance, code anchors, source fidelity, semantics; emit refactor suggestions | fixes only mechanical issues on unprotected pages |
| **refactor** `<op>` | **restructure** toward the principles (§8) | dry-run → log → one commit per refactor |
| **review** `<page>` | human sets `reviewed:`, advances status | agents never self-review |
| **promote** | gate check and plan for moving pages to the next tier (§9) | gated; read-only; starts from a page list or a tag |
| **integrate** | the receiving tier writes the moved page and logs it (§9) | only the receiving tier writes; human approval |

Rhythm: lint after every ingest; refactor when suggestions accumulate or before a review or a move.

## 8. Lint signals → principle → refactor

| Signal (lint) | Principle | Refactor op |
|---|---|---|
| page too long (e.g. > 800 words / > 5 H2) or second idea | P1 | **extract** section → new page; leave lede summary + link |
| page mixes Diataxis modes | P4 | **extract** by mode (e.g. pitfall essay out of a marker page) |
| other pages link to one of its sections | P1, P3 | **extract** that section |
| concept mentioned on ≥ 3 pages without its own page | P6 | **stub** new page |
| same explanation written in two places | P2 | **extract** + link from both |
| two pages with heavy overlap (semantic search) | P2 | **merge** (frontmatter union, aliases, redirect stub, never delete) |
| page renamed / moved / retyped | P5 | **relink** (rewrite all inbound links) |
| answered `question` belongs to a page | P2 | **fold** into target, mark question folded |
| ≥ 5 pages share a tag, no hub | P6 | **hub** create |
| claim without source / number not verbatim in source | P8 | flag (`review_flags`) — no auto-fix |
| page contradicts newer source or evidence | P9 | add `Contested`/`Outdated` block + `contradicts` link — no silent edit |
| project number on a `scope: general` page | P10 | move to "Our experience" / case |
| unknown tag / relation key | §3, §5 | fix or extend vocab (human) |
| hand-edited hub listing | P12 | regenerate |

Refactors must run **headless** (no editor/app required), keep every link resolvable, and append
`log.md`: date, op, pages before → after, reason, principle.

## 9. Lifecycle — three tiers

Knowledge moves up through three tiers, one step at a time:

1. **project** — a research project's wiki (e.g. pixecog): develops pages from its data, code and
   reading; keeps dataset pages, cases and its own findings.
2. **personal** — the researcher's field knowledge base (e.g. lit-studio): general field pages
   gathered from all of their projects.
3. **lab** — the lab hub (e.g. sirocampus): pages the lab has reviewed and shares.

A wiki states its tier in `wiki.yml` (`tier: project | personal | lab`, default `project`) and
its name (`name:`, default the repository folder name), which is the prefix in `promoted_to`.

**Page status:** `stub` → `draft` → `reviewed` → `stable` (reviewed + lint-clean + in use). The
page left behind after a move is marked `promoted`.

**Gates.** Each step has its own gate; `biblio wiki promote` checks it and prints the plan.

| Step | Gate |
|---|---|
| project → personal | `scope: general`; lint-clean; every general claim cites a held source (`sources:` not empty, citekeys held, quotes exact). Claims that rest only on project records stay in "Our experience". No review is needed at this step. |
| personal → lab | `scope: general`; `status` reviewed or stable; lint-clean; every citekey in the lab hub's bibliography; no project findings outside "Our experience". |

`case` and `question` pages never move.

**A move is a move, not a copy.**

- Either side may start it: the personal tier when it needs a page, or the project through a note
  that gives the page's path and commit. Only the receiving tier writes the moved page.
- The receiving page gets an `origin:` entry (§5); project facets, `evidence:` IDs and the
  "Our experience" section stay behind.
- The page left behind shrinks to its lede, a link to the moved page, "Our experience" and its
  project facets, with `status: promoted` and `promoted_to: <tier-wiki>:<path>`.
- Both `log.md` files get an `integrate` entry.
- **Never sideways**: pages do not move between two projects, or between two wikis of the same
  tier. A project that needs another project's knowledge links to the tier above.

**Tags.** `wiki-<subject>-v0.1` is a tier's own first-review milestone (a tagged commit in that
wiki's repository). Promotion tags towards the lab (`wiki-<subject>-vX.Y`) are cut in the personal
tier, and the lab-side commit references the tag.

**Visibility.** A wiki enters its project's public docs navigation only after its `v0.1`; before
that the working view is the editor (Obsidian or VS Code).

## 10. Rendering compatibility

| | Obsidian | mkdocs | Quarto |
|---|---|---|---|
| relative markdown links | native (relative link format) | native | native |
| `[[wikilinks]]` (optional binding) | native | `mkdocs-ezlinks` | not rendered |
| YAML frontmatter | properties | ignored | native |
| `[@citekey]` | text / citations plugin | `mkdocs-bibtex` | native |
| math, mermaid | ✓ | `pymdownx.arithmatex`, `superfences` | ✓ |
| tags `facet/value` | nested tags | (tags plugin optional) | metadata |

Obsidian vault root = the project root, so links into `bib/derivatives/` resolve (settings:
biblio's [editor how-to](../how-to/wiki-editors.md)).

## 11. Adopting in a project — the binding file (`SCHEMA.md`)

A project declares only:
1. **Raw source locations** (full text, digests, notes, analysis docs, code roots).
2. **Bibliography** file used for citekey checks.
3. **Search tool** for query/merge detection (e.g. an existing RAG index; no new vector DB required).
4. **Vocabulary extension**: its project facets and values (`project_facets` in `wiki.yml`).
5. **Tier and next tier**: this wiki's `tier` and `name`, and the wiki one tier up (repo + docs
   path) with the type → section mapping there.
6. **Rendering**: which of Obsidian / mkdocs / Quarto it uses.
7. **First subject** (one hub) — start with one, grow by demand (P6).
8. **Decisions log** (project-specific choices).

The machine-readable part lives in `wiki.yml` next to the pages; `biblio wiki init` writes a
commented template. Two keys tune lint for the project: `meta_files` (wiki-relative files that
are not pages, such as a generated `terms.md`, added to the defaults `index.md`, `log.md`,
`README.md`, `SCHEMA.md`, ...) and `severity_overrides` (lint code to `error`, `warning`,
`suggestion`, `info` or `off`).

## 12. Open questions

1. ~~Link style.~~ Settled (biblio W03, 2026-10-22): relative markdown links; wikilinks are an
   optional binding (§6.2).
2. Vocabulary governance: who approves new facet values; when project values become general.
3. Lab-hub layout: the hub currently uses `concepts/<topic>/` folders. Adopting type folders + hubs
   there is the lab's decision and is specified with the lab (sirocampus D20), not here.
