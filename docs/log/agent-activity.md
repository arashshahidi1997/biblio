# Agent Activity Log

Recent agent session summaries for handoff context.

## 2026-03-28 18:47 | biblio | opus | 1 steps

**Note:** The projio MCP server registration (`projio/mcp/biblio.py` + `server.py`) needs the `biblio_tag_vocab` tool registered — I couldn't write to those files due to permissions. The biblio-side functions are ready.

Session: `ab332f8a` | Task: `task-arash-20260328-183529-707815.md`

## 2026-03-28 18:59 | biblio | opus | 1 steps

**6. `make test`** passes (21/21 existing tests). New test file was saved but couldn't be run independently due to permission restrictions.

Session: `cbab501c` | Task: `task-arash-20260328-183533-140894.md`

## 2026-03-28 19:07 | biblio | opus | 1 steps

**Note:** The projio MCP server registration (`src/projio/mcp/server.py` and `src/projio/mcp/biblio.py`) couldn't be written due to permission restrictions on the parent package. The biblio-side functions are ready — the projio tools just need wrappers added.

Session: `b4ac92c9` | Task: `task-arash-20260328-183530-864527.md`

## 2026-03-28 19:17 | biblio | opus | 1 steps

**Tests** — 18 tests covering prompt construction, LLM call (mocked), vocabulary validation/filtering, reference propagation logic with threshold, auto-tag skip logic, caching roundtrip, orchestrator merging, MCP wrapper, and CLI parser

Session: `e1410ca8` | Task: `task-arash-20260328-183532-000175.md`

## 2026-03-28 19:27 | biblio | opus | 1 steps

**Note:** The projio MCP server wrappers (`src/projio/mcp/biblio.py`) couldn't be written due to permission restrictions on the parent package. The biblio-side functions are ready — the projio tools just need wrappers added.

Session: `69b5ecfd` | Task: `task-arash-20260328-183534-265778.md`

## 2026-03-28 19:35 | biblio | opus | 1 steps

**Tests:** 20 new tests (111 total passing) covering prompt assembly, LLM mocking, MCP delegation, CLI parsing, and template validation.

Session: `48137e91` | Task: `task-arash-20260328-183535-407935.md`

## 2026-03-28 19:44 | biblio | opus | 1 steps

**130 tests pass** (111 existing + 19 new).

Session: `24818cce` | Task: `task-arash-20260328-183536-559855.md`

## 2026-03-28 21:14 | biblio | opus | 1 steps

**Model payload** — `/api/model` now includes `has_summary`, `has_concepts`, `has_slides`, `has_autotag` per paper

Session: `0b5a94ba` | Task: `task-arash-20260328-210152-348312.md`

## 2026-03-28 21:19 | biblio | opus | 1 steps

**Tests**: 130 passed. Saved with datalad.

Session: `a3c281ce` | Task: `task-arash-20260328-210153-600539.md`

## 2026-03-28 21:25 | biblio | opus | 1 steps

### CSS (`App.css`)
- `.col-tree-smart-form`, `.col-tree-query-editor`, `.col-tree-query-input`, `.col-tree-query-help` styles

Session: `9536f3ab` | Task: `task-arash-20260328-210154-791668.md`

## 2026-03-28 21:30 | biblio | opus | 1 steps

**`frontend/src/App.css`**
- Added `.slides-pre` style for the slides markdown display

Session: `aec30795` | Task: `task-arash-20260328-210155-950332.md`

## 2026-03-28 21:37 | biblio | opus | 1 steps

### CSS
- Styled all new components: concept pills (per-category colors), comparison bar/modal, reading list panel with score bars, concept search results

Session: `8ff02a40` | Task: `task-arash-20260328-210157-123214.md`

## 2026-03-28 21:42 | biblio | opus | 1 steps

**`frontend/src/App.css`** — Styles for research tab, subtabs, mode tabs, textarea, cite highlights, slide preview grid/cards, template picker cards

Session: `d5bfef1a` | Task: `task-arash-20260328-210158-299797.md`
