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


def test_init_stays_in_the_current_folder_below_a_git_repo(tmp_path, monkeypatch, capsys):
    """A .git above (a dotfiles repo in $HOME) must not pull the scaffold up there."""
    from biblio import cli
    (tmp_path / ".git").mkdir()
    here = tmp_path / "papers"
    here.mkdir()
    monkeypatch.chdir(here)
    cli.main(["init"])
    assert (here / ".projio" / "biblio" / "biblio.yml").is_file()
    assert not (tmp_path / ".projio").exists()
    monkeypatch.chdir(here / "bib")                                  # inside a workspace: use it
    cli.main(["init"])
    assert "already initialized" in capsys.readouterr().out


def test_help_marks_beta_and_experimental(capsys):
    import pytest
    from biblio import cli
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "[beta] Digests" in out and "[experimental] Serve a local" in out
    assert out.index("  init ") < out.index("  quotes ") < out.index("  digest ")


def test_plugin_marketplace_matches_the_package():
    """The Claude Code plugins (biblio: the stable skills; biblio-kb: the beta rest) are versioned
    with the CLI their skills call, and between them ship every bundled skill once."""
    import json
    from pathlib import Path
    import biblio
    from biblio.skills_bundle import skill_infos
    root = Path(__file__).resolve().parent.parent
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    shipped = []
    for plugin in market["plugins"]:
        assert plugin["version"] == biblio.__version__
        for path in plugin["skills"]:
            assert (root / path / "SKILL.md").is_file(), path
            shipped.append(Path(path).name)
        for agent in plugin.get("agents", []):
            assert (root / agent).is_file(), agent
    assert sorted(shipped) == sorted(s.name for s in skill_infos())
    base = next(p for p in market["plugins"] if p["name"] == "biblio")
    assert {Path(x).name for x in base["skills"]} == {s.name for s in skill_infos() if s.stability == "stable"}


def test_install_user_copies_skills_and_agents(tmp_path, monkeypatch, capsys):
    from biblio import cli
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    cli.main(["skills", "install", "--user", "paper-scrutiny", "paper-text"])
    assert (tmp_path / ".claude" / "skills" / "paper-scrutiny" / "PROTOCOL.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "paper-text" / "SKILL.md").is_file()
    assert (tmp_path / ".claude" / "agents" / "paper-attacker.md").is_file()
    cli.main(["skills", "install", "--user", "--stable", "--force"])
    out = capsys.readouterr().out
    assert "paper-text: installed" in out and "wiki-ingest" not in out
    cli.main(["skills", "list"])
    out = capsys.readouterr().out
    assert "biblio-batch-curate [beta, needs projio]" in out and "paper-text [stable]" in out
