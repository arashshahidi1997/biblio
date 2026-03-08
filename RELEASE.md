# Release Notes

## Build and check locally

From the repository root:

```bash
python -m build
python -m twine check dist/*
```

## Test upload to TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
```

## Upload to PyPI

```bash
python -m twine upload dist/*
```

## Recommended environment

Install the development extras so `build` and `twine` are present:

```bash
pip install -e ".[dev]"
```
