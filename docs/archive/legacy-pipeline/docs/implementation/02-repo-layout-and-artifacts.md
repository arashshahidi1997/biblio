# Repo Layout and Artifacts

This document defines the on-disk layout for Bronze, Raw, Silver, and Gold artifacts under `data/01_bronze` through `data/04_gold`.

---

## Bronze (immutable inputs)
- PDFs
- Zotero/BibTeX snapshots
- Artifact hashes and IDs

---

## Raw (immutable extraction outputs)
Raw tool outputs are stored immutably and never modified.

````

data/02_raw/
docling/<artifact_id>*<tool_version>*<config_hash>/
grobid/<artifact_id>*<tool_version>*<config_hash>/

```

These outputs are the source for re-materializing Silver artifacts.

---

## Silver (reconciled view)
Silver artifacts are **derived views** produced from raw outputs and overrides.

- Re-materializable without re-running extraction
- Schema-versioned
- Fully traceable to raw tool outputs

---

## Gold (serving layer)
- Chunk stores
- Vector indices
- Citation graphs
- Derived reports

Gold artifacts are disposable and always regenerable from Silver.

---

## External metadata cache (immutable)
API responses from external services (e.g., OpenAlex) are cached:

```

data/02_raw/openalex_cache/
work/<id>.json
doi/<doi>.json

```

This ensures reproducibility and debuggability.

---

## Invariants
- Raw and Bronze artifacts are immutable.
- Silver is re-materializable from Raw + overrides.
- Gold is re-materializable from Silver.
- Every artifact is keyed by `(work_id, artifact_id, extraction_id)`.
***
