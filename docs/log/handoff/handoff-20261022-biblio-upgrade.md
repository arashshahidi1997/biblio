---
title: "Handoff: biblio upgrade (scope, wiki toolkit, H items, W16, D10)"
date: 2026-10-22
branch: feat/knowledge-graph
status: hold
---

# Handoff 2026-10-22: biblio upgrade

## How to resume

- Repo: `/storage2/arash/projects/projio/packages/biblio`, branch
  **`feat/knowledge-graph`** (de-facto upgrade branch; not merged, not pushed).
  The global `biblio` CLI (uv tool env) runs editable from this checkout, so
  switching branches changes what every project's `biblio` does.
- Tests: `pixi run -e dev test` (350 passed, 0 skipped). Never use bare
  `python3`: on gamma2 it is the shared Anaconda base.
- The uv tool env was reinstalled today with `biblio[openalex,zotero,ui]`;
  MCP servers started before ~16:40 run old code until restarted.
- Plan of record: `docs/backlog.md` (milestones, forcing goals, item IDs).
  Design: `docs/explanation/{scope,wiki,principles}.md`.

## What shipped this session (newest first)

| Commit | What |
|--------|------|
| 3777ec6 | backlog D11: figures round 2 (journal-club feedback) |
| 55a2736 | pixi dev/test env committed; GUI tests run again; docling error detail restored; `python-multipart` added to `ui` extra |
| 05c9692 | backlog H09 (Zotero fallback citekeys) |
| c3257a5 | D10 `biblio figures run`: native-resolution figures (embedded via pdfimages, else pdftoppm 300 dpi) |
| 6752a97 | W16 wiki lint resolves citekeys and quotes across pools |
| 84116de | backlog repaired (corrupted by an edit in 7a7de86) |
| 1b823c9 | H08 current Claude models, text-block extraction, refusal fallbacks |
| 7a7de86 | H07 log triage (89 cancelled, 15 resolved) |
| af4d642 | H06 citation edges between held papers (`biblio graph local`) |
| 8e9a364 | H05 conda out (pixi/uvx) |
| f6f965a | H04 test fixes, `library lint` crash |
| f1739dc | H03 DOI metadata from the registry first |
| 9d1dfd8 | H02 one family-name rule for citekeys |
| 44ffbcf | H01 `.projio/biblio/biblio.yml` resolved everywhere |
| c0252a3, 8db497a | backlog + principles/resources/ideas write-up |
| af65941 | wiki toolkit phase 1 (`biblio wiki init/stub/lint/hubs/status`, `biblio skills`) |
| 02822e1, 1b2bbce | scope doc |
| 6ba5751 … 8ea470e | KG experiment scaffold, a07 people view, foundations bib (92 works) |

Verify state: `pixi run -e dev test` 350 passed. Real-data checks: ingest of
60 verified DOIs reproduces hand-checked keys; `graph local` on pixecog cache
2,114 edges; wiki lint with journal-club's pools 1.1 s; figures on
alemanzapata_2026 give Figures 1-6 at 300 ppi.

## Uncommitted / in flight (not mine, don't sweep in)

- Pre-existing WIP: `.gitignore`, `.projio/*`, `.vscode/settings.json`,
  `mkdocs.yml` (projio-managed blocks), staged deletions of
  `.claude/settings.json`, `.codex/config.toml`, `.mcp.json`, untracked
  `Taskfile.yml`, `.projio/Taskfile.yml`, `docs/log/mkdocs.yml`, log index files.
- journal-club session's edits: R04 issue note reopened with feedback
  (`docs/log/issue/issue-arash-20261022-154443-625358.md`, now backlog D11);
  R06 idea note untracked.
- The projio superproject shows `packages/biblio` as modified (submodule
  pointer); not committed there.

## Parked / open

- **I04 one-paper Zotero ingest:** buildable now (pyzotero in pixi and uv
  envs) but only testable against mocks from gamma2; real check needs the
  laptop local API or a Zotero web API key.
- Pre-existing: the Zotero fallback in `zotero.item_to_bibtex` has its own
  citekey rule (H09).

## Prioritized next steps

1. **D11** figures round 2 (journal-club, after its 2026-10-23 talk): captions
   and numbers, ED/Supp names, `ga`, logo threshold, vector crop, provenance
   fields. Reference: journal-club `code/figures.py`.
2. **I05** reference triage for one paper (prototype in journal-club,
   `papers/alemanzapata_2026_DeltasSpindles/refs.json`).
3. **I04** Zotero one-paper ingest (+ laptop to server skill); decide test path.
4. **M1 wiki in use:** W02 (pixecog layer-ID subject), W03 link style, W04
   editor setup how-to.
5. **M2 digest:** D01 read by section, D02 digest store, D03 summary/question modes.
6. Small: H09.

## Kickoff

Read `packages/biblio/docs/log/handoff/handoff-20261022-biblio-upgrade.md`,
then continue from "Prioritized next steps" on biblio branch `feat/knowledge-graph`.
