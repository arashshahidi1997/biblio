# Changelog

## Unreleased

### Added
- **`load_active_citekeys(cfg)`** — canonical API for listing active citekeys; reads from merged bib with fallback to srcbib scan
- **`compile_bib(sources, output)`** — merge multiple intermediate `.bib` files into a single compiled output for pandoc/mkdocs-bibtex

### Changed
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
