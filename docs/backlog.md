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
- [x] **W05 relink (M3).** `biblio wiki relink OLD NEW [--apply]`: rename
  (same folder), `folder/name` or `folder/`; wikilinks by name or path,
  markdown links by resolved path, `related:`-type frontmatter values; the
  moved page's own links re-based; code fences untouched; files outside the
  wiki that mention the old path listed. Dry run by default; logged. (P5)
- [x] **W06 merge (M3).** `biblio wiki merge A B [--apply]`: B gets the union
  of list keys (tags, sources, aliases incl. A's title and name, relations,
  minus itself), A's body under `## Merged from ...` with its links re-based,
  status back to draft if it was reviewed; A becomes a stub with
  `redirect: <B>` (lint checks only the target, RED001); links to A point at
  B. Never deletes. (P2)
- [x] **W07 extract (M3).** `biblio wiki extract PAGE --section H --name N
  [--type T] [--apply]`: the section to a new draft page from its type's
  template (under the section of the same name when the type has one), with
  the tags, the citekeys cited in the section as `sources:` and `related:`
  back; the first paragraph and a link stay. Tried on a copy of
  journal-club's wiki (relink, a move across folders, merge, extract): no new
  lint findings except FM008 for the deliberate cross-folder move. (P1)
- [ ] **W08 suggest (M3).** Lint findings as machine-readable refactor
  suggestions (signal, principle, op). *Depends* W05 to W07.
- [ ] **W09 views (M3).** Generate Obsidian Bases tables (review queue,
  contested, stubs), people pages (from K02/D08) and a typed graph as static
  HTML. (P12)
- [x] **W10 wiki-synthesize skill (M3).** Drafted 2026-10-23 on claims digests:
  statements from papers only with their exact quote, own reasoning marked
  **Synthesis:**, contested blocks, definition tables. First run 2026-10-23
  (journal-club T14 "ripple heterogeneity", scratch copy, 7 digests): 3 pages
  + 3 edited, 37 quotes all exact, lint clean. Fixed from its report: quotes
  inside Contested blocks are now checked (they were skipped), quotes do not
  count toward the word limit, a `synthesis` page type, `biblio fulltext
  --grep/--section` for exact wording in project or pool text, precede/follow
  /lead/lag as meaning words. Open: D12, D13, W23.
- [ ] **W11 wiki-query and wiki-review skills.** Review done 2026-10-22:
  `biblio wiki review packet|accept|flag|reopen` (accept needs `--by` a
  person, refuses lint errors and open flags; frontmatter edited in place)
  and skill `wiki-review` (agent pre-checks and proposes flags, the person
  decides). Open: `wiki-query` (answers from the wiki, then full text by
  citekey and section). (B4, P11)
