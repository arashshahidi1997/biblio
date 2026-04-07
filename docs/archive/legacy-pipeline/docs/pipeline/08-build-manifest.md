# Build Manifest and Pipeline State

The Build Manifest is the authoritative record of pipeline state, health,
and provenance. It defines **what was processed, how, with which tools,
and why something failed or was excluded** so that the infrastructure remains transparent and auditable.

The manifest is not a log.
It is a **queryable state ledger**.

---

## Purpose

The Build Manifest exists to answer, at any point in time:

- What works are in scope?
- Which artifacts were processed successfully?
- Which pipeline stages failed, and why?
- Which tool versions and configurations were used?
- What data products are valid and safe to consume?

In a research context, this information is as important as the extracted data itself.

---

## Design Principles

- **Single source of truth** for pipeline state
- **Append-only by run**, with stable per-work records
- **Machine-readable first**, human-readable summaries derived
- **Stage-aware**, not monolithic
- **Tool-agnostic**

---

## Manifest Layers

The manifest is composed of a run record and a per-work ledger, stored as JSONL entries in a single file.

### 1. Run Manifest

Describes a single pipeline execution.

**File:**  
```

manifest.jsonl

```

**Contents:**
- run_id
- timestamp
- pipeline version
- configuration hash
- enabled stages
- tool versions (Docling, GROBID, OpenAlex client, embedding model, etc.)
- host / environment metadata (optional)

The run manifest guarantees reproducibility.

---

### 2. Work State Ledger

Tracks the state of each work across pipeline stages.

**File:**  
```

manifest.jsonl

```

One record per `(work_id, artifact_id)` pair.

**Fields:**
- work_id
- artifact_id
- source (zotero, bibtex, manual)
- current_status
- stage_status:
  - ingestion
  - docling
  - grobid
  - alignment
  - linking
  - vectorization
- failure_reason (nullable)
- last_successful_stage
- last_updated

This ledger is **the operational dashboard** of the system.

---

### 3. Derived Reports

Human-facing summaries generated from the ledger.

**Examples:**
```

reports/health.md
reports/failures.md
reports/coverage.md

```

These files are disposable; the JSONL ledger is canonical.

---

## Status Vocabulary

Stages report status using a constrained vocabulary:

- `pending`
- `success`
- `failed`
- `skipped`
- `blocked` (waiting on upstream stage)

This vocabulary is intentionally small to support automation.

---

## Failure Semantics

Failures are first-class and informative.

Each failure must include:
- stage name
- error class (e.g., `pdf_not_found`, `parser_timeout`)
- short message
- pointer to raw logs (if available)

Failures do NOT abort the entire pipeline by default.
They are isolated per work/artifact.

---

## Interaction with Overrides

Manual overrides affect *outcomes*, not *history*.

- The manifest records both:
  - the automated result
  - the post-override reconciled state
- Overrides never delete failure records; they supersede them.

This ensures auditability.

---

## Consumption Rules

Downstream stages MUST consult the manifest:

- Gold-layer products may only be built from Silver artifacts marked `success`.
- RAG queries must exclude artifacts not marked `success` at required stages.
- Reports must state coverage explicitly (e.g., “42 / 47 works indexed”).

---

## Invariants

- **Completeness:** every in-scope work has a manifest record.
- **Monotonicity:** a stage cannot silently regress from success to unknown.
- **Explainability:** exclusions are explicit, never implicit.
- **Rebuild safety:** deleting derived data does not erase manifest history.

---

## Rationale

Without an explicit Build Manifest, a bibliography pipeline degrades into
a collection of scripts whose outputs are difficult to trust.

With it, the system behaves like a **data engineering platform**:
observable, debuggable, and reproducible.
