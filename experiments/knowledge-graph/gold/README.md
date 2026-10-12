# Gold annotations

Hand annotations for the `gold` set in `corpus/corpus.yml`. They give precision
and recall for the extraction-type approaches (a01-a05).

## How to annotate

1. Copy `_template.yml` to `<citekey>.yml`.
2. Read the paper (docling markdown under `$KG_CORPUS_ROOT/bib/derivatives/docling/<citekey>/`).
3. List the items below. Each item needs a verbatim `quote`.
   - **claims**: the main findings the authors state as results. Aim for 5-15.
   - **methods**: named techniques with their parameters.
   - **experiments**: species, preparation, regions, recording, conditions.
   - **questions**: explicit open questions, limitations, future work.
   - **theories**: frameworks the paper places itself in, with stance.
4. Link claims to project hypotheses where it applies (`project_link`).

Annotating one paper takes roughly an hour. Do it before looking at any
approach's output for that paper, so the gold set stays independent.

## Matching rule

An extracted node matches a gold item when both have the same type and either
the quotes overlap, or a reviewer judges the labels equivalent. The evaluator
proposes matches by quote overlap; a human confirms the rest.
