# Paper scrutiny: protocol v1.1

How to break down a paper's information and arguments in order to scrutinise
it. Written from two hand-runs in lit-studio (2026-11, a correlational human
study and a causal rodent study), not designed in advance. Background:
Toulmin's argument model, stasis theory, argument maps and strong inference
(Platt).

**Uses:** presenting or leading discussion at a journal club; weighing a
claim for an analysis or a wiki question; reviewing a manuscript; learning
and teaching critical reading.

## When to make a breakdown

A breakdown is the deep mode of reading a paper, not the default:

| Depth | What | For which papers |
|---|---|---|
| **Default** | a claims digest: question, setup, claims with quotes (literature-sourcing, or `biblio digest claims`) | any paper read |
| **On use** | a breakdown (this protocol): conditions, figure pass, inferences, rivals, citing line, blind attack | a paper something now relies on |

**Triggers:** a paper presented at a journal club or in a talk; a paper an
analysis or a manuscript leans on for a specific claim; a load-bearing source
of a contested question; reviewing a manuscript; a paper chosen to teach a
critical-reading move. Each breakdown costs a supplement, a figure pass and a
blind attack; most papers are cited for one fact a digest already covers.

## Inputs

- the full text and the figures: **look at the key figures yourself**; a
  breakdown that reads only the text inherits the authors' description of
  their figures;
- the claims digest, if one exists: cite its claims, don't repeat them;
- **the supplement: required.** In the first run it decided the main
  question. Until it is held, mark each rebuttal "Supp, unseen";
- **check each figure crop is the figure it claims to be:** in the second
  run the crops labelled as supplementary figures were fragments of the main
  article (the PDF and the text came from different versions). Without usable
  crops, read the figures from page renders (`pdftoppm`) and say so.

## Steps → sections of `papers/<key>/breakdown.md`

1. **One paragraph:** what was measured, what is concluded, and which steps
   are inferred rather than measured.
2. **Conditions:** one table of the facets every claim holds under: species
   and population, drugs, state, recording, reference, channel selection,
   event definitions, unit of analysis; each with a quote. Assumptions the
   paper borrows (e.g. a polarity convention) are marked *assumed*.
3. **Claim ladder:** measured → derived → interpreted → framework. Note
   **hedging drift** (the same rung stated as a result in one section and as
   open in another), quoting both.
4. **Figure pass:** for each key figure, what each panel shows, *including
   what it doesn't*: per-subject spread behind group statistics, cells that
   are not significant, axis floors and colour scales, rescaled effect sizes,
   possible leakage. State the axis limits, the colour scale **and the
   per-panel values the reading uses** (both runs misread a figure: a
   cluster's extent; a fold-change and dots pooled across panels).
5. **Argument map:** the main claim, sub-claims and the inferences between
   them, as a tree. For each inference, the Toulmin parts (grounds, warrant,
   backing, qualifier, rebuttals), plus **answered?**: does the paper answer
   the rebuttal (with a quote), or does the answer sit in a supplement not
   held. Search the **whole paper**. A critique's own premises need sources
   too. **Before writing "no":** search the paper's own data for anything
   that constrains the rebuttal, and for every control list what it does
   **not** control for (both runs closed "answered?" too early).
6. **Stasis:** for each open point, whether the dispute is one of fact,
   definition, quality or policy.
7. **Rival readings:** alternatives that produce the same data, each with
   the test that would tell them apart.
8. **What it does not show:** scope limits, as "not in this paper".
9. **Uses:** a short take per use: journal-club prompts; what an analysis
   may and may not cite it for; reviewer requests; which critical-reading
   move the paper teaches.
10. **Check:** how each open point was resolved and what a reader would
    look at to check it (the review's step 3, in `breakdown-check.md`).

## Review

1. **Quote check:** every quoted string is exact in the full text and the
   supplement: `biblio quotes check papers/<key>/breakdown.md --text <key>
   --text <supplement>`. Unquote labels, paraphrases and an earlier version's
   wording rather than loosening the check.
2. **Blind attack** (agent `paper-attacker`): a fresh agent reads the paper
   and writes its own critique list *before* seeing the breakdown, then
   attacks the breakdown: wrong facts, unfair critiques (the paper answers
   them), overreach (figure readings included), quotes that don't fit,
   misses, structure.
3. **Resolve by rule:** open points are resolved from the paper, not by
   judgment:
   - what the paper **reports** (numbers, tests, figures, supplement)
     outranks what it **says** about them;
   - where they differ, record both side by side;
   - describe, don't weigh: no "how serious" ratings.
   The result is `breakdown-check.md`. A person's review is optional and
   comes with use; until then the breakdown is "agent-checked",
   `reviewed: null`.
4. **Learn:** what the run taught about the protocol is noted where the
   project keeps such notes; a failure seen in two runs becomes a proposed
   change to this protocol.

**Main limit:** drafter and attacker are both Claude. An outside reader is
still to come.
