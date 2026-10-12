# a05: Generic text-to-KG extractor

**Status:** planned

## Inspiration

- KGGen (arXiv 2502.09956), https://github.com/stair-lab/kg-gen: extraction plus entity clustering
- KARMA (arXiv 2502.06472): multi-agent extraction, for reference

## Idea

KGGen extracts subject-relation-object triples and then clusters equivalent
entities and relations. Its strength should be cross-paper merging, which is
the weak point of per-paper extraction. Compare its merge quality with the
corpus pass in a01.

## Inputs

- docling markdown, by section

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|
| entity | Concept by default | reviewer assigns types on a sample |
| relation | informs | relation text in `attrs.native_type` |
| entity cluster | merged node | `sources` from all members |

## Plan

1. Run on `core`, then `extended`.
2. Export to interchange; sample 20 merged clusters and judge duplicates and
   false merges.
3. Compare with a01 merging on the same papers.

## Open questions

- Untyped triples score poorly on most CQs. Is KGGen worth it only as the
  merging step on top of a01?

## Findings
