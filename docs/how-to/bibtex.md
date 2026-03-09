# Merge BibTeX And Fetch PDFs

## Merge multiple source files

```bash
biblio bibtex merge
```

This reads `bib/srcbib/*.bib` and writes a single normalized main bibliography.

## Fetch PDFs from BibTeX `file` fields

```bash
biblio bibtex fetch-pdfs
```

This copies or symlinks PDFs into the local bibliography article layout.
