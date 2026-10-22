# Principles, resources and ideas

**Status:** living document
**Updated:** 2026-10-22

This page collects the reasoning behind biblio's [scope](scope.md), the
[wiki toolkit](wiki.md) and the knowledge-graph experiment
(`experiments/knowledge-graph/`), so later decisions can point to it. Citekeys
refer to `experiments/knowledge-graph/literature/foundations.bib`.

## 1. Principles

### 1.1 biblio

| ID | Principle | In practice |
|----|-----------|-------------|
| B1 | **Two core jobs.** Digest and wiki at full depth; discovery and ingest only as far as they serve them. | New features name the area they serve and at what depth. |
| B2 | **Files are the state.** Every operation reads and writes plain files in git. | The editor, the CLI and agents see the same state; no state lives only in a GUI or a database. |
| B3 | **CLI canonical, skills for workflows, MCP thin.** | Every capability is a `biblio` subcommand; skills describe how to combine them. |
| B4 | **No retrieval dependency.** Retrieval (RAG) is optional and unevaluated. | Agents read full text by citekey and section. |
| B5 | **Quotes or nothing.** Every extracted claim carries a verbatim quote and its section. | `biblio wiki lint` checks quotes against the full text. |
| B6 | **Whole paper, by section.** | No reader truncates a paper to its first N characters. |
| B7 | **Derivatives are regenerable.** Digests are addressed by citekey, mode, context, prompt version and model; nobody edits them by hand. | Curation happens in the wiki. |
| B8 | **Registry metadata first.** Bibliographic facts come from the DOI registry (Crossref, DataCite). | OpenAlex enriches, after its match is checked by DOI. |
| B9 | **Agents propose, people decide.** | Agent-written pages stay `draft`; only a person sets `reviewed`. |
| B10 | **Delegate what others do better.** Open search (OpenAlex, Semantic Scholar), the personal library (Zotero), reading and editing (Obsidian, VS Code). | biblio owns the path in and the path back. |
| B11 | **pixi and uv.** pixi for project environments, uv for global CLIs. | No conda in code, docs or generated commands. |
| B12 | **Measure before building.** Changes to the knowledge model go through the experiment first. | Fixed corpus, competency questions, gold annotations, one rubric. |

### 1.2 The wiki method

From the wiki specification (pixecog `docs/wiki/SPEC.md`, v0.1-draft).
"Related reading" points to works that develop the same idea.

| ID | Principle | Meaning | Related reading |
|----|-----------|---------|-----------------|
| P1 | Atomicity | one idea per page; split when a second appears | `luhmann_1981_KommunikationMit`, `schmidt_2018_NiklasLuhmann`, `rayward_1994_VisionsXanadu` |
| P2 | Single source of truth | each fact lives on one page; others link | `matuschak_nd_EvergreenNotes`, `smith_2007_OboFoundry` |
| P3 | Title and lede are the interface | concept-oriented title, one-paragraph definition | `matuschak_nd_EvergreenNotes` |
| P4 | One mode per page | tutorial, how-to, reference and explanation kept apart | `procida_nd_Diataxis` |
| P5 | Associative over hierarchical | folders for page type only; subject through tags and links | `bush_1945_AsWe`, `ranganathan_1967_ProlegomenaLibrary`, `hjorland_2013_FacetAnalysis` |
| P6 | Grow, don't pre-build | stubs first; hubs when a subject reaches its squeeze point | `milo_nd_LinkingYour`, `shipman_1999_FormalityConsidered` |
| P7 | Explicit epistemic status | growth stage, review, contested and outdated marks are visible | `appleton_2020_BriefHistory`, `latour_1979_LaboratoryLife`, `toulmin_1958_UsesArgument` |
| P8 | Source fidelity | every claim traceable; quotes and numbers verbatim | `karpathy_2026_LlmWiki`, `groth_2010_AnatomyNanopublication`, `greenberg_2009_HowCitation` |
| P9 | Never silently rewrite | contradictions recorded side by side; superseded content marked | `lakatos_1970_FalsificationMethodology`, `clark_2014_MicropublicationsSemantic` |
| P10 | Knowledge and findings apart | general knowledge separate from the project's own results | |
| P11 | People own judgment | agents draft and propose; people review and promote | `shipman_1999_FormalityConsidered`, `engelbart_1962_AugmentingHuman` |
| P12 | Derived views are caches | hub lists and indexes are generated | `hogan_2021_KnowledgeGraphs` |

