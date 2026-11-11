"""Agent skills shipped with biblio; ``biblio skills install`` copies them into a project or ~/.claude.

The same folders make biblio's Claude Code plugins (``.claude-plugin/marketplace.json`` at the repository
root points at ``src/biblio/skills`` and ``src/biblio/agents``).
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BUNDLED = Path(__file__).resolve().parent / "skills"
AGENTS = Path(__file__).resolve().parent / "agents"


def skills_dir() -> Path:
    """The bundled skills folder; projio finds it through the ``projio.skills`` entry point."""
    return BUNDLED


@dataclass
class SkillInfo:
    name: str
    description: str
    stability: str = "stable"                       # stable | beta
    needs: list[str] = field(default_factory=list)  # e.g. ["biblio", "projio"]
    agents: list[str] = field(default_factory=list)


def skill_infos() -> list[SkillInfo]:
    from .wiki.pages import split_frontmatter

    out = []
    for skill_md in sorted(BUNDLED.glob("*/SKILL.md")):
        fm_text, _, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
        meta = (yaml.safe_load(fm_text) or {}) if fm_text else {}
        md = meta.get("metadata") or {}
        short = md.get("short-description")
        out.append(SkillInfo(
            name=skill_md.parent.name,
            description=str(short or meta.get("description", "")).strip(),
            stability=str(md.get("stability") or "stable"),
            needs=[str(x) for x in md.get("needs") or ["biblio"]],
            agents=[str(x) for x in md.get("agents") or []]))
    return out


def list_skills() -> list[tuple[str, str]]:
    """Return (name, description) for each bundled skill."""
    return [(s.name, s.description) for s in skill_infos()]


def install(dest: Path, names: list[str] | None = None, force: bool = False,
            agents_dest: Path | None = None) -> list[tuple[str, str]]:
    """Copy skills into ``dest/<name>/`` and the agents they use into ``agents_dest``.

    Returns (name, action) pairs; agents are named ``agent:<name>``.
    """
    results = []
    wanted_agents: set[str] = set()
    for info in skill_infos():
        if names is not None and info.name not in names:
            continue
        wanted_agents.update(info.agents)
        target = dest / info.name
        if target.exists() and not force:
            results.append((info.name, "exists (use --force to overwrite)"))
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(BUNDLED / info.name, target, ignore=shutil.ignore_patterns("__pycache__"))
        results.append((info.name, "installed"))
    if agents_dest is not None:
        for agent in sorted(wanted_agents):
            src = AGENTS / f"{agent}.md"
            if not src.is_file():
                continue
            target = agents_dest / src.name
            if target.exists() and not force:
                results.append((f"agent:{agent}", "exists (use --force to overwrite)"))
                continue
            agents_dest.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
            results.append((f"agent:{agent}", "installed"))
    return results
