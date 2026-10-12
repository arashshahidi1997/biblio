# Interchange format

Each approach keeps its native output, and also exports a common format so that
one evaluator can score all of them. A run folder looks like this:

```
runs/<approach>/<run-id>/
  run.yml        # what ran: approach, corpus set, model, date, cost, wall time
  nodes.jsonl    # one node per line
  edges.jsonl    # one edge per line
  native/        # the tool's own output, untouched
```

`run-id` is `YYYYMMDD-HHMM` plus an optional short tag, for example
`20261012-1430-haiku`.

## run.yml

```yaml
approach: a01-llm-schema
run_id: 20261012-1430-haiku
corpus_set: core            # core | extended | gold
model: claude-haiku-4-5     # or null for non-LLM approaches
started: 2026-10-12T14:30:00
wall_time_s: 812
cost_usd: 0.42              # null if unknown
tokens: {input: 1200000, output: 90000}
notes: ""
```

## nodes.jsonl

```json
{"id": "a01:claim:sirota2003:01",
 "type": "Claim",
 "label": "Neocortical up-states precede hippocampal sharp-wave ripples",
 "text": "Longer free-text statement, optional",
 "attrs": {},
 "source": {"citekey": "sirota_2003_CommunicationNeocortex",
            "section": "Results",
            "quote": "verbatim sentence from the paper",
            "page": null},
 "provenance": {"method": "a01-llm-schema", "model": "claude-haiku-4-5",
                "run_id": "20261012-1430-haiku", "status": "candidate"}}
```

- `id` is unique within the run. Prefix it with the approach ID.
- `type` must be a node type from `reference-schema.yml`. Approaches whose types
  differ map them in their README, and put the original type in
  `attrs.native_type`.
- `source.quote` must appear in the paper's docling markdown, allowing for
  whitespace and hyphenation differences. `common/interchange.py` checks this.
  Use `null` when the approach gives no quote.
- Nodes that span papers (Theory, Concept, Method after merging) use a list:
  `"sources": [{...}, {...}]` instead of `source`.
- Paper, Person and Institution nodes use stable IDs: `paper:<citekey>`,
  `person:<openalex A-id>`, `inst:<ror or openalex I-id>`.

## edges.jsonl

```json
{"src": "a01:evidence:sirota2003:03", "dst": "a01:claim:sirota2003:01",
 "type": "supports",
 "attrs": {"strength": "strong"},
 "source": {"citekey": "sirota_2003_CommunicationNeocortex", "quote": "..."},
 "provenance": {"method": "a01-llm-schema", "status": "candidate"}}
```

`type` must be an edge type from `reference-schema.yml`, or the native type
goes in `attrs.native_type` with `type: informs`.
