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

---

## Layout

The UI fills the full browser viewport with no side margins — each column scrolls
independently.

```
┌─ title bar ──────────────────────────────────────────────┐
│ BiBlio                                          Docs  ⚙  │
├─ sidebar ─┬─ main content ───────────────────────────────┤
│  ⌕        │  ‹  ›  ▤ Library  │  paper…  │  paper…  ×  │
│  ⓘ        ├──────────────────────────────────────────────┤
│           │  [controls bar]                              │
│  ⚙        │  ┌─ col ──┐  ┌─ col ──┐  ┌─ col ──┐        │
│           │  │library │  │ graph  │  │ paper  │        │
│           │  │ (scrolls│  │(scrolls│  │(scrolls│        │
└───────────┴──┴────────┴──┴────────┴──┴────────┴─────────┘
```

### Left sidebar

Slim icon rail with:

| Icon | Function |
|------|----------|
| **⌕** | Toggle the Search panel |
| **ⓘ** | Toggle the Graph Inspector (Library tab only) |
| **⚙** | Open Settings |

### Global tab strip

Sits above the content area. Navigation buttons `‹` and `›` let you move
back and forward through your navigation history.

The leftmost tab is the **▤ Library** tab (warm earthy color). Paper tabs open
to its right when you double-click a row in the Library or click **↗ Open**.
Each paper tab has a `×` close button.

Clicking any tab records a navigation history entry; `‹` / `›` let you retrace
your path without losing open tabs.

---

## Tabs

### Library

A filterable table of all local papers (those with a configured citekey). Each
row shows the citekey, title, year, and artifact badges (`pdf`, `docling`,
`openalex`, `grobid`).

**Filtering:**

- **Search** — free-text filter on citekey and title
- **Status** — filter by library status (unread / reading / processed / archived)
- **Tags** — filter by tag

Double-click a row to open its Paper tab. Click **↗** to open the tab or **◎**
to focus the network graph on that paper.

**Right-click a row** to open a context menu with:

| Action | Effect |
|--------|--------|
| **↻ Refresh metadata from DOI** | Re-fetches OpenAlex metadata for the paper using its recorded DOI |
| **✕ Drop from library** | Removes the paper from `citekeys.md` (files are kept; confirm required) |
| **Add to collection** | Add/remove the paper from any collection |

