# biblio example: PDF fetch cascade demo

This example demonstrates biblio's PDF fetching through multiple sources,
including institutional access via EZProxy.

## Papers

| Citekey | Journal | Paywall? | Expected source |
|---------|---------|----------|----------------|
| `silver2021` | Artificial Intelligence | Open-access | `openalex` or `unpaywall` |
| `buzsaki2014` | Nature Reviews Neuroscience | Paywalled | `ezproxy` (with auth) or `no_url` |
| `okeefe1971` | Brain Research | Paywalled | `ezproxy` (with auth) or `no_url` |
| `zipf1949` | Book (Addison-Wesley, 1949) | No DOI | `no_url` |

## Quick start

```bash
cd packages/biblio/example

# 1. Merge srcbib → main.bib
biblio bibtex merge

# 2. Resolve metadata via OpenAlex (needed for OA PDF URLs)
biblio openalex resolve

# 3. Fetch PDFs — without institutional access
biblio bibtex fetch-pdfs-oa
```

Expected output without EZProxy:

```
silver2021   → openalex  (open-access PDF downloaded)
buzsaki2014  → no_url    (paywalled, no open-access version)
okeefe1971   → no_url    (paywalled, 1971 Elsevier)
zipf1949     → no_url    (no DOI, cannot resolve)
```

## With institutional access (LMU Munich)

```bash
# One-time setup
biblio profile use lmu-munich
biblio auth ezproxy            # opens browser → paste cookies

# Now fetch again
biblio bibtex fetch-pdfs-oa
```

Expected output with EZProxy:

```
silver2021   → skipped   (already exists)
buzsaki2014  → ezproxy   (downloaded through LMU proxy)
okeefe1971   → ezproxy   (downloaded through LMU proxy)
zipf1949     → no_url    (no DOI)
```

## Verify

```bash
ls bib/articles/*/
# bib/articles/silver2021/silver2021.pdf         (always)
# bib/articles/buzsaki2014/buzsaki2014.pdf       (with EZProxy)
# bib/articles/okeefe1971/okeefe1971.pdf         (with EZProxy)
```

## Full pipeline

After PDFs are fetched, run the full extraction pipeline:

```bash
biblio docling batch          # extract text from PDFs
biblio grobid run --all       # extract references
biblio rag sync               # register for search indexing
```

## Via MCP tools

```python
biblio_merge()
biblio_pdf_fetch_oa()                              # all papers
biblio_pdf_fetch_oa(citekeys=["buzsaki2014"])       # just the paywalled one
biblio_docling_batch()
```
