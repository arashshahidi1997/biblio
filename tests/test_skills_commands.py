"""Every `biblio ...` command a bundled skill names exists in the CLI (skills drift when commands change)."""
from __future__ import annotations

import argparse
import re

import pytest

from biblio.cli import _build_parser
from biblio.skills_bundle import skills_dir

CMD_RE = re.compile(r"\bbiblio((?:\s+[a-z][a-z-]*)+)")


def _tree(parser: argparse.ArgumentParser) -> dict:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return {name: _tree(sub) for name, sub in action.choices.items()}
    return {}


def _commands(text: str) -> set[str]:
    """`biblio wiki lint ...` in backticks, code blocks and the tooling lists."""
    spans = re.findall(r"`([^`]+)`", text) + re.findall(r"```[a-z]*\n(.*?)```", text, re.S)
    spans += re.findall(r"cli:\s*\[([^\]]+)\]", text)
    out = set()
    for span in spans:
        for m in CMD_RE.finditer(span):
            out.add(" ".join(m.group(1).split()))
    return out


SKILLS = sorted(p.parent.name for p in skills_dir().glob("*/SKILL.md"))


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_names_only_existing_commands(skill):
    tree = _tree(_build_parser())
    text = (skills_dir() / skill / "SKILL.md").read_text(encoding="utf-8")
    bad = []
    for cmd in sorted(_commands(text)):
        node, words = tree, cmd.split()
        if words[0] not in node:
            bad.append(cmd)
            continue
        for w in words:
            if not node:          # reached a leaf command: the rest are arguments
                break
            if w not in node:
                bad.append(cmd)
                break
            node = node[w]
        else:
            if node:              # stopped at a group ("biblio wiki") without a subcommand
                bad.append(cmd)
    assert not bad, f"{skill} names commands the CLI does not have: {bad}"


def test_every_skill_has_a_usable_description():
    import yaml
    for skill in SKILLS:
        text = (skills_dir() / skill / "SKILL.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(text.split("---", 2)[1])
        assert fm["name"] == skill
        desc = " ".join(str(fm["description"]).split())
        assert 80 <= len(desc) <= 1024 and "Use " in desc, f"{skill}: description must say when to use it"
