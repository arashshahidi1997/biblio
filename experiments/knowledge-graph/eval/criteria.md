# Scoring rubric

Scores are recorded per approach and run in `scoreboard.md`. Sections 1-3 are
measured on the interchange files. Sections 4-6 are judged from the README and
from running the approach.

## 1. Competency questions (main score)

For each question in `competency/questions.yml`, a reviewer queries the
approach's graph (or, for a08, asks the system) and scores:

| Score | Meaning |
|-------|---------|
| 0 | Cannot answer, or the answer is wrong |
| 1 | Partly answers: some right items, missing structure or sources |
| 2 | Answers fully, and every item traces to a quote in a paper |

Report the total and the per-kind subtotals (theory, claim, method, people, ...).
The answer text goes in `runs/<approach>/<run-id>/cq/<CQ-id>.md` so scores can
be re-checked.

## 2. Extraction quality against gold

On the `gold` papers only, per node type (Claim, Method, Experiment, Question,
Theory):

- **precision**: matched extracted items / all extracted items
- **recall**: matched gold items / all gold items
- **parameter accuracy** (Method, Experiment): share of gold parameters found
  with the right value

## 3. Graph structure

Measured automatically where possible (`common/interchange.py --stats`):

- **quote validity**: share of nodes whose `quote` is found in the source text
- **type coverage**: which reference node and edge types appear at all
- **level connectivity**: share of Claim nodes with a path up to a Theory and
  down to an Experiment or Parameter
- **cross-paper merging**: number of Method / Concept / Theory nodes with
  sources from 2+ papers, and the duplicate rate a reviewer finds in a sample
  of 20
- **people coverage** (a07): share of authors with ORCID, with an institution,
  with an openly licensed photo

## 4. Human in the loop

| Score | Meaning |
|-------|---------|
| 0 | Output is opaque or only editable in a proprietary tool |
| 1 | Editable, but edits are lost on re-run, or diffs are unreadable |
| 2 | Plain files in git, readable diffs, review status per node, edits survive re-runs |

## 5. Cost and operations

- cost per paper (USD) and wall time per paper
- runs offline / self-hostable (yes / partly / no)
- license of the tool and of its output
- install weight (number of extra dependencies, GPU needed or not)

## 6. Fit with projio

| Score | Meaning |
|-------|---------|
| 0 | Needs its own server or database with no file export |
| 1 | Exports files, but mapping to biblio / notio / questio needs custom glue |
| 2 | Maps directly onto biblio derivatives or notio notes and can be queried through MCP |

## Decision rule

No approach is expected to win everywhere. The outcome is a layer-by-layer
choice: which approach supplies people, citation statements, candidate
extraction, the curated layer and the views. Write the recommendation in
`scoreboard.md` under "Conclusion" with the evidence it rests on.
