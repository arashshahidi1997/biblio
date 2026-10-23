# biblio

## Projio workspace

This project uses **projio** — a project-centric research assistance ecosystem.
All project knowledge (papers, notes, code libraries, search indexes) is managed
through MCP tools. **Always use MCP tools instead of direct file manipulation**
for projio-managed resources.

**Tool preference:** Follow the routing table below. Where it names an MCP
tool, prefer it over the Bash equivalent — even for simple commands like
`git status` or `datalad status`: MCP tools return structured output and
resolve environment variables that differ from the MCP server's own env.
Where it names a CLI command (marked "CLI"), run that command; those
subsystems are CLI-first and their skills say how.

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
| Look up papers (key, DOI or 'Author Year Title'; project or pools) | `paper_lookup(refs)` | Read .bib files or search pools by hand |
| A paper's sections, GROBID header, topics | `paper_lookup(refs, detail="context")` | Read docling/GROBID outputs directly |
| Read exact wording from a paper | `biblio fulltext KEY --section S` / `--grep W` / `--lines A-B` (CLI) | Read the docling .md directly (artefacts, other line numbers) |
| Extract full text, references, OA PDFs, claims digests | `biblio_job("start", kind=docling\|grobid\|oa_fetch\|digest, keys=[...])`, then `biblio_job("status", job_id=...)` | Run a batch without keys in a shared copy |
| Ingest papers by DOI | `biblio_ingest(dois)` | Write BibTeX by hand |
| Add papers from Zotero (groups too) | `biblio add zotero REF... --local` (CLI, on the Zotero machine) | Copy PDFs from Zotero storage by hand |
| Where is each paper of a list | `biblio locate --from list.txt [--openalex]` (CLI) | Search Zotero and pools one by one |
| A held paper's references | `biblio refs triage KEY` (CLI) | Parse references.json manually |
| Check quotes in any markdown file | `biblio quotes check FILE` (CLI) | Grep quotes by hand |
| Claims across papers | `biblio digest claims-table KEY... --grep W` (CLI) | Read digests one by one |
| Literature wiki | skills `wiki-ingest`, `wiki-synthesize`, `wiki-maintain`, `wiki-review`; `biblio wiki lint` (CLI) | Edit reviewed pages, or links by hand (`biblio wiki relink`) |
| Pipeline status per paper | `biblio_status(citekeys)` | Inspect derivative folders manually |
| Compile the bibliography for rendering | `biblio_compile()` | Concatenate .bib files |
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
2. **Ingest pipeline** — add papers (`biblio_ingest(dois)`, or `biblio add zotero` on the Zotero machine), then `biblio_job("start", kind="grobid", keys=[...])` and `kind="docling"` for those keys only; `biblio_job("status", job_id=...)` until done
3. **Pool promote** — after processing, `biblio pool promote KEY...` (CLI) shares PDFs and derivatives across projects
4. **Zotero** — `biblio add zotero REF... --local` (CLI) adds papers with their PDFs; `biblio zotero pull|push` (CLI) syncs a collection. Uses optimistic concurrency (version check); tags use `biblio:` prefix
5. **Record decisions** — create notes to capture analysis and decisions

## Development

```bash
make         # see available targets
make save    # datalad save
make push    # datalad push
```
