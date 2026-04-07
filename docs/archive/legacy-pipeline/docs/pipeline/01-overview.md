# Pipeline Overview

The pipeline composes specialized tools into a coherent system of infrastructure that externalizes expert mental models into computable, document-grounded artifacts.

At a high level:

```

Zotero / BibTeX
↓
Document registry
↓
Docling (document structure)
↓
GROBID (bibliography + citations)
↓
OpenAlex (canonical IDs + graph)
↓
Alignment + indexing

```

Each stage produces durable artifacts that are reused downstream.

The pipeline is **stage-oriented**:
- each stage can be re-run independently,
- outputs are cached and versioned,
- failures are localized.

Subsequent documents describe each stage in detail.
