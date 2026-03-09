# PDF Discovery Candidates

Date: 2026-03-09

## Context

`biblio` currently supports:

- PDF fetch from BibTeX `file` fields
- direct PDF ingestion via `biblio ingest pdfs`

It does not yet have a true PDF discovery layer for finding accessible full text from metadata such as DOI, OpenAlex IDs, or related identifiers.

## Strong Candidates

Priority order:

1. DOI landing page resolution
2. Unpaywall-style open-access lookup
3. OpenAlex open-access and metadata signals
4. arXiv resolution
5. PubMed Central / Europe PMC resolution
6. publisher page parsing as a fallback

## Rationale

- DOI resolution is the most natural first step because `biblio` already supports DOI ingestion.
- Unpaywall-style OA lookup is a strong legal and reliable source for accessible PDFs.
- OpenAlex is already a core metadata and graph backend for `biblio`, so it is a natural companion signal source.
- arXiv and PMC are high-value special cases with relatively deterministic full-text locations.
- generic publisher scraping should remain a fallback rather than the primary architecture.

## Recommended Product Shape

Possible future command:

```bash
biblio pdf discover
```

Suggested behavior:

- discover candidate PDF URLs from DOI and metadata
- record provenance and confidence
- optionally download only when explicitly requested
- keep early versions review-oriented rather than fully automatic

## Non-Goals

Avoid:

- brittle broad web scraping as the main strategy
- illegal or questionable download sources
- hiding provenance of how a PDF candidate was found

## Suggested Architecture

1. metadata and identifier normalization
2. DOI -> OpenAlex enrichment
3. DOI -> OA/full-text candidate lookup
4. domain-specific resolvers like arXiv and PMC
5. manual review or explicit download step

