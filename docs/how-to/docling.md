# Run Docling

Run Docling for every known paper:

```bash
biblio docling run --all
```

Run Docling for one citekey:

```bash
biblio docling run --key smith2020
```

Convert only the papers you name (in a shared copy, a batch without keys can
pick up another session's pending paper):

```bash
biblio docling batch --keys a_2020_X,b_2021_Y
biblio docling batch --from new-keys.txt
```

Each folder `bib/derivatives/docling/<key>/` holds `<key>.md`, `<key>.json`,
`<key>_artifacts/` (figure crops) and `_biblio.json` (provenance: source PDF
hash, docling command, docling version, whether page images were kept).

## The pinned docling environment

biblio's `pixi.toml` has a `docling` environment with docling **2.64.1**
(docling-core 2.55.0, docling-ibm-models 3.10.3, docling-parse 4.7.2) and CPU
torch, for linux-64 and osx-arm64. Every project on a host can use the same
one, so pools and new conversions come from one version. Install it once
in the biblio checkout:

```bash
pixi install -e docling        # in packages/biblio
```

Then point a project's `.projio/biblio/biblio.yml` at it (on gamma2):

```yaml
docling:
  cmd: ["pixi", "run", "--manifest-path", "/storage2/arash/projects/projio/packages/biblio/pixi.toml",
        "-e", "docling", "docling"]
```

`pixi` must be on PATH (or give its full path). The command runs from the
paper's output folder, so the manifest path has to be absolute.

**Pools.** The shared pools (sirocampus, pixecog) were converted with the conda
env `rag`, which has had docling 2.64.1 since 2025-12-12 (all pool outputs are
newer; DoclingDocument schema 1.8.0). The pinned versions are the same, down
to the companion packages; only the PyTorch build differs (CPU instead of
CUDA 12.8, which gamma2 cannot use anyway). Checked on 2026-10-28 with a
sirocampus paper (`davis_2011_DeltaWave`): the new `.md` is byte-identical to
the pool's, the JSON has the same texts and page sizes. The first call takes
about a minute while pixi and docling start; a 3-page paper converts in 40 s.
Folders converted from now on record the version in `_biblio.json`
(`docling.version`); older folders have no version field.

## Page images

Docling embeds a rendering of every page in `<key>.json` as a base64 data URI
(`pages[*].image`), even with `image_export_mode: referenced`: about 1 MB a
page, 20 MB for a 16-page paper whose text is 0.4 MB. biblio drops them after
each conversion. To keep them, set `docling.page_images: true` (see
[Configuration](../reference/configuration.md#docling)).

For JSON converted before this, slim it in place without re-running docling:

```bash
biblio docling slim --all --dry-run      # what would be saved; writes nothing
biblio docling slim --all                # the project's docling folders
biblio docling slim --key a_2020_X       # one paper (repeat --key for more)
biblio docling slim --dir /path/to/pool/derivatives/docling   # any docling root, e.g. a pool's
```

The command reports bytes before and after for each file and in total. The new
file is written beside the old one and renamed over it, so in a DataLad dataset
a locked annex file becomes a regular file; `datalad save` annexes it again
(the old content stays in the annex history until dropped). A file that is
annexed without content is skipped with a hint to `datalad get` it.

## What biblio reads from the JSON

Safe to drop anything not listed here. biblio reads:

| Part | Used for |
|------|----------|
| `pages` keys and `pages[*].size` | page count check and bbox conversion (`biblio figures`) |
| `texts[*]`: `text`, `prov` (`page_no`, `bbox`), `self_ref` | figure captions, caption positions, graphical-abstract pages |
| `pictures[*]`: `prov`, `captions` | which figures exist, where, and their captions |
| `pictures[*].image.uri` | matching crops in `<key>_artifacts/` to captions (UI, slides) |

The full text everyone reads (`biblio fulltext`, digests, wiki quote checks,
RAG) comes from `<key>.md`, not the JSON. `pages[*].image` is never read.
