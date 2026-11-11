---
name: paper-text
description: >
  Get a paper's full text, figures and header: look it up by citekey, title,
  author or DOI in the project and the shared pools, or convert a PDF the user
  has with docling. Use when the user names a paper or gives a PDF for Claude
  to read, or asks "do we have <paper>?". Questions about what a paper says go
  on to literature-sourcing. Not for downloading papers.
metadata:
  short-description: Find a paper's text (project, pools) or convert the user's PDF; check the title
  tags: [papers, docling, fulltext]
  stability: stable
  needs: [biblio]
  tooling:
    cli: [biblio profile show, biblio fulltext, biblio locate, biblio init, biblio add doi, biblio docling run]
---

# paper-text

Find or make the converted text of a paper, check it is the right paper, and
say where it is. This skill only finds texts; questions about the content go
to **literature-sourcing**.

## Steps

0. **Setup.** `biblio profile show`. If it prints `agent_notes`, follow them:
   they name the lab's hosts, collection and docling command, and a laptop
   route. A biblio workspace is a folder with `.projio/biblio/biblio.yml`
   (the current one or a parent).
1. **Pin down the paper:** citekey, DOI, title words, first author and year,
   or a PDF path. Ask if it is ambiguous.
2. **Look for a text already held**, in this order:
   - by citekey: `biblio fulltext <key> --lines 1-15` (project, then pools);
   - by DOI or "Author Year Title": `biblio locate "<item>"` prints where
     each item is held (project, pool, Zotero) and its citekey;
   - in the user's folder from earlier sessions: `bib/derivatives/docling/*/`.
3. **If none is held and the user has the PDF:**
   - Work in a biblio workspace in the user's current folder; create one with
     `biblio init` if there is none. Never convert into a temporary or
     scratch folder: later sessions must find the text.
   - The key: `biblio add doi <doi>` when the DOI is known (it prints the
     citekey); otherwise `author_year_FirstWord`.
   - Copy the PDF to `bib/articles/<key>/<key>.pdf`; never move or rename
     the user's original.
   - `biblio docling run --key <key>` (about a minute per paper on a CPU;
     books take longer, say so).
   - The text lands in `bib/derivatives/docling/<key>/<key>.md`, figures in
     `<key>_artifacts/`.
4. **No text and no PDF:** stop and ask the user to save the PDF (from
   Zotero or the publisher's page) and give its path. Do not search the web
   for PDFs or download them; never bulk-download.
5. **Check it is the right paper.** Compare the title near the top of the
   text (and `header.json` when GROBID has run) with what was asked. A pool
   folder can hold a different paper than its key says. Report a mismatch
   instead of reading on.
6. **Report:** the `.md` path and its word count, the number of figures in
   `_artifacts/`, where it came from (project, pool, new conversion), and
   the version held (preprint, accepted, published) when the text shows it.
7. **Questions about the content go to literature-sourcing**, even a quick
   "what does it show?": it answers with claims whose quotes are checked.

## Notes

- docling's figure PNGs are crops at screen resolution: good for reading,
  not for slides (`biblio figures run --key <key>` gives native resolution).
- Pools are read-only. New conversions belong to the user's folder.
