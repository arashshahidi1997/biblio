# Quickstart

This tutorial shows the smallest practical `biblio` workflow.

## Install

```bash
pip install "biblio-tools[openalex]"
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

## Add BibTeX sources

Place one or more `.bib` files under `bib/srcbib/`.

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
