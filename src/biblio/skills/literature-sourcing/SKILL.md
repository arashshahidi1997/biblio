---
name: literature-sourcing
description: >
  Answer a question or back a claim from the literature with verbatim quotes
  that are checked against the papers' full texts: find the papers held in
  the project and the pools, list the ones that are missing (with doi.org
  links) for the user to capture, read the exact wording by section and line,
  write a source file of quotes, and check every quote with `biblio quotes
  check`. Use when asked to "source this", "find the evidence for",
  "answer the audience's question from the papers", to back the numbers and
  claims on a slide or page, or to check the quotes in an existing file.
metadata:
  short-description: Question -> held papers -> exact quotes by line -> source file -> quotes check
  tags: [literature, quotes, evidence, talks, wiki]
  tooling:
    cli: [biblio digest claims-table, biblio fulltext, biblio locate, biblio refs triage, biblio add zotero, biblio add doi, biblio docling batch, biblio grobid run, biblio digest claims, biblio quotes check]
    mcp:
      - server: projio
        tools: [paper_lookup, biblio_job]
---

# Literature sourcing

Every statement taken from a paper rests on a quote copied verbatim from the
paper's full text and checked exact. Your own reasoning is allowed, marked as
yours, never presented as a source's.

## When to use

- A question from a talk, a review or the user, to answer from papers.
- The claims and numbers of a slide or a wiki page, to back with quotes.
- An existing source file whose quotes need checking.

Not for writing a wiki page from digests (`wiki-synthesize`) or adding one
known paper (`zotero-add`).

## Workflow

1. **Pin the question.** Write what would count as an answer: the claim,
   the species and preparation (rat, mouse, human; sleep, anesthesia, slice),
   the measure. Ambiguous wording ("CA2 projects to radiatum") gets split
   into checkable parts.

2. **Search what is held first.**
   - Claims already digested: `biblio digest claims-table --grep "<words>"`
     (all digests) gives claim, section, line and whether its quote is exact.
     A digest quote marked exact carries its line, the exact characters of
     `<key>.md` when they differ (`quote_raw`, findable with `grep -F`), and
     the whole sentence when the quote is part of one (`quote_sentence`).
   - Exact wording in a paper: `biblio fulltext <key> --grep "<regex>"`; for
     a whole section, `--section <id or title>`; for context around a line,
     `--lines A-B`. The text is docling's, cleaned on the same lines.
   - Is a paper held at all, and where: `paper_lookup(refs=[...])` or, for a
     list, `biblio locate --from list.txt`.
   - What a key paper cites: `biblio refs triage <key>`.

3. **List what is missing.** For papers not held, `biblio locate --from
   list.txt --openalex` gives one table with doi.org links. Give the user a
   capture list with those links only (never a guessed DOI). Do not fetch
   PDFs in bulk from publishers; papers come from the user's Zotero or the
   pools.

4. **Add and extract the captured papers.** `biblio add zotero --from
   refs.txt --local` on the Zotero machine (see `zotero-add`), or `biblio add
   doi`. Then extract exactly those: `biblio grobid run --keys a,b` and
   `biblio docling batch --keys a,b` (or `biblio_job(action="start",
   kind="docling", keys=[...])`); never a batch without keys in a shared
   copy. Optional: `biblio digest claims --keys a,b` for papers you will
   come back to.

5. **Write the source file**, one quote per item:

   ```
   - Q3a, oliva_2016_RoleHippocampal, Discussion, L290: "in a minority of cases we observed ..." — exact
   - Q3b, same, L302: "..." — exact
   ```

   `same` repeats the previous paper; the section is optional; `L<n>` is the
   line `biblio fulltext --grep` printed. Copy the quote from that output,
   unchanged (no ellipses inside a quote, no fixed typos). Beside each
   answer say its status: established (several independent papers),
   reported (one paper), hypothesis, or disputed (both sides quoted), and
   name the species and preparation. A review's statement is quoted as the
   review's; prefer the primary paper when it is held.

6. **Check.** `biblio quotes check <file> --json <file>.quotes.json`. Every
   item must be `exact`. For `approximate` or `changed`, copy the passage
   again from `biblio fulltext`; for `missing`, find the right paper or drop
   the claim. Wrong line numbers: `--fix-lines`. "Not checked (no L<n>)"
   lines claim a check they did not get: add `L<n>` or remove the claim.

7. **Report**: the answer per question with its status, the quotes that
   carry it, what is still missing (the capture list), and the check result
   (`N quotes, N exact`).

## Hard rules

- No number or claim from a paper without a quote that checks exact.
- Quotes come from `biblio fulltext` (or the docling text); never from
  memory, an abstract page, retrieval snippets or another document's
  paraphrase.
- Your own inference is labelled as such and cites no paper as its source.
- Do not change the meaning by cutting: a quote that drops a "not", a
  condition or a species is wrong even if each word matches.
- Do not write into other projects' files; pools are read-only.
