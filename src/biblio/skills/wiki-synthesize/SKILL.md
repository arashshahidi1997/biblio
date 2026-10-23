---
name: wiki-synthesize
description: >
  Write wiki pages that combine several papers: a concept or theory page with
  the evidence for and against, a comparison of methods or subtypes across
  studies, or the open questions on a subject. Builds on claims digests
  (`biblio digest claims`), so every statement taken from a paper carries a
  verbatim quote that was checked against that paper. Use when asked to
  "synthesize", "what does the literature say about X", "write the page on X
  from these papers", "compare how studies define Y", or for a talk's
  background pages.
metadata:
  short-description: Claims digests of several papers -> cross-paper pages with verified quotes
  tags: [wiki, synthesis, literature, knowledge-base]
  tooling:
    cli: [biblio digest claims, biblio digest claims-table, biblio digest list, biblio wiki stub, biblio wiki lint, biblio wiki hubs, biblio wiki review packet]
---

# Wiki synthesize

A synthesis page answers a question across papers ("are ripple subtypes the
same thing in different labs?"). The risk is the opposite of ingest: claims
drift from their sources as they are combined. So the page is built from
claims digests, whose quotes were checked against each paper, and your own
cross-paper reasoning is kept visibly apart from what the papers say.

## When to use

- A subject has several ingested or held papers and a page should combine them.
- A talk or review needs background: the state of a question, the camps, the
  open problems.
- Not for one paper: that is `wiki-ingest`.

## Workflow

1. **Scope.** Agree on the page's question and type: `synthesis` (a question
   answered across papers: definitions compared, agreement, disagreement, open
   problems), `concept` (what X is, with the evidence), `method` (how studies
   measure X, compared), or `question` (one open problem). One question per page.
2. **Sources.** List the papers that bear on it: the hub's source pages,
   `biblio refs triage` of the key paper, the project bibliography. Only
   papers with full text can be used.
3. **Digests.** `biblio digest list`; for each source paper without a claims
   digest, `biblio digest claims <citekey>` (context `wiki`; `talk` for talk
   preparation). Read each digest's quote counts: only claims whose quote is
   `exact` can be used as they are. For the others, and for anything a digest
   only paraphrases (often the authors' own caveats), find the exact words with
   `biblio fulltext <citekey> --grep "<words>"` or `--section <id>` (it reads the
   same text the quote check uses, in the project or a pool), or leave it out.
4. **Map.** Put the relevant claims side by side with `biblio digest
   claims-table <citekey>... --grep "<words>" [--kind finding] [--quotes]`
   (one table across digests; without citekeys, every digest), then judge
   which agree, which
   disagree, which use different definitions or methods for the same word
   (often the real story: two labs' "ripple types" may not be the same
   thing). Note each paper's evidence strength from its digest: animals vs
   events as samples, single channels, thresholds set by eye.
5. **Write.** `biblio wiki stub <name> --type <type> --tag <facet/value>
   --author llm --status draft`, then fill the sections:
   - Each statement from a paper: one sentence in your words, then its quote
     from the digest, copied unchanged: `> "verbatim" [@citekey]`. Add the
     citekey to `sources:`.
   - Agreement across papers: say how many and which, each with its quote.
   - Disagreement: both sides with their quotes in a `> **Contested.**`
     block (quotes there are checked like any other), and what would decide it.
   - Your own cross-paper reasoning (a pattern no single paper states) goes
     in a paragraph that starts with **Synthesis:** and cites no paper as its
     source. It is a proposal for the reviewer, not a fact.
   - Definitions that differ between papers: a small table (paper, term,
     operational definition, quote).
   - Open problems: a `question` page each, linked.
6. **Lint and review.** `biblio wiki lint <page>` until it shows no errors and
   no FID warnings: every quote exact (an approximate quote, FID003, is a
   warning but not acceptable on a synthesis page). Long pages are fine when
   the length is quoted evidence (quotes do not count toward the word limit).
   `biblio wiki hubs`; then `biblio wiki review packet <page> --out <file>`
   and hand the file to the person.
   Papers held only in a pool show as CIT003 notes: list them for the person,
   who adds them to the project bibliography (e.g. `biblio add doi <doi>`)
   before anything is rendered.
7. **Log.** Append to `log.md`: date, `synthesize`, the papers used, pages
   created and updated.

## Hard rules

- No statement attributed to a paper without its exact quote; a claim whose
  quote you cannot make exact is left out, not paraphrased into the page.
- Never merge two papers' numbers into one figure or average them; report
  each with its source.
- A finding and an interpretation are different: keep the digest's `kind`
  (say "the authors interpret ..." for interpretations).
- Synthesis paragraphs are marked as such and never cite a paper as their
  source.
- Pages you write are `author: llm`, `status: draft`; a person reviews them.
- Project results only in "Our experience" (P10); a hub's scope and reading
  order are a person's curation.
