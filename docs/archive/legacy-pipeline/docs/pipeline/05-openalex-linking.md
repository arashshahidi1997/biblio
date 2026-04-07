# OpenAlex Linking and Graph Expansion

OpenAlex provides **canonical identifiers** and a **global citation graph**, connecting document-grounded observations to a broader, inspectable map of the field.

## Responsibilities

- Resolve references to canonical works.
- Deduplicate variants.
- Expand the local corpus with related papers.

## Usage pattern

- Link GROBID-extracted references to OpenAlex works.
- Use OpenAlex IDs as global anchors.
- Construct citation, co-citation, and coupling graphs.

## Scope control

Graph expansion is governed by:
- depth limits,
- edge-weight thresholds,
- and project scope policies.

OpenAlex connects the local document-grounded corpus to the broader literature.