When the **Network** sidebar is enabled, the Library tab also shows the
Cytoscape graph and controls (see [Network graph](#network-graph) below).

---

### Paper tab

Opened per paper by double-clicking in the Library or clicking **↗ Open**.
Multiple paper tabs can be open simultaneously.

#### Header

Shows citekey, year, title, authors, and artifact badges. Badges without an
artifact become action buttons:

| Badge | Action on click |
|-------|-----------------|
| `no pdf` | Fetch PDF from OpenAlex OA |
| `no docling` | Run Docling on this paper |
| `no openalex` | Resolve OpenAlex metadata |
| `no grobid` | Run GROBID on this paper |
| `expand graph ↻` | Expand the citation graph for this paper |

#### Content subtabs

A `⛶` / `⊠` button at the far right of the subtab bar toggles **fullscreen**
for the content column.

**PDF** — inline PDF viewer (requires a PDF artifact).

**Markdown** — the GROBID-resolved Pandoc markdown for this paper, rendered
as HTML. In-text citations (`[@citekey]`) become clickable links:

- **Hover** — tooltip shows the cited paper's title, authors, year,
  citation count (from OpenAlex), and first research topic.
- **Click** — opens the cited paper in a new tab (only works for papers
  already in your local library).

To generate the Markdown:

```bash
biblio ref-md run --key <citekey>
```

**Figures** — image gallery for figures extracted by Docling.

- Navigate with `←` / `→` buttons.
- Captions from the Docling JSON are shown below each figure when available.
- **Filter logos** checkbox hides small or very wide images unlikely to be
  content figures.

**Refs** — GROBID header metadata (title, authors, year, DOI, abstract) and
the **Absent refs** panel.

#### Absent refs panel

Lists GROBID-extracted references not yet in your local library. Loads
automatically when you open the Refs subtab. Previous CrossRef resolutions
are cached on disk and restored immediately.

| Control | Effect |
|---------|--------|
| **Resolve all (N)** | Look up CrossRef DOIs for all unresolved titles in one pass |
| **Min match slider** | Threshold for accepting a fuzzy-matched DOI (default 70 %) — always visible; shows how many resolved refs pass |
| **Copy DOIs** | Copy all qualifying DOIs to the clipboard |
| **Add all (N)** | Add all qualifying papers to your library via OpenAlex |
| **↺** | Reload absent refs from disk |
| Per-row **Resolve** | Look up CrossRef for that reference |
| Per-row **Add** | Add one paper by DOI |

Resolution results are saved automatically to
`bib/derivatives/grobid/<citekey>/_ref_resolutions.json` so they survive
page reloads.

#### Sidebar

- **Library** — set status, priority, and tags; click **Save**.
- **Related local papers** — papers sharing references (by overlap score).
- **Neighborhood** — outgoing reference count and incoming citation count.
- A compact note below Neighborhood shows how many GROBID refs were extracted;
  open the **Refs** subtab to resolve absent ones.

---

### Network graph

Enable with the **◎** button in the left sidebar (visible on the Library tab).

**Controls bar** (above the graph):

| Control | Options | Effect |
|---------|---------|--------|
| Search papers | free text | filter by citekey or title |
| Focus paper | dropdown | set the active paper |
| Graph filter | Local + external / Local only | show or hide external OpenAlex nodes |
| Explore mode | Focused neighborhood / All papers | limit to active paper's neighbors or show all |
| Direction | Past + future / Past works / Future works | filter edge direction |
| Size by | cited\_by / uniform | scale node size by citation count |
| Color by | year / uniform | color nodes by year (blue gradient) |

**Overlay toolbar** (top-right inside the graph canvas):

- **⊙** — toggle Focused / All mode
- **← ⟷ →** — switch direction filter

**Node style:**

- Local papers — sized by citation count (Size by = cited\_by), colored by year
  (Color by = year). Label shows `Author Year` (e.g. `Battaglia 2004`).
- External (OpenAlex) nodes — smaller, dimmed, no label (label shown in hover tooltip).
- Selected node — blue glow.
- Selecting a node fades all non-neighbor nodes.

**Graph actions sidebar** (to the right of the graph):

- **+** / **−** — zoom in/out
- **⤢** — fit graph to view
- **↻** — expand the citation graph for the selected paper

**Year legend** — shown below the graph when Color by = year; gradient from
oldest to newest paper.

**Inspector** — enable with **ⓘ** in the left sidebar; shows the selected
paper's metadata and candidates panel (papers discovered by graph expansion).

#### Candidates panel

Lists papers from graph expansion not yet in your library. Each entry shows:

- Title, year
- Direction badge: `→ ref` (paper references it) or `← citing` (it cites the paper)
- **in corpus** badge if already in your library
- **Add to Bib** button for external papers

---

### Setup

Subtabs: **Overview**, **Docling**, **GROBID**, **RAG**.

**Overview — Workspace** shows all configured paths and a readiness summary
(paper / pdf / docling / openalex counts).

**Overview — Pipeline** provides numbered one-click buttons for the full data
pipeline:

| Step | Action |
|------|--------|
| 1 | Fetch PDFs (OpenAlex OA) |
| 2 | Resolve OpenAlex metadata |
| 3 | Expand citation graph |
| 4 | Run GROBID (all PDFs) |
| 5 | Match GROBID references to local library |

**Overview — Normalize citekeys** — renames existing BibTeX keys that do not
match the standard `author_year_Title` format (e.g. `battaglia_2004_Hippocampal`).
Click **Preview renames** to see proposed changes, then **Apply N renames** to
write them. Derived artifacts (Docling, GROBID) will need re-running after.

**Docling** — view and change the Docling executable command. Options:

- Save a raw command string
- Use a conda environment by name
- Install Docling into a local `uv`-managed environment

**GROBID** — view GROBID server status and configure the server URL and optional
installation path.

**RAG** — edit `bib/config/rag.yaml` (embedding model, chunk size/overlap,
default store, persist directory) and sync owned sources.

!!! note
    The Setup tab manages `bib/config/rag.yaml` only. Building the RAG index
    requires the `rag` tool: `rag build --config bib/config/rag.yaml`.

---

## Citekey format

Papers added via DOI or OpenAlex are assigned citekeys in the form
`author_year_TitleWords`, e.g. `battaglia_2004_HippocampalSharp`. The author
token is the first author's lowercase family name; the title token is the first
two significant words of the title in CamelCase.

Existing citekeys that do not follow this format can be renamed using
**Setup → Normalize citekeys**.

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
2. Check artifact badges — click any missing one to generate it.
3. Read the **Markdown** subtab. Hover `[@citekey]` links for cited-paper
   previews (title, authors, year, citation count); click to open that paper.
4. Browse **Figures** for extracted figures with captions.
5. Go to **Refs → Absent refs** — resolutions load automatically. Resolve
   remaining DOIs, adjust the match threshold, and add missing references in bulk.
