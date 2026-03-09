# Build The Bibliography Site

Build:

```bash
biblio site build
```

Serve:

```bash
biblio site serve
```

Clean:

```bash
biblio site clean
```

Inspect the workspace first if needed:

```bash
biblio citekeys status
```

## Launch the interactive local UI

Install the UI extra:

```bash
pip install "biblio-tools[ui]"
```

Then run:

```bash
biblio ui serve
```

The local UI can also trigger selected `biblio` actions directly, including:

- BibTeX merge
- OpenAlex resolve
- graph expansion
- site rebuild
- Docling for the currently selected paper

The UI currently has four tabs:

- `Explore`
- `Corpus`
- `Paper`
- `Actions`

If the requested port is already in use, `biblio ui serve` automatically picks
the next free port and prints the final URL.
