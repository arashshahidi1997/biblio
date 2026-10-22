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

- [ ] **H01 Config path.** 17 places in `cli.py`, plus `site.py`, `pool.py`
  and `ui.py`, hardcode `bib/config/biblio.yml` although
  `config.default_config_path` resolves `.projio/biblio/biblio.yml` first.
  `docling run/batch` fail in projio workspaces without `--config`
  ([issue 2026-10-22](log/issue/issue-arash-20261022-154246-616402.md), R01).
  *Done when* every command uses `default_config_path`, help texts say so, and
  a test runs `docling run` in a `.projio/biblio` workspace.
- [x] **H02 Citekey generator.** One rule in `citekey.py`, which `ingest.py`
  now delegates to: generational suffixes dropped (`Shipman III` → `shipman`);
  lowercase particles dropped, as biblatex's `useprefix=false`
  (`de Waard` → `waard`, `van Beest` → `beest`, matching existing keys);
  capitalized multi-word family names kept whole (`La Barre` → `labarre`,
  `Buckingham Shum, Simon` → `buckinghamshum`); letters NFKD cannot decompose
  transliterated (`ø` → `o`); hyphens removed (`Aleman-Zapata` →
  `alemanzapata`, R02). Same key for "Given Family" and "Family, Given".
  Limit: "Simon Buckingham Shum" without a comma still gives `shum`.
- [ ] **H03 DOI ingest metadata.** Take bibliographic metadata from the DOI
  registry (CSL-JSON by content negotiation); use OpenAlex for enrichment only
  after a DOI-checked match; map entry types. Today arXiv DOIs resolve to the
  wrong work and books lose authors. *Depends* H02. (B8)
- [ ] **H04 Failing tests.** 10 tests fail on the current branch, mostly LLM
  mocks (`test_author_search`, `test_autotag`, `test_cite_draft_review`,
  `test_present`, `test_biblio_summarize`, `test_tag_vocab` CLI lint).
  *Done when* the suite is green or the tests move with their modules (S03 to S05).
- [ ] **H05 Conda out.** Remove conda paths from docling hints and the GUI
  setup; a pixi feature or uv tool for docling. (B11)
- [ ] **H06 Local citation edges.** `graph.py:316` drops OpenAlex references
  between two held papers. *Done when* the corpus graph includes them.
- [ ] **H07 Log triage.** The notio log holds 122 task notes and 16 issues
  from March 2026, mostly GUI and writing-helper features; several are marked
  `scheduled` four or five times, and 14 issues are automatic "Execution
  failed" reports. Nothing is queued in worklog (checked 2026-10-22). *Done
  when* each note is closed, superseded by an item here, or kept with a reason.

## W. Wiki toolkit

- [x] **W01 Phase 1.** `biblio wiki init|stub|lint|hubs|status`,
  `biblio skills list|install`, skills `wiki-maintain` and `wiki-ingest`,
  13 tests (af65941). Answers R05 part 1.
- [ ] **W16 Pools in lint (R05, first for journal-club).** Citekey and quote
  checks resolve against the project bibliography *and* the shared pools
  (`pool.search`), since a literature wiki cites mostly pool papers. *Done
  when* a wiki citing a pool paper lints without CIT001, and its quotes are
  checked against the pool's full text.
- [ ] **W17 Figure embeds (R05).** Wiki pages embed figures from D10 in a way
  that works with annexed files in both editors. *Depends* D10, W04.
- [ ] **W02 First real subject (M1).** Use phase 1 on pixecog's layer
  identification (pixecog wiki backlog L01 to L03): hub, ingest of the
  audit, code pages. Record what the tools lacked. *Depends* W01.
- [ ] **W03 Link style (M1).** Decide one style per wiki (SPEC §12.1);
  proposal: relative markdown links, made move-safe by W05.
- [ ] **W04 Editor setup (M1).** How-to for Obsidian (vault at the repo root,
  excluded folders, link settings, unlocked annex checkout for figures) and
  VS Code (settings written between managed markers).
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
- [ ] **W11 wiki-query and wiki-review skills.** Answers from the wiki, then
  full text by citekey and section; review packets for people. (B4, P11)
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
- [ ] **D06 methods mode.** Comparison rows with quoted parameters; from
  `compare.py` and a03.
- [ ] **D07 citations mode.** Citing sentences with intent labels
  (`docs/specs/biblio/citation-context.md` in projio); from a06.
- [ ] **D08 people digest.** The a07 author index moves into biblio.
- [ ] **D09 Fold concepts and autotag** into the subject and claims modes and
  the shared vocabulary (W14).
- [ ] **D10 Figures at native resolution (R04).** docling crops are page
  renders at 144 dpi. For each docling picture (page and bbox in its JSON),
  take the embedded image covering the bbox, else re-render the bbox at a
  configurable dpi (default 300); write `bib/derivatives/figures/<key>/` with
  a manifest (number, caption, page, bbox, embedded or rendered, size).
  Consumers: the wiki (W17) and figure requests.

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
- [ ] **I03 Needs-PDF queue and pool:** keep as storage; review the surface.
- [ ] **I04 One-paper ingest from Zotero (R02).** `biblio add zotero
  <itemKey|citekey>` through the local API (laptop) or the web API: entry in
  srcbib under biblio's citekey convention, PDF copied, extraction queued;
  plus a skill for the laptop-to-server flow. `zotero.py` pull is
  collection-wide today. *Depends* H02.
- [ ] **I05 Reference triage for one paper (R03).** Per reference: in a pool
  with full text, PDF available, metadata only, or absent; matched by DOI,
  then normalized title and year, then OpenAlex `referenced_works`; across
  project, pools and an optional Zotero export; JSON and markdown output.
  `get_absent_refs` (`grobid.py:505`) checks only the project's own srcbib.
  Consider GROBID `consolidate_citations` on by default: about 79% of pool
  references lack DOIs. This is discovery from a held paper (scope: partial).
