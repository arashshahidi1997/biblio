# Upgrade backlog

**Updated:** 2026-10-22

The plan for bringing biblio to its proposed [scope](explanation/scope.md):
digest and wiki as the core, discovery and ingest partial, a slimmer
interface. Each item has an ID, what it depends on, and when it counts as
done. Mark `[x]` when done. Principles are cited by ID
([principles](explanation/principles.md)).

**Milestones:** M0 hygiene → M1 wiki in use → M2 digest by section → M3 wiki
phase 2 → M4 slimming. The knowledge-graph experiment (K) runs alongside and
feeds M2 and M3.

## Forcing goals

Two projects drive the order of work:

| Project | Goal | Needs first |
|---------|------|-------------|
| journal-club | lab-meeting talk on `alemanzapata_2026_DeltasSpindles`, **2026-10-23**: ingest the paper and its references, a literature wiki, figures, the talk (its `backlogs/2026-10-23-alemanzapata-tooling.md`) | **W16**, H01, then I04, I05, D10 |
| pixecog | wiki subject "layer identification" (its `docs/wiki/BACKLOG.md`) | W02, W03, W04 |

Requests from journal-club are tagged R01 to R06 below.

## H. Hygiene (M0)

- [x] **H01 Config path.** Every command resolves `.projio/biblio/biblio.yml`
  first, then the legacy `bib/config/biblio.yml` (`config.default_config_path`);
  17 hardcoded paths in `cli.py` plus `site.py`, `pool.py` and `ui.py` fixed;
  `pool link` writes to the resolved file; tests cover ten commands and guard
  the literal. Reported from journal-club (R01, issue 2026-10-22).
- [x] **H02 Citekey generator.** One rule in `citekey.py`, which `ingest.py`
  now delegates to: generational suffixes dropped (`Shipman III` → `shipman`);
  lowercase particles dropped, as biblatex's `useprefix=false`
  (`de Waard` → `waard`, `van Beest` → `beest`, matching existing keys);
  capitalized multi-word family names kept whole (`La Barre` → `labarre`,
  `Buckingham Shum, Simon` → `buckinghamshum`); letters NFKD cannot decompose
  transliterated (`ø` → `o`); hyphens removed (`Aleman-Zapata` →
  `alemanzapata`, R02). Same key for "Given Family" and "Family, Given".
  Limit: "Simon Buckingham Shum" without a comma still gives `shum`.
- [x] **H03 DOI ingest metadata.** `ingest dois` and `add doi` take
  bibliographic metadata from the DOI registry (CSL-JSON by content
  negotiation, with retries); OpenAlex fills in only when the registry has no
  record, and only when its work carries the requested DOI; entry types map
  from CSL and OpenAlex types (books, chapters, proceedings, arXiv preprints
  as `@misc`). The normalize path applies the same DOI check. On the 60
  verified foundations DOIs, ingest now yields exactly the hand-checked keys.
  Limit: records the registry lists without authors (e.g. one Morgan Kaufmann
  book) still get `anon_`.
- [x] **H04 Failing tests.** Suite green (328 passed). Causes: a real bug,
  `biblio library lint` crashed because a local import in `main()` made
  `load_library` local to the whole function; LLM tests assumed the API
  backend while the default became the `claude` CLI, so test runs shelled out
  to the real CLI (tests now default to `BIBLIO_LLM_BACKEND=api` in
  `conftest.py`); a fake client and three message assertions were out of date.
  Correction: those runs used the shared Anaconda Python, which lacks
  `fastapi`, so the GUI tests were skipped. Tests now run in pixi
  (`pixi run -e dev test`, extras and poppler declared in `pixi.toml`):
  350 passed, none skipped, after fixing a lost docling error detail in the
  GUI, three tests on legacy config paths, and `python-multipart` missing
  from the `ui` extra.
- [x] **H05 Conda out.** The GUI's docling setup offers a pixi environment
  (`pixi run [-e env] docling`) and rejects conda with a clear message;
  hints, the config template and docs show pixi and `uvx` commands. Bundle
  rebuilt. (B11)
