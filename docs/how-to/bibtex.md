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

## Start from non-BibTeX sources

If your starting point is not `.bib`, import into the managed source file first:

```bash
biblio ingest csljson exports/library.json
biblio ingest ris exports/library.ris
biblio ingest dois reading-list.txt
biblio ingest pdfs ~/Downloads/papers/
```

Then run:

```bash
biblio bibtex merge
```
