# Build The Bibliography Site

## Inspect readiness

```bash
biblio citekeys status
```

## Build

```bash
biblio site build
```

## Serve

```bash
biblio site serve
```

## Clean

```bash
biblio site clean
```

## Check a built site

```bash
biblio site doctor
```

The generated site lives under `bib/site/` and can be opened directly in a
browser or served over HTTP with `biblio site serve`.

For an interactive live view during active work, see [Use The Local UI](ui.md).