### 1.3 The experiment

| ID | Principle |
|----|-----------|
| E1 | Every approach runs on the same papers (`corpus.yml`). |
| E2 | Competency questions come first and are the main score (`noy_2001_OntologyDevelopment`). |
| E3 | Gold annotations are written before looking at any approach's output. |
| E4 | Every approach exports one interchange format with provenance, so one evaluator scores all of them. |
| E5 | Fit with biblio counts: an approach that needs its own store scores at most 1 of 2. |
| E6 | Plain retrieval without a graph is the control. |

### 1.4 Tensions to keep in view

From the literature (details in `literature/README.md`):

1. Strict types help machines; forcing them at capture time hurts people.
   Types are strict in the schema and assigned late, with review.
2. Realist ontology (what exists) vs pragmatic ontology (what a community
   agrees to talk about). A project wiki is pragmatic.
3. Facets change with use; record vocabulary changes.
4. A claim's status changes over time; keep superseded versions.
5. Notes are idea-sized, bibliographies paper-sized; claim-level IDs connect them.

## 2. Resources

### 2.1 Literature

92 works in `experiments/knowledge-graph/literature/` with a reading guide by
design question. Start with: `hogan_2021_KnowledgeGraphs`,
`groth_2010_AnatomyNanopublication`, `clark_2014_MicropublicationsSemantic`,
`chan_2024_StepsTowards`, `peroni_2012_FabioCito`,
`latour_1979_LaboratoryLife`, `lakatos_1970_FalsificationMethodology`,
`schmidt_2018_NiklasLuhmann`, `shipman_1999_FormalityConsidered`,
`hjorland_2013_FacetAnalysis`, `noy_2001_OntologyDevelopment`,
`edge_2024_LocalGlobal`.

### 2.2 Systems for claim-level and scholarly knowledge

Surveyed 2026-10-12.

