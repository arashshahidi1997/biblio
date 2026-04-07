# Goals and Non-Goals

This document defines the intent and scope of the system as infrastructure for transparent, document-grounded scientific reasoning.

## Goals

### 1. Project-scoped authority
The bibliography defines the *authoritative literature perimeter* for a specific research project.
Everything the system produces is constrained to this scope unless explicitly expanded, preserving a computable, inspectable mental model of the field as understood by project experts.

### 2. Document-grounded truth
All extracted information must be traceable to:
- a specific paper,
- a specific section, figure, or table,
- and, where possible, a concrete text span.

Ungrounded assertions are considered failures.

### 3. Bibliographic correctness
Each work should be associated with canonical identifiers (DOI, OpenAlex ID) when available.
Multiple versions (preprint, journal) must be linked and reconciled.

### 4. Citation-aware reasoning
Citations are treated as first-class objects that keep reasoning grounded and auditable:
- where they occur,
- which paper they refer to,
- and why they are used (method, background, comparison, etc.).

### 5. RAG readiness
The system must support retrieval-augmented generation using:
- stable chunks,
- explicit provenance,
- and auditable sources.

### 6. Reproducibility
Pipeline stages are deterministic, cached, and versioned.
Rebuilding the system with the same inputs should yield the same artifacts.

---

## Non-goals

- Replacing global scholarly databases (OpenAlex, Semantic Scholar).
- Perfect extraction for all PDFs or publishers.
- Fully autonomous literature review writing without human oversight.
- Acting as a general-purpose citation manager for unrelated projects.

The system optimizes for **research rigor**, not convenience alone.
