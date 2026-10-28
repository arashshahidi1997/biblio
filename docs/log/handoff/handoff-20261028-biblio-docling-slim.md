---
title: "Handoff: biblio 0.3.5 (docling JSON without page images, pinned docling, lit-studio rename)"
date: 2026-10-28
branch: feat/knowledge-graph
status: hold
---

# Handoff 2026-10-28: biblio 0.3.5

A headless session started from lit-studio at the user's request: commit the
projio sync and worklog leftovers, then lit-studio's R47, R48, R41, and check R05.

## How to resume

- Repo: `/storage2/arash/projects/projio/packages/biblio`, branch
  `feat/knowledge-graph`, **not pushed** (github, RIA) and not published to
  PyPI: the user decides. `master` is behind by this session's commits.
- Tests: `pixi run -e dev test` (498 passed). Docs: `pixi run -e docs docs`
  (strict, clean).
- The global `biblio` (uv tool env, editable) already runs the new code; its
  metadata still says 0.3.4 until
  `uv pip install --python /storage2/arash/infra/uv-tools/projio/bin/python3 --no-deps -e .`
  (not run).

## Commits

| Commit | What |
|---|---|
| d0421a6 | projio sync output: `.gitignore` projio block, `code.runner: pixi`, figio package, mkdocs search/monorepo/ezlinks + Log nav, render CSL/quarto.yml, notio result template. The sync had dropped the Backlog, Wiki Toolkit and Principles nav entries; kept them |
| 6499714 | gitignore `/.projio/biblio/` (the repo's local bibliography workspace, same content as the ignored `bib/config/`, plus a generated `merged.bib`) |
| 2910eb4 | worklog notes 2026-10-23..28 and indexes |
| 2d1d4ff | R47: page images dropped on write, `biblio docling slim`, docling version in `_biblio.json` |
| cd21ccf | R41: `docs/explanation/wiki.md` |
| 5e20970 | R48: pinned docling pixi env |
| (release) | 0.3.5: CHANGELOG, version, backlog (I11, I12, W15, R41 lines), notes closed, this handoff |

## Requests

- **R47** done (I11). Verified first that biblio reads only `pages` keys and
  `size`, `texts`, `pictures` (`prov`, `captions`, `image.uri`). Page images
  are removed after each conversion (`docling.page_images`, default false
  unless `image_export_mode: embedded`). `biblio docling slim --key | --all |
  --dir [--dry-run]` uses temp file + rename (locked annex symlink becomes a regular file).
  On copies: 20.0 MB -> 669 KB, 7.2 MB -> 207 KB. **Not run** on lit-studio or
  the pools; owners run `--dry-run`, then for real, then `datalad save`.
- **R48** done (I12). pixi env `docling` (2.64.1 plus rag's companion
  versions, CPU torch), installed, 1.7 GB. Pools came from rag's 2.64.1; a
  pool paper converted through the env gave a byte-identical `.md`.
  lit-studio/pixecog can switch `docling.cmd` (see `docs/how-to/docling.md`).
- **R41** done: three lines only; the journal-club slide template and "journal-club Rnn" comments are kept.
- **R05** closed: W01, W16, W17 and W15 (ticked now) cover all four parts.

## Left alone

- `.vscode/settings.json`: uncommitted. Its base is personal (conda as VS
  Code env manager) and the projio block made it invalid JSON (no comma after
  the second line). The user should fix or discard it.
- pixecog's wiki SPEC home (W13, issue 20261028-010355): open, through worklog W02.
- Old open issue `issue-arash-20260327-110607-562641` (unified PDF ingestion), not reviewed.

## Open / next

1. lit-studio: `biblio docling slim --all` on its 71 folders, switch `docling.cmd` to the pixi env, close its I05.
2. The pools' owners: `biblio docling slim --dir <pool>/derivatives/docling --dry-run`.
3. Push and release 0.3.5 when the user says so.
