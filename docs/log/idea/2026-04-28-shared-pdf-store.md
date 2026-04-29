# Shared PDF store across projects

Date: 2026-04-28

## Context

Today, when a paper is relevant to multiple projects (e.g. a methods paper used by both `cogpy` and `pixecog`), the options biblio supports are:

1. **Copy mode in each project** — every project owns a full PDF copy under its own `bib/articles/<citekey>/<citekey>.pdf`. Bytes are duplicated; updates don't propagate.
2. **Symlink mode with `dest_root` override** — one project is designated as canonical and others' `bib/articles` are configured to symlink into it. Works, but couples mirror projects to the canonical project's filesystem path.

The asymmetry between "main" and "mirror" is real but the *project layer* shouldn't have to know about it — at the file level, every consumer just wants "give me a path that points at the bytes for `<citekey>`".

## Proposal: a content-addressed shared store

Introduce a project-external canonical store, e.g.:

```
/storage2/arash/bib/store/
  └── <citekey>/
        ├── <citekey>.pdf            # the canonical bytes
        └── meta.json                # sha256, source bib, ingest timestamp, originator project
```

Each project's `bib/articles/<citekey>/<citekey>.pdf` becomes **always a symlink** into the store, regardless of whether the project is "main" or "mirror" for that paper. The "main" / "mirror" distinction collapses into a single notion: "a project that has the citekey in its srcbib".

Configuration shape:

```yaml
pdf_fetch:
  store_root: "/storage2/arash/bib/store"   # global; or null for legacy in-project mode
  store_pattern: "{citekey}/{citekey}.pdf"
  mode: "symlink"                           # implicit when store_root is set
```

Behaviour change in `biblio bibtex fetch`:

- If `store_root` is set: resolve source PDF (from `file = {…}`, OA cascade, ezproxy, etc.), copy into store *if not already there*, then symlink from the project's `bib/articles/<citekey>/<citekey>.pdf` into the store.
- If `store_root` is unset: current behaviour.

## Why this is better than the dest_root override

| | dest_root symlink override | shared store |
|--|--|--|
| Survives canonical project moving | no — symlinks break | yes — store is global |
| Works when "main" hasn't been picked yet | no — ordering matters | yes — first ingest populates store |
| Garbage collection of orphan PDFs | manual | trivial: walk store, drop entries no project's main.bib references |
| Disk savings on many overlapping projects | 0 (one canonical + N symlinks) | same | ← tied; both win over copy mode |
| Provenance ("who first ingested?") | implicit in dest_root choice | explicit in `meta.json` |
| Cross-project diff ("which projects cite X?") | needs custom walk | one grep over `bib/main.bib` files, OR a store-side index |

The big pragmatic win is the second row: with `dest_root`, you have to designate a "main" project up front. With a shared store, ingests are commutative.

## Corollary changes worth considering

1. **`file_field_remap` for laptop→server bridging.** Better BibTeX writes absolute paths from the export machine (e.g. `/Users/arash/Zotero/storage/ABC/paper.pdf`). Today these don't resolve when `biblio bibtex fetch` runs on gamma2. A config-level remap:

   ```yaml
   bibtex:
     fetch:
       file_field_remap:
         "/Users/arash/Zotero/storage/": "/storage2/arash/zotero-mirror/"
   ```

   …would let a single rsync of `~/Zotero/storage/` to gamma2 satisfy `_resolve_source_path` without rewriting bib files.

2. **Citekey uniqueness across projects.** Once a shared store exists, citekey collisions across projects become real bugs (project A's `smith_2023_foo` is not project B's `smith_2023_foo` if they were generated independently). Two mitigations:
   - Recommend a deterministic citekey scheme in docs (Better BibTeX `[auth:lower][year][shorttitle]` already gives this).
   - Add `biblio citekeys verify --global` that scans every project's main.bib and flags collisions where the DOI differs.

3. **Adopt the generic cookies.txt model in addition to ezproxy.** `biblio auth ezproxy` is great for the EZProxy case, but a tool like `cookie-pusher` (Chrome extension → native host → scp) handles publisher cookies that aren't routed through EZProxy (e.g. JSTOR direct, society sites). A `pdf_fetch.cookies_dir: ~/.cookies/` config that biblio scans by domain when downloading would close the loop.

## Out of scope for this idea

- A web UI for the store (interesting but separate).
- Dedup by content hash rather than citekey (powerful but pulls in `bib/articles/by-hash/...` complexity).
- Cross-machine store replication (use rsync/datalad).

## Suggested next step

Spec a single config flag `pdf_fetch.store_root` and a tiny refactor of `pdf_fetch.fetch_pdfs` so the dest path is computed in two stages:

1. canonical store path (if `store_root` set, else existing behaviour)
2. project-local symlink to the canonical path

Existing copy/symlink modes remain available for users without a shared store.

## Addendum (same day): ban-risk-aware modes

This note originally framed the proposed `pdf_fetch.cookies_dir` and the
existing OA cascade as straightforward improvements. Real-world usage exposed
a constraint that should shape the API:

**Some users (myself, on the LMU network) cannot afford automated bulk publisher
fetching at all.** Even the "soft" steps in `bibtex fetch-pdfs-oa` —
OpenAlex/Unpaywall lookups — return URLs that often point at publisher landing
pages, and biblio then issues direct GETs to those URLs. From a single host on
the institutional network, this is exactly the access pattern that gets you
banned, and a re-ban after an elevated case is much harder to recover from.

What this implies for biblio's design:

1. **`bibtex fetch-pdfs-oa` should never be implicit.** Today it is reachable
   only via explicit invocation, which is correct. Any future "auto-cascade in
   pull" feature would need a per-project opt-in flag (`pdf_fetch.auto: false`
   default).
2. **Cascade tiers should be explicitly labelled by network blast-radius**, not
   just by source preference. E.g.
   ```
   sources:
     - pool          # local only, zero network
     - openalex_api  # api.openalex.org only — safe metadata service
     - unpaywall_api # api.unpaywall.org only — safe metadata service
     - publisher     # follows OA URLs into publisher domains — DANGER on
                     # institutional networks; off by default
     - ezproxy       # routes through institutional proxy — separate consent
   ```
   The current `sources` list mixes safe (api.openalex.org) and risky (any
   resolved URL going to a publisher CDN) under the same tier name.
3. **A "dry-mode" cascade** that prints would-be URLs without fetching them
   would let users sanity-check the blast radius before turning on a tier.
4. **Per-host overrides.** A `~/.config/biblio/host.yml` could set
   `pdf_fetch.allow_publisher_fetch: false` machine-wide, regardless of any
   project's per-project config — useful when running on an institutional
   host where you can't trust every project's settings.

The proposed `pdf_fetch.store_root` change is orthogonal to this and remains
the right primary refactor; just want to flag that the next layer down
(*which* fetching is safe to do automatically) is also a real design question.
