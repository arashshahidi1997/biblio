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

1. **Start from a claims digest when you can.** For a paper, `biblio digest
   claims <citekey>` gives its claims with evidence, caveats and a verbatim
   quote each, checked against the full text (only quotes marked `exact` are
   verified). Use it as your map of the paper, then read the sections it
   points to. **Read the source in full** in any case: for a paper, read
   `bib/derivatives/docling/<citekey>/<citekey>.md` section by section (fetch
   it with biblio docling if missing). A summary alone is not enough.
2. **Extract** what the subject needs, each item with its location:
   claims and findings, methods with parameters, markers, pitfalls, open
   questions. Copy quotes and numbers verbatim with the section name.
3. **Plan.** List the pages that change or are created, one line each, with
   the principle that places the content there (one idea per page, P1; each
   fact in one place, P2). When someone is in the conversation and more
   than 3 pages change, show the plan and let them adjust it before writing.
   When you run unattended (a batch, a delegated task), carry out the whole
   plan and put it at the top of your report instead: stopping early leaves
   the wiki half connected, and the review step is where people judge it.
4. **Write.**
   - New pages: `biblio wiki stub <name> --type <type> --tag <facet/value>
     --author llm --status draft`, then fill the sections. Record project
     notes and analysis IDs in `evidence:` and code in `code:`
     (`path::function`). Title plus a one-paragraph lede
     is the page's interface (P3).
   - Existing pages with `status: stub` or `draft`: edit in place.
   - Pages with `status: reviewed` or later: write a proposed diff in the
     report, do not edit (P11).
   - Links between pages follow `link_style` in `wiki.yml` (default
     `markdown`): relative markdown links with the page title as text, e.g.
     `[Sharp-wave ripple](../concepts/sharp-wave-ripple.md)`.
   - Literature claims cite `[@citekey]`. Back each claim taken from a paper
     with a short verbatim quote, `> "verbatim" [@citekey]`, copied exactly
     from the full text (docling's split ligatures such as "identif ied" may
     be written whole). Lint checks every quote against the paper: only exact
     matches pass; an approximate match is a warning (FID003) and a changed
     negation, comparative or number an error (FID004). The quote is what
     makes the claim checkable for the reviewer. Add every cited key to `sources:`.
   - Project results go only in "Our experience" or a `case` page, cited by
     stable ID (P10).
   - Conflicting sources: record both, add `> **Contested.**` and a
     `contradicts:` link (P9).
   - For a paper, create or update its `source` page: contribution to the
     subject, key claims with sections, figures, links to full text.
   - Figures: `biblio figures run --key <citekey>` once, then paste the output
     of `biblio wiki figure <citekey> <n> --page <page>` (embed, caption,
     citation). Embed only figures the page discusses.
5. **Lint and views.** `biblio wiki lint <changed pages>` until no errors,
   then `biblio wiki hubs`.
6. **Log.** Append to `log.md`: date, `ingest`, source, pages created and
   updated.

## Hard rules

- A hub's scope and reading order are a person's curation: propose changes
  in the report, do not edit them. Regenerating the generated lists with
  `biblio wiki hubs` is fine.
- Touch only the wiki. Project backlogs, notes and analysis documents are
  sources, not targets.
- Pages written by you carry `author: llm` (or `mixed` when editing a human
  page) and `status: draft` at most.
- No claim without a source location; no number that is not in the source.
- Never edit raw sources.
- Do not rely on RAG retrieval; read the cited full text.
