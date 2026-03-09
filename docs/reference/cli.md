# CLI

## Command groups

| Group | Purpose |
|-------|---------|
| `biblio init` | Initialize a `bib/` workspace scaffold |
| `biblio citekeys` | Manage `bib/config/citekeys.md` |
| `biblio ingest` | Import DOIs, CSL JSON, RIS, or local PDFs |
| `biblio bibtex` | Merge srcbib and fetch PDFs |
| `biblio docling` | Run Docling to generate markdown and JSON |
| `biblio openalex` | Resolve srcbib entries to OpenAlex works |
| `biblio add` | Add a paper by DOI or OpenAlex ID |
| `biblio graph` | Expand the reference graph from OpenAlex data |
| `biblio rag` | Manage bibliography-owned RAG source config |
| `biblio site` | Build, serve, inspect, and clean the static site |
| `biblio ui` | Serve the local interactive browser UI |

## Key commands

```bash
# workspace
biblio init
biblio citekeys status
biblio citekeys add @author2024_Title
biblio citekeys list

# import
biblio ingest dois reading-list.txt
biblio ingest csljson exports/library.json
biblio ingest ris exports/library.ris
biblio ingest pdfs ~/Downloads/papers/

# bibtex
biblio bibtex merge
biblio bibtex fetch-pdfs

# docling
biblio docling run --all
biblio docling run --key author2024_Title
biblio docling run --all --screen   # run in detached GNU screen session

# openalex
biblio openalex resolve

# add a paper
biblio add doi 10.xxxx/example
biblio add openalex W1234567890

# graph expansion
biblio graph expand                        # both directions (default)
biblio graph expand --direction references # papers your corpus cites
biblio graph expand --direction citing     # papers that cite your corpus
biblio graph expand --force                # ignore cached work payloads

# rag
biblio rag sync
biblio rag sync --force-init

# site
biblio site build
biblio site serve
biblio site clean
biblio site doctor

# local UI
biblio ui serve
biblio ui serve --port 8020
biblio-gui          # alias for biblio ui serve
```

## Local UI (`biblio ui serve`)

Starts a FastAPI + React app at `http://127.0.0.1:8010` (or next free port).

**Tabs:**

- **Explore** — Cytoscape graph with focus/direction/mode filters; Candidates
  sidebar lists expansion candidates for the active paper with Add to Bib actions
- **Corpus** — table of all papers; per-row Open / Explore / Docling actions
- **Paper** — PDF inline viewer (Show/Hide), Docling excerpt rendered as markdown,
  related papers and neighborhood
- **Actions** — BibTeX merge, OpenAlex resolve, graph expand, site build, Docling
  for selected; progress bars for long-running jobs; Add paper by DOI field
- **Setup** — Docling command config, workspace path summary, readiness stats,
  RAG config editor

The UI frontend is a Vite + React app built to `src/biblio/static/`. To rebuild:

```bash
make build-frontend
```

For development with hot-module reload:

```bash
cd frontend && npm run dev   # proxies /api to localhost:8010
```

## Shell completion

```bash
eval "$(register-python-argcomplete biblio)"
```

## Full help

```bash
biblio --help
biblio <command> --help
biblio <command> <subcommand> --help
```
