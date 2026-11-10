"""Citekey aliases: several keys for one paper (lit-studio R66).

A project lists them in ``.projio/biblio/citekey_aliases.yml``, canonical key
first::

    ji_2007_CoordinatedMemory: [ji_2006_CoordinatedMemory]

Either key then resolves to the same full text and derivatives (project or
pool), and wiki lint treats them as one paper. ``biblio bibtex merge
--collapse-aliases`` keeps only the canonical entry of a DOI group in the
merged bib; without it every key stays, so documents citing an alias still
render.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ALIASES_REL = Path(".projio") / "biblio" / "citekey_aliases.yml"


@dataclass
class CitekeyAliases:
    canonical_of: dict[str, str] = field(default_factory=dict)   # alias -> canonical
    path: Path | None = None

    def canonical(self, key: str) -> str:
        key = key.lstrip("@")
        return self.canonical_of.get(key, key)

    def equivalents(self, key: str) -> list[str]:
        """``key`` first, then its canonical key and the canonical key's other aliases."""
        key = key.lstrip("@")
        canon = self.canonical(key)
        out = [key] if key == canon else [key, canon]
        out += sorted(a for a, c in self.canonical_of.items() if c == canon and a not in out)
        return out

    def __bool__(self) -> bool:
        return bool(self.canonical_of)


_CACHE: dict[Path, tuple[tuple[int, int], CitekeyAliases]] = {}


def aliases_path(repo_root: Path) -> Path:
    return Path(repo_root) / ALIASES_REL


def load_aliases(repo_root: Path | None) -> CitekeyAliases:
    """The project's aliases; empty when the file is absent. Cached per file mtime."""
    if repo_root is None:
        return CitekeyAliases()
    path = aliases_path(repo_root).resolve()
    if not path.is_file():
        return CitekeyAliases()
    st = path.stat()
    mtime = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected 'canonical_key: [alias, ...]' entries")
    canonical_of: dict[str, str] = {}
    for canon, aliases in data.items():
        canon = str(canon).lstrip("@")
        if canon in canonical_of:
            raise ValueError(f"{path}: {canon} is listed as an alias of {canonical_of[canon]} and as canonical")
        for alias in [aliases] if isinstance(aliases, str) else (aliases or []):
            alias = str(alias).lstrip("@")
            if alias == canon:
                continue
            if alias in data:
                raise ValueError(f"{path}: {alias} is canonical and an alias of {canon}")
            if canonical_of.get(alias, canon) != canon:
                raise ValueError(f"{path}: {alias} is an alias of both {canonical_of[alias]} and {canon}")
            canonical_of[alias] = canon
    result = CitekeyAliases(canonical_of, path)
    _CACHE[path] = (mtime, result)
    return result


def add_alias(repo_root: Path, canonical: str, alias: str) -> Path:
    """Record ``alias`` as another key of ``canonical`` (kept sorted; comments are not preserved)."""
    path = aliases_path(repo_root)
    data = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}
    canonical, alias = canonical.lstrip("@"), alias.lstrip("@")
    if alias == canonical:
        raise ValueError("an alias must differ from its canonical key")
    if alias in data:
        raise ValueError(f"{alias} is itself canonical in {path}")
    current = load_aliases(repo_root).canonical_of.get(canonical)
    if current:
        raise ValueError(f"{canonical} is an alias of {current}; use {current} as the canonical key")
    keys = [str(k) for k in (data.get(canonical) or [])]
    if alias not in keys:
        keys.append(alias)
    data[canonical] = sorted(keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Citekey aliases: canonical_key: [alias, ...] (biblio, lit-studio R66)\n"
    path.write_text(header + yaml.safe_dump(dict(sorted(data.items())), sort_keys=False), encoding="utf-8")
    load_aliases(repo_root)  # validate what was written
    return path
