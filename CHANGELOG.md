# Changelog

## 0.2.1 (2026-10-22)

Fixes from journal-club's 0.2.0 trial (R09-R13).

### Changed
- **Quote fidelity is exact-only**: a quote is verified only on an exact match (after normalizing whitespace, punctuation, hyphenation and docling ligature splits). Near matches are aligned to one passage and reported with a word diff: FID003 warning, or FID004 error when a negation, comparative, direction word or number differs. The review packet shows the same verdicts.
- `wiki lint` reads `bib/srcbib/*.bib` too; CIT005 when a project has no bibliography of its own.

### Fixed
- `wiki lint <folder>` checked nothing and reported 0 errors; folders now expand, and unmatched paths exit 2.
- `wiki init --tag` failed on the first run when `.projio/biblio/tag_vocab.yml` existed.
- `wiki stub --title "A: b"` wrote invalid YAML.

## 0.2.0 (2026-10-22)

### Added
- **Knowledge wiki toolkit** (`biblio wiki`): `init`, `stub`, `lint`, `hubs`, `status`, `embeds`, `figure` and `review`. Lint covers frontmatter, structure, vocabulary tags, links, citations across the project and pools, quotes checked against the paper's full text, code anchors in frontmatter and body (including Snakemake rules), project tokens on general pages, and embedded figures in DataLad datasets. Relative markdown links by default; `--tag` values join `vocab.yml`. See `docs/explanation/wiki.md` and `docs/how-to/wiki-editors.md`.
- **Human review**: `biblio wiki review packet|accept|flag|reopen`; accept needs the reviewer's name and refuses lint errors and open flags.
- **Agent skills** shipped in the package: `wiki-ingest`, `wiki-maintain`, `wiki-review`, `zotero-add`. projio discovers them through the `projio.skills` entry point; `biblio skills install` copies them elsewhere.
- **`biblio refs triage KEY`**: per reference of a held paper, fulltext / pdf / metadata / absent across the project, pools and an optional Zotero library (`zotero.sqlite` or export), matched by DOI, title and year, and OpenAlex `referenced_works`.
- **`biblio add zotero REF`**: one paper from Zotero (item key, DOI or citekey) by the local API (`--local`) or the web API; entry under biblio's citekey, PDF copied.
- **`biblio figures run`**: figures at native resolution from PDFs (embedded images via `pdfimages`, else rendered at 300 dpi) with a manifest.
- **`biblio graph local`**: citation edges between held papers from cached OpenAlex works.
- pixi `dev` environment for tests (`pixi run -e dev test`).
- **`load_active_citekeys(cfg)`** — canonical API for listing active citekeys; reads from merged bib with fallback to srcbib scan
- **`compile_bib(sources, output)`** — merge multiple intermediate `.bib` files into a single compiled output for pandoc/mkdocs-bibtex

### Changed
- One family-name rule for citekeys on every ingest path; DOI metadata from the registry first; `.projio/biblio/biblio.yml` resolved in every command; current Claude models for LLM features; conda replaced by pixi/uv in docling setup.
- `zotero.local: true` now really uses the local API (it went to the web API before).
- **Config and logs moved to `.projio/biblio/`** — `biblio.yml`, `library.yml`, `tag_vocab.yml`, and all logs now live under `.projio/biblio/` instead of `bib/config/` and `bib/logs/`
  - Config loading supports both paths (`.projio/biblio/` preferred, `bib/config/` legacy fallback)
  - All run ledgers (merge, fetch, docling, openalex, pool) write to `.projio/biblio/logs/runs/`
  - Import log: `.projio/biblio/logs/imports.jsonl`
- **Scaffold restructured** — `init_bib_scaffold()` writes config to `.projio/biblio/`, source dirs to `bib/`; `bib/.gitignore` only created when `bib/` is its own git repo (subdataset)
- **`bib/README.md` template** — replaces narrow `srcbib/README.md`; documents full pipeline, CLI, and MCP tools
- **Merge output** — `default_bibtex_merge_config()` now writes to `.projio/biblio/merged.bib` instead of `bib/main.bib`
- **RAG config** — default path changed to `.projio/biblio/rag.yaml`; UI follow-up command updated
- **CLI `biblio citekeys`** — simplified to flat list command reading from merged bib; `add`/`remove`/`status` subcommands removed
- **CLI `--all` flags** — docling, grobid, ref-md now read citekeys from merged bib instead of citekeys.md

### Removed
- **`citekeys.md`** — scaffold template removed; `citekeys` config key no longer needed; all `load_citekeys_md` / `add_citekeys_md` / `remove_citekeys_md` usage replaced by `load_active_citekeys(cfg)` across batch, site, grobid, ingest, graph, and pool modules
- **`bib/Makefile` template** — superseded by biblio MCP tools
- **`bib/config/rag.yaml` template** — belongs to indexio, not biblio
