---
name: zotero-add
description: >
  Bring one paper from the user's Zotero library into a project: bibliography
  entry under biblio's citekey, PDF copied, then GROBID and docling on the
  server. Covers the usual two-machine setup (Zotero on a laptop, extraction on
  a server) and the web-API route. Use when asked to "add this paper from
  Zotero", "pull <citekey> into the project" or to ingest the references a
  `biblio refs triage` lists as PDF-in-Zotero.
metadata:
  short-description: One Zotero item -> srcbib entry + PDF -> sync -> GROBID + docling
  tags: [zotero, ingest, literature]
  tooling:
    cli: [biblio add zotero, biblio refs triage, biblio grobid run, biblio docling run]
---

# Add a paper from Zotero

## When to use

- One paper (or a short list, one at a time) is in the user's Zotero and
  should be read in this project.
- Not for syncing a whole library or collection: that is `biblio zotero pull`.

## Where each step runs

Zotero's local API only answers on the machine running the Zotero app. The
heavy extraction usually runs on a server. So:

| Step | Machine | Needs |
|---|---|---|
| Find the item, write the entry, copy the PDF | laptop (Zotero app) | Zotero 7+, Settings > Advanced > "Allow other applications on this computer to communicate with Zotero" |
| Save and push | laptop | the project as a DataLad dataset (PDFs are annexed) |
| GROBID and docling | server | `datalad update` + `datalad get` of the PDF |

Without the laptop: the web API works from anywhere, with `zotero.library_id`
in biblio.yml and `BIBLIO_ZOTERO_API_KEY` in the environment. It only sees
PDFs stored in Zotero's cloud storage; linked files are never reachable.

## Workflow

1. **Check what Zotero holds** (laptop, project root):
   `biblio add zotero <ref>... --local --dry-run`, or `--from refs.txt` (one
   ref per line). A ref is an item key (`ABCD1234`), a DOI, Better BibTeX's
   citekey, biblio's own key (as the pools use it) or a title. The user's
   library and every group library are searched (`--library group:<id>` for
   one); a `[group:...]` tag says where an item was found. The output prints
   biblio's citekey; use that one from now on. Duplicates of one paper are
   resolved to the copy with a stored PDF (the others are listed as `note:
   duplicate ...`); different papers matching one ref are an error that lists
   their item keys.
2. **Add them**: the same command without `--dry-run`. The last line sums up
   added, already present, no PDF, not found and duplicates. The entry goes to
   `bib/srcbib/zotero.bib` with a `zotero = {ITEMKEY}` field, the PDF to
   `bib/articles/<key>/<key>.pdf`. A paper already in the project keeps its
   key; only a missing PDF is filled in. Read the `note:` lines: "no PDF
   attached" means the user has to attach one in Zotero first.
3. **Save and push** (laptop): `datalad save -m "bib: add <key> from Zotero"`
   then `datalad push --to <sibling>`.
4. **Extract** (server): `datalad update --how merge`, `datalad get
   bib/articles/<key>`, then the `next:` line from step 2
   (`biblio grobid run --keys a,b && biblio docling batch --keys a,b`: only
   those papers, never another session's). If one machine does everything,
   add `--extract` to step 2 instead.
5. **For a talk's background**: `biblio refs triage <target> --zotero
   <path to zotero.sqlite>` (usually `~/Zotero/zotero.sqlite`; a snap install
   keeps it in `~/snap/zotero-snap/common/Zotero/`) lists the references held in Zotero with a PDF;
   add them one by one with steps 1 to 4, rerun the triage, and report what
   is still absent.
6. **A PDF the API cannot serve** (`pdf: failed` for a group item): with
   `--local` biblio also copies it from Zotero's own `storage/<attachment
   key>/` folder (`~/Zotero`, a snap install's `~/snap/zotero-snap/common/Zotero`,
   or `ZOTERO_DATA_DIR`).

## Hard rules

- Never rename a citekey by hand; biblio's key is the one other tools resolve.
- Never write a Zotero API key into biblio.yml or any tracked file; use
  `BIBLIO_ZOTERO_API_KEY` or `~/.config/biblio/config.yml`.
- `biblio add zotero` only reads from Zotero; it never changes the library.
- Do not run docling on the laptop unless the user asks; it is slow and the
  server is where the project's derivatives live.
