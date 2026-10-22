---
title: "Laptop test: biblio's Zotero ingest and the wiki in Obsidian"
date: 2026-10-22
timestamp: 20261022-laptop-zotero-obsidian
status: open
actionable: true
project_primary: "biblio"
tags: [task, zotero, obsidian, wiki, laptop]
depends_on: []
---

# Laptop test: biblio's Zotero ingest and the wiki in Obsidian

## From

The biblio session on gamma2, 2026-10-22, for the agent working on the
user's laptop. gamma2 has no Zotero app and no desktop, so two parts of
biblio can only be checked on the laptop:

1. **I04** `biblio add zotero`: one paper from Zotero into a project, through
   Zotero's local API. It is built and tested only against a fake pyzotero
   client (`tests/test_zotero_add.py`).
2. **M1 wiki in an editor** (backlog W03 link style, W04 editor setup, W17
   figure embeds): nobody has opened a biblio wiki in Obsidian yet.
   `docs/explanation/wiki.md`, section "Working in the editors", states what
   we *expect*; your job is to find out what actually happens.

Plan of record: `docs/backlog.md` (items I04, W03, W04, W17). Context:
`docs/log/handoff/handoff-20261022-biblio-upgrade.md`.

## Ground rules

- **Read only on Zotero.** Never create, edit, tag or delete anything in the
  user's Zotero library. `biblio add zotero` only reads; do not run
  `biblio zotero push` or `biblio zotero pull`.
- **Test in a scratch project**, not in journal-club or any real project,
  except where a step says to read journal-club's laptop clone.
- No API keys in any tracked file.
- **Do not change biblio's code.** If something is broken, write it down
  (with the command, the output and what you expected). The gamma2 session
  fixes it, so the branch does not diverge on two machines.
- Write in plain prose: no em-dashes, US spelling.

## 0. Set up biblio from the laptop's projio clone

biblio is a DataLad subdataset of projio at `packages/biblio` (no standalone
clone). The work is on branch **`feat/knowledge-graph`** on GitHub
(`git@github.com:arashshahidi1997/biblio.git`).

1. In the laptop's projio clone: `cd packages/biblio`, fetch from the GitHub
   remote, and check out `feat/knowledge-graph`. If the subdataset is not
   installed, `datalad get -n packages/biblio` first.
2. Run the tests: `pixi run -e dev test`. Expect **376 passed**. If pixi is
   missing, record that and use whatever Python env the laptop's projio uses.
3. Make `biblio` on PATH run this checkout, editable (for example
   `uv tool install --editable "packages/biblio[zotero,openalex]"`, or the
   pixi `dev` env). Check: `biblio add zotero --help` exists.
4. Record the versions: OS, Zotero, Better BibTeX, Obsidian, pyzotero
   (`python -c "import pyzotero; print(pyzotero.__version__)"`), git-annex.

## 1. Zotero: `biblio add zotero`

Scratch project: `mkdir ~/scratch/biblio-laptop-test && cd` there, `git init`,
`biblio init`. Zotero must be running with Settings > Advanced > "Allow other
applications on this computer to communicate with Zotero".

1. Local API reachable:
   `curl -s "http://127.0.0.1:23119/api/users/0/items?limit=1"` returns JSON.
