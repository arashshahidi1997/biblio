# Core Data Schemas

This document defines minimal schemas used across the pipeline to keep the system’s mental model computable, grounded, and inspectable.

## Work record

- work_id
- title
- year
- authors
- doi (optional)
- openalex_id (optional)
- pdf_path
- source

## Reference record

- ref_local_id
- raw_string
- parsed_metadata
- linked_work_id (optional)
- confidence

## Citation context

- citing_work_id
- cited_ref_local_id
- cited_work_id (optional)
- section_anchor
- context_text
- confidence

Schemas are intentionally minimal and extensible.

## Identifiers and Provenance Keys

The system distinguishes between intellectual works, concrete artifacts,
and tool-specific derivations.

### Work ID
- Represents the intellectual entity.
- Stable across versions.
- Backed by DOI and/or OpenAlex ID when available.

### Artifact ID
- Represents a concrete file instance (e.g., a specific PDF).
- Derived from content hash or persistent storage identity.
- Changes if the file changes.

### Extraction ID
- Represents a tool-derived artifact.
- Defined by:
  - tool name
  - tool version
  - configuration hash
  - artifact_id

All downstream data products must reference all applicable identifiers.
