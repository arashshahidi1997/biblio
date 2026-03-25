# biblio

## Projio workspace

This project uses **projio** — a project-centric research assistance ecosystem.
All project knowledge (papers, notes, code libraries, search indexes) is managed
through MCP tools. **Always use MCP tools instead of direct file manipulation**
for projio-managed resources.

At the start of a session, call `project_context()` to understand the workspace
and `runtime_conventions()` to see available Makefile targets.

## Agent tool routing

| Intent | MCP tool | Do NOT |
|--------|----------|--------|
| Understand the project | `project_context()` | Read config files directly |
| See available commands | `runtime_conventions()` | Parse the Makefile manually |
| Search project knowledge | `rag_query(query)` | Grep through docs manually |
| Multi-facet search | `rag_query_multi(queries)` | Run multiple greps |
| Check indexed sources | `corpus_list()` | Inspect Chroma store directly |
| Rebuild search index | `indexio_build()` | Run `indexio build` in terminal |
| Ingest papers by DOI | `biblio_ingest(dois)` | Write BibTeX by hand |
| Look up a paper | `citekey_resolve(citekeys)` | Read .bib files directly |
| Get full paper context | `paper_context(citekey)` | Read docling/GROBID outputs directly |
| Find unresolved refs | `paper_absent_refs(citekey)` | Parse references.json manually |
| Check paper status | `library_get(citekey)` | Read library.yml directly |
| Update paper status | `biblio_library_set(citekeys)` | Edit library.yml directly |
| Merge bibliography | `biblio_merge()` | Run `biblio merge` in terminal |
| Extract full text | `biblio_docling(citekey)` | Run `biblio docling` in terminal |
| Extract references | `biblio_grobid(citekey)` | Run `biblio grobid` in terminal |
| Check GROBID server | `biblio_grobid_check()` | Curl the GROBID API manually |
| Create a note/task/idea | `note_create(note_type)` | Create markdown files directly |
| List recent notes | `note_list()` | List files in notes/ directory |
| Read a note | `note_read(path)` | Read the file directly |
| Search notes | `note_search(query)` | Grep through notes/ |
| Update note metadata | `note_update(path, fields)` | Edit frontmatter directly |
| See note types | `note_types()` | Read notio.toml directly |
| Add a library | `codio_add_urls(urls)` | Edit YAML registry files |
| Find libraries by capability | `codio_discover(query)` | Grep catalog.yml |
| Inspect a library | `codio_get(name)` | Read catalog + profiles manually |
| List all libraries | `codio_list()` | Parse registry files directly |
| Check registry vocabulary | `codio_vocab()` | Read schema docs |
| Validate registry | `codio_validate()` | Run consistency checks manually |

## Workflow conventions

1. **Search first** — check existing knowledge before creating new content
2. **Ingest pipeline** — after `biblio_ingest`, run `biblio_merge` → `biblio_docling` → `biblio_grobid` → `indexio_build`
3. **Record decisions** — create notes to capture analysis and decisions

## Development

```bash
make         # see available targets
make save    # datalad save
make push    # datalad push
```