- [x] **H06 Local citation edges.** `graph expand` records references
  between held papers in `local_edges.json` (beside the candidates, which stay
  a to-ingest list); `biblio graph local` rebuilds them from cached OpenAlex
  works without expanding; the site graph reads them. On pixecog's cache
  alone: 2,114 edges among 333 held papers, where there were none.
- [x] **H07 Log triage.** 122 task notes: 29 done, 89 cancelled (duplicates
  of done or kept notes, or superseded by D02, D04, D05, W10, S03), 4 kept
  pending with a reason (GUI work deferred to S08; PDF annotations after D02).
  15 automatic "Execution failed" issues resolved. Open issues each name
  their backlog item. Each changed note has a dated follow-up line.
- [x] **H08 LLM model names.** API backend maps `sonnet`/`opus`/`haiku`/`fable`
  to `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-4-5`,
  `claude-fable-5-1`; `BIBLIO_LLM_MODEL` sets the default. Text comes from
  the `text` blocks (responses start with thinking blocks); refusals are
  reported; caps get headroom for thinking (at least 16000); Opus 5.5,
  Sonnet 5.5 and Fable 5.1 calls opt into server-side refusal fallbacks
  (`fallbacks: "default"`).
- [ ] **H09 Zotero fallback keys.** `zotero.item_to_bibtex` builds keys with
  its own rule (capitalized family name, one title word); route it through
  `citekey.canonical_citekey_str` like the other ingest paths (H02). Only
  `zotero pull` still uses it: `add zotero` replaces the key. Since I04's
  follow-up the rule uses authors only (editors for an edited volume).
- [x] **W01 Phase 1.** `biblio wiki init|stub|lint|hubs|status`,
  `biblio skills list|install`, skills `wiki-maintain` and `wiki-ingest`,
  13 tests (af65941). Answers R05 part 1.
- [x] **W16 Pools in lint (R05, first for journal-club).** Citekeys resolve
  against all project bibliographies (`compiled.bib`, `merged.bib`,
  `main.bib`) and the pools in `pool.search`; a key found only in a pool is
  a note (CIT003, "add before rendering"), not an error; quotes are checked
  against the pool's full text. Real run with journal-club's two pools: 1.1 s.
- [x] **W17 Figure embeds (R05).** `biblio wiki figure KEY N [--page P]`
  prints the embed with caption and citation from the D10 manifest;
  `biblio wiki embeds [--get] [--unlock]` lists embedded files by annex state
  and fetches or unlocks them; lint `IMG001` (content absent), `IMG002`
  (locked, invisible in Obsidian), `IMG003` (paper's figure without its
  citation). Laptop test 2026-10-22: Obsidian ignores annex symlinks, an
  unlocked figure displays. VS Code untested. D11's manifest fields (credit,
  licence, `ref`) will feed the snippet.
- [x] **W02 First real subject (M1).** pixecog layer identification
  (its L01-L03), 2026-10-22: hub, 3 concepts, 6 methods, 17 markers (4
  stubs), 12 pitfalls, 8 tool pages from the 2026-10-19 audit and the code,
  written by four agents in parallel with `wiki stub` + `wiki-ingest` rules;
  47 pages lint clean, 59 body code anchors verified; all `author: llm`,
  awaiting review; untracked in pixecog (its `docs/wiki/` was never
  committed). What the tools lacked, fixed the same day: lint checks code
  anchors in the body and Snakemake `rule name:` anchors; `stub` writes
  `evidence:` and `code:` and takes `--status`; placeholder lede flagged
  (STR003); relations `affects` (pitfall to marker) and `implements` (tool);
  `Observed in` may name sessions (SCOPE001); no hub suggestion for pages a
  hub already lists. Not fixed: W18 to W22. Skill-creator evals not run yet.
