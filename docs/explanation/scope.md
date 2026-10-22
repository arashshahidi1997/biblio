# Scope

**Status:** Proposed (draft for review)
**Date:** 2026-10-22

## What biblio is for

biblio turns the papers a project relies on into knowledge the project can
cite and review. Its two core jobs are **digest** (read papers into
structured, quotable derivatives, in modes that depend on the context) and
**wiki** (keep the literature side of the project wiki faithful to its
sources). It does only as much **discovery** and **ingest** as those two jobs
need, and leaves the rest to tools built for them.

| Area | Scope | biblio owns | Left to |
|------|-------|-------------|---------|
| Discovery | partial | expanding from papers the project already holds; checking candidates against the library | open search and browsing: OpenAlex, Semantic Scholar, Zotero ([discovery model](discovery.md)) |
| Ingest | partial | identifier to verified entry, canonical citekey, library status, open-access PDF | the personal library and attachments (Zotero); paywalled access |
| Digest | full | full-text extraction; context-specific digests with provenance | |
| Wiki | full | literature pages of the project wiki and the checks that keep them faithful | project findings (notio), project hypotheses (questio), the lab hub (sirocampus) |

## Discovery (partial)

biblio expands outward from what the project holds. It does not search the
open literature.

- **Keep:** reference and citing-paper expansion from held papers
  (`graph.py`, `graph_promote.py`); author and institution lookups as context
  for held papers (`author_search.py`, `discovery.py`).
- **Fix:** `graph.py` drops citation edges between two held papers, so the
  corpus graph depends on GROBID title matching.
- **Rule:** discovery writes a candidate list. Nothing enters the library
  without going through ingest.

## Ingest (partial)

Ingest ends when a paper has a verified entry, a canonical citekey, a library
status and, when one is openly available, a PDF.

- **Keep:** DOI, arXiv, BibTeX, RIS and CSL-JSON inputs (`ingest.py`,
  `bibtex.py`); canonical citekeys, dedup, quality checks, merge and compile
  (`citekey.py`, `dedup.py`, `quality.py`, `normalize.py`); open-access PDF
  fetch (`pdf_fetch_oa.py`, `unpaywall.py`); library status (`library.py`);
  Zotero pull, since Zotero is where people collect papers.
- **Fix:** metadata must come from the DOI registry (Crossref, DataCite).
  OpenAlex is for enrichment only, after its match is checked by DOI. Today
  OpenAlex returns the wrong work for some arXiv DOIs, drops book authors and
  types every entry as `@article`; the citekey generator mangles multi-word
  family names and some letters (`ø`).
- **Review:** Zotero push; the shared PDF pool (`pool.py`) as storage, not a
  feature surface; the needs-PDF queue.

## Digest (full)

Digest is the center of biblio. It has two stages.

1. **Extraction** (deterministic, one per paper): docling markdown and figures,
   GROBID TEI parsed into sections, references and citation contexts. Cached
   under `bib/derivatives/`.
2. **Digests** (LLM, context-specific): a *mode* plus a *context* produce a
   derivative.

### Modes

| Mode | Context | Output | Today |
|------|---------|--------|-------|
| `summary` | none | whole-paper digest | `summarize.py` |
| `question` | a research question or hypothesis | relevance, support or opposition, with quotes | `extract.py` (against `plan/questions.yml`) |
| `subject` | a wiki subject (hub and tags) | draft source page: claims, methods, markers relevant to the subject | new (wiki ingest) |
| `methods` | a template, e.g. "ripple detection" | one comparison row per paper with quoted parameters | partly `compare.py` |
| `claims` | none, or a subject | claim, evidence and gap candidates | new |
| `citations` | none | citing sentences with intent labels | spec only (`citation-context.md`) |
| `people` | none | author and institution index, no LLM | new |

### Rules for every digest

- **Addressed by** citekey, mode, context, prompt version and model. Stored as
  `bib/derivatives/digest/<mode>/<context>/<citekey>.*`. Regenerable and never
  edited by hand; curation happens in the wiki.
- **Whole paper, by section.** Read from TEI sections or docling headings.
  Today every LLM module reads a truncated slice (`[:1000]` to `[:15000]`).
- **Quotes or nothing.** Every claim carries a verbatim quote and its section,
  and a fidelity check confirms the quote is in the paper.
- `concepts.py` and `autotag.py` fold into the `subject` and `claims` modes and
  the shared tag vocabulary.

## Wiki (full)

biblio owns the literature-facing part of the project wiki, following the wiki
specification (pixecog `docs/wiki/SPEC.md`):

- `source` pages per paper, drafted from the `subject` digest;
- ingest of a paper into the knowledge pages it touches;
- lint checks that concern literature: citekeys resolve, quotes and numbers
  are verbatim in the source, claims are cited;
- generated views over the literature: people pages, comparison tables,
  citation and claim graphs.

Project findings and hypotheses stay in notio and questio and are linked by
ID. The format, the page types and the review lifecycle come from the wiki
spec; biblio follows it rather than defining its own.

## Interfaces

- **CLI is canonical.** Every operation is a `biblio` subcommand that reads and
  writes files.
- **Skills over MCP.** Agents run the CLI through skills that describe the
  workflows. MCP stays thin: a handful of tools where structured input and
  output help (resolve citekeys, read a paper's digests, set library status,
  run a digest). Today there are 46 functions in `mcp.py` and 37 projio
  wrappers.
- **No retrieval dependency.** Digest and wiki work without RAG. Agents read
  derivatives by citekey and section. `rag.py`, `rag_support.py`,
  `vector_store.py` and the indexio integration become an optional extra, off
  by default, until retrieval is evaluated (the knowledge-graph experiment
  keeps a RAG baseline as its control).
- **Environments:** pixi for the workspace, with a feature per heavy tool
  (docling); uv for global CLIs. No conda in code, docs or generated commands.
  GROBID runs as a service addressed by URL.

## Outside the core (proposed)

| Module | Reason | Proposal |
|--------|--------|----------|
| `ui.py` + `frontend/` (3,210 lines, 111 endpoints; 22 frontend source files plus a Node build) | about half the endpoints run or configure pipelines, duplicating the CLI | keep the navigators; trim run and setup endpoints later |
| `site.py` | static paper site | fold into the wiki's generated views |
| `present.py` | slides belong to projio's `present_*` | remove |
| `cite_draft.py`, `lit_review.py`, `review` | writing with the literature; two of them depend on RAG | move to notio manuscript, consuming digests |
| `reading_list.py` | LLM curation over truncated text | drop, or rebuild as discovery from held papers |
| `rag.py`, `rag_support.py`, `vector_store.py` | retrieval is not trusted yet | optional extra, off by default |
| `ezproxy.py`, `auth` | paywalled access carries ban risk | separate opt-in plugin |

## Decided (2026-10-22)

1. **Interface:** the vault, opened in Obsidian or VS Code, is where people
   read, edit and review. The GUI stays, valued for its navigators, but work
   on it waits; the run and setup endpoints are the first candidates to go
   when it is revisited.
2. **Wiki home:** biblio owns the wiki tooling and its skills
   ([wiki toolkit](wiki.md)); the wiki method is versioned with them.

## Decisions needed

1. **MCP:** which few tools stay, or CLI plus skills only?
2. **RAG:** keep as an optional extra, or remove until it is evaluated?
3. **Zotero push and EZProxy:** keep, plugin, or drop?
