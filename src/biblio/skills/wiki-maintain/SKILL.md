---
name: wiki-maintain
description: >
  Keep a project knowledge wiki healthy: run `biblio wiki lint`, read the
  findings, fix mechanical issues on unprotected pages, propose content and
  structural fixes for the rest, regenerate hubs, and re-lint. Use after an
  ingest or editing session, before a review, or when asked to "lint", "check"
  or "clean up" the wiki. Detects first; restructures only with a dry run and
  the user's go-ahead.
metadata:
  short-description: Lint the wiki, fix what is mechanical, propose the rest
  tags: [wiki, lint, refactor, knowledge-base]
  tooling:
    cli: [biblio wiki lint, biblio wiki hubs, biblio wiki status, biblio wiki stub]
---

# Wiki maintain

The wiki follows the wiki specification (principles P1 to P12, page types,
frontmatter, lifecycle) and the project's binding (`SCHEMA.md`, `wiki.yml`).
`biblio wiki lint` detects deviations; this skill decides what to do about them.

## When to use

- After ingesting sources or an editing session in Obsidian or VS Code.
- Before a human review or a promotion.
- When the user asks to lint, check, tidy or restructure the wiki.

## Workflow

1. **Lint.** `biblio wiki lint --format json` (add page paths to limit scope).
   Group findings by severity and code. Read `principle` and `op` on each.
2. **Fix mechanical issues** on pages with `status: stub` or `draft` only:
   - stale hub lists (HUB001): `biblio wiki hubs`;
   - frontmatter shape (FM002, FM003, FM005, FM007), missing `sources:`
     entries for citations already in the text (CIT002);
   - broken links whose intended target is unambiguous (LNK001, LNK004).
   Never touch `reviewed`, `stable` or `promoted` pages: write the proposed
   change as a diff in your report instead (P11).
3. **Do not auto-fix content findings.** Report them with the location and a
   proposed fix:
   - FID001 quote not found in the source: re-read the cited section of the
     full text (`bib/derivatives/docling/<citekey>/<citekey>.md`) and propose
     the verbatim sentence, or flag the claim in `review_flags`;
   - CIT001 unknown citekey: check `citekey_resolve` / the bibliography; never
     invent a key;
   - SCOPE001 project token on a general page: propose moving the sentence to
     "Our experience" or a `case` page (P10);
   - contradictions with newer sources: add a `> **Contested.**` block with both
     citations and a `contradicts:` link; never overwrite (P9).
4. **Restructure** only from suggestions (SUG001 extract, SUG002 stub, SUG003
   hub), one refactor at a time: show the plan (pages before and after, the
   principle), wait for the go-ahead, apply, run `biblio wiki lint` again,
   append a line to `log.md`. Use `biblio wiki stub NAME --type TYPE` for new
   pages so they get the required sections.
5. **Semantic pass** (pages changed since the last lint and their neighbours):
   look for the same idea explained on two pages (P2, propose merge), pages
   mixing Diataxis modes (P4, propose extract), and claims newer sources
   contradict (P9). Use the full text, not retrieval.
6. **Report.** Errors left, what was fixed, what needs a decision, and the
   `biblio wiki status` review queue.

## Hard rules

- Lint detects; you propose; the user decides on anything beyond mechanics.
- Never set `reviewed:` or advance `status` past `draft`.
- Never edit raw sources (full text, digests, notes, analysis docs, code).
- Quotes and numbers come verbatim from the cited source, or they get flagged.
- Do not use RAG retrieval to answer or verify; read the cited full text.
