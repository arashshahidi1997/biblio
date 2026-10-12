# aNN: <approach name>

**Status:** planned | running | scored | dropped

## Inspiration

Tool or paper, with links.

## Idea

Two or three sentences: what this approach does and why it might fit.

## Inputs

Which derivatives it reads from `$KG_CORPUS_ROOT` (docling markdown, GROBID TEI,
OpenAlex `resolved.jsonl`, ...).

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|

## Run

```bash
pixi run -e <feature> python approaches/aNN-<name>/run.py --set core
```

Outputs go to `runs/aNN-<name>/<run-id>/` (see `schema/interchange.md`).

## Plan

1. ...

## Open questions

- ...

## Findings

<!-- Dated notes. Scores go in eval/scoreboard.md. -->
