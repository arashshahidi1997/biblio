# Use The Local UI

The local UI is a browser-based interface for interacting with your bibliography
workspace without using the command line.

## Install

```bash
pip install "biblio-tools[ui]"
```

## Start

```bash
biblio ui serve
```

Or use the alias:

```bash
biblio-gui
```

If port `8010` is already in use, `biblio` automatically picks the next free port
and prints the URL.

During development you can run the frontend with hot-module reload:

```bash
cd frontend && npm run dev
```

This starts a Vite dev server at `http://localhost:5173`, proxying API calls to
the FastAPI backend at `http://localhost:8010`.

## Tabs

### Explore

A Cytoscape graph of your bibliography and its reference network.

**Controls** (always visible above the graph):

| Control | Options | Effect |
|---------|---------|--------|
| Search papers | free text | filter by citekey or title |
| Focus paper | dropdown | set the selected paper |
| Graph filter | Local + external / Local only | show or hide external OpenAlex nodes |
| Explore mode | Focused neighborhood / All papers | limit to the active paper's neighbors or show everyone |
| Direction | Past + future / Past works / Future works | filter edges by reference direction |

**Inspector sidebar** (right panel):

- **Inspector** — shows which node is selected
- **Stats** — paper/docling/openalex counts
- **Paper card** — citekey, title, authors, artifact badges
- **Candidates** — neighbors discovered by graph expansion for the active paper

The Candidates panel is the primary way to review graph expansion results.
For each neighbor it shows the title, year, and direction badge:

- `→ ref` — this paper references it (past work)
- `← citing` — this paper is cited by it (future work)

Papers already in your corpus get an **in corpus** badge.
External papers get an **Add to Bib** button that adds them via OpenAlex metadata.

Clicking a node in the graph also selects it. Clicking an external (openalex)
node shows the **Selected external paper** panel with an **Add to Bib** button.

### Corpus

A table of all discovered papers (configured citekeys plus candidates from
srcbib). Each row shows artifact status (pdf / docling / openalex) and per-row
actions:

- **Open** — switch to the Paper tab for that paper
- **Explore** — switch to the Explore tab focused on that paper
- **Docling** — trigger Docling for that paper immediately

### Paper

Detailed view of the selected paper:

- **PDF** — hidden by default; click **Show PDF** to open an inline viewer
- **Docling excerpt** — first portion of the Docling-generated markdown, rendered
- **Related local papers** — papers sharing outgoing or incoming references
- **Neighborhood** — outgoing reference count, incoming citation count

### Actions

Trigger long-running operations and watch progress:

| Button | Command equivalent |
|--------|--------------------|
| Merge BibTeX | `biblio bibtex merge` |
| Resolve OpenAlex | `biblio openalex resolve` |
| Expand Graph | `biblio graph expand` |
| Build Site | `biblio site build` |
| Run Docling For Selected | `biblio docling run --key <citekey>` |

A progress bar is shown for OpenAlex resolve, graph expand, and Docling.

To add a paper by DOI directly, enter the DOI in the **Add paper by DOI** field
and click **Add DOI**.

### Setup

Inspect and configure the workspace:

- **Docling command** — the executable `biblio` will call; edit and save a raw
  command, a conda env name, or install Docling into a local `uv`-managed
  environment
- **Workspace paths** — citekeys, srcbib, pdf root, Docling output, OpenAlex out
- **Readiness summary** — paper/docling/openalex counts and any warnings
- **RAG** — edit and save the bibliography-owned RAG source config at
  `bib/config/rag.yaml`:
    - embedding model
    - chunk size and overlap
    - default store and persist directory
    - **Sync owned sources** / **Reinitialize + sync** buttons

!!! note
    The Setup tab manages `bib/config/rag.yaml` only. Building the RAG index
    itself requires the `rag` tool: `rag build --config bib/config/rag.yaml`.

## Typical explore-and-add workflow

1. Run `biblio openalex resolve` (or use the **Resolve OpenAlex** button in
   Actions).
2. Run `biblio graph expand` (or use the **Expand Graph** button in Actions).
3. Switch to the **Explore** tab. Select a paper. The **Candidates** sidebar
   panel now lists papers that cite or are referenced by that paper.
4. Click **Add to Bib** for any candidate you want to include.
5. Run **Merge BibTeX** to consolidate the new entries.
