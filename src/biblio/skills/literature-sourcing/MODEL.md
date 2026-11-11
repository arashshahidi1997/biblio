# What literature-sourcing works with

Paper → Text → **Claims** → Check → Answer or Digest

| Thing | What it is | Fields |
|---|---|---|
| **Paper** | the work asked about | citekey, title, DOI, version held (preprint, accepted, published) |
| **Text** | the converted full text and figures; the only thing quoted from | `<key>.md` path, figure PNGs |
| **Claim** | one statement the paper supports: the unit of every answer | statement; level; quote(s); location; conditions |
| **Check** | `biblio quotes check`'s verdict on each quote | exact, approximate, changed, missing |
| **Answer** | a question answered from one or more papers | the question; the claims; gaps ("not in the text held") |
| **Digest** | a fixed set of claims for one paper | question; setup; main findings; limits the authors state; what it doesn't show |

## Claim fields

- **Statement:** one sentence in your words.
- **Level:**
  - **measured:** a value or observation the paper reports directly;
  - **derived:** computed from measurements (a statistic, a model fit, a decoding result);
  - **interpreted:** what the authors conclude it means.
- **Quote(s):** copied exactly from the text, in straight double quotes, one line each.
- **Location:** a section, or a figure and panel; add the line (`L<n>`) that
  `biblio fulltext --grep` printed when you have it.
- **Conditions:** species and population, preparation, state, recording or
  analysis method, n. Only those the text states; "not stated" otherwise. Any
  number among them must appear in one of the claim's quotes.

Write a claim like this:

    - **<level>** — <statement> (<species>, <preparation>, <state>, <method>, n = <n as stated>). "<exact words from the text>" (<section, or Fig. and panel>)

The terms match biblio's `digest claims` (claim, evidence, caveats, quote) and
lit-studio's claims digest and paper breakdown, so a page made from one reads
like the others.

## Digest

About one page of claims for one paper, built and checked like an answer:

- **Question:** what the paper asks.
- **Setup:** the conditions shared by its claims (species, preparation, methods), each with a quote.
- **Main findings:** claims, each with its level, quote and figure.
- **Limits the authors state:** quoted.
- **What it doesn't show:** gaps a reader might assume are covered.
