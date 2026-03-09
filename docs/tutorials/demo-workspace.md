# Demo Workspace

This tutorial uses the small local `bib/` workspace that ships with the
standalone `biblio` development repo.

It is intended for trying the tool quickly without preparing your own project
first.

## What is included

The demo workspace contains:

- `bib/config/biblio.yml`
- `bib/config/citekeys.md`
- `bib/config/rag.yaml`
- `bib/srcbib/sample.bib`
- three matching PDFs under `bib/articles/`

The workspace is intentionally thin:

- source BibTeX and citekeys are present
- PDFs are present
- Docling and OpenAlex derivatives are not pre-copied

That keeps the repo lightweight and makes it easy to test regeneration.

## Inspect the workspace

From the repository root:

```bash
biblio citekeys status
```

You should see three configured papers with `pdf` status.

## Merge the source bibliography

```bash
biblio bibtex merge
```

This writes:

- `bib/main.bib`

## Run Docling

```bash
biblio docling run --all
```

This creates Docling outputs under:

- `bib/derivatives/docling/`

## Resolve OpenAlex metadata

```bash
biblio openalex resolve
```

This creates OpenAlex outputs under:

- `bib/derivatives/openalex/`

## Build the static site

```bash
biblio site build
biblio site serve
```

The generated site lives under:

- `bib/site/`

## Launch the interactive UI

```bash
biblio ui serve
```

The UI can:

- explore the local graph
- inspect paper details
- trigger selected actions directly

If `8010` is unavailable, `biblio` chooses the next free port automatically.
