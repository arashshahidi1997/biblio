Now for your question about GROBID reference accuracy and OpenAlex verification:

There's no automated verification step yet. Here's the picture:

What GROBID does (and where it goes wrong):

Extracts reference metadata from PDF text via OCR/parsing — titles can be truncated, have OCR errors, or be incorrectly segmented
Our match_biblstructs_to_corpus does DOI-first then fuzzy title match against the local corpus — if GROBID extracted the wrong title, the title match may fail or worse, match the wrong paper
What already exists that could help:

openalex_client.py has search_works(query) — can search by title
extract_doi.py shows the pattern: query Crossref by title → get canonical DOI → Levenshtein verify
The verification idea — adding an OpenAlex enrichment pass:


# Pseudocode for a new function in ref_md.py
def enrich_biblstructs_via_openalex(cfg, biblstructs, bib_id_to_citekey):
    """For biblstructs not yet matched, search OpenAlex by title
    and try to match the returned canonical DOI against the local corpus."""
    unmatched = {k: v for k, v in biblstructs.items() if k not in bib_id_to_citekey}
    for xml_id, bib_data in unmatched.items():
        title = bib_data.get("title")
        if not title:
            continue
        # Search OpenAlex
        results = client.search_works(title, per_page=3)
        if not results:
            continue
        best = results[0]
        # Verify with Levenshtein similarity
        if levenshtein_ratio(normalize(title), normalize(best["display_name"])) < 0.85:
            continue  # not confident enough
        canonical_doi = best.get("doi")
        if canonical_doi and canonical_doi in doi_index:
            bib_id_to_citekey[xml_id] = doi_index[canonical_doi]
    return bib_id_to_citekey
Should I implement this? It would:

Make the biblio ref-md run pipeline call OpenAlex for unresolved references (with caching via openalex_cache)
Significantly improve match rates for title-matched cases
Be opt-in via a --verify-openalex flag
The risk: adds network calls (mitigated by caching), and OpenAlex title search can return wrong results for very short/common titles. The Levenshtein threshold (0.85–0.90) guards against false positives.

Want me to implement this enrichment step in ref_md.py? It would wire into the existing openalex_cache infrastructure for zero-cost repeat runs.