# Resolve OpenAlex Metadata

Install the OpenAlex extra:

```bash
pip install "biblio-tools[openalex]"
```

## Resolve metadata for all srcbib entries

```bash
biblio openalex resolve
```

This writes resolved metadata to `bib/derivatives/openalex/resolved.jsonl`.

## Expand the reference graph

After resolving, discover papers that cite or are referenced by your corpus:

```bash
biblio graph expand
```

This writes candidates to `bib/derivatives/openalex/graph_candidates.json`.

Use `--direction` to control what is fetched:

```bash
biblio graph expand --direction references   # papers your corpus cites
biblio graph expand --direction citing       # papers that cite your corpus
biblio graph expand --direction both         # default
```

`graph_candidates.json` keeps the candidates of every seed expanded so far.
To work on one paper, expand only that seed (`--fresh` replaces the file
instead of adding to it):

```bash
biblio graph expand --keys ye_2026_BrainWide --direction references
```

## Review and add candidates

Candidates appear in the **Explore** tab of `biblio ui serve` under the
**Candidates** panel. Each candidate shows title, year, direction, and an
**Add to Bib** button for papers not yet in your corpus.

To add candidates in bulk, filter them and ingest by DOI. `--seed` keeps only
the candidates found from those seed papers; without it, every seed's
candidates in the file are eligible and the command warns when there are
several:

```bash
biblio graph promote --seed ye_2026_BrainWide --tag ye-refs --dry-run
biblio graph promote --seed ye_2026_BrainWide --tag ye-refs --min-citations 10
```

For the exact reference list of one paper, GROBID on its PDF is more
reliable than OpenAlex: `biblio refs triage KEY`.

To add a single paper from the command line:

```bash
biblio add doi 10.xxxx/example
biblio add openalex W1234567890
```
