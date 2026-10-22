---
name: wiki-review
description: >
  Help a person review the project knowledge wiki: walk the review queue (draft
  pages written by an agent), present each page as a review packet with its
  claims checked against the sources, and record the person's decision
  (accept, request changes, reopen). Use when asked to "review the wiki",
  "go through the drafts", "what needs review", "accept this page", or before
  a wiki release tag. Never use it to approve pages on your own.
metadata:
  short-description: Review queue -> packets -> the person decides -> record it
  tags: [wiki, review, knowledge-base]
  tooling:
    cli: [biblio wiki status, biblio wiki review packet, biblio wiki review accept, biblio wiki review flag, biblio wiki review reopen, biblio wiki lint]
---

# Wiki review

Agents draft wiki pages; people review them (SPEC principle P11). A page
becomes `reviewed` only when a named person says so. Your job is to make that
judgment fast and well informed, and to record it exactly.

## When to use

- The person wants to go through drafts, or asks what is waiting for review.
- Before tagging a wiki release (`wiki-<subject>-vX.Y`), where every page in
  scope must be `reviewed` or later.
- A reviewed page changed materially and should go back to draft.

## Workflow

1. **Queue.** `biblio wiki status` lists the review queue (drafts by `llm` or
   `mixed`). Agree with the person on a batch: one hub's reading order is a
   good unit, about 5 to 10 pages per sitting.
2. **Packets.** `biblio wiki review packet <pages...> --out <file>` writes one
   packet per page: lede, open flags, lint; each claim beside its quote, the
   quote marked verified exact / APPROXIMATE / MEANING CHANGED / NOT FOUND
   with its section and `path:line` in the paper; citations without a quote;
   numbers not found in the cited papers (project numbers labeled); where
   each citation resolves (pool-only keys must join the project
   bibliography); figures; hubs and links; the page's log history.
   Start the pre-check from "Citations without a quote" and "Numbers": that
   is where drafts go wrong.
3. **Pre-check (yours, before the person reads).** For each page, read the
   page and spot-check what lint cannot: does each claim say what its quote
   says, are numbers in the main sections general knowledge rather than
   project results, is anything important from the source missing, does the
   page hold one idea. Write your doubts as proposed flags, each one line and
   concrete ("the lede says granule layer; the quoted source says inner
   molecular layer"). Do not fix the page during review.
4. **Present.** Per page: title, the one-line verdict you would suggest
   (accept / changes / unsure), your proposed flags, and the packet's open
   flags. Keep it short; link the page so the person can open it.
5. **Record exactly what the person decides:**
   - accept: `biblio wiki review accept <page> --by "<their name>"`; add
     `--resolve-flags` only if they say the open flags are settled.
   - changes: `biblio wiki review flag <page> "<what to change>"`, one flag per
     requested change, in their words.
   - stable (reviewed, lint clean, in use): `... accept <page> --by ... --stable`.
   - reopen a reviewed page: `biblio wiki review reopen <page> --reason "..."`.
6. **After the batch:** `biblio wiki lint` and `biblio wiki hubs`; summarize
   how many pages were accepted and flagged, and which flags someone (often an
   ingest run) should work on next.

## Hard rules

- Never run `accept` without an explicit decision from the person in this
  conversation, and always with their name in `--by`. Never put your own or a
  model's name there.
- Never edit page content during a review; changes go in as flags and are
  made afterwards, then reviewed again.
- `accept` refuses pages with lint errors or open flags. Do not work around
  that (no manual frontmatter edits of `status` or `reviewed`).
- A page accepted earlier and then changed materially goes back with
  `reopen`; small fixes (typos, links) do not need it.