| System | Models | What we take |
|--------|--------|--------------|
| [ORKG](https://orkg.org) | papers as contributions described by templates; comparison tables | per-problem templates and comparison tables (a03) |
| [Nanopublications](https://knowledgepixels.com) | assertion, provenance, publication info; signed, immutable | provenance kept apart from the claim |
| Micropublications (Clark et al. 2014) | claim, evidence, support, challenge | claim and evidence relations |
| [SEPIO](https://github.com/monarch-initiative/SEPIO-ontology) | assertion, evidence line, evidence items | evidence line as its own node |
| CiTO and [pandoc-ext/cito](https://github.com/pandoc-ext/cito) | typed citations (supports, disputes, usesMethodIn) | citation intents; `[@supports:key]` in manuscripts |
| [Discourse Graphs](https://discoursegraphs.com) | Question, Claim, Evidence, Source as notes with typed links | the curated layer as markdown notes |
| Hypothes.is and SciBot | anchored annotations; machine-proposed, human-validated | the propose-then-validate loop |
| [Scite](https://scite.ai) | citing sentences as supporting, contrasting, mentioning | citation statements (a06); its contrasting class is noisy |
| Elicit, Consensus | extraction tables with sentence provenance; consensus meter | cell-level quotes; stance per theory |
| Undermind, Ai2 Asta, PaperQA | agentic search; corpus tools over MCP; RAG with citations | the RAG control (a08) |
| Connected Papers, Inciteful, Litmaps, Open Knowledge Maps | similarity and citation maps; topic clusters | views over the citation graph |
| [GraphRAG](https://github.com/microsoft/graphrag), [LightRAG](https://github.com/HKUDS/LightRAG), [KGGen](https://github.com/stair-lab/kg-gen) | generic entity graphs, communities, entity merging | comparisons only (a04, a05); they bring their own stores |

### 2.3 People and identity

| Source | Provides | Limits |
|--------|----------|--------|
| OpenAlex | authors, ORCID, institutions with ROR, topics, works per year (CC0) | no photos; author IDs can split |
| Wikidata and [Scholia](https://scholia.toolforge.org) | profiles, photos (P18) with Commons license, doctoral advisors (P184) | photos for 4% of authors in our test corpus, none of the top 20 |
| ORCID, Semantic Scholar | identifiers, affiliations, homepages | no photos |
| Google Scholar | photos uploaded by researchers | terms of service forbid automated access |

Photos are personal data; open ones come from Commons with attribution, others
stay in a local folder outside git.

### 2.4 Neuroscience vocabularies

Cognitive Atlas (concepts, tasks, contrasts), BrainMap taxonomy (behavioral
domains, paradigm classes), NIF and InterLex, RRIDs for tools and reagents,
Neurosynth and NeuroQuery, CoCoMac as a precedent for findings with
parameters.

### 2.5 LLM-maintained wiki tools

Surveyed 2026-10-19 for the wiki specification (pixecog `docs/wiki/RESOURCES.md`).

| Tool | What we take |
|------|--------------|
| [Karpathy, LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | raw sources, maintained wiki, schema; ingest, query, lint |
| [praneybehl/llm-wiki-plugin](https://github.com/praneybehl/llm-wiki-plugin) | principles first; lint finding to fix map; page size caps |
| [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) | quotes and numbers checked against the source; Outdated and Disputed blocks |
| [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) | merge with frontmatter union, aliases, redirect stub, never delete |
| [research-superpowers](https://github.com/leiverkus/research-superpowers) | `author: human/llm/mixed`, `review_flags`, `contradicts` |
| [nvk/llm-wiki](https://github.com/nvk/llm-wiki) | indexes and hubs as a derived cache |
| [m4bwav/obsidian-notes](https://github.com/m4bwav/obsidian-notes) | portability lint: ambiguous links, duplicate basenames |

None of them ships headless refactoring (split, extract, merge, relink)
derived from a principle set; biblio writes its own.

### 2.6 Editors and rendering

- **Obsidian:** heading links with hover previews; Bases (`.base` YAML) for
  table views over frontmatter; Excluded files for code and data. File
  symlinks are unsupported, so git-annex PDFs and figures do not display
  ([symlinks](https://obsidian.md/help/symlinks), [Bases syntax](https://obsidian.md/help/bases/syntax)).
- **VS Code:** opens the repo root and follows symlinks; relative markdown
  links work natively.
- **mkdocs** (ezlinks, bibtex) for the site; **Quarto** for tutorials.

### 2.7 In the ecosystem

biblio derivatives (docling, GROBID, OpenAlex), questio (project questions and
hypotheses), notio (notes, manuscripts), codio (code anchors), sirocampus (lab
hub), the experiment folder (corpus loader, interchange validator, a07 people
view).

## 3. Ideas

| Idea | Origin | Status |
|------|--------|--------|
| Four layers: raw sources, machine derivatives, curated wiki, generated views | session 2026-10-12 | adopted (scope) |
| Digest modes: summary, question, subject, methods, claims, citations, people | scope | proposed |
| Scope field (`general`/`project`) on every node | wiki P10 | in the wiki; to add to the experiment schema |
| Status ladder with `author` and `review_flags` | wiki spec | adopted |
| Quote fidelity check shared by the wiki and the experiment | wiki W06, experiment | done in `biblio.wiki.fidelity` |
| Claim-level addresses inside pages (block IDs such as `^c-sirota2003-01`) | wiki and KG comparison | open |
| Typed citation statements; `[@supports:key]` in manuscripts | Scite, CiTO | planned (a06) |
| Evidence line between claim and data | SEPIO | open |
| Comparison tables per research problem | ORKG, Elicit | planned (a03, methods mode) |
| Gaps: explicit from limitations sections; implicit as empty cells of the facet cross-product (region × event × state) | Swanson, GAPMAP, wiki facets | idea |
| Theory pages with stance per paper | Consensus, Lakatos | idea |
| People pages: OpenAlex aggregation, Commons photos plus a local folder, advisor lineage, last-author groups; consortium papers weighted by 1/(n-1) | a07 | a07 scored; pages are a phase 2 view |
| Relative markdown links, made move-safe by `relink` | wiki SPEC §12.1 | proposed |
| Obsidian Bases as review queues | editors | phase 2 |
| GUI as navigator and review desk (select a sentence to annotate) | session 2026-10-22 | deferred |
| Reviewed wiki pages as gold standard; SWR detection as a shared subject | wiki and experiment | idea |
| Extraction output feeds "wanted page" lint signals | wiki and experiment | idea |
| a02 reworked into "wiki as graph" | wiki and experiment | proposed |
| Disambiguate "question": wiki question (answered query), questio question (hypothesis), open problem (literature gap) | naming | open |
| Skills shipped with biblio and discovered by projio | wiki toolkit | partial (`biblio skills install`) |
| Unlocked annex checkout where Obsidian needs figures | editors | documented |
| Parked: GraphRAG, LightRAG or KGGen in production; scraping Google Scholar; features that depend on RAG | B3, B4 | parked |
