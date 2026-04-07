# Phases and Milestones

This plan prioritizes early delivery of a trustworthy “Silver layer” and a minimal “Gold layer,”
with strong observability (manifest) and human-in-the-loop correction (overrides).

The phases are designed to be **deterministic, resumable, and failure-tolerant**.

---

## Phase 0 — Bootstrap and Contracts
**Goal:** Freeze contracts so implementation is guided by stable interfaces.

### Deliverables
- `mkdocs.yml` builds successfully.
- Design, pipeline, reference, and implementation docs finalized.
- Schema definitions validated (JSON/YAML).

### Tests / Gates
- Documentation build test: `mkdocs build` passes.
- Schema validation passes.

---

## Phase 0.5 — Tiny Corpus Fixture (Early Vertical Slice)
**Goal:** Enable parallel development of alignment, vectorization, and retrieval without waiting for full extraction hardening.

### Steps
1. Select 3–5 representative PDFs.
2. Produce pinned raw extraction outputs (Docling + GROBID).
3. Manually curate or lightly patch a minimal Silver output.

### Deliverables
- Frozen tiny-corpus directory:
  - raw extraction outputs
  - reconciled Silver artifacts
- Used as a regression and demo fixture.

### Tests / Gates
- Rebuild Silver and Gold from frozen raw assets.
- Demo walkthrough runs end-to-end on this corpus.

---

## Phase 1 — Bronze Layer: Corpus Registry + PDF Integrity
**Goal:** Establish immutable inputs and a reproducible registry.

### Steps
1. Ingest Zotero/BibTeX export into an internal registry.
2. Assign stable `work_id`.
3. Compute `artifact_id` from PDF content hash.
4. Write initial manifest entries.

### Deliverables
- Bronze store: PDFs + hashes
- Work ↔ artifact registry
- Manifest ledger with `ingestion=success|failed`

### Tests / Gates
- Deterministic IDs across repeated ingestion.
- Missing PDFs recorded with explicit failure reason.
- Manifest completeness: every work has a ledger record.

---

## Phase 2 — Raw Extraction (Docling / GROBID)
**Goal:** Produce immutable raw tool outputs, avoiding unnecessary re-execution.

### Determinism model
Extraction outputs are keyed by:
```

(artifact_id, tool_name, tool_version, config_hash)

```

If an output already exists for this key, extraction is **skipped**, not re-run.

### Steps
1. Check for existing extraction via content-addressable key.
2. If missing, run tool and store outputs immutably.
3. Record extraction metadata in manifest.

### Deliverables
- `raw/docling/<extraction_id>/...`
- `raw/grobid/<extraction_id>/...`
- Manifest updates for `docling` and `grobid`

### Tests / Gates
- CAS hit/miss behavior verified.
- Semantic validation (not byte equality):
  - Docling: section tree non-empty, text coverage > threshold.
  - GROBID: reference list parseable, citation contexts extracted.
- Failures recorded with error class; pipeline continues for other artifacts.

---

## Phase 3 — Silver Layer: Alignment + Reconciliation
**Goal:** Produce reconciled, inspectable Silver artifacts as a re-materializable view.

### Steps
1. Load raw Docling + GROBID outputs.
2. Perform multi-signal alignment to generate citation contexts.
3. Apply overrides (alignment, identity, ignore).
4. Emit reconciled Silver artifacts.

### Deliverables
- `silver/<extraction_id>/reconciled_document.json`
- `silver/<extraction_id>/citation_contexts.jsonl`
- Alignment confidence report + unresolved queue

### Tests / Gates
- Alignment coverage metrics computed.
- Overrides deterministically applied.
- Silver artifacts reference raw tool IDs and anchors.
- Silver schema version recorded.

---

## Phase 4 — Canonical Linking & Local Citation Graph
**Goal:** Link references to canonical IDs with reproducibility.

### Determinism model
All OpenAlex API responses are cached as immutable artifacts.
Linking operates only on cached responses in deterministic runs.

### Steps
1. Resolve works/references via OpenAlex.
2. Cache full API responses.
3. Build project-scoped citation graph.
4. Record linking confidence and unresolved references.

### Deliverables
- `openalex_cache/<id>.json`
- Citation edge tables
- Manifest updates for `linking`

### Tests / Gates
- Cached responses reused across runs.
- Graph integrity checks (no dangling edges).
- Stable outputs given identical cache + config.

---

## Phase 5 — Gold Layer: Vectorization & Indexing
**Goal:** Build grounded, queryable indices.

### Steps
1. Generate structure-aware chunks from Silver.
2. Embed chunks with context metadata.
3. Build vector and keyword indices.

### Deliverables
- Chunk store
- Vector index
- Index metadata recorded in manifest

### Tests / Gates
- Grounding invariant: every chunk maps to a Silver block.
- No index entries without chunk records.
- Regression queries return anchored sources.

---

## Phase 6 — End-to-End Hardening & Demo
**Goal:** Demonstrate stability, observability, and recovery.

### Steps
1. One-command run on small corpus.
2. Generate health and coverage reports.
3. Validate partial rebuild behavior.

### Tests / Gates
- Rebuild Gold from Silver only.
- Single-artifact failure does not halt pipeline.
- Validation gates enforced before indexing.
