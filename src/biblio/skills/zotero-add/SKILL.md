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
   `biblio add zotero <ref> --local --dry-run`. `<ref>` is an item key
   (`ABCD1234`), a DOI, Better BibTeX's citekey, or biblio's own key (as the
   pools use it). The output prints biblio's citekey; use that one from now on.
   If several items match, rerun with the item key it lists.
2. **Add it**: `biblio add zotero <ref> --local`. The entry goes to
   `bib/srcbib/zotero.bib` with a `zotero = {ITEMKEY}` field, the PDF to
   `bib/articles/<key>/<key>.pdf`. A paper already in the project keeps its
   key; only a missing PDF is filled in. Read the `note:` lines: "no PDF
   attached" means the user has to attach one in Zotero first.
3. **Save and push** (laptop): `datalad save -m "bib: add <key> from Zotero"`
   then `datalad push --to <sibling>`.
4. **Extract** (server): `datalad update --how merge`, `datalad get
   bib/articles/<key>`, then `biblio grobid run --key <key>` and
   `biblio docling run --key <key>`. If one machine does everything, add
   `--extract` to step 2 instead.
5. **For a talk's background**: `biblio refs triage <target> --zotero
   <path to zotero.sqlite>` (usually `~/Zotero/zotero.sqlite`; a snap install
   keeps it in `~/snap/zotero-snap/common/Zotero/`) lists the references held in Zotero with a PDF;
   add them one by one with steps 1 to 4, rerun the triage, and report what
   is still absent.

## Hard rules

- Never rename a citekey by hand; biblio's key is the one other tools resolve.
- Never write a Zotero API key into biblio.yml or any tracked file; use
  `BIBLIO_ZOTERO_API_KEY` or `~/.config/biblio/config.yml`.
- `biblio add zotero` only reads from Zotero; it never changes the library.
- Do not run docling on the laptop unless the user asks; it is slow and the
  server is where the project's derivatives live.
