# a03: Contribution templates and comparison tables

**Status:** planned

## Inspiration

- ORKG, https://orkg.org: papers split into contributions, described with templates
- ORKG templates: https://orkg.readthedocs.io/en/latest/client/templates.html
- Elicit extraction tables: one column per property, each cell linked to a sentence

## Idea

Define a template per research problem, for example "sharp-wave ripple
detection" (band, threshold, minimum duration, reference channel, species,
preparation) or "spindle-ripple coupling analysis" (window, statistic,
direction). Fill one row per paper. The output is a comparison table, which is
the view most useful for methods sections and for CQ04, CQ05 and CQ06.

This approach does not try to be the whole graph. It tests whether
problem-specific tables beat a generic schema for low-level detail.

## Inputs

- GROBID TEI methods sections
- docling markdown for quote checks

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|
| Contribution | Experiment or Method | depends on template |
| Template property | Parameter | `has_parameter` edge |
| Research problem | Topic or Question | |

## Plan

1. Write 2-3 templates as YAML (local, no ORKG account needed).
2. LLM fills each template per paper, with a quote per cell.
3. Render comparison tables (markdown) and score CQ04-CQ06.
4. Optional: check whether the `orkg` Python client can export the same
   templates, so the tables could be shared on ORKG later.

## Open questions

- Who writes templates: the user, or an agent proposing them from the corpus?

## Findings
