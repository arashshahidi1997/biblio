# Wiki toolkit

**Status:** Proposed; phase 1 implemented (`src/biblio/wiki/`, skills in `src/biblio/skills/`)
**Date:** 2026-10-22

biblio builds and maintains a project's knowledge wiki: small, linked markdown
pages about concepts, methods, markers, pitfalls, tools and sources, drafted
with an agent and reviewed by people. The method (principles P1 to P12, page
types, frontmatter, lifecycle) is defined in the wiki specification first
written for pixecog (`docs/wiki/SPEC.md` there). This page defines what biblio
provides to apply it.

## Who does what

| Actor | Does | Never does |
|-------|------|------------|
| **Editor** (Obsidian or VS Code) | read, write, navigate (backlinks, hover previews, search), review (set `status`, `reviewed`), work through queues | validate, restructure across files |
| **biblio CLI** (deterministic, no LLM) | create skeleton and stubs, lint, regenerate hubs and views, refactor across files, check quotes against sources, report status, build review packets, record a named person's review decision | judge content, decide a review |
| **Skills** (agent, LLM) | ingest sources, synthesize across sources, answer questions, propose refactors, prepare reviews | edit reviewed pages directly, review its own work |

Every CLI write is a plain file change in git, so the editor and the CLI never
disagree about state. The CLI runs after editor sessions (lint) and before
reviews (lint, hubs).

## Commands

`biblio wiki <command>`. The wiki root defaults to `docs/wiki`; an optional
`wiki.yml` in that folder holds the machine-readable part of the project
binding (bibliography, vocabulary, extra relation keys, project tokens).

| Command | Does | Principle | Phase |
|---------|------|-----------|-------|
| `init [--subject NAME --tag T]` | type folders, `wiki.yml`, `vocab.yml`, `index.md`, `log.md`, first hub | P6 | 1 |
| `stub NAME --type TYPE` | new page from the type's template, with required sections | P6 | 1 |
| `lint [PATHS] [--format text\|json\|tsv]` | detect deviations (list below); exit 1 on errors | all | 1 |
| `hubs [--check]` | regenerate hub page lists and the hub index | P12 | 1 |
| `status` | pages by type and status, review queue, open flags | P7 | 1 |
| `embeds [--get] [--unlock]`, `figure KEY N` | embedded files by annex state; a paper's figure as embed + caption + citation | P8 | 1 |
| `review packet [PAGES] [--out F]` | per page: lede, open flags, lint, quotes verified or not, citations, evidence, contested blocks | P11 | 1 |
| `review accept PAGE --by NAME [--stable] [--resolve-flags]`, `review flag PAGE TEXT`, `review reopen PAGE` | record a person's decision; accept refuses lint errors and open flags | P11 | 1 |
| `relink OLD NEW [--apply]` | rename or move a page and rewrite every inbound link and `related:` value; dry run first; logged | P5 | 2 (done) |
| `merge A B [--apply]` | frontmatter union, aliases, A's text appended to B to fold in, redirect stub (`redirect:`), never delete; logged | P2 | 2 (done) |
| `extract PAGE --section H --name N [--apply]` | section to a new page, leave lede and link; logged | P1 | 2 (done) |
| `suggest` | lint findings as refactor suggestions (signal, principle, op) | | 2 |
| `views` | Obsidian Bases tables (review queue, contested, stubs) and static HTML (people, typed graph) | P12 | 2 |
| `promote --tag T` | gate check and plan for the lab hub; copies only after approval | | 3 |

### Lint checks

| Group | Check | Severity |
|-------|-------|----------|
| Frontmatter | required keys; `type`, `status`, `scope`, `author` values; `reviewed` is `{by, date}` when status is reviewed or later; unknown keys; relation keys in the closed set | error / warning |
| Structure | lede paragraph present; required H2 sections per type (skipped for stubs) | warning (error once reviewed) |
| Tags | `facet/value` tags exist in the vocabulary | error |
| Links | wikilinks and relative markdown links resolve; heading anchors exist; no `![[embeds]]`; basenames unique | warning (error once reviewed) |
| Embeds | an embedded image's annexed content is present (`IMG001`); a locked annex symlink is noted because Obsidian ignores it (`IMG002`); a figure from `bib/derivatives/figures/<citekey>/` cites that paper (`IMG003`) | warning / note |
| Citations | `[@citekey]` exists in the project bibliography or a pool (`pool.search`; pool-only keys are a note to add before rendering); in-text citations listed in `sources:` | error / warning / note |
| Fidelity | quoted text attributed to a citekey appears in that paper's full text (project or pool) | error |
| Code | `path::function` anchors exist | warning |
| Scope | no project tokens (e.g. `sub-01`, `ses-03`) on `scope: general` pages outside "Our experience" | warning |
| Views | hub page lists match what `hubs` would generate | warning |
| Suggestions | page over 800 words; unresolved link wanted by 3 or more pages; 5 or more pages share a tag with no hub | suggestion |