- [ ] **W18 Evidence IDs.** `evidence:` (notio note and analysis IDs) is never
  checked; notes exist as `result-arash-20260918-225102-356299` while docs cite
  `result-20260918-225102`, and audits shorten groups (`-0202`). Decide the
  canonical form, resolve through notio, lint EVD001; make IDs clickable.
- [ ] **W19 Citing project documents.** Section-level links into analysis docs
  (`audit §3`) are prose only; numbers taken from them have no fidelity check
  (P8 covers literature full text only). Heading-anchored links plus quote and
  number checks against the cited section.
- [ ] **W20 Scope beyond sub/ses tokens.** SCOPE001 misses depths (2400),
  note IDs and analysis IDs on general sections. Defaults for ID patterns in
  `project_tokens`; a number heuristic as a suggestion.
- [ ] **W21 Template and SPEC fit.** `Our experience` as an optional H2 for
  concept, method and tool pages; SPEC's ">5 H2 = split" contradicts the
  method template (6 required); default `scope` for tool pages about project
  code; whether `localizes` needs anatomy pages first; marker vs tool page
  boundary for code detail. pixecog's SPEC still says wikilinks (§6.2) and its
  section numbers drifted (W13 moves the spec here).
- [ ] **W22 Stub and vocab ergonomics.** Relation flags on `stub`; a command
  to bump `updated:`; add a facet from the CLI; `vocab.yml` writes safe for
  parallel writers (W02 pre-added tags to avoid the race); SUG001 word count
  states what it counts (a writer saw 804 vs 714).
- [x] **W03 Link style (M1).** Relative markdown links, the default
  `link_style: markdown` (wikilinks opt-in): Obsidian resolves, inserts and
  rewrites them on rename; with relative link format a rename turns wikilinks
  into path wikilinks. Decided from the laptop test 2026-10-22.
- [x] **W04 Editor setup (M1).** [How-to](how-to/wiki-editors.md): vault at
  the project root, wikilinks off, relative paths, auto-update links,
  `bib/` excluded, `.obsidian/workspace*.json` ignored, unlock embedded
  figures. VS Code section untested. Also fixed from the same test:
  `wiki init --tag` and `stub --tag` add the tag to `vocab.yml` (unknown
  facets refused), so a new wiki passes lint at once.
- [ ] **W05 relink (M3).** Rename or move a page and rewrite inbound links;
  dry run, log. (P5)
- [ ] **W06 merge (M3).** Frontmatter union, aliases, redirect stub, never
  delete; dry run, log. (P2)
- [ ] **W07 extract (M3).** Section to a new page, leaving the lede and a
  link; dry run, log. (P1)
- [ ] **W08 suggest (M3).** Lint findings as machine-readable refactor
  suggestions (signal, principle, op). *Depends* W05 to W07.
- [ ] **W09 views (M3).** Generate Obsidian Bases tables (review queue,
  contested, stubs), people pages (from K02/D08) and a typed graph as static
  HTML. (P12)
- [ ] **W10 wiki-synthesize skill (M3).** Concept and theory pages with
  evidence for and against, method comparisons, open questions. *Depends* D04
  to D06.
- [ ] **W11 wiki-query and wiki-review skills.** Review done 2026-10-22:
  `biblio wiki review packet|accept|flag|reopen` (accept needs `--by` a
  person, refuses lint errors and open flags; frontmatter edited in place)
  and skill `wiki-review` (agent pre-checks and proposes flags, the person
  decides). Open: `wiki-query` (answers from the wiki, then full text by
  citekey and section). (B4, P11)
- [ ] **W12 promote.** Gate check and plan for the lab hub. (SPEC §9)
- [ ] **W13 Spec home.** Move the wiki SPEC from pixecog into biblio's docs
  after its first review, so method and tools version together.
- [ ] **W14 One vocabulary.** The wiki's `vocab.yml` and biblio's
  `tag_vocab.yml` become one file (pixecog wiki backlog E03).
- [ ] **W15 Skill discovery (R05).** projio discovers skills shipped by
  installed packages; until then `biblio skills install`.

