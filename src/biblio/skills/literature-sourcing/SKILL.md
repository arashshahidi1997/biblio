---
name: literature-sourcing
description: >
  Required for any statement about what a paper says, shows, measured or
  concludes, even a quick "what is the main finding". Use to answer a question
  from one or more papers, write a claims digest, or back the claims and
  numbers of a slide or page: every claim carries an exact quote, checked
  against the paper's full text by `biblio quotes check`.
metadata:
  short-description: Question -> texts -> claims with exact quotes -> quotes check -> the checked file
  tags: [literature, quotes, evidence, claims, talks, wiki]
  stability: stable
  needs: [biblio]
  tooling:
    cli: [biblio fulltext, biblio locate, biblio quotes check, biblio refs triage, biblio digest claims-table]
---

# Literature sourcing

Every statement taken from a paper rests on a quote copied character for
character from the paper's full text and checked. Read `MODEL.md` (next to
this file) first: the **claim** is the unit of every answer.

## When to use

- A question about one or more papers: what they show, how it was done,
  what they say about X. Also "do we have X, and what does it show?".
- A claims digest of one paper, on request.
- The claims and numbers of a slide, a talk or a wiki page, to back with
  quotes; or a file whose quotes need checking.

Not for writing a wiki page from digests (`wiki-synthesize`) or for adding
papers (`zotero-add`, `paper-text`).

## Workflow

1. **Pin the question.** What would count as an answer: the claim, the
   species and preparation, the measure. Split ambiguous wording into
   checkable parts.
2. **Get the texts.** For each paper, the paper-text skill: held in the
   project or a pool (`biblio fulltext <key>` works for both), or converted
   from the user's PDF. Check the title matches before reading.
3. **Find what is missing.** For papers not held, `biblio locate --from
   list.txt --openalex` gives doi.org links. Give the user a capture list
   with those links only (never a guessed DOI). Papers come from the user's
   Zotero or the publisher's page, one at a time; never bulk-download.
4. **Read what the question needs.** Methods for "how", results and figure
   captions for "what". Find exact wording with `biblio fulltext <key>
   --grep "<regex>"` (prints section and line), a section with `--section`,
   context with `--lines A-B`. For a figure, open the PNGs next to its
   caption. If the project has claims digests, `biblio digest claims-table
   --grep "<words>"` finds claims already checked.
5. **Write the answer in a file** in the user's folder, never a temporary
   one: `answers/<key>-<short-topic>.md` (several papers:
   `answers/<topic>.md`; a digest: `answers/<key>-digest.md`). Start with the
   paper(s) and the path of each text checked against. Then the claims, in
   MODEL.md's format:
   - level, statement, conditions in brackets, the quote in straight double
     quotes copied from the text, the location;
   - **numbers only inside quotes**, the conditions' n included; a number in
     no quote needs its own quote, or it stays out;
   - docling's `&lt;`, `&gt;`, `&amp;` are written as `<`, `>`, `&` (the
     check accepts both); a garbled symbol stays as converted, so it checks,
     with its reading in brackets right after the quote: "20-60 l A" [µA];
   - the gaps: what the question asks that the text doesn't say ("not in the
     text held"); the version held when it could matter;
   - several papers: say per answer whether it is established (several
     independent papers), reported (one), a hypothesis, or disputed (both
     sides quoted); a review's statement is quoted as the review's.
6. **Check every quote:**
   `biblio quotes check answers/<file>.md --text <key> [--text <key2>]`
   (`--text` takes a citekey or a path to a `.md`, `.txt` or `.pdf`). Every
   quote must be `exact`. For `approximate` or `changed`, copy the passage
   again from `biblio fulltext`; for `missing`, find the right passage or
   remove the quote marks from a paraphrase. Never loosen the check. Repeat
   until it prints `[OK]`.
7. **Reply with the checked file, not a retelling.** Every claim in the
   reply carries its level, conditions, quote and location exactly as in the
   file; nothing is shortened into unquoted prose, and no number appears
   outside a quote. If the file is long, show the claims the question needs
   and give the path for the rest. Anything you add goes under a final
   **Notes** line, without new numbers. End with the checker's last line
   (`N quotes; N exact`) and the file path.

## A source list for a talk or page

For slide or page sources, one quote per item with its line, checked
without `--text`:

```
- Q3a, oliva_2016_RoleHippocampal, Discussion, L290: "in a minority of cases we observed ..." — exact
- Q3b, same, L302: "..." — exact
```

`biblio quotes check <file> --json <file>.quotes.json`; `--fix-lines` fixes
wrong line numbers.

## Hard rules

- No number or claim from a paper without a quote that checks exact.
- Quotes come from the paper's text (`biblio fulltext` or the docling
  `.md`); never from memory, an abstract page, search snippets or another
  document's paraphrase.
- Your own inference is labelled as yours and cites no paper as its source.
- Cutting must not change the meaning: a quote that drops a "not", a
  condition or a species is wrong even if each word matches.
- People judge: Claude drafts and checks; the reader decides what to trust.
- Pools and other projects' files are read-only.

## Notes

- A quote is one line, 12 characters or more. Split a long one with `…`;
  each part must be exact.
- When a table, equation or symbol is too garbled to quote, say so instead
  of forcing it.
- Converted texts and journal figures are not for public repos or sites.