- [x] **W24 Skills audit (2026-10-24).** Test `tests/test_skills_commands.py`:
  every `biblio ...` command a bundled skill names exists in the CLI, and
  each description says when to use it. New skill `literature-sourcing`
  (question -> held papers -> exact quotes by line -> source file -> `quotes
  check`, journal-club's T47 loop). `biblio-batch-curate` moved here from
  projio (it is biblio's pipeline). `zotero-add` covers lists and group
  libraries. Open: delivery to Claude Code with real descriptions (projio
  sync wrote command files whose description was a comment, so agents never
  picked a skill from the task); evals beyond the one `wiki-ingest` run.
- [ ] **W12 promote.** Gate check and plan for the lab hub. (SPEC §9)
- [ ] **W13 Spec home.** Move the wiki SPEC from pixecog into biblio's docs
  after its first review, so method and tools version together.
- [ ] **W14 One vocabulary.** The wiki's `vocab.yml` and biblio's
  `tag_vocab.yml` become one file (pixecog wiki backlog E03).
- [ ] **W15 Skill discovery (R05).** projio discovers skills shipped by
  installed packages; until then `biblio skills install`.

## D. Digest (M2)

- [x] **D01 Read by section.** `biblio.sections`: docling markdown first
  (the text the quote check uses), GROBID TEI as fallback (the reverse of the
  first plan, so copied quotes verify exactly); references and admin sections
  dropped. 2026-10-23.
- [x] **D02 Digest store.** `bib/derivatives/digest/<mode>/<context>/<key>.{json,md}`
  with prompt version, model, source and quote counts; `biblio digest list`.
- [ ] **D03 summary and question modes.** Port `summarize.py` and `extract.py`
  onto D01 and D02, with quotes. (B5)
- [ ] **D04 subject mode.** Draft source-page content for a wiki subject;
  feeds `wiki-ingest`.
- [x] **D05 claims mode (R06).** `biblio digest claims KEY [--context wiki|talk]`:
  claims with evidence, caveats, section and one verbatim quote each, checked
  exact-only, one repair pass; `talk` adds rigor notes and figure roles.
  Decoupled from K03 (the KG experiment can score it later). First real run
  2026-10-23 on alemanzapata_2026 (talk): 15 claims, 15/15 quotes exact, 10 of
  the hand digest's 11 claims plus 2 interpretations, 12 rigor notes. Next:
  a `terms` section (the hand digest's measured/derived/interpreted tables).
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

- [x] **D12 claims-2 prompt (R25).** Quoted author caveats and rigor notes,
  `terms` (layer, operational definition, difference from the field),
  `inconsistencies` (both passages quoted). On alemanzapata_2026: 18 claims
  incl. the missed C5, all quotes exact, 10 terms, 2 real inconsistencies,
  no false rigor note. 2026-10-23.
- [x] **D14 Quote check for any file (R29).** `biblio quotes check FILE...
  [--json OUT] [--fix-lines]` reads journal-club's source format (`- <id>,
  <citekey>, <section>, L<n>: "<quote>" — exact`; `same` or a key named in
  the prose before the item; quoted sections; `L<n> (note):`), checks each
  quote in project then pool full text, reports exact / approximate (with
  the diff) / changed / missing, the located line, heading and pool, exits 1
  unless all exact, and lists items that claim a check without `L<n>`. One
  line numbering (`sections.text_lines`, `\n` only): docling writes stray
  `\r`, which universal newlines counted as breaks (buzsaki_2015: 21 lines
  off); `fulltext --grep`, sections, the checker and the review packet now
  agree with `grep -n`. A quote that occurs twice keeps the written line.
  On journal-club's two source files: 119/119 and 86/86 exact, no line off.
- [x] **D15 Claims digests for a list (R31).** `biblio digest claims KEY... |
  --keys | --from list.txt [--concurrency N] [--screen] [--stale]`: papers
  with a digest are skipped unless `--force` (`--stale` redoes those made
  with an older prompt, e.g. claims-1 to claims-2); a line per paper and a
  summary (papers, digested, skipped, failed, claims, all quotes exact of
  checked) also stored in `bib/derivatives/digest/_runs/claims-<ctx>-<ts>.{json,md}`;
  `--screen` runs it detached with a log beside the summary. Exit 1 if any
  paper failed.
- [x] **D16 Clean docling text (R32).** `biblio.textclean`, applied when a
  full text is read (sections, digests, `fulltext`, the quote checker), line
  for line so line numbers stay those of `<key>.md`: ligature glyph names
  rejoined with a shipped word list (`signi /uniFB01 cant`, `the /uniFB01
  rst`), symbol-font codes mapped where ~820 papers agree (`/C24` ~, `/C0` −,
  `/C14` °, `/C6` ±, `/C2` ×, `/C20`/`/C21` ≤ ≥) and others reported, accents
  before their letter (`Buzs /C19 aki`), HTML entities, and words run
  together split only where the paper writes the same word pairs apart
  (conservative: long glued runs with two rare words stay). The checker
  accepts a quote matching the clean or the raw text, so old quotes with
  artefacts still verify. `biblio fulltext KEY --changes` lists the
  substitutions; `--lines A-B`, `--raw`. Nothing is written into pools.
  On journal-club's Oliva 2016: `(~5 ms)`, `Sharp-wave ripples (SPW-Rs) in
  the hippocampus are`; its two source files still check 278/278 and 86/86.
- [x] **D17 Quote spans (R39).** Every quote a digest checks stores
  `quote_line`, `quote_raw` (a plain substring of `<key>.md`, cut out by
  aligning letters and digits so glued words, entities, `/C24` and ligature
  glyphs line up) and `quote_sentence` (the cleaned sentence, when the quote
  is 3+ words shorter); `biblio digest recheck` fills them for stored digests
  without an LLM; prompt claims-3 asks for whole sentences. On a copy of
  journal-club's 81 digests: 2277 of 2277 exact quotes give a plain
  substring (196 needed the raw span); 1109 of 1274 claim quotes were
  fragments of a longer sentence (claims-2's 8-40 word rule).
- [x] **D13 Cross-digest view.** `biblio digest claims-table [KEY...|--keys|--from]
  [--grep RX] [--kind finding,...] [--section S] [--context] [--quotes]
  [--exact-only] [--json]`: claims of several digests (default all) in one
  markdown table with section line and quote check; a key without a digest is
  named. On journal-club: `--grep spindle --kind finding` gives 69 claims from
  11 papers in one call (the "map" step of `wiki-synthesize` read 7 digests,
  120 KB, by hand).
- [x] **W23 Synthesis provenance.** A **Synthesis:** paragraph cites no paper;
  it now ends with `Rests on: citekey:C3, citekey:C7` (in the paragraph or
  the line after it), and lint checks it: SYN001 warning without a pointer,
  SYN002 error for a claim id the paper's claims digests lack, SYN003 info
  when the paper has no digest, SYN004 warning when the paper is not in
  `sources:`. The wiki-synthesize skill asks for it. journal-club's wiki has
  13 such paragraphs without a pointer (SYN001, warnings only).

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

- [x] **S01 MCP.** Decided by projio's spec `docs/specs/agent-interface-layers.md`
  (branch `docs/agent-interface-layers`): biblio is CLI-first; MCP keeps
  `paper_lookup` (`biblio.mcp.paper_lookup`: citekey, DOI or author-year,
  project and pools, where the derivatives are) and `biblio_job`
  (`biblio.mcp.job`: docling, grobid, oa_fetch and digest jobs that run the
  CLI with `keys`, status from its log, kill), plus `biblio_status`,
  `biblio_ingest`, `biblio_compile`. 34 tools deprecated for one release.
  Usage that decided it: 17 of 37 tools ever called in 350 sessions. Open:
  remove the deprecated tools and their `biblio.mcp` functions next release;
  CLI forms for crossref resolve, PDF validate, library quality, enrich and
  author/institution discovery before those go. (B3)
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
- [x] **I07 A list from Zotero, groups included (R27).** `biblio add zotero
  REF... | --from refs.txt [--library user|group:<id>|all]`: refs may also be
  titles; with `--local` the user's library and every group library are
  searched (`open_libraries`) and the matching library is shown; duplicates
  of one paper (same DOI, else title) resolve to the copy with a stored PDF,
  the others listed; a group PDF the API cannot serve is copied from
  Zotero's `storage/` folder; a summary at the end (added, already present,
  no PDF, not found, duplicates) and a `next:` line with `--keys` for
  GROBID and the docling batch. Tested with a fake client only: the real
  14-paper check (incl. Pfeiffer & Foster 2013 in SirotaLab) needs the
  laptop.
- [x] **I09 Locate a list (R30).** `biblio locate ITEM... | --from list.txt
  [--zotero zotero.sqlite|export.bib|local] [--openalex] [--json OUT]`: per
  DOI or "Author Year Title" line, the best holding (project or pool full
  text, PDF only, entry only; Zotero with library, item key, PDF or not, and
  duplicate items) or "not held", with a doi.org link; OpenAlex fills DOIs
  and catches papers held under another title. Matching: DOI, title with the
  year within one, first author (accents folded) and year with all title
  words. Markdown table plus counts. On journal-club: Navarro-Lobato 2023,
  Dudek 2016 and Buzsáki 2015 (pixecog pool) found from author-year lines.
- [x] **I08 Extract named papers (R28).** `biblio docling batch --keys a,b |
  --from list.txt` converts exactly those papers (a batch in a shared copy no
  longer picks up another session's pending paper); `grobid run` takes the
  same options. srcbib keys count as active before `bibtex merge`, so a paper
  just added is visible to every batch tool. The batch lists each skipped key
  with its reason (`done`, `done in pool`, `no PDF`, `not in the
  bibliography, no PDF`) and exits 1 when a named key cannot be converted.
  The background job (`jobs.launch_docling_batch_background`) takes `keys`;
  projio's `biblio_docling_batch` MCP tool does not pass it yet.
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
