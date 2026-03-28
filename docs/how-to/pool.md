# Use a Shared PDF Pool

A PDF pool is a standalone `biblio` workspace whose `bib/articles/` directory
is the authoritative store of PDFs. Projects link to the pool and access PDFs
through symlinks, keeping project repos free of large binary files.

## Concepts

| Term | Meaning |
|---|---|
| **Pool workspace** | A directory with its own `bib/config/biblio.yml` whose `pdf_root` holds real PDFs |
| **Personal pool** | Your own pool on personal HPC storage, writable by you |
| **Lab pool** | A shared pool on shared storage, typically read-only for regular users |
| **Pool search list** | Ordered list of pools queried when looking up a PDF — lab pool first, personal second |
| **Inbox** | A staging directory where you drop new PDFs before ingestion |

---

## Link a project to a pool

```bash
biblio pool link
```

Reads `pool.path` from `~/.config/biblio/config.yml` (set by `biblio profile
use`) and writes it into the project's `bib/config/biblio.yml`. Also adds
`bib/articles/` to `.gitignore`.

To link to a specific pool not in your user config:

```bash
biblio pool link --pool /storage2/arash/bib
```

To link your personal pool and register a lab pool in the search list at the
same time:

```bash
biblio pool link --pool /storage2/arash/bib \
                 --lab /storage/share/sirocampus/bib
```

This writes:

```yaml
pool:
  path: /storage2/arash/bib
  search:
    - /storage/share/sirocampus/bib
    - /storage2/arash/bib
```

After linking, existing citekeys that are already in any pool are symlinked
immediately. Pass `--no-sync` to skip that step.

---

## Ingest PDFs from an inbox

```bash
biblio pool ingest ~/inbox
```

For each PDF in `~/inbox`:

1. GROBID extracts the header (title, authors, DOI)
2. OpenAlex enriches metadata if a DOI is found
3. PDF is copied to the pool at `bib/articles/<citekey>/<citekey>.pdf`
4. A BibTeX entry is appended to `bib/srcbib/inbox.bib`

Options:

| Flag | Effect |
|---|---|
| `--pool <path>` | Target pool (defaults to `pool.path` in config) |
| `--dry-run` | Report what would happen without writing anything |
| `--move` | Delete source PDF from inbox after ingestion |

---

## Watch an inbox continuously

```bash
biblio pool watch ~/inbox --move --interval 60
```

Polls the inbox every 60 seconds and ingests any new PDFs. Useful to leave
running alongside a drop server.

To run detached in a GNU screen session:

```bash
biblio pool watch ~/inbox --move --screen
```

---

## Serve a drop endpoint

Start an HTTP server that accepts PDF uploads:

```bash
biblio pool serve --inbox ~/inbox
```

Default host is `127.0.0.1`, default port is `7171`. To accept connections from
other machines (e.g. your laptop connecting to an HPC login node):

```bash
biblio pool serve --inbox ~/inbox --host 0.0.0.0 --port 7171
```

### Browser bookmarklet

```bash
biblio pool bookmarklet
```

Prints a `javascript:` URI. Drag it to your browser's bookmarks bar. On any
paper page that exposes a `citation_doi` meta tag, clicking the bookmarklet
sends the DOI to the running drop server, which fetches the PDF into your inbox.

Combine with `biblio pool watch` so drops are ingested automatically.

---

## Manage the needs-PDF queue

When `biblio bibtex fetch-pdfs` cannot find a PDF (no OA URL, download error,
not in any pool), the citekey is added to a queue at
`bib/config/fetch_queue.yml`.

```bash
biblio queue list          # show queued citekeys + reason
biblio queue open          # open queue file in $EDITOR
biblio queue drain         # re-attempt fetch for all queued citekeys
biblio queue remove <key>  # remove a specific citekey from the queue
```

---

## Pool lookup order

When fetching PDFs (`biblio bibtex fetch-pdfs`), `biblio` checks pools before
attempting any network download. The search order follows `pool.search`:

1. Lab pool (if configured)
2. Personal pool
3. Open-access download via OpenAlex URL

A pool hit creates a symlink in `bib/articles/` pointing to the pool PDF. No
duplicate copies are made.

---

## Sync pool symlinks

After new PDFs arrive in any pool, refresh symlinks for the current project:

```bash
biblio pool link --no-sync   # re-link config without sync
# or just run fetch-pdfs to pick up new pool entries automatically:
biblio bibtex fetch-pdfs
```
