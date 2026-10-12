# a07: People view

**Status:** planned

## Inspiration

- Scholia, https://scholia.toolforge.org: author pages from Wikidata (works per year, co-authors, topics)
- OpenAlex authors and institutions (CC0), with ORCID and ROR
- Semantic Scholar author pages (homepage, affiliations; no photos)

## Idea

Build an author index from data biblio already has: `openalex/resolved.jsonl`
stores the full authorship list for every paper (OpenAlex ID, ORCID, position,
corresponding author, institutions with ROR). Aggregate it into Person and
Institution nodes, a co-author graph, and per-person topic and timeline
summaries. Add photos from Wikidata (property P18, images on Wikimedia
Commons) with license and author taken from the Commons API.

Once a01 runs, link people to what they contributed (`contributed` edges via
authorship of the paper that states a claim or introduces a method).

## Inputs

- `openalex/resolved.jsonl` (authorships)
- OpenAlex author API, cached (topics, counts by year)
- Wikidata SPARQL: ORCID (P496) to item, then P18 image
- Wikimedia Commons `imageinfo` API for license metadata

## Mapping to the reference schema

| Native type | Reference type | Notes |
|-------------|----------------|-------|
| author | Person | `person:<A-id>`, `attrs.orcid`, `attrs.photo` |
| institution | Institution | `inst:<ror>` |
| authorship | authored_by | `attrs.position`, `attrs.corresponding` |
| co-authorship | coauthor | derived, weight = shared papers |

## Plan

1. Aggregate authors from `resolved.jsonl` for `extended`; report counts and
   ORCID coverage.
2. Wikidata lookup by ORCID; report photo coverage and licenses.
3. Static HTML cards for a few people (photo, papers in corpus, co-authors,
   topics) to judge the view.
4. Score CQ11 and CQ12.

## Open questions

- Photo coverage will be low for most researchers. Is a manual
  `people/<orcid>.jpg` folder (kept out of git) acceptable as fallback?
- Which authors count as "main contributors": last author, corresponding
  author, or paper count?

## Findings
