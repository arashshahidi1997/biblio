---
type: readme
---

# Legacy Pipeline Archive

This directory preserves the old standalone bibliography project and its
pipeline state.

Archived here:

- standalone project files such as `Snakefile`, `pyproject.toml`, and test
  scaffolding
- legacy implementation code formerly under `bib/src/`
- legacy documentation formerly under `bib/docs/`
- generated pipeline state such as `data/`, `manifest*.jsonl`, `reports/`,
  `logs/`, and `overrides/`

What was promoted into the active `labpy` toolchain:

- the OpenAlex graph-expansion idea from the legacy pipeline is now exposed as
  `biblio graph expand` via
  `code/labpy/src/sutil/biblio/graph.py`

Everything else here is retained as historical reference, not as supported
runtime code.
