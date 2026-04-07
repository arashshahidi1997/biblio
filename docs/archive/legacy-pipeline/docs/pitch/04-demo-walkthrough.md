# Demo Walkthrough

This walkthrough illustrates how a single paper flows through the system as its reasoning is made transparent and grounded at each stage.

## Step 1 — Ingestion

A researcher curates papers in Zotero.
The system treats this as a **wishlist**, not an execution log.

## Step 2 — Automated extraction

![Automated Extraction Flowchart](../assets/figures/fig-04-automated-extraction-flowchart.png)

- PDFs are ingested as immutable Bronze artifacts.
- Docling extracts structural blocks.
- GROBID extracts references and citation markers.

Failures are recorded, not hidden.

## Step 3 — Reconciliation

Citations are aligned to document structure.
Low-confidence matches are flagged for review.
Manual fixes are applied via patch files and survive rebuilds.

## Step 4 — Global linking

![Global Citation Graph Integration](../assets/figures/fig-06-global-citation-graph-integration.png)

Local works are linked to canonical OpenAlex identifiers.
The project corpus is embedded into the global citation graph while remaining project-scoped.

## Step 5 — Retrieval

![Hierarchical Document Chunking for RAG](../assets/figures/fig-08-hierarchical-document-chunking-for-rag.png)

Instead of naive chunking, retrieval operates on structure-aware blocks with section context.

![Context-Enriched Vectorization](../assets/figures/fig-09-context-enriched-vectorization.png)

Each chunk is enriched with citation and identity metadata prior to embedding, ensuring grounded answers.

The result is RAG that can explain *why* an answer is correct.
