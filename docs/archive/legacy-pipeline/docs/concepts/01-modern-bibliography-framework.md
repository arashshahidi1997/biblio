# A Modern Bibliography Framework

Traditional bibliography tools treat papers as static records.
Modern research requires treating them as **structured, relational, and computable objects** so that an expert’s mental model of a field can be externalized into an inspectable, document-grounded system.

This system adopts a layered model:

```

Discovery → Identity → Metadata → Documents → Structure
→ Citation Graph → Semantics → Retrieval → Writing

```

Each layer answers a distinct question.

## Discovery
What papers exist that may be relevant?

## Identity
Are two records the same work?
Are they different versions of the same intellectual contribution?

## Metadata
What are the authoritative bibliographic attributes of this work?

## Documents
Where is the concrete artifact (PDF)?
Which version is being analyzed?

## Structure
How is the document internally organized?
Where are sections, figures, and tables?

## Citation graph
How does this work relate to others through citations?

## Semantics
What claims, methods, or evidence does the work contribute?

## Retrieval
How can this corpus be queried reliably and efficiently?

## Writing
How does this system support human authorship and citation?

---

### Key principle: loose coupling
Each layer can evolve independently, as long as contracts between layers remain stable.
This allows the system to improve incrementally without architectural rewrites.
