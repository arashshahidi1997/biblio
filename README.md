# biblio

Turn the papers you rely on into full text you can quote, and check every
quote against the paper.

- **Ingest:** a bibliography under stable citekeys (`author_year_TitleWords`),
  from a DOI or your Zotero library, PDFs included.
- **Extract:** full text, figures and structure with
  [docling](https://github.com/docling-project/docling) (pinned), header and
  references with [GROBID](https://github.com/kermitt2/grobid), figures at
  native resolution.
- **Read and check:** a paper's text by section, line or search
  (`biblio fulltext`), and `biblio quotes check`, which checks every quote in
  a markdown file against the papers' texts.
- **Agent skills** for Claude Code that use these commands: find or convert a
  paper, answer questions from it with claims whose quotes are checked, bring
  papers in from Zotero.

PyPI: `biblio-tools`. Import: `biblio`. CLI: `biblio`.

## Install

```bash
uv tool install "biblio-tools[zotero,docling]" --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
```

- `docling` installs the converter, pinned to docling 2.64.1 and its
  companions. The PyTorch index gives the CPU build of torch (a GPU build is
  several GB larger). On macOS the index is not needed. Leave the extra out to
  use a docling you already have (`docling.cmd` in the config).
- `zotero` adds Zotero intake (`biblio add zotero`).
- `pdftotext` and `pdfimages` (poppler) are needed for `biblio figures` and
  for checking a PDF's title: `apt install poppler-utils`, `brew install
  poppler`, or `pixi global install poppler`.
- **GROBID** runs as a server. With Docker:

  ```bash
  docker run --rm --init -p 8070:8070 grobid/grobid:0.8.2-crf
  ```

  biblio looks for it at `http://127.0.0.1:8070` (`grobid.url` in the
  config); `biblio grobid check` tests the connection.

Python 3.11 or newer. Update with `uv tool upgrade biblio-tools`.

## Quickstart, from an empty folder

```bash
mkdir my-papers && cd my-papers
biblio init                                   # bib/ and .projio/biblio/ here
biblio add doi 10.1371/journal.pcbi.1004785   # prints the citekey: collins_2016_MotorDemands
```

Put the paper's PDF at `bib/articles/<citekey>/<citekey>.pdf` (from your
Zotero library or the publisher's page; one paper at a time). With Zotero
running on the same machine, `biblio add zotero --local <DOI or title>` does
both steps.

```bash
biblio docling run --key collins_2016_MotorDemands   # text + figures, about a minute on a CPU
biblio grobid run --key collins_2016_MotorDemands    # header, references, sections
biblio figures run --key collins_2016_MotorDemands   # figures at native resolution
biblio fulltext collins_2016_MotorDemands --grep "motor"   # exact wording, by section and line
```

Write quotes in any markdown file and check them:

```bash
biblio quotes check answer.md --text collins_2016_MotorDemands
```

Every `"quoted string"` of 12 characters or more must be in the paper's text;
the command exits 1 otherwise and says which quote differs and how.

What lands where (the layout is stable; shared pools rely on it):

```
bib/articles/<key>/<key>.pdf
bib/derivatives/docling/<key>/<key>.md, <key>.json, <key>_artifacts/
bib/derivatives/grobid/<key>/header.json, references.json, <key>.tei.xml
bib/derivatives/figures/<key>/manifest.yml
.projio/biblio/biblio.yml                       # configuration
```

## Skills for Claude Code

```bash
biblio skills install --user        # into ~/.claude/skills (or omit --user: this project's .claude/skills)
biblio skills list                  # stable or beta, and what each needs
```

Or install them as a plugin, which updates with `claude plugin update`:

```bash
claude plugin marketplace add arashshahidi1997/biblio
claude plugin install biblio@biblio
```

| Skill | Status | What it does |
|---|---|---|
| `paper-text` | stable | find a paper's text in the project or a pool, or convert the user's PDF; check the title |
| `literature-sourcing` | stable | answer a question or write a claims digest; every claim with an exact, checked quote |
| `zotero-add` | stable | papers from Zotero (personal and group libraries) with their PDFs |
| `paper-scrutiny` | beta | break a paper's argument down, then a blind attack by a second agent |
| `wiki-ingest`, `wiki-synthesize`, `wiki-maintain`, `wiki-review` | beta | a project knowledge wiki whose quotes are checked |
| `biblio-batch-curate` | beta | batch intake; needs projio's MCP tools |

The skills call the CLI, so they need `biblio` on PATH. A lab can ship its
hosts, shared collection and docling install as a profile (`biblio profile
list`, `biblio profile use <name>`); the skills read it.

## Stable base and beta

The commands in `biblio --help` without a mark are the stable base: `init`,
`add`, `docling`, `grobid`, `figures`, `fulltext`, `locate`, `pool`,
`quotes`, `skills`, `profile`, and the on-disk layout above. Their interface
is kept across minor versions; a breaking change takes a major version and a
migration note. `[beta]` commands (digests, the wiki, bibliography
maintenance, `biblio mcp`) are in use but may still change; `[experimental]`
ones may change or go. See [scope](docs/explanation/scope.md).

Known issues: [docs/reference/known-issues.md](docs/reference/known-issues.md).

## MCP server (optional, beta)

```bash
uv tool install "biblio-tools[zotero,docling,mcp]" ...   # same index flags as above
claude mcp add biblio -- biblio mcp
```

A small server over the stable commands (paper lookup, full text, quote
check, add, docling and GROBID runs). The skills do not need it.

## Development

```bash
pixi run -e dev test       # the test suite
pixi run -e docs docs      # the documentation site (strict)
pixi run -e dev publish    # build, check and upload (RELEASE.md)
```

Documentation: <https://arashshahidi1997.github.io/biblio/>.
