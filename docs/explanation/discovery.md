# Discovery Model

**Status:** Accepted
**Date:** 2026-04-03

## Design Principle

Biblio is a **local bibliography manager**, not a literature search engine.
Discovery features exist to bridge the gap between external databases
(OpenAlex, Semantic Scholar, publisher sites) and the local `bib/` workspace.

The guiding rule: **delegate browsing to purpose-built tools, own the import
path.** OpenAlex has a better author search than biblio ever will. The value
biblio adds is making the round-trip seamless — outbound links to explore,
inbound paste/API to ingest.

## Discovery Surfaces

Biblio exposes discovery through three interfaces, each with different
capabilities reflecting its use context:

### MCP Tools (agent workflows)

Agents cannot browse the web, so they get full structured discovery:

| Tool | Purpose |
|------|---------|
| `biblio_discover_authors(query)` | Search authors by name |
| `biblio_discover_authors(orcid=...)` | Lookup by ORCID |
| `biblio_discover_authors(author_id=...)` | Lookup by OpenAlex ID |
| `biblio_discover_institutions(query)` | Search institutions by name |
| `biblio_institution_works(id, since_year, min_citations)` | All papers from an institution |
| `biblio_institution_authors(id, min_works)` | Researchers at an institution |
| `biblio_author_papers(id, position, since_year)` | Author works with position filter |
| `biblio_graph_expand(citekeys, direction)` | Citation graph expansion from seeds |
| `biblio_ingest(dois)` | Ingest by DOI |

**Position filter** (`first` / `middle` / `last`) enables "lab output" queries:
`biblio_author_papers(author_id="A5013744561", position="last")` returns papers
where Sirota is senior/PI author.

**Typical agent workflow:**
```
discover_authors("Buzsáki")          → pick A5023888391
author_papers(id, position="last",   → 180 papers
              since_year=2020)
biblio_ingest(selected_dois)         → add to local bib
biblio_merge() → biblio_compile()    → update bibliography
```

### GUI (biblio ui)

The GUI delegates discovery to OpenAlex and focuses on the import path:

| Feature | Location | Purpose |
|---------|----------|---------|
| **Paste toast** | Global | Detects DOIs and OpenAlex URLs (`openalex.org/works/W...`) pasted anywhere; offers one-click import |
| **Import panel** | Sidebar (magnifying glass icon) | Textarea for pasting OpenAlex URLs, work IDs, or DOIs in bulk |
| **ORCID import** | Actions tab | Enter ORCID → preview works → select & import |
| **Graph explore** | Explore tab (Cytoscape) | Visual citation graph; expand nodes; add candidates to bib |
| **Outbound links** | Paper detail view | DOI and OpenAlex links on every paper for quick context switching |

**Typical GUI workflow:**
1. Browse [openalex.org/works?filter=authorships.author.id:A5013744561](https://openalex.org/works?filter=authorships.author.id:a5013744561)
2. Copy work URLs for papers of interest
3. Paste into biblio → toast or import panel picks them up
4. One-click import resolves metadata and writes BibTeX

### CLI

| Command | Purpose |
|---------|---------|
| `biblio add doi 10.xxxx/...` | Ingest single paper by DOI |
| `biblio add openalex W1234567890` | Ingest single paper by OpenAlex ID |
| `biblio openalex resolve` | Resolve all srcbib entries to OpenAlex metadata |
| `biblio graph expand` | Expand citation graph from resolved seeds |

## Discovery Strategies

### Inside-out: seed expansion

Start from papers already in the library. Expand via citations.

```
existing papers → openalex resolve → graph expand → review candidates → ingest
```

Best for: deepening coverage around a known topic. The Explore tab visualizes
the citation neighborhood and highlights candidates not yet in the library.

### Outside-in: author/institution lookup

Start from a person or lab. Get their publications. Selectively ingest.

```
author name/ORCID → list works → filter (year, citations, position) → ingest
```

Best for: onboarding a new collaborator's work, tracking a lab's output,
building a reading list around a research group.

### Browse and paste

User drives discovery in an external tool (OpenAlex web, Google Scholar,
Connected Papers, Semantic Scholar). Pastes identifiers back into biblio.

```
browse externally → copy URLs/DOIs → paste into biblio → import
```

Best for: exploratory reading, following references from a talk or review,
ad-hoc additions. The paste toast makes this zero-friction.

## What Biblio Does Not Do

- **Keyword/topic search across all of OpenAlex.** Use openalex.org for that.
  Biblio searches *your library* (via RAG, concept search, tag queries).
- **Saved searches or alerts.** No periodic polling of external APIs.
  Use OpenAlex email alerts or RSS feeds externally.
- **Author disambiguation.** Biblio trusts OpenAlex author IDs. If OpenAlex
  merges or splits author records, biblio follows.
- **Full-text search of external papers.** Only indexed local papers
  (after docling extraction) are searchable via RAG.

## Data Flow

```
                    ┌─────────────────────┐
                    │  External Sources    │
                    │  OpenAlex, CrossRef, │
                    │  Unpaywall, EZProxy  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼──────┐  ┌─────▼──────┐  ┌──────▼─────┐
        │ MCP tools  │  │ GUI paste/ │  │ CLI add    │
        │ discover_* │  │ import     │  │ doi/oa_id  │
        └─────┬──────┘  └─────┬──────┘  └──────┬─────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  add_openalex_work  │
                    │  _to_bib()          │
                    │  (resolve + write)  │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  bib/imports/*.bib  │
                    │  (new entries)      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  biblio_merge →     │
                    │  biblio_compile     │
                    │  (rebuild bib)      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Enrichment         │
                    │  pdf_fetch → docling│
                    │  → grobid → RAG    │
                    └─────────────────────┘
```

## OpenAlex API Endpoints Used

| Endpoint | Biblio usage |
|----------|-------------|
| `GET /works/{id}` | Resolve by OpenAlex ID |
| `GET /works/doi:{doi}` | Resolve by DOI |
| `GET /works?search=` | Title search (resolution fallback) |
| `GET /works?filter=author.id:` | Author works |
| `GET /works?filter=institutions.id:` | Institution works |
| `GET /works?filter=cites:` | Citing works (graph expand) |
| `GET /authors?search=` | Author name search |
| `GET /authors?filter=orcid:` | ORCID lookup |
| `GET /authors?filter=last_known_institutions.id:` | Institution authors |
| `GET /institutions?search=` | Institution name search |
| `GET /institutions/{id}` | Institution lookup |

Position filtering (`first` / `middle` / `last`) is done client-side by
inspecting the `authorships[].author_position` field in work records.
