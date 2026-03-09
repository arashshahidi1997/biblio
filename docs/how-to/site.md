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
