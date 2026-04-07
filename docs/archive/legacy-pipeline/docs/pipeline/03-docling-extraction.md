# Docling: Document Restructuring

Docling is responsible for **layout-preserving document restructuring**, making the document’s structure explicit so downstream reasoning stays transparent and grounded.

## Responsibilities

- Detect section hierarchy.
- Extract figures and captions.
- Identify tables.
- Produce stable anchors for text blocks.

## What Docling is *not* responsible for

- Bibliographic normalization.
- Reference parsing.
- Citation resolution.

## Outputs

- Structured document representation.
- Markdown with section boundaries.
- Image assets for figures.

Docling provides the **structural backbone** for all downstream reasoning.
