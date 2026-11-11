---
name: paper-scrutiny
description: >
  (beta) Break down and scrutinise one paper: conditions, figure pass, the
  argument as Toulmin inferences with "answered?", rival readings, what it can
  and cannot be cited for; then a blind attack by the paper-attacker agent and
  a check list resolved by rule. Use to prepare a paper for a journal club or
  talk, to weigh a claim an analysis relies on, or to review a manuscript. Not
  for a summary (literature-sourcing writes digests).
metadata:
  short-description: Breakdown -> quote check -> blind attack -> resolve by rule
  tags: [literature, appraisal, journal-club, review]
  stability: beta
  needs: [biblio]
  agents: [paper-attacker]
  tooling:
    cli: [biblio fulltext, biblio figures run, biblio quotes check]
---

# paper-scrutiny (beta)

The method is `PROTOCOL.md` next to this file (v1.1). **Read it first.**
This is the run sheet. The user's role is optional: ask them only for the
paper, the supplement, and decisions about the method; don't hand them
judgments the paper can resolve.

## 1. Is a breakdown the right depth?

A claims digest (literature-sourcing) is the default. A breakdown is for a
paper something now relies on (PROTOCOL.md, "When to make a breakdown"). If
the user wants a summary, write the digest instead.

## 2. Inputs, all before drafting

1. **The text:** the paper-text skill; note the version (author manuscript
   or published).
2. **The supplement: required.** Ask the user for its PDF (from Zotero or
   the publisher's page, with a doi.org link from the bibliography, never
   guessed or fetched by you). Convert it like the paper, or read it with
   `pdftotext -layout`. Until it is in, mark rebuttals "Supp, unseen".
3. **Figures:** `biblio figures run --key <key>` gives native-resolution
   figures with a manifest. Check each is the figure it claims to be;
   otherwise render pages (`pdftoppm -f N -l N -r 110 -png <pdf> <out>`) and
   say so. Look at every key figure yourself.
4. **A claims digest**, if there is one: read it and cite its claims.

## 3. Draft `papers/<key>/breakdown.md`

In the user's folder. Follow PROTOCOL.md's sections 1-10, with a frontmatter
header (citekey, version, protocol, status, sources, supplement, figures).
Two rules caught errors in both trial runs:

- **"answered?":** search the whole paper and its data before writing "no";
  for every control, say what it does not control for.
- **Figure readings:** state axis limits, colour scale and the per-panel
  values used.

Mark arithmetic you did as yours. No numbers outside quotes, no ratings.

## 4. Quote check

```bash
biblio quotes check papers/<key>/breakdown.md --text <key> --text <supplement.md|.pdf>
```

Fix every non-exact quote by copying it again or unquoting a label or
paraphrase.

## 5. Blind attack

Run the `paper-attacker` agent (in the background). Give it the citekey, the
paths of the full text, supplement and figures, the breakdown's path, and one
line on what kind of paper it is. It reads the paper before the breakdown and
returns a report. Then:

1. **Check its checkable claims yourself** (quotes, figure readings,
   arithmetic). Agreement between two agents is not review.
2. **Save the report** as `papers/<key>/breakdown-attack.md`, with a header
   saying what you verified.
3. **Apply the corrections** as the breakdown's next version, each marked
   "← A<n>", and run the quote check again.

## 6. Resolve by rule → `papers/<key>/breakdown-check.md`

Per open point: reported data outrank the authors' description; where they
differ, record both; describe, don't weigh. One row each: resolution,
anchor, what to look at. Finish with the **citing line** (what the paper is
safe and not safe to cite for). Status "agent-checked", `reviewed: null`.

## 7. Close

Tell the user the three paths and the citing line. Note what the run taught
about the protocol where the project keeps such notes. Save with explicit
paths (`git add papers/<key>` or `datalad save papers/<key>`).

## Without the agent

`biblio skills install` copies `paper-attacker` into `.claude/agents/`; the
plugin install provides it too. Without it, start a fresh subagent with the
agent file's text as its instructions.
