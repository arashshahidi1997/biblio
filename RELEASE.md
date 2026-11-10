# Release Notes

## One command

From the repository root, with the version set in `src/biblio/__init__.py`, the CHANGELOG section dated, and the release tagged:

```bash
pixi run -e dev publish-test   # TestPyPI first
pixi run -e dev publish        # then PyPI
```

Both run `scripts/publish.py`: a clean `python -m build`, `twine check`, and `twine upload` of this version's files only. The API token comes from `TWINE_PASSWORD` (with `TWINE_USERNAME`, default `__token__`), else from `~/.config/tokens/pypi.token` or `~/.config/tokens/testpypi.token`, else from `--token-file PATH`:

```bash
pixi run -e dev python scripts/publish.py --test --token-file ~/tokens/testpypi.token
```

## Step by step

```bash
pixi run -e dev build          # python -m build
pixi run -e dev check          # twine check dist/*
pixi run -e dev python -m twine upload --repository testpypi dist/*
pixi run -e dev python -m twine upload dist/*
```

The `dev` environment carries `build` and `twine`; no other environment is needed.
