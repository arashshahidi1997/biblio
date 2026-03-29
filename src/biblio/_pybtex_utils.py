from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


def require_pybtex(feature: str) -> None:
    try:
        from pybtex.database import parse_file  # noqa: F401
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            f"biblio {feature} requires `pybtex` (install with `pip install biblio-tools`)."
        ) from e


@contextmanager
def non_strict_pybtex():
    from pybtex.errors import capture, set_strict_mode

    set_strict_mode(False)
    try:
        with capture():
            yield
    finally:
        set_strict_mode(True)


def parse_bibtex_file(path: str | Path):
    require_pybtex("BibTeX features")
    from pybtex.database import parse_file

    with non_strict_pybtex():
        return parse_file(str(path))


def parse_bibtex_string(text: str):
    """Parse a BibTeX string and return a BibliographyData object."""
    require_pybtex("BibTeX features")
    from pybtex.database import parse_string

    with non_strict_pybtex():
        return parse_string(text, "bibtex")
