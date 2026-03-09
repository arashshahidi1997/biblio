# biblio

Portable bibliography workspace tooling.

Distribution name: `biblio-tools`
Import package: `biblio`
CLI: `biblio`

`biblio` bootstraps a repo-local `bib/` workspace, manages citekeys and
BibTeX imports, runs Docling, resolves OpenAlex metadata, syncs a
bibliography-owned RAG config, expands local literature graphs, and builds a
standalone bibliography explorer.

In the development repo, there is also a small local demo workspace under
`bib/` with three sample papers so you can try the commands immediately.

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

Enable shell completion for `bash`:

```bash
eval "$(register-python-argcomplete biblio)"
```

Example ingestion flow:

```bash
biblio ingest csljson exports/library.json
biblio ingest ris exports/library.ris
biblio ingest dois reading-list.txt --stdout
biblio ingest pdfs ~/Downloads/papers/
```

Example local demo flow from this repo:

```bash
make ui-serve
biblio citekeys status
biblio bibtex merge
biblio docling run --all
biblio openalex resolve
biblio site build
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

The UI serves a local FastAPI app with a React/Cytoscape front end. It can:

- explore the local paper graph
- inspect corpus and paper details
- trigger selected `biblio` actions directly
- fall back to the next free port if `8010` is already in use

## Release workflow

Build and validate distributions:

```bash
python -m build
python -m twine check dist/*
```

Upload instructions live in `RELEASE.md`.