## D. Digest (M2)

- [ ] **D01 Read by section.** One reader that yields sections from GROBID
  TEI, falling back to docling headings. *Done when* no LLM module truncates
  text. (B6)
- [ ] **D02 Digest store.** `bib/derivatives/digest/<mode>/<context>/<citekey>.*`,
  addressed by citekey, mode, context, prompt version and model;
  `biblio digest <mode>` command group. (B7)
- [ ] **D03 summary and question modes.** Port `summarize.py` and `extract.py`
  onto D01 and D02, with quotes. (B5)
- [ ] **D04 subject mode.** Draft source-page content for a wiki subject;
  feeds `wiki-ingest`.
- [ ] **D05 claims mode.** Claim, evidence and gap candidates; from K03.
  Target shape: journal-club's hand-written
  `papers/alemanzapata_2026_DeltasSpindles/digest.md` (claims with evidence,
  caveats, test statistics and n), plus a `talk` context that adds rigor
  notes and figure roles (R06).
  Rigor notes use a fixed vocabulary (design validity, confounders,
  statistical pitfalls, evidence level), borrowed with credit from K-Dense's
  MIT `scientific-critical-thinking` references.
- [ ] **D06 methods mode.** Comparison rows with quoted parameters; from
  `compare.py` and a03.
- [ ] **D07 citations mode.** Citing sentences with intent labels
  (`docs/specs/biblio/citation-context.md` in projio); from a06.
- [ ] **D08 people digest.** The a07 author index moves into biblio.
- [ ] **D09 Fold concepts and autotag** into the subject and claims modes and
  the shared vocabulary (W14).
