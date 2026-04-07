from __future__ import annotations

import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterator, Tuple

try:  # Python >= 3.11
    from importlib.resources.abc import Traversable
except Exception:  # pragma: no cover
    Traversable = Any


TEMPLATE_PACKAGE = "biblio"
TEMPLATE_ROOT_BIB = Path("templates/bib")
TEMPLATE_ROOT_PROJIO = Path("templates/projio_biblio")


@dataclass(frozen=True)
class ScaffoldResult:
    root: Path
    files_written: tuple[Path, ...]


def _template_dir(name: str = "bib") -> Traversable:
    root = TEMPLATE_ROOT_BIB if name == "bib" else TEMPLATE_ROOT_PROJIO
    return resources.files(TEMPLATE_PACKAGE).joinpath(str(root))


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

    files_written: list[Path] = []

    # 1. bib/ templates — README and source data directories
    #    .gitignore is only written if bib/ is its own git repo (e.g. datalad subdataset).
    bib_is_git_repo = (repo_root / "bib" / ".git").exists()
    tpl_bib = _template_dir("bib")
    if tpl_bib.is_dir():
        for rel, entry in _iter_template_files(tpl_bib):
            if rel.name.endswith(".tmpl"):
                rel = rel.with_suffix("")
            if rel.name == ".gitignore" and not bib_is_git_repo:
                continue
            dest = repo_root / "bib" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and not force:
                continue
            dest.write_bytes(entry.read_bytes())
            files_written.append(dest)

    # 2. .projio/biblio/ templates — config files (biblio.yml, citekeys, tag_vocab)
    tpl_projio = _template_dir("projio_biblio")
    if tpl_projio.is_dir():
        for rel, entry in _iter_template_files(tpl_projio):
            if rel.name.endswith(".tmpl"):
                rel = rel.with_suffix("")
            dest = repo_root / ".projio" / "biblio" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and not force:
                continue
            dest.write_bytes(entry.read_bytes())
            files_written.append(dest)

    # Ensure directories exist even if everything already present.
    (repo_root / "bib").mkdir(exist_ok=True)
    (repo_root / "bib" / "srcbib").mkdir(exist_ok=True)
    (repo_root / "bib" / "articles").mkdir(exist_ok=True)
    (repo_root / ".projio" / "biblio").mkdir(parents=True, exist_ok=True)
    return ScaffoldResult(root=repo_root, files_written=tuple(files_written))
