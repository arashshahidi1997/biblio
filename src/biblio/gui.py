from __future__ import annotations

import sys

from .cli import main


def gui_main() -> None:
    sys.argv = [sys.argv[0], "ui", "serve", *sys.argv[1:]]
    main()
