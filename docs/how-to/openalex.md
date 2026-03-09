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

## Review and add candidates

Candidates appear in the **Explore** tab of `biblio ui serve` under the
**Candidates** panel. Each candidate shows title, year, direction, and an
**Add to Bib** button for papers not yet in your corpus.

To add a single paper from the command line:

```bash
biblio add doi 10.xxxx/example
biblio add openalex W1234567890
```
