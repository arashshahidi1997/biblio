from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Iterator, Tuple


TEMPLATE_PACKAGE = "biblio"
TEMPLATE_ROOT = Path("templates/bib")


@dataclass(frozen=True)
class ScaffoldResult:
    root: Path
    files_written: tuple[Path, ...]


def _template_dir() -> Traversable:
    return resources.files(TEMPLATE_PACKAGE).joinpath(str(TEMPLATE_ROOT))


def _iter_template_files(root: Traversable) -> Iterator[Tuple[Path, Traversable]]:
    def _recurse(node: Traversable, rel: Path) -> Iterator[Tuple[Path, Traversable]]:
        for child in node.iterdir():
            child_rel = rel / child.name
            if child.is_dir():
                yield from _recurse(child, child_rel)
            else:
                yield child_rel, child

    return _recurse(root, Path())


def init_bib_scaffold(repo_root: str | Path, *, force: bool = False) -> ScaffoldResult:
    repo_root = Path(repo_root).expanduser().resolve()
    tpl_root = _template_dir()
    if not tpl_root.is_dir():
        raise FileNotFoundError(f"Missing template dir in package: {TEMPLATE_PACKAGE}/{TEMPLATE_ROOT}")

    files_written: list[Path] = []
    for rel, entry in _iter_template_files(tpl_root):
        if rel.name.endswith(".tmpl"):
            rel = rel.with_suffix("")
        dest = repo_root / "bib" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not force:
            continue
        data = entry.read_bytes()
        dest.write_bytes(data)
        files_written.append(dest)

    # Ensure bib/ exists even if everything already present.
    (repo_root / "bib").mkdir(exist_ok=True)
    return ScaffoldResult(root=repo_root, files_written=tuple(files_written))
