---
name: wiki-ingest
description: >
  Ingest a source into the project knowledge wiki: read a paper (by citekey),
  a note, an analysis doc or a code module, extract what is relevant to a wiki
  subject with verbatim quotes and locations, plan which pages change, and
  write or update atomic pages. Use when asked to "add X to the wiki",
  "ingest this paper" or "start the wiki for <subject>".
metadata:
  short-description: Source -> plan -> atomic pages with quotes, then lint
  tags: [wiki, ingest, literature, knowledge-base]
  tooling:
    cli: [biblio wiki stub, biblio wiki lint, biblio wiki hubs, biblio wiki init]
---

# Wiki ingest

## When to use

- A paper, note, analysis document or code module should feed the wiki.
- A new subject starts: `biblio wiki init --subject <name> --tag <facet/value>`
  creates the skeleton (first use) and the subject's hub.

## Workflow

1. **Read the source in full.** For a paper, read
   `bib/derivatives/docling/<citekey>/<citekey>.md` section by section (fetch
   it with biblio docling if missing). A summary alone is not enough.
2. **Extract** what the subject needs, each item with its location:
   claims and findings, methods with parameters, markers, pitfalls, open
   questions. Copy quotes and numbers verbatim with the section name.
3. **Plan.** List the pages that change or are created, one line each, with
   the principle that places the content there (one idea per page, P1; each
   fact in one place, P2). Show the plan and wait when more than 3 pages
   change.
4. **Write.**
   - New pages: `biblio wiki stub <name> --type <type> --tag <facet/value>
     --author llm`, then fill the sections. Title plus a one-paragraph lede
     is the page's interface (P3).
   - Existing pages with `status: stub` or `draft`: edit in place.
   - Pages with `status: reviewed` or later: write a proposed diff in the
     report, do not edit (P11).
   - Links between pages follow `link_style` in `wiki.yml` (default
     `markdown`): relative markdown links with the page title as text, e.g.
     `[Sharp-wave ripple](../concepts/sharp-wave-ripple.md)`.
   - Literature claims cite `[@citekey]`; quotes as `> "verbatim" [@citekey]`.
     Add every cited key to `sources:`.
   - Project results go only in "Our experience" or a `case` page, cited by
     stable ID (P10).
   - Conflicting sources: record both, add `> **Contested.**` and a
     `contradicts:` link (P9).
   - For a paper, create or update its `source` page: contribution to the
     subject, key claims with sections, figures, links to full text.
5. **Lint and views.** `biblio wiki lint <changed pages>` until no errors,
   then `biblio wiki hubs`.
6. **Log.** Append to `log.md`: date, `ingest`, source, pages created and
   updated.

## Hard rules

- Pages written by you carry `author: llm` (or `mixed` when editing a human
  page) and `status: draft` at most.
- No claim without a source location; no number that is not in the source.
- Never edit raw sources.
- Do not rely on RAG retrieval; read the cited full text.
