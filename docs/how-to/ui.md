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

## Layout

The UI is organized as three columns:

- **Left sidebar** — icon buttons to toggle the network graph, inspector, and setup panels
- **Main area** — a global tab strip along the top; content fills the area below
- **Right column** — shown when the inspector is enabled

### Global tab strip

The leftmost tab is the **▤ Library** tab (earthy warm color). Paper tabs open
to its right when you double-click a row in the Library or click **Open** in
the Corpus table. Each paper tab has a `×` close button.

---

## Tabs

### Library

A filterable list of all local papers (those with a configured citekey). Each
row shows the citekey, title, year, and artifact badges (`pdf`, `docling`,
`openalex`, `grobid`).

**Filtering:**

- **Search** — free-text filter on citekey and title
- **Status** — filter by library status (unread / reading / processed / archived)
- **Tags** — filter by tag

Double-click a row to open its Paper tab.

When the **Network** sidebar is enabled, the Library tab also shows the
Cytoscape graph and controls (see [Explore / Network graph](#network-graph) below).

### Paper tab

Opened per paper by double-clicking in the Library or clicking **Open** in
the Corpus. Multiple paper tabs can be open simultaneously.

#### Header

Shows the citekey, year, title, authors, and artifact badges. Badges without
an artifact become action buttons:

| Badge | Action on click |
|-------|-----------------|
| `no pdf` | Fetch PDF from OpenAlex OA |
| `no docling` | Run Docling on this paper |
| `no openalex` | Resolve OpenAlex metadata |
| `no grobid` | Run GROBID on this paper |
| `expand graph ↻` | Expand the citation graph for this paper |

#### Content subtabs

**PDF** — inline PDF viewer (requires a PDF artifact).

**Docling** — the full Docling-generated HTML content rendered in the browser.

**Standardized** — the GROBID-resolved Pandoc markdown for this paper.
In-text citations (`[@citekey]`) are rendered as clickable links. Hovering
a citation link shows a tooltip with the cited paper's title, authors, and year.
Papers not yet in your local library are still linked (the tooltip shows the
citekey).

To generate the standardized markdown:

```bash
biblio ref-md run --key <citekey>
```

**Figures** — image gallery for figures extracted by Docling.

- Navigate with `←` / `→` buttons.
- Captions extracted from the Docling JSON are shown below each figure (when
  available).
- **Filter logos** checkbox hides small or very wide images (icons, headers)
  that are unlikely to be content figures.

**GROBID** — GROBID header metadata (title, authors, year, DOI, abstract) and
the **Absent refs** panel.

#### Absent refs panel

Lists GROBID-extracted references that are not yet in your local library.

- **Resolve all** — look up CrossRef DOIs for all unresolved titles in one go.
- **Min match slider** — threshold for accepting fuzzy-matched DOIs (default 70%).
- **Copy DOIs** — copy all qualifying DOIs to the clipboard.
- **Add all (N)** — add all qualifying papers to your library via OpenAlex.
- Per-row **Resolve** and **Add** buttons for individual references.

#### Sidebar info

- **Library** — set status, priority, and tags; click **Save**.
- **Related local papers** — papers sharing references (by overlap score).
- **Neighborhood** — outgoing reference count and incoming citation count.

---

### Network graph

Enable the graph with the **◎** button in the left sidebar (visible on the
Library tab).

**Controls bar** (above the graph):

| Control | Options | Effect |
|---------|---------|--------|
| Search papers | free text | filter by citekey or title |
| Focus paper | dropdown | set the active paper |
| Graph filter | Local + external / Local only | show or hide external OpenAlex nodes |
| Explore mode | Focused neighborhood / All papers | limit to active paper's neighbors or show all |
| Direction | Past + future / Past works / Future works | filter edge direction |
| Size by | cited\_by / uniform | scale node size by citation count |
| Color by | year / uniform | color nodes by publication year (blue→light gradient) |

**Overlay toolbar** (top-right inside the graph canvas):

- **⊙** — toggle between Focused and All mode
- **← ⟷ →** — switch direction filter

**Node style:**

- Local papers: sized by citation count (when Size by = cited\_by), colored by
  year (when Color by = year). Label shows `Author Year` (e.g. `Battaglia 2004`).
- External (OpenAlex) nodes: smaller, dimmed, no label (shown in hover tooltip).
- Selected node: blue glow highlight.
- When a node is selected, its direct neighbors remain fully visible and all
  other nodes fade.

**Graph actions sidebar** (right of graph):

- **+** / **−** — zoom in/out
- **⤢** — fit graph to view
- **Expand graph ↻** — expand the citation graph for the selected paper

**Year legend** — shown below the graph when Color by = year; displays the
gradient from oldest to newest paper.

**Inspector** — enable with the **ⓘ** button in the left sidebar; shows the
selected paper's metadata and candidates panel (see below).

#### Candidates panel

Lists papers discovered by graph expansion for the active paper (references and
citing works not yet in your library). Each entry shows:

- Title, year
- Direction badge: `→ ref` (paper references it) or `← citing` (it cites the paper)
- **in corpus** badge if already in your library
- **Add to Bib** button for external papers

---

### Corpus

A table of all discovered papers (configured citekeys plus candidates from
srcbib). Each row shows artifact status and per-row actions:

- **Open** — open the Paper tab for that paper
- **Explore** — switch to the graph focused on that paper
- **Docling** — trigger Docling for that paper

---

### Setup

Subtabs: **Overview**, **Docling**, **GROBID**, **RAG**.

**Overview — Workspace** shows all configured paths (citekeys, srcbib, pdf
root, Docling output, OpenAlex out) and a readiness summary (paper/pdf/docling/
openalex counts).

**Overview — Pipeline** provides numbered one-click buttons to run the full
data pipeline in order:

| Step | Action |
|------|--------|
| 1 | Fetch PDFs (OpenAlex OA) |
| 2 | Resolve OpenAlex metadata |
| 3 | Expand citation graph |
| 4 | Run GROBID (all PDFs) |
| 5 | Match GROBID references to local library |

**Docling** — view and change the Docling executable command. Options:

- Save a raw command string
- Use a conda environment by name
- Install Docling into a local `uv`-managed environment

**GROBID** — view GROBID server status (URL, latency, reachable badge) and
configure the server URL and optional installation path.

**RAG** — edit `bib/config/rag.yaml` (embedding model, chunk size/overlap,
default store, persist directory) and sync owned sources.

!!! note
    The Setup tab manages `bib/config/rag.yaml` only. Building the RAG index
    itself requires the `rag` tool: `rag build --config bib/config/rag.yaml`.

---

## Typical explore-and-add workflow

1. Run `biblio openalex resolve` (or **Resolve OpenAlex** in Setup → Pipeline).
2. Run `biblio graph expand` (or **Expand Graph** in Setup → Pipeline).
3. Open the **Library** tab and enable the **◎ Network** sidebar.
4. Select a paper in the graph. The **Inspector → Candidates** panel lists
   papers that cite or are referenced by that paper.
5. Click **Add to Bib** for any candidate you want to include.
6. Run `biblio bibtex merge` to consolidate new entries.

## Typical per-paper reading workflow

1. Double-click a paper in the Library to open its tab.
2. Check artifact badges — click any missing artifact button to generate it.
3. Read the **Docling** or **Standardized** subtab.
4. In the **Standardized** subtab, hover over `[@citekey]` links to preview
   cited papers. Click nothing required — tooltip appears on hover.
5. Browse **Figures** to see extracted figures with captions.
6. Go to **GROBID → Absent refs**, resolve DOIs, and add missing references
   in bulk.
