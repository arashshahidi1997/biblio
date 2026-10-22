"""Where the wiki's sources live: the project bibliography and the shared pools.

A literature wiki cites papers processed in other projects (pools, configured
under ``pool.search`` in biblio.yml). Lint needs two answers per citekey: is
the key known, and where is its full text. Project files win over pools.
"""
from __future__ import annotations

import re
from pathlib import Path

from .schema import WikiConfig

_ENTRY_RE = re.compile(r"^\s*@\w+\s*\{\s*([^,\s]+)\s*,", re.M)
_DOI_RE = re.compile(r"\bdoi\s*=\s*[{\"]\s*([^}\"]+?)\s*[}\"]", re.I)


def bib_keys_and_dois(path: Path) -> tuple[set[str], dict[str, str]]:
    """Citekeys in a BibTeX file and their DOIs (a fast scan, no full parse)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    keys: set[str] = set()
    dois: dict[str, str] = {}
    matches = list(_ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        key = m.group(1)
        keys.add(key)
        body = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        doi = _DOI_RE.search(body)
        if doi:
            dois[key] = doi.group(1)
    return keys, dois


def _project_bibliographies(cfg: WikiConfig) -> list[Path]:
    if cfg.bibliography_explicit:
        return [cfg.bibliography] if cfg.bibliography else []
    candidates = [cfg.repo_root / rel for rel in
                  (".projio/render/compiled.bib", ".projio/biblio/merged.bib", "bib/main.bib")]
    return [p for p in candidates if p.is_file()]


class SourceIndex:
    """Citekeys and full texts across the project and its pools."""

    def __init__(self, cfg: WikiConfig):
        self.cfg = cfg
        self.project_keys: set[str] = set()
        self.dois: dict[str, str] = {}
        self.biblio_cfg = self._load_biblio_cfg()
        self.bibliographies = _project_bibliographies(cfg)
        if not cfg.bibliography_explicit:
            # the project's own sources count even before `biblio bibtex merge` (as in refs triage)
            self.bibliographies += [p for p in self._srcbib_files() if p not in self.bibliographies]
        for path in self.bibliographies:
            keys, dois = bib_keys_and_dois(path)
            self.project_keys |= keys
            self.dois.update(dois)
        self.pool_keys: dict[Path, set[str]] = {}
        for pool_root in self.pool_roots:
            bib = self._pool_bib(pool_root)
            if bib is not None:
                keys, dois = bib_keys_and_dois(bib)
                self.pool_keys[pool_root] = keys
                for key, doi in dois.items():
                    self.dois.setdefault(key, doi)

    def _load_biblio_cfg(self):
        try:
            from ..config import default_config_path, load_biblio_config
            return load_biblio_config(default_config_path(root=self.cfg.repo_root), root=self.cfg.repo_root)
        except Exception:
            return None

    def _srcbib_files(self) -> list[Path]:
        merge = getattr(self.biblio_cfg, "bibtex_merge", None)
        src_dir = merge.src_dir if merge else self.cfg.repo_root / "bib" / "srcbib"
        pattern = merge.src_glob if merge else "*.bib"
        return sorted(p for p in Path(src_dir).glob(pattern) if p.is_file()) if Path(src_dir).is_dir() else []

    @property
    def pool_roots(self) -> tuple[Path, ...]:
        return tuple(getattr(self.biblio_cfg, "pool_search", ()) or ())

    @staticmethod
    def _pool_bib(pool_root: Path) -> Path | None:
        from ..pool import _find_pool_bib
        return _find_pool_bib(pool_root)

    @property
    def has_bibliography(self) -> bool:
        return bool(self.bibliographies or self.pool_keys)

    def locate(self, citekey: str) -> str | None:
        """'project', the pool root holding the key, or None."""
        if citekey in self.project_keys:
            return "project"
        for pool_root, keys in self.pool_keys.items():
            if citekey in keys:
                return str(pool_root)
        if self.biblio_cfg is not None and self.pool_roots and self._pool_dir(citekey) is not None:
            return "pool"
        return None

    def _pool_dir(self, citekey: str) -> Path | None:
        from ..pool import resolve_pool_derivative
        return resolve_pool_derivative(self.biblio_cfg, citekey, "docling", doi=self.dois.get(citekey))

    def fulltext(self, citekey: str) -> Path:
        """The paper's docling markdown: the project's copy, else a pool's."""
        local = self.cfg.fulltext_path(citekey)
        if local.is_file() or self.biblio_cfg is None or not self.pool_roots:
            return local
        pool_dir = self._pool_dir(citekey)
        if pool_dir is not None:
            for name in (f"{pool_dir.name}.md", f"{citekey}.md"):
                if (pool_dir / name).is_file():
                    return pool_dir / name
        return local
