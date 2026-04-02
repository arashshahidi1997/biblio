# CLI

## Command groups

| Group | Purpose |
|-------|---------|
| `biblio init` | Initialize a `bib/` workspace scaffold |
| `biblio citekeys` | Manage `bib/config/citekeys.md` |
| `biblio ingest` | Import DOIs, CSL JSON, RIS, or local PDFs |
| `biblio bibtex` | Merge srcbib, fetch PDFs (local + open-access cascade) |
| `biblio docling` | Run Docling to generate markdown and JSON (single or batch) |
| `biblio openalex` | Resolve srcbib entries to OpenAlex works |
| `biblio add` | Add a paper by DOI, OpenAlex ID, or ORCID |
| `biblio graph` | Expand the reference graph from OpenAlex data |
| `biblio grobid` | GROBID scholarly structure extraction (check, run, match) |
| `biblio rag` | Manage bibliography-owned RAG source config |
| `biblio library` | Manage per-paper status, tags, and priority |
| `biblio collection` | Manage paper collections (manual and smart/query-driven) |
| `biblio queue` | Manage the needs-PDF queue |
| `biblio pool` | Manage the shared PDF pool workspace |
| `biblio ref-md` | Produce reference-resolved markdown from docling+GROBID |
| `biblio concepts` | Extract and search key concepts from papers |
| `biblio compare` | Generate comparison tables for multiple papers |
| `biblio reading-list` | Curate a reading list for a research question |
| `biblio cite-draft` | Draft a citation paragraph grounding a claim in papers |
| `biblio review` | Literature review synthesis and planning |
| `biblio summarize` | Generate structured paper summaries via LLM |
| `biblio present` | Generate Marp slide decks from paper context |
| `biblio auth` | Manage authentication for external services (EZProxy cookies) |
| `biblio profile` | Manage user-level biblio profiles |
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
biblio bibtex fetch-pdfs                        # copy/symlink from Zotero file= fields
biblio bibtex fetch-pdfs-oa                     # open-access cascade (pool/OA/Unpaywall/EZProxy)
biblio bibtex fetch-pdfs-oa --citekeys a b c    # fetch specific papers only
biblio bibtex export --all -o refs.bib          # export all entries

# docling
biblio docling run --all
biblio docling run --key author2024_Title
biblio docling run --all --screen               # run in detached GNU screen session
biblio docling batch                            # batch-process all pending papers
biblio docling batch --concurrency 4            # parallel workers

# grobid
biblio grobid check                             # test GROBID server connectivity
biblio grobid run --all                         # extract structured refs from all PDFs
biblio grobid run --key author2024_Title
biblio grobid match --all                       # match GROBID refs against local corpus

# openalex
biblio openalex resolve

# add a paper
biblio add doi 10.xxxx/example
biblio add openalex W1234567890
biblio add orcid 0000-0001-2345-6789

# graph expansion
biblio graph expand                             # both directions (default)
biblio graph expand --direction references      # papers your corpus cites
biblio graph expand --direction citing          # papers that cite your corpus
biblio graph expand --force                     # ignore cached work payloads

# library management
biblio library list
biblio library set author2024 --status read --tags "review,methods"
biblio library lint                             # check for non-vocabulary tags
biblio library dedup                            # detect duplicate papers
biblio library autotag --all                    # auto-tag via LLM/reference propagation

# collections
biblio collection create "my-review" --description "Papers for review"
biblio collection list
biblio collection show my-review

# PDF queue
biblio queue list                               # papers still needing PDFs
biblio queue drain                              # re-attempt OA fetch for all queued
biblio queue open author2024                    # open URL in browser

# authentication (institutional access)
biblio auth ezproxy                             # opens browser, prompts for cookie
biblio auth ezproxy --no-open                   # skip browser, just prompt

# PDF pool (shared workspace)
biblio pool ingest ~/Downloads/inbox/
biblio pool watch ~/Downloads/inbox/            # continuous ingestion
biblio pool link                                # configure project to use pool
biblio pool serve                               # HTTP drop server

# reference-resolved markdown
biblio ref-md run --all

# concepts
biblio concepts extract author2024
biblio concepts index
biblio concepts search "neural oscillations"

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
biblio-gui                                      # alias for biblio ui serve
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
  for selected; progress bars for long-running jobs; Add paper by DOI field;
  Fetch PDFs (OA cascade) with progress polling
- **Setup** — Docling command config, PDF fetch settings (Unpaywall email, EZProxy
  base URL/mode, cascade order, delay), workspace path summary, readiness stats,
  RAG config editor
- **Search** — full-text semantic search across indexed papers
- **Research** — analysis tools, reading list generation, citation drafting
- **Collections** — paper collection management with membership views
- **Stats** — overview statistics and quick-action buttons

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
