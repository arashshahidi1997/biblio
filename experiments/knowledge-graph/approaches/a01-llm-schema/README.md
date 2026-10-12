# a01: LLM extraction into the reference schema

**Status:** planned

## Inspiration

- SciClaim (EMNLP 2021, arXiv 2109.10453): fine-grained claims over experimental variables
- Nanopublications: keep the assertion separate from its provenance
- biblio's own `extract.py`, which this approach generalizes

## Idea

Ask an LLM to extract nodes of the reference types directly, one paper at a
time, with a verbatim quote and section for each node. Use GROBID TEI sections
so the model sees the full paper section by section, instead of the first 15k
characters that `extract.py` reads today. A second pass merges Method, Concept
and Theory nodes across papers.

This is the baseline. It shows what a schema-first extractor gives before we
add any outside tool.

## Inputs

- GROBID TEI (`grobid/<ck>/<ck>.tei.xml`) for section structure
- docling markdown (`docling/<ck>/<ck>.md`) as fallback and for quote checks
- the project's hypotheses (`plan/questions.yml`) for `project_link`

## Mapping to the reference schema

Native output is the reference schema, so the mapping is identity.

## Plan

1. Section splitter over TEI, falling back to docling headings.
2. Per-section prompt with a JSON output schema (node types + quotes).
3. Paper-level pass: link claims to evidence and experiments within the paper.
4. Corpus-level pass: merge equivalent Method / Concept / Theory nodes
   (embedding candidates, then LLM confirm).
5. Run on `core` with Haiku and with Sonnet, to see what the model tier buys.

## Open questions

- One prompt for all node types, or one per type?
- How to keep merging stable across re-runs, so curated edits survive?

## Findings
