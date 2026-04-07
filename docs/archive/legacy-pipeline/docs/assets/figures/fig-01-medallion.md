# Figure 1: Medallion Data Architecture
**Category:** Bronze / Silver / Gold Architecture

![alt text](fig-01-medallion.png)

### Description
This diagram illustrates the multi-stage refinement process. Raw ingestion (Bronze) preserves the immutable source of truth, while the Silver layer introduces schema-alignment (joining Docling/GROBID), and Gold serves the vectorized, project-ready index.

### Documentation Mapping
- **File:** `docs/concepts/01-modern-bibliography-framework.md`
- **Rationale:** Supports the "loose coupling" principle and data provenance.

```
