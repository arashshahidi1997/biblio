# Knowledge-graph experiments

Branch: `feat/knowledge-graph`

## Goal

Decide whether biblio can be the backbone of a literature knowledge graph, and
which approach to build on. The graph should hold more than papers:

- theories, hypotheses, claims, evidence, experiments, methods, datasets
- open questions and gaps
- the people behind the work (profiles, photos, contributions, collaborations)

and it should let us move from high-level theory down to low-level experimental
parameters.

Nothing in `src/biblio/` changes until this comparison has a result.

## Protocol

1. **Fixed corpus.** Every approach runs on the same papers
   ([`corpus/corpus.yml`](corpus/corpus.yml)): a `core` set of 12 papers tied
   to the test project's hypotheses, and an `extended` set of 39 papers with full
   derivatives (docling + GROBID + OpenAlex).
2. **Shared target schema.** [`schema/reference-schema.yml`](schema/reference-schema.yml)
   lists the node and edge types we care about. It is a yardstick for scoring.
   It is not the final design.
3. **Common output format.** Each approach exports its result to the interchange
   format in [`schema/interchange.md`](schema/interchange.md) (`nodes.jsonl` +
   `edges.jsonl`), alongside its own native output. Scoring runs on the
   interchange files only.
4. **Competency questions.** [`competency/questions.yml`](competency/questions.yml)
   lists the questions the graph must answer. These are the main test.
5. **Gold annotations.** A few `core` papers get hand annotations
   ([`gold/`](gold/)) for precision and recall on claims, methods and open
   questions.
6. **Scoring.** [`eval/criteria.md`](eval/criteria.md) defines the rubric.
   Results go into [`eval/scoreboard.md`](eval/scoreboard.md).

## Approaches

| ID | Approach | Inspiration | Main question it answers | Status |
|----|----------|-------------|--------------------------|--------|
| [a01](approaches/a01-llm-schema/) | LLM extraction into the reference schema, with quotes | SciClaim, nanopub provenance | How far does a direct, schema-first extraction get? (baseline) | planned |
| [a02](approaches/a02-discourse-notes/) | Discourse-graph notes (Question / Claim / Evidence / Source) | Discourse Graphs (Chan) | Do markdown notes with typed links work as the curated layer? | planned |
| [a03](approaches/a03-orkg-contrib/) | Contribution templates + comparison tables | ORKG | Are structured per-problem tables the right view for methods and parameters? | planned |
| [a04](approaches/a04-graphrag/) | Generic entity graph + community summaries | Microsoft GraphRAG, LightRAG | Does an off-the-shelf graph builder give useful structure for free? | planned |
| [a05](approaches/a05-kggen/) | Generic text-to-KG extractor | KGGen | Same question, with a lighter tool and entity merging | planned |
| [a06](approaches/a06-citation-statements/) | Citing sentences with intent labels | Scite, CiTO | What do typed citation edges add on top of the claim layer? | planned |
| [a07](approaches/a07-people-view/) | Author index, co-author graph, photos | Scholia, OpenAlex | How complete a people view can open data give us? | planned |
| [a08](approaches/a08-paperqa-baseline/) | Query-time RAG, no persistent graph | PaperQA2 | Control: which competency questions need a graph at all? | planned |

New approaches start from [`approaches/_template/`](approaches/_template/).

## Layout

```
corpus/        fixed paper sets (citekeys only, no paper content)
schema/        reference schema + interchange format
competency/    competency questions
gold/          hand annotations for scoring
approaches/    one folder per approach: README, code, config
common/        shared loaders and checks (corpus access, interchange validation)
eval/          rubric and scoreboard
runs/          raw outputs, gitignored: runs/<approach>/<run-id>/
```

## Running

The corpus lives in a separate projio project. Point to it with an env var:

```bash
export KG_CORPUS_ROOT=/path/to/project   # must contain bib/derivatives/
python common/corpus.py --set core        # check which derivatives are present
```

Approaches with heavy dependencies get their own pixi feature in
[`pixi.toml`](pixi.toml), so the biblio env stays clean:

```bash
pixi run -e graphrag python approaches/a04-graphrag/run.py
```

Validate any run before scoring:

```bash
python common/interchange.py runs/a01-llm-schema/<run-id>/
```

## Rules

- Paper content (PDF text, docling markdown, TEI) never gets copied into this
  folder. Read it from `KG_CORPUS_ROOT`; write outputs under `runs/`.
- Every extracted node keeps its source: citekey, section and a verbatim quote.
  An approach that cannot give a quote records `quote: null`, and that shows up
  in the score.
- Record cost and wall time for every run in `runs/<approach>/<run-id>/run.yml`.
- Photos of researchers stay out of git. Only openly licensed images (for
  example Wikimedia Commons) may be cached, together with license and author.
