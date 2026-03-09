# biblio

Portable bibliography workspace tooling.

Distribution name: `biblio-tools`
Import package: `biblio`
CLI: `biblio`

`biblio` bootstraps a repo-local `bib/` workspace, manages citekeys and
BibTeX imports, runs Docling, resolves OpenAlex metadata, syncs a
bibliography-owned RAG config, expands local literature graphs, and builds a
standalone bibliography explorer.

It can also ingest structured inputs before you have `.bib` files, including:

- DOI lists
- CSL JSON
- RIS
- local PDFs

Install for development:

```bash
pip install -e ".[dev]"
```

Install by distribution name:

```bash
pip install biblio-tools
```

Run the CLI:

```bash
biblio --help
```

Example ingestion flow:

```bash
biblio ingest csljson exports/library.json
biblio ingest ris exports/library.ris
biblio ingest dois reading-list.txt --stdout
biblio ingest pdfs ~/Downloads/papers/
```

## Documentation

Install docs dependencies:

```bash
pip install -e ".[docs]"
```

Preview locally:

```bash
mkdocs serve
```

The docs site uses a Diataxis layout and is intended for GitHub Pages deployment.

Optional local UI:

```bash
pip install -e ".[ui]"
biblio ui serve
```

## Release workflow

Build and validate distributions:

```bash
python -m build
python -m twine check dist/*
```

Upload instructions live in `RELEASE.md`.
