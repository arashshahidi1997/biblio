# Zotero Ingestion

Zotero serves as the primary **human-facing corpus manager**, anchoring the system’s computable bibliography in curated, inspectable scope decisions.

## Responsibilities

- Manual curation of relevant papers.
- Attachment of PDFs.
- Export of structured metadata.

## Ingestion strategy

- Use Better BibTeX to export a stable BibTeX file.
- Treat the BibTeX as the authoritative project registry.
- Assign internal `work_id`s on import.

## Outputs

- Registry of works in scope.
- Mapping from Zotero keys to internal IDs.
- Paths to associated PDF files.

Zotero remains the place where humans curate scope;
the pipeline treats it as read-only input.