- [x] **D10 Figures at native resolution (R04).** `biblio figures run --key K`
  (or `--all`): for each docling picture, the embedded image matching its
  page and displayed size is extracted losslessly (`pdfimages -all`), else the
  bbox is re-rendered (`pdftoppm`, 300 dpi default); tiny pictures skipped;
  `bib/derivatives/figures/<key>/` with `manifest.yml` (number and caption
  from docling, page, bbox, embedded or rendered, pixel size). Needs poppler.
  On journal-club's target paper: Figures 1-6 as the original 300-ppi JPEGs
  (1900 px wide; docling's crops are 144 dpi), 1.8 s. Panel splitting later.
- [x] **D11 Figures, round 2 (R04 reopened by journal-club).** 2026-10-23:
  names from captions (`fig-3`, `fig-S2`, `ed-4`, `ga`), the nearest unused
  "Figure N" text when docling links a caption to a margin icon, pictures
  under 1% of the page and uncaptioned ones under 5% skipped, split panels
  merged (touching pieces; every piece on Extended Data and supplementary
  pages), every figure also as a one-page PDF cropped to its box
  (`pdftocairo`, vector art kept), `art` raster/vector/mixed from image
  positions (`pdftohtml -xml`) plus a render-vs-image check (Pillow, extra
  `figures`) that catches labels drawn as outlines over an image, and a v2
  manifest: project-relative `pdf`, `pdf_sha256`, `pdf_version`, `credit`,
  `licence`, per-figure `ref`, `kind`, `art`, sha256 per file. Checked on
  alemanzapata_2026 (ga + Figs 1-6 native, logos gone), maingret_2016 (4
  figures numbered and captioned, vector) and sebastian_2023 (Figs 1-7 and
  ED 1-10 from 24 pictures). Poppler only (no PyMuPDF, AGPL).

## K. Knowledge-graph experiment

- [x] **K01 Scaffold, a07 people view, foundations literature.**
- [ ] **K02 Gold annotations** for 3 papers, before looking at any output (E3).
- [ ] **K03 a01** LLM extraction into the reference schema. *Depends* K02, D01.
- [ ] **K04 a06** citation statements.
- [ ] **K05 a08** RAG control, all 14 questions (E6).
- [ ] **K06 a02 as "wiki as graph"**: wiki frontmatter and citations exported
  to the interchange format. *Depends* W02.
- [ ] **K07 a03** comparison tables.
- [ ] **K08 Schema update:** `scope` field, status ladder, Pitfall, Tool and
  Marker types, shared relation vocabulary, Question renamed to Gap.
- [ ] **K09 Conclusion** in `eval/scoreboard.md`: which approach supplies
  which layer.
- [ ] **K10** The experiment's quote checker uses `biblio.wiki.fidelity`.

## S. Slimming (M4)

- [ ] **S01 MCP.** Choose the few tools that stay (decision in the scope doc). (B3)
- [ ] **S02 RAG.** Optional extra, off by default, or removed until evaluated
  (decision). (B4)
- [ ] **S03 Writing helpers** (`cite_draft.py`, `lit_review.py`, `review`)
  move to notio manuscript, consuming digests.
- [ ] **S04 Slides.** Remove `present.py` (projio `present_*` covers it).
- [ ] **S05 reading_list.py.** Drop, or rebuild as discovery from held papers.
- [ ] **S06 EZProxy, auth, Zotero push.** Keep, plugin or drop (decision).
- [ ] **S07 site.py** folds into the wiki's generated views (W09).
- [ ] **S08 GUI.** Keep the navigators; trim the run and setup endpoints;
  later, a review desk with select-to-annotate (serves K02 and review).

## I. Ingest and discovery (partial)

- [ ] **I01 Pool-aware derivatives** (projio task, pending): docling, GROBID
  and OpenAlex outputs resolved from the shared pool.
- [ ] **I02 GROBID coverage.** Empty GROBID folders in pixecog (4 of 38 in the
  test corpus); rerun and record failures.
- [ ] **I06 Stale keys in resolved.jsonl.** pixecog's
  `openalex/resolved.jsonl` holds 424 records, including old-style keys
  (`Swanson_2025_Topography` beside `swanson_2025_TopographyPutative`).
  Re-resolve after citekey normalization and drop records whose key is no
  longer in the bibliography.
- [ ] **I03 Needs-PDF queue and pool:** keep as storage; review the surface.
- [x] **I04 One-paper ingest from Zotero (R02).** `biblio add zotero REF
  [--local] [--extract] [--dry-run]`: REF is an item key, DOI, Better BibTeX
  citekey or biblio's own key; entry to `bib/srcbib/zotero.bib` under
  biblio's citekey with `zotero = {ITEMKEY}`, PDF to `pdf_root` (stored file,
  main text and published version preferred); a paper already in the project
  keeps its key, an entry in `zotero.bib` is refreshed under its key.
  `--local` needs no config. Skill `zotero-add` covers the laptop-to-server
  flow. Real check on the laptop 2026-10-22 ([results](log/task/task-arash-20261022-laptop-zotero-obsidian.md)):
  all reference forms, 0.24 s per paper, clear error when Zotero is closed;
  its bugs fixed (editors no longer authors, preprints keep the arXiv id,
  re-runs say "refreshed", no path after `pdf: none`). Also fixed:
  `ZoteroClient` never passed `local=True` to pyzotero.
- [x] **I05 Reference triage for one paper (R03).** `biblio refs triage KEY
  [--zotero zotero.sqlite|export.bib] [--openalex]`: each GROBID reference
  gets `fulltext`, `pdf`, `metadata` or `absent`, with where it is held
  (project, `pool:<name>`, `zotero`) and how it matched (DOI; normalized title
  with year within one, tolerating OCR noise and a glued-on venue; a DOI from
  the paper's OpenAlex `referenced_works`, which also adds references GROBID
  missed). Output `bib/derivatives/refs/KEY/triage.{json,md}`. On
  journal-club's target paper (2 s, 4 s with OpenAlex): 21 fulltext, 12
  metadata, 34 absent; agrees with its prototype except two extra finds.
  Open: `consolidate_citations` default (costs GROBID time, sends every
  reference to Crossref); `paper_absent_refs` MCP tool still uses the old
  srcbib-only check.
