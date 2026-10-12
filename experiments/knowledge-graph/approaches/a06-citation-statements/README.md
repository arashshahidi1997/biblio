# a06: Citation statements with intent labels

**Status:** planned

## Inspiration

- Scite smart citations: citing sentence plus supporting / contrasting / mentioning
- CiTO, the citation typing ontology (SPAR)
- pandoc-ext/cito, https://github.com/pandoc-ext/cito: `[@supports:key]` in markdown
- biblio's own spec: `docs/specs/biblio/citation-context.md` in projio (status: proposed)

## Idea

From GROBID TEI, keep every in-text citation with its sentence and section,
resolve it to a local citekey, and label the intent with a CiTO subset
(supports, disputes, uses_method_in, uses_data_from, extends, mentions). This
gives typed Paper-to-Paper edges, which a claim graph can then attach to
specific claims.

Compare an LLM classifier with a small zero-shot model, since Scite's own
numbers show the contrasting class is hard (about 60% accuracy).

## Inputs

- GROBID TEI (`<ref type="bibr">` callouts, `<listBibl>`)
- `grobid/local_refs.json` and OpenAlex `referenced_works` for resolving targets

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|
| citation statement | `cites` edge | `attrs.intent`, `attrs.sentence`, `attrs.section` |
| cited claim (optional) | `supports` / `opposes` to a Claim | needs a01 claims |

## Plan

1. Context extractor over TEI for the `extended` set.
2. Hand-label about 100 statements (sample) for intent.
3. Classify with Haiku and with a zero-shot NLI model; compare with labels.
4. Score CQ05 and CQ14; also check how many local-to-local edges this adds,
   since `graph.py` currently drops local OpenAlex edges.

## Open questions

- Only 42 of 347 papers have GROBID output in the test project. Run GROBID on
  the rest before scoring at scale.

## Findings
