# Docling And OpenAlex Walkthrough

This tutorial focuses on the two strongest enrichment steps in `biblio`.

## Goal

Starting from `bib/srcbib/*.bib` and local PDFs, produce:

- Docling markdown and sidecars under `bib/derivatives/docling/`
- OpenAlex resolution output under `bib/derivatives/openalex/`

## Merge and fetch

```bash
biblio bibtex merge
biblio bibtex fetch-pdfs
```

## Run Docling for all known papers

```bash
biblio docling run --all
```

Expected outputs per citekey:

- markdown
- structured JSON
- provenance sidecar

## Resolve OpenAlex

```bash
biblio openalex resolve
```

Expected outputs:

- `bib/derivatives/openalex/resolved.jsonl`
- optional CSV summary
- cached API responses under `bib/derivatives/openalex/cache/`

## Next step

Use these derivatives to build a browsable portal:

```bash
biblio site build
```
