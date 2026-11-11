# Quickstart

From an empty folder to a paper's full text, figures and checked quotes, then
the same through Claude Code. Every command here is part of the stable base.

## 1. Install

```bash
uv tool install "biblio-tools[zotero,docling]" --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
```

- The `docling` extra pins docling 2.64.1 and its companions, the version the
  shared pools were converted with; the PyTorch index gives the CPU build of
  torch. Without the extra, point `docling.cmd` in the config at a docling you
  have.
- poppler (`pdftotext`, `pdfimages`) for figures and title checks:
  `apt install poppler-utils`, `brew install poppler` or `pixi global install poppler`.
- GROBID, as a server:

  ```bash
  docker run --rm --init -p 8070:8070 grobid/grobid:0.8.2-crf
  ```

  `biblio grobid check` tests the connection (default `http://127.0.0.1:8070`).

In a lab with a profile (shared pools, a docling install), apply it once:
`biblio profile list`, then `biblio profile use <name>`.

## 2. A workspace and a paper

```bash
mkdir my-papers && cd my-papers
biblio init
biblio add doi 10.1371/journal.pcbi.1004785
```

`init` sets up `bib/` and `.projio/biblio/biblio.yml` in the current folder.
`add doi` writes the entry to `bib/srcbib/imported.bib` under its citekey,
here `collins_2016_MotorDemands`.

Save the PDF from your Zotero library or the publisher's page as
`bib/articles/collins_2016_MotorDemands/collins_2016_MotorDemands.pdf`.
With Zotero running on the same machine (Zotero 7, local API enabled),
`biblio add zotero --local 10.1371/journal.pcbi.1004785` adds the entry and
copies the PDF in one step. One paper at a time: never bulk-download.

## 3. Extract

```bash
biblio docling run --key collins_2016_MotorDemands
biblio grobid run --key collins_2016_MotorDemands
biblio figures run --key collins_2016_MotorDemands
```

| Command | Output |
|---|---|
| `docling run` | `bib/derivatives/docling/<key>/<key>.md` (full text), `<key>.json`, `<key>_artifacts/` (figure crops) |
| `grobid run` | `bib/derivatives/grobid/<key>/` header, references, TEI |
| `figures run` | `bib/derivatives/figures/<key>/` figures at native resolution, `manifest.yml` |

For several papers: `biblio docling batch --keys a,b` and
`biblio grobid run --keys a,b`.

## 4. Read and quote

```bash
biblio fulltext collins_2016_MotorDemands                 # its sections
biblio fulltext collins_2016_MotorDemands --grep "motor"  # exact wording, section and line per hit
biblio fulltext collins_2016_MotorDemands --lines 45-50
```

Write an answer with quotes copied from that output, e.g. `answers/motor.md`:

```markdown
- **interpreted** — Action shapes thought (human). "reminds us that how we act constrains how we think" (Author Summary)
```

and check it:

```bash
biblio quotes check answers/motor.md --text collins_2016_MotorDemands
```

Every `"quoted string"` of 12 characters or more must be in the text; change
one word and the check names it and exits 1. `--text` also takes a path to a
`.md`, `.txt` or `.pdf`, and repeats for several papers.

## 5. With Claude Code

```bash
biblio skills install --user
```

Then ask Claude, in the workspace folder: "Do we have the Collins 2016 paper
on motor demands? What did they find?" The `paper-text` skill finds the text
(or converts a PDF you give it), and `literature-sourcing` answers with
claims whose quotes pass `biblio quotes check`, saved under `answers/`.
`biblio skills list` shows which skills are stable and which are beta.
