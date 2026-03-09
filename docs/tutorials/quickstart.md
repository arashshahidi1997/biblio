# Quickstart

This tutorial shows the smallest practical `biblio` workflow for a fresh
project, then points to the built-in demo workspace used by the development
repo.

## Install

```bash
pip install "biblio-tools[openalex]"
```

If you also want the local interactive UI:

```bash
pip install "biblio-tools[openalex,ui]"
```

## Initialize a bibliography workspace

From your project root:

```bash
biblio init
```

This creates:

- `bib/config/biblio.yml`
- `bib/config/citekeys.md`
- `bib/config/rag.yaml`
- `bib/srcbib/`

## Optional: try the standalone repo demo workspace

The `biblio` development repo includes a small local `bib/` workspace with
three sample papers, matching PDFs, and config files. From that repo you can
run:

```bash
biblio citekeys status
biblio bibtex merge
biblio docling run --all
biblio site build
biblio ui serve
```

## Add BibTeX sources

Place one or more `.bib` files under `bib/srcbib/`.

If you do not have BibTeX yet, you can import structured sources first:

```bash
biblio ingest csljson exports/library.json
biblio ingest ris exports/library.ris
biblio ingest dois reading-list.txt
biblio ingest pdfs ~/Downloads/papers/
```

## Merge and normalize

```bash
biblio bibtex merge
biblio bibtex fetch-pdfs
```

## Run Docling

```bash
biblio docling run --all
```

## Resolve OpenAlex metadata

```bash
biblio openalex resolve
```

## Build the bibliography site

```bash
biblio site build
biblio site serve
```

The generated site lives under `bib/site/`.

## Launch the local UI

```bash
biblio ui serve
```

The UI provides tabs for:

- `Explore`
- `Corpus`
- `Paper`
- `Actions`

If port `8010` is occupied, `biblio` automatically chooses the next free port
and prints the final local URL.