2. Pick the journal-club target paper (Aleman-Zapata et al. 2026, SLEEP,
   "Deltas' and spindles' cross-area synchronization and ripple subtypes";
   Better BibTeX key `aleman-zapata_2026_DeltasSpindles`). Run
   `biblio add zotero <ref> --local --dry-run` with each form of `<ref>`:
   - its Zotero item key (8 characters, from the item's context menu or the API)
   - its DOI
   - the Better BibTeX key `aleman-zapata_2026_DeltasSpindles`
   - biblio's key `alemanzapata_2026_DeltasSpindles`

   Each should print `alemanzapata_2026_DeltasSpindles` and the same item key.
3. Real add: `biblio add zotero <item key> --local`. Check:
   - `bib/srcbib/zotero.bib` has one entry with key
     `alemanzapata_2026_DeltasSpindles`, a `zotero = {...}` field, the DOI, a
     sensible title, authors and journal
   - `bib/articles/alemanzapata_2026_DeltasSpindles/alemanzapata_2026_DeltasSpindles.pdf`
     opens and is the right paper
   - running the same command again reports `pdf: present` and leaves one entry
4. Edge cases (find suitable items in the library; note their keys):
   - an item with **no PDF attached**: expect `pdf: none` and a note
   - an item whose PDF is a **linked file** (not stored in Zotero): what happens?
   - an item with **two PDFs** (main text and supplement): which one is copied?
   - a **book chapter or preprint**: is the BibTeX entry type sensible?
   - a **non-ASCII author** (e.g. Fernández-Ruiz): what key comes out?
   - Zotero **not running**: the error message should say so plainly.
5. Speed: time one `add` (`time biblio add zotero ... --local`).
6. Reference triage against the real library, read only. In journal-club's
   laptop clone (`~/dev/projects/journal-club`), with Zotero's database path
   (usually `~/Zotero/zotero.sqlite`):
   `biblio refs triage alemanzapata_2026_DeltasSpindles --zotero ~/Zotero/zotero.sqlite --out ~/scratch/biblio-laptop-test/triage`.
   This works while Zotero is open (the database is opened immutable). It
   needs the paper's GROBID output in that clone; if it is missing, say so
   and skip. journal-club's prototype found 19 references with a PDF in
   Zotero; compare the `pdf` and `fulltext` counts. Do not commit anything
   in journal-club.

## 2. Obsidian: a biblio wiki in the editor

Same scratch project.

1. Make a small wiki:
   `biblio wiki init --subject ripples --tag event/ripple`, then a few pages,
   for example `biblio wiki stub sharp-wave-ripple --type concept --tag event/ripple`
   and `biblio wiki stub ripple-detection --type method`. Link them both ways:
   one link as `[[sharp-wave-ripple]]`, one as a relative markdown link
   (`[Sharp-wave ripple](../concepts/sharp-wave-ripple.md)`, with the real
   relative path). Run `biblio wiki lint`.
2. Open the **project root** as an Obsidian vault. Record:
   - Do both link styles open the target? Do backlinks and hover previews work for both?
   - With Settings > Files and links set to "Use [[Wikilinks]]" off and "New
     link format" relative, does a link Obsidian inserts pass `biblio wiki lint`?
   - **Rename** a page in Obsidian with "Automatically update internal links"
     on. Which links did it rewrite, in which style? Does lint still pass?
   - Frontmatter: does Obsidian's Properties view show the fields cleanly? Does
     editing a property (e.g. `status`) keep the YAML lint accepts?
   - Which folders clutter search and the graph (`bib/`, `.projio/`, `.pixi/`,
     `.git`)? Which excluded-files settings fix it?
   - A link from a wiki page to a paper's full text under
     `bib/derivatives/docling/<key>/<key>.md`: does it open?
3. **Annexed figures** (W17). In the scratch project make it a DataLad dataset
   (`datalad create --force .`), `datalad save` the PDF from step 1, and, if
   poppler is installed, `biblio figures run --key alemanzapata_2026_DeltasSpindles`
   (needs docling output; if docling is not available on the laptop, copy any
   PNG into `bib/derivatives/figures/test/fig1.png` and `datalad save` it).
   Embed it in a wiki page as `![Figure 1](<relative path>)`. Record:
   - Locked (annex symlink): does Obsidian display the image? Does VS Code's preview?
   - After `git annex adjust --unlock` (or `datalad unlock` on the file): does it display now?
   - The design doc claims Obsidian does not follow file symlinks. True or false on this laptop?

## 3. Report back

Append a section `## Results (laptop, <date>)` to **this file**, with one
subsection per numbered step above: what you ran, what happened, and a
verdict (works / works with caveat / broken). Paste short outputs; put long
ones in `docs/log/task/laptop-test-artifacts/` (text only, no PDFs, no
images over 200 KB, nothing from the user's library beyond titles and keys).
End with:

- a list of **bugs** (command, output, expected)
- your **recommendation for W03** (one link style for biblio wikis, and why)
- the **Obsidian settings** a W04 how-to should prescribe

Then in `packages/biblio`: commit only this file and the artifacts folder
(`git commit -- <paths>`), and push to the GitHub remote on
`feat/knowledge-graph`. If the push is rejected because gamma2 pushed in the
meantime, `git pull --rebase` and push again; never force-push.

## Results (laptop, 2026-10-22)

Run by the agent on Arash's laptop. Scratch project: `~/scratch/biblio-laptop-test`
(a DataLad dataset made with `-c text2git`, so markdown is in git and PDFs and
figures are annexed). Nothing was written to Zotero, journal-club or any real
project. Long outputs are in `docs/log/task/laptop-test-artifacts/`.

### 0. Setup: works

- The laptop had no projio clone. I cloned the superdataset from gamma2's RIA
  (`datalad clone 'ria+ssh://gamma2/storage/share/git/ria-store#276e82d2-d016-42b6-9422-4b9a1267e57b' ~/dev/projects/projio-eco`),
  then `datalad get -n packages/biblio` (installed from the RIA alias), added
  the GitHub remote as `github`, fetched, and checked out `feat/knowledge-graph`
  at `f899969`.
- `pixi run -e dev test`: **376 passed in 4.54s**.
- `uv tool install --editable "packages/biblio[zotero,openalex]"` puts `biblio`
  on PATH from this checkout (`~/.local/bin/biblio`, `biblio.__file__` points
  into `packages/biblio/src`). `biblio add zotero --help` exists.
- Versions: Ubuntu 22.04.5 LTS (kernel 6.8.0-138), Zotero 9.0.1 (snap),
  Better BibTeX 9.0.71, Obsidian 1.14.4 (installer 1.12.7, `.deb`),
  pyzotero 1.12.0, git-annex 10.20260213, DataLad 1.4.1 (pixi global).
- Note: the Zotero data directory is the snap one,
  `~/snap/zotero-snap/common/Zotero/zotero.sqlite`, not `~/Zotero`.

### 1. Zotero: `biblio add zotero`

**1.1 Local API: works.** `curl -s "http://127.0.0.1:23119/api/users/0/items?limit=1"`
returns JSON (HTTP 200).

**1.2 Ref forms: works.** The target paper is Zotero item `4FI7Q8I8`. All four
forms (`4FI7Q8I8`, `10.1093/sleep/zsag168`, `aleman-zapata_2026_DeltasSpindles`,
`alemanzapata_2026_DeltasSpindles`) printed the same line with `--dry-run`:

```
[OK] alemanzapata_2026_DeltasSpindles (found) <- Zotero 4FI7Q8I8: Deltas’ and spindles’ cross-area synchronization and ripple subtypes
  note: Zotero calls it aleman-zapata_2026_DeltasSpindles; biblio uses alemanzapata_2026_DeltasSpindles
```

**1.3 Real add: works, with one cosmetic issue.** `bib/srcbib/zotero.bib` has
one `@article` with key `alemanzapata_2026_DeltasSpindles`, `zotero = {4FI7Q8I8}`,
the DOI, the right title, all seven authors (non-ASCII `Özsezer` kept), journal
Sleep, volume 49, number 9, pages zsag168. The PDF (2.5 MB) was copied and its
first page is the right paper. A second run reports `pdf: present` and leaves one
entry, but the status word still says `(added)` (bug 4).

**1.4 Edge cases** (entry headers in `laptop-test-artifacts/zotero-add-entries.txt`):

| Case | Item | Result | Verdict |
|---|---|---|---|
| No PDF attached | `ABVD2DXK` (Senzai 2022) | `pdf: none -> <path>` and `note: no PDF attached in Zotero` | works (the path printed after `none` does not exist, bug 5) |
| Linked-file PDF | none found | The library has 68 linked-file attachments but all are markdown notes, no linked PDF | not tested |
| Several PDFs | `E92JEP9U` (Buzsáki 2012: "Accepted Version" plus two identical imported copies) | Copied the first PDF child in API order (`YXQVBRC2`, imported file), not the "Accepted Version" | works with caveat: there is no ranking rule. No item with a labeled supplement PDF was found to test main vs supplement |
| Book chapter | `Z9KIF4G9` (Zago et al. 2016 in Brunoni et al., eds.) | `@incollection` with `booktitle` and `publisher` (good), but the editors are listed in `author` and the key is `brunoni_2016_HistoricalAspects` (BBT: `zago_2016_HistoricalAspects`) | broken (bug 2) |
| Preprint | `B3CN9RJE` (arXiv:2110.14599) | `@article` with only title, author, year, url; no journal, no eprint | works with caveat (bug 3) |
| Non-ASCII author | `AYCVBRGZ` (Fernández-Ruiz 2012) | key `fernandezruiz_2012_SustainedIncrease`, author kept as `Fernández-Ruiz` | works |
| Zotero not running | simulated with an empty network namespace (`unshare -rn`), so connection refused on 23119 | `[ERROR] Zotero request failed via the local API (is Zotero running, with local API access enabled?): [Errno 111] Connection refused`, exit 1 | works |

**1.5 Speed: works.** `time biblio add zotero 4FI7Q8I8 --local`: real 0.24 s
(including the 2.5 MB PDF copy).

**1.6 Triage: works.** In journal-club's laptop clone (GROBID output present),
with `--zotero ~/snap/zotero-snap/common/Zotero/zotero.sqlite` while Zotero was
open: `[OK] 66 references: 1 fulltext, 34 pdf, 0 metadata, 31 absent` in 0.38 s.
`git status` in journal-club was identical before and after. Comparison with the
prototype's `papers/alemanzapata_2026_DeltasSpindles/refs.json`: the prototype's
"19 with a PDF in Zotero" counts only references not already in the pool; the
prototype has 35 references with any Zotero hit, and triage also has 35 Zotero
hits (34 pdf + 1 fulltext). They differ on two references, both in biblio's favor:
ref 11 (Robinson 2026) is matched by title in triage but was missed by the
prototype; ref 29 (Paxinos, The Rat Brain in Stereotaxic Coordinates, 2013, no DOI)
was matched by the prototype to a 1983 edition by title only, which triage
rightly rejects. Ref 9 (Stark 2014) has a GROBID-garbled title with a PDF
watermark in it ("Downloaded from academic", venue "by Wilke Fortuin user on ...");
that is a GROBID input problem, not triage. Full table:
`laptop-test-artifacts/triage-alemanzapata_2026_DeltasSpindles.md`.

### 2. Obsidian

Method: Obsidian was started with `--remote-debugging-port` and the scratch
project root was opened as a vault. Checks used Obsidian's own API
(`metadataCache`, `fileManager.generateMarkdownLink`, `processFrontMatter`,
`renameFile`, `workspace.openLinkText`), which is what the UI calls. The
window was not on screen, so the reading view did not paint: hover previews
and the visual look of the image were **not checked by eye** (see "Not
verified" below).

**2.1 Wiki setup: works with caveat.** `biblio wiki init --subject ripples --tag event/ripple`,
`wiki stub sharp-wave-ripple --type concept --tag event/ripple`,
`wiki stub ripple-detection --type method`. One `[[ripple-detection]]` and one
`[Sharp-wave ripple](../concepts/sharp-wave-ripple.md)`. The very first
`biblio wiki lint` fails: `TAG001 tag 'event/ripple' is not in the vocabulary`
on the concept page and the hub, because `wiki init` writes `vocab.yml` with
`event: values: []` (bug 1). After adding `ripple` and `biblio wiki hubs`:
0 errors, 0 warnings. Lint does flag broken links of both styles (`LNK001`
for `[[no-such-page]]`, `LNK004` for a missing relative path).

**2.2 Obsidian:**

- Both link styles resolve (`metadataCache.resolvedLinks`), open the target
  (`openLinkText`), and produce backlinks: the concept page has backlinks from
  the method page (markdown link) and the hub; the method page has a backlink
  from the concept page (wikilink). Verdict: works.
- With "Use [[Wikilinks]]" off and "New link format" relative, Obsidian inserts
  `[sharp-wave-ripple](../concepts/sharp-wave-ripple.md)`, a heading link
  `[ripple-detection](../methods/ripple-detection.md#Procedure)`, and
  `[alemanzapata_2026_DeltasSpindles](../../../bib/derivatives/docling/.../alemanzapata_2026_DeltasSpindles.md)`.
  All pass lint. Verdict: works.
- Rename `sharp-wave-ripple.md` to `sharp-wave-ripples.md` with "Automatically
  update internal links" on: both markdown links in the method page were
  rewritten to `../concepts/sharp-wave-ripples.md`, and where the link text
  equaled the old file name Obsidian changed the text too. The generated hub's
  `[[sharp-wave-ripple|Sharp wave ripple]]` became
  `[[../concepts/sharp-wave-ripples|Sharp wave ripple]]` (a path-style wikilink,
  because the new-link format is relative). Lint still passed (only `HUB001`
  "generated list is out of date"); `biblio wiki hubs` put back the short form.
  Diff: `laptop-test-artifacts/obsidian-edits.diff`. Verdict: works with caveat
  (wikilinks become path wikilinks on rename; markdown links stay clean).
- Frontmatter: Obsidian types the fields as text (`title`, `type`, `scope`,
  `status`, `reviewed`, `author`), date (`updated`), multitext (`sources`,
  `review_flags`, `related`), plus its own `tags` and `aliases`. Editing
  `status` and `aliases` through the Properties code path rewrote flow lists
  as block lists (`tags: [event/ripple]` became `tags:\n  - event/ripple`) and
  `reviewed: null` as `reviewed:` (still null). Lint accepts all of it.
  Verdict: works (expect whole-frontmatter diffs on the first edit in Obsidian).
- Clutter: dot folders (`.git`, `.datalad`, `.projio`, `.obsidian`, `.pixi`)
  are never indexed. What does show up: `bib/README.md`,
  `bib/derivatives/docling/<key>/<key>.md` (full texts in search, graph and
  quick switcher, each with a dozen unresolved image links), `bib/srcbib/*.bib`
  and JSON/YAML under "show all file types", and project files like `triage/`.
  Settings > Files and links > Excluded files = `bib/` hides them from search
  and graph, and links into `bib/` still resolve and open. Obsidian also
  creates `.obsidian/` at the project root, and `.obsidian/workspace.json`
  changes on every click.
- Link to a full text under `bib/derivatives/docling/<key>/<key>.md`: resolves
  and opens (it is a plain file because the dataset is text2git). Verdict:
  works. Images inside the docling markdown do not resolve when they are
  annexed (see 2.3).

**2.3 Annexed figures (W17).** `datalad create --force -c text2git .`,
`datalad save`, then `biblio figures run --key alemanzapata_2026_DeltasSpindles`
(with journal-club's docling output copied in; poppler present):
`9 figures (7 embedded, 2 rendered, 3 small skipped)` in 0.54 s. Embedded
`![Figure 1](../../../bib/derivatives/figures/alemanzapata_2026_DeltasSpindles/fig-1.jpg)`.

- Locked (annex symlink): Obsidian does not display it. The file is absent from
  the vault index, the link is in `unresolvedLinks`, and the embed renders as
  "could not be found" (`file-embed mod-empty-attachment`).
- After `datalad unlock` on that file: the file enters the vault index and the
  embed renders as an image (`image-embed`, decoded at 1446x2033).
- The design doc's claim that Obsidian does not follow file symlinks: **true**
  on this laptop. Every annexed file (PDFs, locked figures, docling artifact
  PNGs) is missing from Obsidian's file list.
- VS Code's preview of the locked image: **not tested** (no way to see it from
  this session).

### Not verified

Hover previews and the on-screen look of the embedded image were not checked by
eye; VS Code was not tried. Both link styles are resolved internal links in
Obsidian's cache, which is what page preview uses, so hover is expected to work
for both. A two-minute manual check in the open vault would settle it.

Update, 2026-10-22: Arash checked by hand in the open vault that the links work in Obsidian (works). Hover previews and the image's look were not separately reported; VS Code is still untested.

### Bugs

1. **`wiki init --tag` / `wiki stub --tag` give a wiki that fails lint at once.**
   Command: `biblio wiki init --subject ripples --tag event/ripple` then
   `biblio wiki stub sharp-wave-ripple --type concept --tag event/ripple`, then
   `biblio wiki lint`. Output: `error TAG001 tag 'event/ripple' is not in the
   vocabulary` on the concept page and `hubs/hub-ripples.md`; `vocab.yml` has
   `event: {..., values: []}`. Expected: `init` adds the subject tag to
   `vocab.yml` (and `stub --tag` either adds it or refuses with a hint).
2. **`add zotero` puts editors in `author` and keys a book chapter by its editor.**
   Command: `biblio add zotero Z9KIF4G9 --local`. Output: `@incollection{brunoni_2016_HistoricalAspects,
   author = {Brunoni, André and Nitsche, Michael and Loo, Colleen and Zago, Stefano and ...}`.
   Zotero creators: Brunoni, Nitsche, Loo are `editor`; Zago, Priori, Ferrucci,
   Lorusso are `author`. Expected: `author` = authors only, `editor` = editors,
   key `zago_2016_HistoricalAspects` (as BBT does).
3. **Preprints lose their archive id.** Command: `biblio add zotero B3CN9RJE --local`.
   Output: `@article{anand_2023_HodgeLaplacian, title, author, year, url}`.
   Zotero has `repository = arXiv`, `archiveID = arXiv:2110.14599`. Expected:
   `@misc` (or `@article` with `journal = {arXiv}`) with `eprint = {2110.14599}`,
   `archiveprefix = {arXiv}`.
4. **Re-running reports `(added)`.** Second `biblio add zotero 4FI7Q8I8 --local`
   prints `[OK] alemanzapata_2026_DeltasSpindles (added)` with `pdf: present`.
   Expected: `(found)` or `(present)`, as the dry run says.
5. **`pdf: none -> <path>`** prints the target path although nothing was copied.
   Expected: `pdf: none` without a path.
6. (Not a bug, a gap) With several PDF attachments the first child in API order
   is copied, with no preference (for example main text over "Supplement", or
   imported file over "Accepted Version").

### Recommendation for W03 (link style)

Use **relative markdown links** (`[Text](../concepts/page.md)`) as the one style
for biblio wikis, and make `biblio wiki hubs` and `stub` write them
(`link_style: markdown`). Reasons from this test: Obsidian resolves, opens,
backlinks and inserts them; Obsidian's rename rewrites them cleanly; they also
work in MkDocs, GitHub and VS Code without plugins; lint already checks them
(`LNK004`). Wikilinks work in Obsidian too, but with the relative link format a
rename turns them into path wikilinks (`[[../concepts/x|...]]`), which is the
worst of both. One caveat: Obsidian rewrites link text that equals the old file
name, so stubs should use the page title, not the slug, as link text.

### Obsidian settings for the W04 how-to

- Open the **project root** as the vault.
- Files and links: "Use [[Wikilinks]]" **off**; "New link format" **Relative
  path to file**; "Automatically update internal links" **on**.
- Files and links: "Excluded files" = `bib/` (plus project folders such as
  `derivatives/` if they hold markdown). Links into `bib/` keep working.
- Add `.obsidian/workspace*.json` to `.gitignore` (or all of `.obsidian/`, if
  the settings are not meant to be shared).
- For figures: unlock the figure files (`datalad unlock bib/derivatives/figures`)
  or keep them in git, because Obsidian ignores annex symlinks. A `biblio`
  command or doc note for "unlock what the wiki embeds" would help.
