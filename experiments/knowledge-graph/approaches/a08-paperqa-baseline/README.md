# a08: Query-time RAG baseline (no persistent graph)

**Status:** planned

## Inspiration

- PaperQA2, https://github.com/Future-House/paper-qa: agentic RAG over a paper folder, answers with citations
- projio's own `rag_query` over the docling corpus (indexio)

## Idea

Answer the competency questions directly from the papers, without building a
graph. This is the control: questions that a01-a07 answer no better than RAG do
not justify a graph. Questions that need structure (CQ09 gaps, CQ13 drill-down,
CQ11 people) should show the difference.

Run two variants: projio `rag_query` + Claude, and PaperQA2.

## Inputs

- docling markdown (indexio corpus `bib`)
- PDFs for PaperQA2

## Mapping to the reference schema

No graph output. Score section 1 (competency questions) only; record answers
in `runs/a08-paperqa-baseline/<run-id>/cq/`.

## Plan

1. Ask each CQ through `rag_query` + Claude; save answers with citations.
2. Same with PaperQA2 on the `extended` PDFs.
3. Score with the same rubric as the graph approaches.

## Findings
