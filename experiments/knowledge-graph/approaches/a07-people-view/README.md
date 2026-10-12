# a07: People view

**Status:** scored (first pass, 2026-10-12)

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

## Run

```bash
export KG_CORPUS_ROOT=/path/to/project
python approaches/a07-people-view/run.py --set extended            # ~30 s, APIs cached after
python approaches/a07-people-view/run.py --set extended --offline  # cache only
```

Files: `people.py` (aggregate + enrich), `run.py` (interchange, stats, CQ answers),
`render.py` (`people.html`: cards, co-author network, institution timeline, table).
Optional private photos: put `<orcid>.jpg` or `<openalex-id>.jpg` in
`experiments/knowledge-graph/people/` (gitignored); they are used when no open
photo exists.

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

### 2026-10-12, run `20261012-1704-fresh` (extended, 38 papers)

| Measure | Value |
|---------|-------|
| Authorships / persons | 255 / 213 (8 without OpenAlex ID) |
| OpenAlex author profile | 202/213 (95%) |
| ORCID | 175/213 (82%) |
| Institution with ROR in corpus | 207/213 (97%), 116 institutions, 18 countries |
| Wikidata item (all matched by ORCID) | 110/213 (52%) |
| Openly licensed photo | 8/213 (4%) |
| Top-20 topic contributors with photo | **0/20** (11/20 have a Wikidata item, none with P18) |
| Doctoral advisor in Wikidata (P184) | 16/213 (8%) |
| Cost / time | $0, 29 s with empty cache, 0.3 s cached |

1. **biblio already holds the people layer.** Everything except photos and
   lineage comes from `openalex/resolved.jsonl`, which biblio writes today. No
   LLM is needed. Building this into biblio is cheap.
2. **Photos from open data do not work for this field.** The 8 photos belong
   to well-known neighbors of the topic (O'Keefe, Moser, Carandini, Häusser).
   None of the people the view is about has one. A personal view needs a
   curated source: user-supplied files (the local `people/` fallback), or lab
   pages fetched with consent. Wikidata stays useful as a first source.
3. **Wikidata advisor links show lineage**, sparsely: for example Zugaro as advisor of
   Maingret, Todorova and Girardeau. Good for an "academic tree" panel when
   present; it cannot be relied on.
4. **Last-author groups** are a usable lab proxy for small-team papers
   (Buzsáki 17 people, Battaglia 8, Prerau 7). Consortium papers distort them:
   one 39-author paper yields 741 of the 1487 co-author pairs. Network edges
   should be weighted by 1/(n-1), or such papers capped.
5. **Topic membership** is a regex over title, keywords and OpenAlex topics
   (20/38 papers on topic). Crude; replace it with concept nodes from a01 or
   with OpenAlex topic IDs.
6. **Contributions are only at paper level.** "What did this person
   contribute" (claims, methods) needs a01 output joined through authorship.
7. Not checked: whether OpenAlex splits some authors across several IDs
   globally (e.g. Anton Sirota's profile lists 56 works). Within the corpus, no
   name maps to two IDs.

Scores in `eval/scoreboard.md`: CQ11 1/2, CQ12 1/2 (provisional).