Quotes are checked when written as a blockquote or inline quotation followed
by a citation, e.g. `> "text" [@sirota_2003_CommunicationNeocortex]`. Status
blocks (`> **Contested.** ...`) and Obsidian callouts are not treated as quotes.

## Skills

Shipped with biblio (`src/biblio/skills/`). In a projio project they need no
install: projio discovers them through biblio's `projio.skills` entry point,
`skill_read` returns them, and `projio sync` writes a `.claude/commands/`
wrapper per skill. Elsewhere, `biblio skills install` copies them into
`.claude/skills/`.

| Skill | Purpose | Uses | Shipped |
|-------|---------|------|---------|
| `wiki-ingest` | a source (paper, note, code) into the pages it touches; with a person present, plan first when more than 3 pages change | `stub`, `lint`, `hubs`, `figure` | yes |
| `wiki-maintain` | lint, read findings, propose and apply refactors with dry runs, re-lint | `lint`, `hubs`, `relink`, `merge`, `extract` | yes |
| `wiki-review` | help a person review: packets with claims beside quotes, unbacked citations and numbers; record their decision | `review packet\|accept\|flag\|reopen` | yes |
| `zotero-add` | one paper from Zotero into the project (laptop to server) | `biblio add zotero` | yes |
| `wiki-synthesize` | pages that combine sources: concept or theory pages with evidence for and against, method comparisons, open questions; every statement from a paper carries a checked quote, own reasoning marked **Synthesis:** | `digest claims`, `stub`, `lint`, `review packet` | yes (draft) |
| `wiki-query` | answer from the wiki, then from source full text by citekey and section; offer to file the answer | `rag` is not used | no (W11) |

## Working in the editors

- **Vault root.** Open the project root, so links from wiki pages to paper
  full text under `bib/derivatives/docling/` resolve. Exclude `code/`, `data/`
  and derivatives that are not text (Obsidian: Settings, Files and links,
  Excluded files).
- **Links.** biblio writes relative markdown links (`link_style: markdown`,
  the default since 2026-10-22); lint accepts them and `[[wikilinks]]`.
  Relative markdown links work unchanged in VS Code, mkdocs, Quarto and
  GitHub, and Obsidian writes and rewrites them cleanly (Use [[Wikilinks]]
  off, new link format relative). With that format, a rename in Obsidian turns
  wikilinks into path wikilinks, which is why they are opt-in. Settings:
  [Edit the wiki in Obsidian or VS Code](../how-to/wiki-editors.md).
- **Queues.** In Obsidian, Bases (`.base` files) give table views over
  frontmatter, e.g. all `draft` pages written by `llm`. `views` will generate
  them; VS Code users read `biblio wiki status`.
- **Annexed files.** DataLad stores PDFs and images as symlinks into
  `.git/annex`. Obsidian ignores file symlinks (confirmed 2026-10-22), so
  annexed figures and PDFs do not display there; markdown full text is a
  regular file and works. VS Code follows the symlinks. Where figures matter
  in Obsidian, unlock them (`datalad unlock <path>`, or `git annex adjust
  --unlock` for a whole checkout).

## Phases

1. **Deterministic core** (done, 0.2.x): `init`, `stub`, `lint` (exact-only
   quote fidelity), `hubs`, `status`, `embeds`, `figure`, `review`; skills
   `wiki-ingest`, `wiki-maintain`, `wiki-review`. Used on pixecog (layer
   identification, 47 pages) and journal-club (sleep coupling).
2. **Restructuring and views:** `relink`, `merge`, `extract`, `suggest`,
   `views`; skill `wiki-synthesize`.
3. **Digest-driven work:** the `subject`, `claims` and `methods` digest modes
   feed ingest and synthesis; `promote`; skill `wiki-query`.

## Open

1. The wiki specification moves from pixecog into biblio's docs once reviewed,
   so the method and the tools version together.
