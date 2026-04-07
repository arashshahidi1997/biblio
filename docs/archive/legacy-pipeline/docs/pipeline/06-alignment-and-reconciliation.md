# Alignment and Reconciliation

Extraction tools such as Docling and GROBID operate independently and produce
non-isomorphic representations of the same document. The purpose of the
Alignment and Reconciliation stage is to merge these outputs into a single,
coherent, document-grounded representation suitable for downstream reasoning and
transparent inspection.

This stage produces the **Silver layer** of the system.

---

## The Anchoring Problem

- **Docling** produces a structural view of the document
  (sections, blocks, figures, tables).
- **GROBID** produces a bibliographic-semantic view
  (metadata, references, in-text citation markers).

To support citation-aware reasoning, the system must answer:

> “Which structured document block contains this citation, and what work does it refer to?”

This requires a robust alignment strategy between heterogeneous coordinate systems.

---

## Alignment Unit

The atomic unit of alignment is a **Citation Context**:

A citation context represents a single in-text citation occurrence and contains:
- the citation marker and local context extracted by GROBID,
- a pointer to the Docling block in which it appears,
- an optional link to a canonical cited work,
- alignment confidence and provenance.

Citation contexts are first-class objects and are preserved even if alignment fails.

---

## Alignment Strategy (Multi-Signal Join)

Alignment is performed using a **multi-signal heuristic join**. Signals are used opportunistically;
absence of any signal must not cause pipeline failure.

Available signals include:

1. **Textual Matching (Primary)**
   - Normalize citation context text and Docling block text.
   - Perform windowed and fuzzy matching within candidate blocks.

2. **Structural Proximity**
   - Restrict candidate blocks to those under the same or nearest section header.
   - Use section paths as coarse anchors.

3. **Spatial Hints (Optional)**
   - Use page numbers or bounding boxes if both tools expose them reliably.
   - This signal is advisory only.

The output of alignment is a ranked candidate list; the top candidate is selected
and assigned a confidence score.

---

## Reconciliation and Overrides (Human-in-the-Loop)

Automated alignment is expected to fail in a minority of cases. To ensure
research-grade rigor, the system supports **patch-based overrides**.

### Override Artifacts

Overrides are stored as version-controlled patch files:

```

overrides/
alignment.yaml
identities.yaml

```

Overrides are applied deterministically during the build.

### Supported Override Actions

- **Force-link**
  - Manually bind a citation context to a specific Docling block.
- **Suppress**
  - Mark a citation context or reference as invalid.
- **Relink**
  - Correct the canonical identity of a cited work.

### Precedence Rule

```

manual override > automated alignment > unresolved

```

Manual overrides always take priority and are never overwritten.

---

## Silver-Layer Output

The reconciled output includes:

- Full Docling document tree.
- GROBID bibliographic metadata.
- Citation contexts decorated onto Docling blocks.
- Confidence scores and provenance for every linkage.

Raw tool outputs are preserved unchanged; the Silver layer is a derived view.

---

## Quality Assurance Outputs

This stage MUST emit:

- `alignment_report.json`
  - counts of aligned / unaligned citation contexts
  - confidence score distributions
- a review queue of low-confidence or unresolved contexts

These artifacts feed the global build manifest.

---

## Invariants

- **No data loss:** raw Docling and GROBID outputs are immutable.
- **Traceability:** every reconciled object points to its tool-specific source IDs.
- **Determinism:** given identical inputs, configs, and overrides, alignment is reproducible.
