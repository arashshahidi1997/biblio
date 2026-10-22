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
