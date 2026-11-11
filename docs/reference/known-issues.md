# Known issues

Open problems in the stable base, until they are fixed. Checked on 0.4.0
(2026-11-11).

## Citekeys

- **Name particles depend on name order.** "van der Meer, Matthijs" gives
  `vandermeer_...`, but "Matthijs van der Meer" gives `meer_...`, and
  "de la Prida, Liset" gives `prida_...`. The same author can get two keys
  across sources. Workaround: `biblio citekey alias CANONICAL ALIAS` makes
  both keys resolve to one paper; rename by hand in `bib/srcbib/` if you
  prefer one key.
- **Family name first, without a comma** (common for Chinese, Korean,
  Vietnamese and Hungarian names written that way) takes the last word as the
  family name.

## Metadata

- **Edited volumes** have editors, not authors; biblio reads authors only, so
  the entry has no author and the key starts with `anon_`. Workaround: add the
  editors as `editor = {...}` and rename the key.
- Fixed since the 2026-11-03 review: arXiv DOIs resolve to the right work
  (metadata comes from the DOI registry first), book authors are kept, entry
  types follow the work's type (`@book`, `@incollection`, `@misc` for
  preprints), and letters like `ø` transliterate (`ostergaard`).

## Full text

- **A PDF and a text from different versions of a paper** (preprint and
  published) give figure crops that do not match their captions. `biblio
  figures run` refuses when the page counts differ (0.3.6); convert the PDF you
  hold again with `biblio docling run --key KEY --force`.
- **Reprints and books** can hold neighbouring articles in one text. `biblio
  fulltext KEY --span` shows where the article sits; `quotes check` warns when
  a quote lies outside it.
- docling writes `<`, `>` and `&` as HTML entities and garbles some symbols
  (µ as `l`); quotes are checked against both the raw and a cleaned text.

## Reporting

Issues: <https://github.com/arashshahidi1997/biblio/issues>.
