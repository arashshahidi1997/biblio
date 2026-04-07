# Vectorization and Indexing

This stage transforms the reconciled Silver layer into a **Gold layer**
optimized for retrieval, reasoning, and analysis, making transparent, document-grounded responses scalable.

The Gold layer is fully regenerable from Silver.

---

## Chunking Strategy

The system uses **structure-aware chunking**, not fixed-length segmentation.

### Atomic Unit
- A single Docling block (paragraph, list item, table row, figure caption).

### Context Enrichment
Each chunk is enriched with:
- its full structural breadcrumb path
  (e.g., `Title > Section 2 > Subsection 2.1`),
- citation metadata if citations occur within the block.

### Text vs Context Separation

Chunks are represented as:
- `chunk.text` — grounded document text only
- `chunk.context` — structural breadcrumbs and citation metadata

Embedding policies may include:
- text-only
- text + context

The chosen policy must be explicit and recorded.

---

## Embedding Strategy

- Embeddings are generated from chunk representations.
- The embedding model is **configurable** and **not hard-coded** in the spec.

For each build, the following must be recorded in the run manifest:
- model identifier
- model version
- embedding dimensionality
- normalization strategy

---

## Indexable Views

The system may maintain multiple logical indices, including:

- **Section blocks**
- **Citation contexts**
- **Figure captions**
- **Tables**
- **Claims** (if semantic extraction is enabled)

Indices may be implemented as separate namespaces or distinct stores,
but must remain logically separable for interpretability.

---

## Retrieval Axes

Queries may operate across multiple axes:

1. **Semantic**
   - “What papers discuss X?”
2. **Structural**
   - “Find tables reporting Y.”
3. **Relational**
   - “Find claims from papers citing Z.”

Hybrid retrieval (vector + graph expansion) is encouraged but not mandated.

---

## Grounding and Identity Invariants

Every retrieved chunk MUST return:
- `work_id` — the intellectual entity
- `artifact_id` — the concrete document instance
- `extraction_id` — the tool-versioned derivation
- `block_id` — the precise structural anchor

The system must never return ungrounded text.

---

## Version Consistency

If an artifact or extraction changes:
- all dependent embeddings and indices must be regenerated
- stale vectors must not be reused

---

## Invariants

- **Grounding:** no chunk exists without a valid anchor.
- **Reproducibility:** Gold is fully regenerable from Silver.
- **Transparency:** retrieval results are explainable in terms of structure and provenance.
