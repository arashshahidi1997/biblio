---
title: "Handoff: biblio 0.2.0 to 0.3.3 (wiki in use, review, figures round 2, claims digests, synthesis)"
date: 2026-10-23
branch: master (= feat/knowledge-graph)
status: hold
---

# Handoff 2026-10-23: biblio wiki, review, figures, digests

## How to resume

- Repo: `/storage2/arash/projects/projio/packages/biblio`. `master` and
  `feat/knowledge-graph` are the same commit (v0.3.3), on GitHub and the RIA
  store. The checkout is on `feat/knowledge-graph`; switching to `master` is
  blocked only by pre-existing WIP (below), which is fine.
- The global `biblio` (uv tool env `/storage2/arash/infra/uv-tools/projio`)
  runs editable from this checkout. After a version bump refresh its metadata
  with `uv pip install --python /storage2/arash/infra/uv-tools/projio/bin/python3 --no-deps -e .`
  (Pillow is installed there for the figure overlay check).
- Tests: `pixi run -e dev test` (449 passed).
- LLM features use the `claude` CLI (found via `BIBLIO_CLAUDE_CLI`, PATH, nvm);
  if it fails with "OAuth session expired", run `claude` once and `/login`.
- Plan of record: `docs/backlog.md`. Design: `docs/explanation/wiki.md`,
  how-to: `docs/how-to/wiki-editors.md`.

## What shipped (releases)

| Version | What |
|---|---|
| 0.2.0 | release of the upgrade branch: wiki toolkit, review, skills, refs triage, add zotero, figures |
| 0.2.1 | exact-only quote fidelity (FID003 approximate, FID004 meaning changed); lint folders; init --tag vocab; stub quoting; srcbib in lint |
| 0.2.2 | review packet: claims beside quotes with section and path:line, unbacked citations, numbers, figures, hubs, history |
| 0.2.3 | refs triage DOI cleanup, duplicates, OpenAlex titles/years; wiki figure short captions; --version; task facet; SUG004 |
| 0.2.4 | figures round 2 (D11): names fig-N / fig-SN / ed-N / ga, caption repair, logos skipped, panels merged, vector PDF per figure, provenance manifest v2, overlay check |
| 0.3.0 | claims digests (D01 read by section, D02 store, D05 claims mode), wiki-synthesize skill |
| 0.3.1 | Contested-block quotes checked, `biblio fulltext`, synthesis page type, HTML entities in quotes |
| 0.3.2 | journal-club R17-R24 (claude lookup, inner quotes, packet --save, init --title, figure captions on facing page, page-count mismatch refused, staged output, hub match: all) |
| 0.3.3 | claims-2 prompt (R25): quoted author caveats and rigor notes, terms, inconsistencies |

Also this session (in other repos): projio skill discovery for packages
(W15, `projio.skills` entry point; projio master 95a1c2f, which also merges the
LSM talk branch); labpy dropped from projio docs and the sirota profile
(uncommitted, see below); pixecog wiki W02 (47 pages, untracked).

## Real-use evidence

- journal-club (0.3.1 run): 28 claims digests, 391/391 quotes exact; 41 wiki
  pages lint clean; 4 synthesis pages (T14); review packet for 39 drafts.
- wiki-ingest eval: skill 21/21 vs baseline 18/21 (workspace in a session
  scratchpad, not kept).
- claims-2 on alemanzapata_2026: 18 claims, all exact, 10 terms, 2 real
  inconsistencies, 9 quoted rigor notes.

## Uncommitted / in flight (not mine, don't sweep in)

- biblio: `.gitignore`, `.projio/*`, `.vscode/settings.json`, `mkdocs.yml`,
  `pixi.lock` (2 lines from test runs), staged-deletion leftovers, log index
  files, `docs/log/mkdocs.yml`, the R06-era idea note `idea-...154518` is now
  committed.
- projio (`talk/lsm-open-science-infra`, fully merged into master): ~48
  modified and ~39 untracked files. Grouping proposed to the user, not
  applied: A pixi/go-task migration (own branch), B labpy cleanup (mine), C
  pipeio-guide + literature-audit skills, D LSM deliverables, E log notes,
  F local config (leave), two `.bak` files (delete with OK). Tests pass with
  the WIP (552).
- pixecog: `docs/wiki/` untracked by the user's choice (design docs + 47 pages).

## Open / next

1. journal-club: upgrade its 28 digests to claims-2 (`--force`); the user
   reviews 39 drafts (`biblio wiki review packet --save`); pool-only papers
   need the user's OK to join its bibliography.
2. D13 cross-digest view (`digest claims-table`), W23 synthesis `rests_on`.
3. R26 idea: discovery graph views of the wiki (lab / timeline / effect modes),
   with viz-studio; ties to W09 views.
4. W05-W07 refactor ops (relink, merge, extract); W18-W22 project-source gaps.
5. projio WIP grouping (above) when the user decides.

## Kickoff

Read `packages/biblio/docs/log/handoff/handoff-20261023-biblio-wiki-digest.md`,
then continue from "Open / next".
