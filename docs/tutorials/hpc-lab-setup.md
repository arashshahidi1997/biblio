# HPC Lab Setup

This tutorial walks a new Sirota Lab member through setting up `biblio` on
UCSF HPC. By the end you will have:

- a personal PDF pool on your HPC storage volume
- automatic access to the shared lab PDF pool
- one project linked to both pools

## Prerequisites

- `biblio-tools` installed in your `rag` conda environment
- Access to UCSF HPC with a personal storage volume at `/storage<N>/<username>/`
- (Optional) a GROBID server running for metadata extraction

---

## Step 1 — Apply the lab profile

The `sirota` profile configures your personal pool path, adds the shared lab
pool to your search list, and sets the lab GROBID server.

```bash
biblio profile use sirota
```

`biblio` scans `/storage[0-9]*/<username>/` and confirms what it finds:

```
Personal storage detected: /storage2/arash
Use this? [Y/n]
```

Press Enter to accept. The profile is written to `~/.config/biblio/config.yml`:

```yaml
pool:
  path: /storage2/arash/bib
  search:
    - /storage/share/sirocampus/bib
    - /storage2/arash/bib
grobid:
  url: http://127.0.0.1:8070
```

If you have storage on a different volume, pass `--storage` explicitly:

```bash
biblio profile use sirota --storage /storage3/arash
```

To confirm the result:

```bash
biblio profile show
```

---

## Step 2 — Link a project to your pool

Inside any project that uses `biblio`, link it to your personal pool:

```bash
cd ~/projects/my-study
biblio pool link
```

This writes `pool.path` into `bib/config/biblio.yml` and adds `bib/articles/`
to `.gitignore`. PDFs are now stored in the pool and accessed through symlinks
— keeping the project repo light.

If any active citekeys already have PDFs in either pool, symlinks are created
immediately.

---

## Step 3 — Verify pool lookup

Run an OA fetch to confirm the pool search works:

```bash
biblio bibtex fetch-pdfs
```

For each citekey the lookup order is:

1. Lab pool (`/storage/share/sirocampus/bib`)
2. Your personal pool (`/storage2/arash/bib`)
3. Open-access download (if no pool hit)

Papers already in the lab pool are symlinked without any download.

---

## Step 4 — Ingest new PDFs into your personal pool

Drop PDFs you have acquired (from journal websites, email, etc.) into an inbox
directory and ingest them:

```bash
mkdir ~/inbox
# copy PDFs there, then:
biblio pool ingest ~/inbox --move
```

Each PDF goes through:

1. GROBID header extraction → DOI + title
2. OpenAlex enrichment (if DOI found)
3. Copy to pool at `bib/articles/<citekey>/<citekey>.pdf`
4. BibTeX entry appended to `bib/srcbib/inbox.bib`

`--move` removes PDFs from the inbox after successful ingestion.

---

## Step 5 — One-click drop from the browser (optional)

Start the drop server on an HPC login node (or locally with port-forwarding):

```bash
biblio pool serve --inbox ~/inbox
```

Then print the bookmarklet:

```bash
biblio pool bookmarklet
```

Drag the printed `javascript:` URI to your browser bookmarks bar. On any paper
page that exposes a `citation_doi` meta tag, clicking the bookmark sends the
DOI to the running server, which downloads the PDF into your inbox.

Run `biblio pool watch ~/inbox --move` in a screen session to ingest
continuously:

```bash
biblio pool watch ~/inbox --move --screen
```

---

## What's stored where

| Location | What lives there |
|---|---|
| `/storage2/arash/bib/bib/articles/` | Your personal PDFs (real files) |
| `/storage/share/sirocampus/bib/bib/articles/` | Shared lab PDFs (read-only) |
| `<project>/bib/articles/` | Symlinks only — no real files |
| `~/.config/biblio/config.yml` | Your user-level defaults |
| `<project>/bib/config/biblio.yml` | Project overrides (wins over user config) |

---

## Next steps

- [Use a Shared PDF Pool](../how-to/pool.md) — full pool command reference
- [Set Up a User Profile](../how-to/profile.md) — managing user config
- [Configuration reference](../reference/configuration.md) — all `biblio.yml` keys
