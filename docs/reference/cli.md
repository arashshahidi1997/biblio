# CLI

Main command groups:

- `biblio init`
- `biblio citekeys ...`
- `biblio ingest ...`
- `biblio bibtex ...`
- `biblio docling ...`
- `biblio openalex ...`
- `biblio rag ...`
- `biblio graph ...`
- `biblio site ...`
- `biblio ui ...`

For full command help:

```bash
biblio --help
biblio citekeys --help
biblio citekeys status --help
biblio ingest --help
biblio ingest dois --help
biblio ingest csljson --help
biblio ingest ris --help
biblio ingest pdfs --help
biblio bibtex --help
biblio docling --help
biblio openalex --help
biblio site --help
biblio ui --help
```

The current UI command is:

- `biblio ui serve`

Useful newer commands:

- `biblio citekeys status`
- `biblio ingest dois`
- `biblio ingest csljson`
- `biblio ingest ris`
- `biblio ingest pdfs`

`biblio ui serve` starts a local FastAPI app with a browser UI for:

- graph exploration
- corpus and paper inspection
- selected action triggers

If the requested default port is busy, it automatically falls back to the next
free port.

Shell completion with `argcomplete`:

```bash
eval "$(register-python-argcomplete biblio)"
```
