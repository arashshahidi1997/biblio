# The Problem

Modern scientific research depends on navigating a rapidly growing and increasingly complex body of literature. However, the tools we use to manage bibliography have not kept pace with how research is actually conducted today.

## What breaks in practice

Researchers face recurring, structural problems:

- PDFs are treated as opaque blobs rather than structured documents.
- Citation managers store references, but do not understand *how* papers cite each other.
- Literature discovery tools surface related papers, but cannot ground claims in specific sections, figures, or tables.
- LLM-based assistants generate fluent summaries, but lack verifiable provenance.

As a result, researchers spend substantial effort manually:
- tracing claims back to original sources,
- reconciling preprints and published versions,
- and maintaining an internal mental model of how papers relate.

## Why this is a systems problem

These failures are not due to missing features in a single tool, but due to **missing architecture**.

What is needed is infrastructure that treats:
- documents as structured objects,
- citations as first-class entities,
- and bibliography as a *computable substrate* rather than a static list.

The following pages describe such a system, designed to make the expert mental model of a field transparent and grounded in documents and citations.
