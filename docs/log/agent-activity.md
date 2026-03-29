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

## 2026-03-29 04:03 | biblio | opus | 1 steps

**Tests**: 129 passed (1 pre-existing failure unrelated to changes).

Session: `0f8a5782` | Task: `task-arash-20260329-035734-363448.md`

## 2026-03-29 04:14 | biblio | opus | 1 steps

**Tests**: 156 passed (27 new), 1 pre-existing failure unrelated to changes.

Session: `74d3513b` | Task: `task-arash-20260329-040346-938013.md`

## 2026-03-29 04:31 | biblio | opus | 1 steps

**Result: 234 passed, 0 failed.**

Session: `4e57d514` | Task: `task-arash-20260329-041416-742117.md`

## 2026-03-29 04:43 | biblio | opus | 1 steps

**Tests**: 240 passed, 0 failed.

Session: `062266c6` | Task: `task-arash-20260329-041419-108879.md`

## 2026-03-29 04:48 | biblio | opus | 1 steps

**Tests**: 157 passed, 0 failed.

Session: `b1c4e66a` | Task: `task-arash-20260329-041421-534165.md`

## 2026-03-29 04:52 | biblio | opus | 1 steps

**Tests**: 157 passed, 0 failed.

Session: `892ea945` | Task: `task-arash-20260329-041423-824361.md`

## 2026-03-29 04:56 | biblio | opus | 1 steps

**CSS** (`App.css`): Toast positioned fixed at top-center with slide-down animation, styled with existing theme variables (`--accent`, `--panel`, `--accent-soft`). Review modal with overlay, scrollable DOI list.

Session: `9bc695a4` | Task: `task-arash-20260329-041425-565370.md`

## 2026-03-29 05:07 | biblio | opus | 1 steps

**Tests** — 4 new tests added, all 161 pass.

Session: `996b6801` | Task: `task-arash-20260329-041427-972311.md`

## 2026-03-29 05:21 | biblio | opus | 1 steps

**Tests** — 10 tests in `tests/test_dedup.py` covering DOI duplicates, DOI normalization, title similarity, threshold tuning, suggested_keep scoring, OpenAlex ID duplicates, missing bib, and helper functions. All 171 tests pass.

Session: `1aab5521` | Task: `task-arash-20260329-041430-380655.md`

## 2026-03-29 05:26 | biblio | opus | 1 steps

**Integration** (`frontend/src/App.jsx`) — StatsPanel placed above CorpusTab in library view. Status clicks set `statusFilter`, tag clicks set `tagFilter`, both filtering the paper list.

Session: `e78966df` | Task: `task-arash-20260329-041432-126590.md`

## 2026-03-29 05:31 | biblio | opus | 1 steps

All 171 tests pass. Changes saved via datalad.

Session: `2dac9f39` | Task: `task-arash-20260329-041434-028047.md`

## 2026-03-29 05:32 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `25f50c78` | Task: `task-arash-20260329-041436-123461.md`

## 2026-03-29 05:33 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `b6a32ec1` | Task: `task-arash-20260329-041438-478170.md`

## 2026-03-29 05:34 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `2be8d1b3` | Task: `task-arash-20260329-041440-823343.md`

## 2026-03-29 05:35 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `4945e7b4` | Task: `task-arash-20260329-042324-863873.md`

## 2026-03-29 05:35 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `46453059` | Task: `task-arash-20260329-042326-064314.md`

## 2026-03-29 05:36 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `5bf98baa` | Task: `task-arash-20260329-042655-069904.md`

## 2026-03-29 05:37 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `d1d726a7` | Task: `task-arash-20260329-042656-523126.md`

## 2026-03-29 05:38 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `ccc6300a` | Task: `task-arash-20260329-042657-767042.md`

## 2026-03-29 05:39 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `f9629a39` | Task: `task-arash-20260329-042756-903726.md`

## 2026-03-29 05:40 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `d3d3f67a` | Task: `task-arash-20260329-042952-343922.md`

## 2026-03-29 05:40 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `9dba7ec8` | Task: `task-arash-20260329-044730-098416.md`

## 2026-03-29 05:41 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `4bc0018a` | Task: `task-arash-20260329-044727-728422.md`

## 2026-03-29 05:42 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `6be4d05d` | Task: `task-arash-20260329-044728-940076.md`

## 2026-03-29 05:43 | biblio | opus | 1 steps

You've hit your limit · resets 7am (Europe/Berlin)

Session: `0aa0b5d5` | Task: `task-arash-20260329-045256-874019.md`

## 2026-03-29 16:19 | biblio | opus | 1 steps

**Fix 3 — Expand-all confirmation:**
- `App.jsx:1123-1150`: The ⊕ button now shows a two-button confirm/cancel flow (✓/✗) before triggering expand-all, with a tooltip showing paper count
- Added progress indicator (`15/42`) next to the graph toolbar during expand
- `ActionsTab.jsx:235`: Also added inline confirmation (though ActionsTab is currently unused in App.jsx)

Session: `7bf5e878` | Task: `task-arash-20260329-160941-127078.md`

## 2026-03-29 16:24 | biblio | opus | 1 steps

171 tests pass.

Session: `f4e7705d` | Task: `task-arash-20260329-160937-683814.md`
