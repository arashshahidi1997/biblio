# What Makes This Different

Most existing tools address only one layer of the bibliography stack.

This system is differentiated by **explicit integration across layers** to externalize the expert mental model of a field into a computable, document-grounded system.

## Document-aware extraction

![PDF to Structured Knowledge Pipeline](../assets/figures/fig-03-pdf-to-structured-knowledge-pipeline.png)

- **Docling-style extraction** recovers document structure: sections, figures, tables.
- **GROBID-style extraction** recovers bibliographic semantics: references and in-text citations.

These outputs are not used independently; they are **reconciled**.

## Alignment as a first-class concept

![Semantic Mapping Between Document Parts](../assets/figures/fig-07-semantic-mapping-between-document-parts.png)

Citations are aligned to specific document blocks via an explicit *Citation Context* record.
This enables:
- citation-aware retrieval,
- intent classification,
- and claim grounding.

Manual corrections are treated as version-controlled patches, not fragile database edits.

## Beyond flat citation lists

![Co-citation and Bibliographic Coupling Networks](../assets/figures/fig-05-co-citation-and-bibliographic-coupling-networks.png)

The system supports:
- direct citations,
- co-citation,
- bibliographic coupling,

and integrates project-scoped literature into global graphs without losing local grounding.

This is fundamentally different from tools that operate only on metadata.
