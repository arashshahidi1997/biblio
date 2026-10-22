"""Agent skills shipped with biblio; ``biblio skills install`` copies them into a project."""
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

BUNDLED = Path(__file__).resolve().parent / "skills"


def skills_dir() -> Path:
    """The bundled skills folder; projio finds it through the ``projio.skills`` entry point."""
    return BUNDLED


def list_skills() -> list[tuple[str, str]]:
    """Return (name, description) for each bundled skill."""
    from .wiki.pages import split_frontmatter

    out = []
    for skill_md in sorted(BUNDLED.glob("*/SKILL.md")):
        fm_text, _, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
        meta = (yaml.safe_load(fm_text) or {}) if fm_text else {}
        short = (meta.get("metadata") or {}).get("short-description")
        out.append((skill_md.parent.name, str(short or meta.get("description", "")).strip()))
    return out


def install(dest: Path, names: list[str] | None = None, force: bool = False) -> list[tuple[str, str]]:
    """Copy skills into ``dest/<name>/``. Returns (name, action) pairs."""
    results = []
    for name, _ in list_skills():
        if names and name not in names:
            continue
        target = dest / name
        if target.exists() and not force:
            results.append((name, "exists (use --force to overwrite)"))
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(BUNDLED / name, target)
        results.append((name, "installed"))
    return results
