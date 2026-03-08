# biblio

Portable bibliography workspace tooling.

Distribution name: `biblio-tools`
Import package: `biblio`
CLI: `biblio`

`biblio` bootstraps a repo-local `bib/` workspace, manages citekeys and
BibTeX imports, runs Docling, resolves OpenAlex metadata, syncs a
bibliography-owned RAG config, expands local literature graphs, and builds a
standalone bibliography explorer.

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

## Release workflow

Build and validate distributions:

```bash
python -m build
python -m twine check dist/*
```

Upload instructions live in `RELEASE.md`.
