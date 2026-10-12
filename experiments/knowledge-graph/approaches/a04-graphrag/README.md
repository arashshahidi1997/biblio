# a04: Generic entity graph with community summaries

**Status:** planned

## Inspiration

- Microsoft GraphRAG, https://github.com/microsoft/graphrag: entities, communities, hierarchical summaries
- LightRAG, https://github.com/HKUDS/LightRAG: lighter variant with dual-level retrieval

## Idea

Run an off-the-shelf graph builder on the docling markdown with minimal
configuration. It extracts entities and relations, groups them into
communities and writes summaries per community level. This tests whether
generic tooling gives useful structure and multi-level summaries without a
domain schema, and what it costs.

Both tools can take custom entity types, so try two settings: default types,
and the reference node types.

## Inputs

- docling markdown

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|
| entity (by entity type) | by type, else Concept | keep `attrs.native_type` |
| relationship | informs | keep description in `attrs` |
| community report | Topic | level from community level |
| text unit | source | quote = text unit excerpt, often too long to verify |

## Plan

1. GraphRAG with default prompts on `core`; record tokens and time.
2. GraphRAG with reference entity types.
3. LightRAG with the same two settings.
4. Export parquet / graph files to interchange; score.

## Open questions

- GraphRAG cost on 38 papers with a Claude backend: check its LLM provider
  support before running (it targets OpenAI-compatible APIs).

## Findings
