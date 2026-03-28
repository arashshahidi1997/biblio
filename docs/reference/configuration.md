# Configuration

`biblio` resolves settings from three sources in order. Later layers win on
conflict; nested sections are deep-merged (a project setting does not erase
unrelated user settings).

| Layer | Path | Scope |
|---|---|---|
| User config | `~/.config/biblio/config.yml` | all projects for this user |
| Project config | `bib/config/biblio.yml` | one project |
| Citekey list | `bib/config/citekeys.md` | active paper set |

Set `BIBLIO_USER_CONFIG` to override the user config path.

---

## `bib/config/biblio.yml` — full key reference

All keys are optional. Relative paths are resolved against the project root.

### `pool`

Controls the shared PDF pool.

```yaml
pool:
  path: /storage2/arash/bib        # write target — ingests go here
  search:                          # lookup order (lab first, personal second)
    - /storage/share/sirocampus/bib
    - /storage2/arash/bib
```

| Key | Type | Description |
|---|---|---|
| `path` | path | Pool workspace root to write new PDFs into. |
| `search` | list of paths | Ordered pool workspace roots to search when looking up a PDF. Defaults to `[path]` when omitted. |

Each entry in `search` is a pool workspace root (the directory that contains
`bib/config/biblio.yml`). `biblio` loads each pool's own config to find its
`pdf_root` and `pdf_pattern`.

### `pdf_root` / `pdf_pattern`

```yaml
pdf_root: bib/articles
pdf_pattern: "{citekey}/{citekey}.pdf"
```

### `grobid`

```yaml
grobid:
  url: http://127.0.0.1:8070
  timeout_seconds: 30
  consolidate_header: true
  consolidate_citations: false
  installation_path: ~/tools/grobid   # optional — used to start GROBID locally
```

### `docling`

```yaml
docling:
  cmd: docling                        # or a full path / conda-run wrapper
  to: [md, json]
  image_export_mode: referenced
```

### `openalex`

```yaml
openalex:
  email: you@example.com             # polite pool — faster rate limits
  cache_dir: bib/derivatives/openalex/cache
```

### `rag`

```yaml
rag:
  python: /path/to/python            # python used to run indexio
  persist_dir: .cache/rag/chroma_db
```

### `fetch_queue`

```yaml
fetch_queue: bib/config/fetch_queue.yml
```

Path to the needs-PDF queue. Citekeys with no OA URL or failed downloads are
added here automatically.

### `citekeys`

```yaml
citekeys: bib/config/citekeys.md
```

### `out_root`

```yaml
out_root: bib/derivatives/docling
```

---

## `~/.config/biblio/config.yml` — user config

Accepts the same keys as the project config. Typically used for:

- `pool.path` and `pool.search` (set once per user, applies to all projects)
- `grobid.url` (shared lab GROBID server)

Example written by `biblio profile use sirota`:

```yaml
pool:
  path: /storage2/arash/bib
  search:
    - /storage/share/sirocampus/bib
    - /storage2/arash/bib
grobid:
  url: http://127.0.0.1:8070
```

A project config can override any of these. For example, a project that needs
no pool:

```yaml
# bib/config/biblio.yml
pool:
  path: ~   # disables pool for this project
```

---

## `bib/config/citekeys.md`

Plain Markdown. Any bare citekey token on its own line (or in a list) is
treated as active:

```markdown
# My reading list

- AttentionIsAllYouNeed2017
- BERTDevlin2019
```

Order and headings are preserved but irrelevant to `biblio`.

---

## `bib/config/rag.yaml`

RAG source definitions owned by the bibliography workspace. Passed to
`indexio` when building the semantic search index.
