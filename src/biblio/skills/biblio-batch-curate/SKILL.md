---
name: biblio-batch-curate
description: >
  End-to-end bibliography curation for a batch of papers: add them (DOIs or
  Zotero), fetch open-access PDFs, extract references and full text for
  exactly those papers as background jobs, compile the bibliography, and
  sync indexes. Use after bulk paper discovery or when a batch needs a full
  refresh.
metadata:
  short-description: Add → fetch → extract (named keys, background) → compile → index
  tags: [bibliography, batch, curation, production]
  tooling:
    mcp:
      - server: projio
        tools:
          - biblio_ingest
          - biblio_job
          - biblio_status
          - biblio_compile
          - paper_lookup
          - indexio_sources_sync
    cli: [biblio add zotero, biblio locate, biblio bibtex merge, biblio graph expand]
---

# Bibliography Batch Curation

Take a batch of papers from references to extracted, indexed papers with a
compiled bibliography for rendering. Every step after the first works on the
batch's citekeys only: a project copy may be shared with other sessions, and
a batch without keys would process their papers too.

## When to use

- After bulk paper discovery (literature-discovery, graph expansion, author search)
- When onboarding a batch of papers from Zotero
- Refreshing a set of papers (new PDFs available, stale docling outputs)

For a single paper use `paper_lookup([ref])`.

## Inputs

- `REFS`: DOIs, Zotero refs, or citekeys already in the project.
- `TAGS` (optional): tags for newly ingested papers.

## Workflow

### 1) What is already held

```
paper_lookup(refs=REFS)
```

Each ref comes back with where it is held (project, a pool, nowhere) and its
citekey. Papers already in the project with full text need nothing more; for
a list of loose references (titles, author-year) the CLI gives one table:
`biblio locate --from refs.txt --openalex`.

### 2) Add the missing papers

- By DOI: `biblio_ingest(dois=[...], tags=TAGS, status="unread")`.
- From Zotero (with PDFs, group libraries too), on the machine running Zotero:
  `biblio add zotero REF... --local` (CLI).

Record the citekeys; they are `KEYS` from here on. New entries count for the
batch tools at once (no merge needed for extraction).

### 3) Open-access PDFs for papers without one

```
biblio_job(action="start", kind="oa_fetch", keys=KEYS)
biblio_job(action="status", job_id=...)
```

The fetch keeps only real PDFs (an HTML paywall page is rejected). Report
fetched and missing; missing papers need a PDF from the user or Zotero.

### 4) References and full text

```
biblio_job(action="start", kind="grobid", keys=KEYS)
biblio_job(action="start", kind="docling", keys=KEYS)
```

The docling start returns its plan first: what will be converted and what is
skipped and why (`done`, `no PDF`, `not in the bibliography, no PDF`). Poll
each job with `biblio_job(action="status", job_id=...)`; its `summary` lists
failures per key. A GROBID failure for every key usually means the server is
down (`biblio grobid check`, CLI); continue without it and say so.

### 5) Citation graph (optional, ask first)

`biblio graph expand` (CLI). Report new DOIs and ask whether to add them
(back to step 2).

### 6) Compile the bibliography

`biblio bibtex merge` (CLI), then:

```
biblio_compile()
```

Report the entry count of `.projio/render/compiled.bib`.

### 7) Status and indexes

```
biblio_status(citekeys=KEYS)
indexio_sources_sync(build=True)
```

## Decision gates

1. After step 1: confirm the batch (what is held, what will be added).
2. After step 5: whether to add newly found papers.

## Guardrails

- Always pass `keys` to `biblio_job`; never start a batch for the whole
  bibliography in a shared copy unless the user asks.
- Docling concurrency stays at 1 (2 at most) on shared machines.
- `biblio bibtex merge` before `biblio_compile`.
- No git or DataLad commands during the workflow.

## Output format

1. Papers added (count, refs that failed)
2. PDFs fetched / missing
3. GROBID and docling: converted, skipped (with reasons), failed
4. Compiled bibliography entry count
5. Index rebuild status
6. Suggested next step (e.g. claims digests: `biblio_job(action="start", kind="digest", keys=KEYS)`)
