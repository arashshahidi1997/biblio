"""How to add an optional extra, for error messages: it differs for a uv tool and a pip install."""
from __future__ import annotations


def install_hint(extra: str) -> str:
    return (f'the "{extra}" extra of biblio-tools: as a uv tool, reinstall with it among the extras '
            f'(uv tool install --reinstall "biblio-tools[<your extras>,{extra}]", or a local path with -e); '
            f'with pip, pip install "biblio-tools[{extra}]"')
