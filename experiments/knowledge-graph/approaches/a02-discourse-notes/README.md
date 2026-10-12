# a02: Discourse-graph notes

**Status:** planned

## Inspiration

- Discourse Graphs, https://discoursegraphs.com (Joel Chan, Akamatsu lab)
- "Steps Towards an Infrastructure for Scholarly Synthesis" (arXiv 2407.20666)
- Obsidian discourse-graph plugin: node types as notes, relations in frontmatter

## Idea

Store the curated layer as markdown notes, one node per note, with the type and
typed links in frontmatter. Base types: Question, Claim, Evidence, Source, plus
Hypothesis and Experiment as lab users do. This tests whether notio-style notes
can hold the graph that people edit and review.

Candidate notes are seeded from a01 output (`status: candidate`), then a person
accepts, edits or rejects them. The graph is rebuilt from the notes.

## Inputs

- a01 run output (candidates)
- the project's `plan/questions.yml` for Hypothesis notes

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|
| Question | Question | |
| Claim | Claim | |
| Evidence | Evidence | |
| Source | Paper | `paper:<citekey>` |
| Hypothesis | Hypothesis | |
| Experiment | Experiment | |
| supports / opposes / informs / derivedFrom | supports / opposes / informs / derived_from | |

## Plan

1. Write a note format (frontmatter fields, link syntax) that notio could adopt.
2. Converter: a01 interchange to notes, and notes back to interchange.
3. Curate the `gold` papers by hand from a01 candidates; time it.
4. Check: do edits survive a re-run of a01 (stable IDs, merge rules)?
5. Try viewing the notes in Obsidian with the discourse-graph plugin, to judge
   the editing experience without building a UI.

## Open questions

- Do notes live under the project's `docs/log/` (notio) or under `bib/`?
- How to handle a claim shared by several papers: one note with many sources?

## Findings
