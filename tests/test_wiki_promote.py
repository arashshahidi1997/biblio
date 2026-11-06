"""Wiki SPEC v0.2: origin/promoted_to keys, one vocabulary (W14), promote gate and plan (W12)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from biblio.cli import main
from biblio.tag_vocab import default_tag_vocab_path
from biblio.wiki.lint import lint
from biblio.wiki.promote import PromoteError, plan_promote
from biblio.wiki.schema import load_wiki_config
from biblio.wiki.scaffold import init

FM = """---
title: {title}
type: {type}
scope: {scope}
status: {status}
author: llm
updated: 2026-10-22
tags: [{tags}]
sources: [{sources}]
{extra}---
"""

BODY = """
# {title}

Sharp-wave ripples are coupled to cortical up-states during sleep.

## Why it matters

It links memory replay to cortical state; see [ripple detection](../methods/ripple-detection.md).

## Key facts

> "Neocortical up-states precede hippocampal sharp-wave ripples by about 50 ms" [@sirota_2003_CommunicationNeocortex]

## Our experience

Seen in our recordings.

## Related

- [ripple detection](../methods/ripple-detection.md)
"""

PAPER = """# Communication between neocortex and hippocampus

## Results

Neocortical up-states precede hippocampal sharp-wave ripples by about 50 ms in
sleeping rats.
"""


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                   capture_output=True)


def _repo(root: Path, wiki_yml: str = "", key_in_bib: bool = True) -> Path:
    (root / "bib").mkdir(parents=True)
    (root / "bib" / "main.bib").write_text(
        "@article{sirota_2003_CommunicationNeocortex,\n  title = {C},\n  year = {2003}\n}\n" if key_in_bib else "")
    paper = root / "bib" / "derivatives" / "docling" / "sirota_2003_CommunicationNeocortex"
    paper.mkdir(parents=True)
    (paper / "sirota_2003_CommunicationNeocortex.md").write_text(PAPER)
    cfg = load_wiki_config(root)
    init(cfg)
    vocab = cfg.wiki_root / "vocab.yml"
    vocab.write_text(vocab.read_text().replace(
        "event: {description: Physiological event, values: []}",
        "event: {description: Physiological event, values: [ripple]}\n"
        "  px-analysis: {description: project thread, values: [laminar]}"))
    if wiki_yml:
        (cfg.wiki_root / "wiki.yml").write_text(wiki_yml)
    return root


def _page(root: Path, rel: str, *, title="Ripple coupling", type="concept", scope="general", status="draft",
          tags="event/ripple, px-analysis/laminar", sources="sirota_2003_CommunicationNeocortex", extra="",
          body=BODY) -> Path:
    path = root / "docs" / "wiki" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FM.format(title=title, type=type, scope=scope, status=status, tags=tags, sources=sources,
                              extra=extra) + body.format(title=title))
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = _repo(tmp_path / "pixecog", "name: pixecog\nproject_facets: [px-analysis]\n")
    _page(root, "concepts/ripple-coupling.md", extra="evidence: [result-20260918]\n")
    method_body = BODY.replace("see [ripple detection](../methods/ripple-detection.md)", "nothing else") \
        .replace("- [ripple detection](../methods/ripple-detection.md)", "- [ripple coupling](../concepts/ripple-coupling.md)")
    _page(root, "methods/ripple-detection.md", title="Ripple detection", type="method",
          body=method_body.replace("## Why it matters", "## Goal").replace("## Key facts", "## Procedure"))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "wiki")
    return root


def _codes(findings, page):
    return [f.code for f in findings if f.page == page]


# --- SPEC §5: origin and promoted_to --------------------------------------------------------------

def test_origin_is_a_known_key_and_checked(tmp_path):
    root = _repo(tmp_path / "lit")
    good = "origin: [{project: pixecog, path: docs/wiki/concepts/a.md, commit: abc123, date: 2026-11-06}]\n"
    _page(root, "concepts/moved.md", extra=good)
    _page(root, "concepts/half.md", title="Half", extra="origin: [{project: pixecog}]\n")
    _page(root, "concepts/left.md", title="Left", extra="promoted_to: concepts/moved.md\n")
    findings = lint(load_wiki_config(root))
    assert "FM005" not in _codes(findings, "concepts/moved.md")
    assert "FM009" not in _codes(findings, "concepts/moved.md")
    assert "FM009" in _codes(findings, "concepts/half.md")
    assert "FM010" in _codes(findings, "concepts/left.md")


def test_sample_wiki_lints_clean_cli(project, capsys, monkeypatch):
    monkeypatch.chdir(project)
    with pytest.raises(SystemExit) as exc:
        main(["wiki", "lint", "--root", str(project), "--min-severity", "warning"])
    assert exc.value.code == 0, capsys.readouterr().out


# --- W14: one vocabulary --------------------------------------------------------------------------

def test_library_tags_use_the_wiki_vocabulary(tmp_path):
    root = tmp_path / "p"
    (root / ".projio" / "biblio").mkdir(parents=True)
    (root / ".projio" / "biblio" / "tag_vocab.yml").write_text("namespaces: {domain: {values: [nlp]}}\n")
    assert default_tag_vocab_path(root) == (root / ".projio" / "biblio" / "tag_vocab.yml").resolve()
    init(load_wiki_config(root))
    assert default_tag_vocab_path(root) == (root / "docs" / "wiki" / "vocab.yml").resolve()
    assert load_wiki_config(root).vocab == default_tag_vocab_path(root)


def test_wiki_yml_vocab_key_names_the_one_file(tmp_path):
    root = tmp_path / "p"
    init(load_wiki_config(root))
    shared = root / "vocab" / "tags.yml"
    shared.parent.mkdir()
    shared.write_text("namespaces: {event: {values: [ripple]}}\n")
    (root / "docs" / "wiki" / "wiki.yml").write_text("vocab: vocab/tags.yml\n")
    assert default_tag_vocab_path(root) == shared.resolve()
    assert load_wiki_config(root).vocab == shared.resolve()


# --- W12: promote gate and plan -------------------------------------------------------------------

def test_project_to_personal_plan(project):
    plan = plan_promote(load_wiki_config(project), ["ripple-coupling"])
    assert (plan.source_tier, plan.target_tier) == ("project", "personal")
    pp = plan.pages[0]
    assert pp.ok, [(c.name, c.detail) for c in pp.checks if not c.ok]
    assert {c.name for c in pp.checks} >= {"type", "scope", "lint", "sources", "committed"}
    assert "reviewed" not in {c.name for c in pp.checks}            # no review at this step
    assert pp.dest == "personal:concepts/ripple-coupling.md"
    assert pp.origin["project"] == "pixecog"
    assert pp.origin["path"] == "docs/wiki/concepts/ripple-coupling.md"
    assert pp.origin["commit"] not in ("", "<commit>")
    assert pp.tags_stripped == ["px-analysis/laminar"] and pp.tags_kept == ["event/ripple"]
    assert any("Our experience" in s for s in pp.stays_behind)
    assert any("result-20260918" in s for s in pp.stays_behind)
    assert pp.links_unresolved == ["methods/ripple-detection.md"]


def test_gate_blocks(project):
    root = project
    _page(root, "concepts/no-sources.md", title="No sources", sources="",
          body=BODY.replace(' [@sirota_2003_CommunicationNeocortex]', ''))
    _page(root, "cases/a-case.md", title="A case", type="case", scope="project")
    cfg = load_wiki_config(root)
    plan = plan_promote(cfg, ["no-sources", "a-case"])
    by = {p.page: {c.name: c.ok for c in p.checks} for p in plan.pages}
    assert by["concepts/no-sources.md"]["sources"] is False
    assert by["concepts/no-sources.md"]["committed"] is False
    assert by["cases/a-case.md"]["type"] is False
    assert by["cases/a-case.md"]["scope"] is False
    assert not plan.ok


def test_tag_selects_pages(project):
    plan = plan_promote(load_wiki_config(project), tag="event/ripple")
    assert {p.page for p in plan.pages} == {"concepts/ripple-coupling.md", "methods/ripple-detection.md"}
    with pytest.raises(PromoteError):
        plan_promote(load_wiki_config(project))


def test_target_tier_rules(project, tmp_path):
    cfg = load_wiki_config(project)
    sideways = _repo(tmp_path / "other", "name: other\n")
    with pytest.raises(PromoteError, match="sideways"):
        plan_promote(cfg, ["ripple-coupling"], target=load_wiki_config(sideways))
    lab = _repo(tmp_path / "lab", "name: sirocampus\ntier: lab\n")
    with pytest.raises(PromoteError, match="next tier"):
        plan_promote(cfg, ["ripple-coupling"], target=load_wiki_config(lab))
    personal = _repo(tmp_path / "lit", "name: lit-studio\ntier: personal\n")
    _page(personal, "methods/ripple-detection.md", title="Ripple detection", type="method")
    plan = plan_promote(cfg, ["ripple-coupling"], target=load_wiki_config(personal))
    pp = plan.pages[0]
    assert pp.dest == "lit-studio:concepts/ripple-coupling.md" and not pp.dest_exists
    assert pp.links_unresolved == []                                 # the linked page is already there


def test_personal_to_lab_needs_review_and_lab_bibliography(tmp_path):
    lit = _repo(tmp_path / "lit", "name: lit-studio\ntier: personal\n")
    _page(lit, "concepts/ripple-coupling.md", tags="event/ripple")
    _git(lit, "init", "-q")
    _git(lit, "add", "-A")
    _git(lit, "commit", "-qm", "wiki")
    lab = _repo(tmp_path / "lab", "name: sirocampus\ntier: lab\n", key_in_bib=False)
    plan = plan_promote(load_wiki_config(lit), ["ripple-coupling"], target=load_wiki_config(lab))
    checks = {c.name: c.ok for c in plan.pages[0].checks}
    assert checks["reviewed"] is False
    assert checks["lab bibliography"] is False
    assert "sources" not in checks
    with pytest.raises(PromoteError, match="top tier"):
        plan_promote(load_wiki_config(lab), ["x"])


def test_promote_cli_json(project, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["wiki", "promote", "ripple-coupling", "--root", str(project), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert exc.value.code == 0
    assert data["ok"] and data["pages"][0]["origin"]["project"] == "pixecog"
    # nothing written
    assert subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True,
                          text=True).stdout == ""
