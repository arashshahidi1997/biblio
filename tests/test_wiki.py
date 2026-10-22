"""Tests for the wiki toolkit: scaffold, lint, hubs, status, skills."""
from __future__ import annotations

from pathlib import Path

import pytest

from biblio.cli import main
from biblio.skills_bundle import install, list_skills
from biblio.wiki.fidelity import QuoteChecker
from biblio.wiki.hubs import regenerate, stale_views
from biblio.wiki.lint import lint
from biblio.wiki.pages import parse_page
from biblio.wiki.scaffold import init, stub
from biblio.wiki.schema import load_wiki_config
from biblio.wiki.status import status

PAPER = """# Communication between neocortex and hippocampus

## Results

Neocortical up-states precede hippocampal sharp-wave ripples by about 50 ms in
sleeping rats. Ripple probability increased during the up-state of the
slow oscillation.
"""

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


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    """Keep the user's ~/.config/biblio settings (e.g. pools) out of these tests."""
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "bib").mkdir()
    (tmp_path / "bib" / "main.bib").write_text(
        "@article{sirota_2003_CommunicationNeocortex,\n  title = {Communication},\n  year = {2003}\n}\n")
    paper = tmp_path / "bib" / "derivatives" / "docling" / "sirota_2003_CommunicationNeocortex"
    paper.mkdir(parents=True)
    (paper / "sirota_2003_CommunicationNeocortex.md").write_text(PAPER)
    cfg = load_wiki_config(tmp_path)
    init(cfg)
    vocab = cfg.wiki_root / "vocab.yml"
    vocab.write_text(vocab.read_text().replace(
        "event: {description: Physiological event, values: []}",
        "event: {description: Physiological event, values: [ripple, up-state]}"))
    return tmp_path


def write(path: Path, *, title="Page", type="concept", scope="general", status="draft", tags="event/ripple",
          sources="", extra="", body="") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FM.format(title=title, type=type, scope=scope, status=status, tags=tags,
                              sources=sources, extra=extra) + body)
    return path


CONCEPT_BODY = """
# Ripple coupling

Sharp-wave ripples are coupled to cortical up-states during sleep.

## Why it matters

It links memory replay to cortical state.

## Key facts

> "Neocortical up-states precede hippocampal sharp-wave ripples by about 50 ms" [@sirota_2003_CommunicationNeocortex]

> "Ripple probability increased during the up‐state of the  slow oscillation" [@sirota_2003_CommunicationNeocortex]

> "Ripple probability rose during the up-state of the slow oscillation" [@sirota_2003_CommunicationNeocortex]

> "Ripples are triggered by the phase of the moon in every species studied" [@sirota_2003_CommunicationNeocortex]

> **Contested.** Some studies report the reverse order [@sirota_2003_CommunicationNeocortex].

In sub-01 we saw this too.

## Our experience

Seen in sub-02 ses-03.

## Related

See [[missing-page]] and [[ripple-detection]].
"""


def codes(findings, page=None):
    return [f.code for f in findings if page is None or f.page == page]


def test_init_is_idempotent(repo):
    cfg = load_wiki_config(repo)
    assert (cfg.wiki_root / "concepts").is_dir()
    assert (cfg.wiki_root / "log.md").read_text().count("init") == 1
    assert init(cfg) == []


def test_stub_has_required_sections_and_lints_clean(repo):
    cfg = load_wiki_config(repo)
    path = stub(cfg, "Ripple detection", "method", tags=["event/ripple"])
    assert path == cfg.wiki_root / "methods" / "ripple-detection.md"
    text = path.read_text()
    for section in ("## Goal", "## Procedure", "## Failure modes", "## Implementation"):
        assert section in text
    findings = lint(cfg, [path])
    assert [f for f in findings if f.severity == "error"] == []


def test_lint_checks_quotes_citations_links_scope(repo):
    cfg = load_wiki_config(repo)
    stub(cfg, "ripple-detection", "method", tags=["event/ripple"])
    page = write(cfg.wiki_root / "concepts" / "ripple-coupling.md",
                 sources="sirota_2003_CommunicationNeocortex", body=CONCEPT_BODY)
    findings = lint(cfg, [page])
    found = codes(findings, "concepts/ripple-coupling.md")
    fid = sorted(f.message for f in findings if f.code == "FID001")
    # exact quotes and formatting noise pass; a fabricated quote and a one-word paraphrase do not
    assert len(fid) == 2 and "rose" in fid[0] and "moon" in fid[1]
    assert "LNK001" in found                                   # [[missing-page]]
    scope = [f for f in findings if f.code == "SCOPE001"]
    assert len(scope) == 1 and "sub-01" in scope[0].message    # "Our experience" is exempt
    assert "CIT001" not in found and "CIT002" not in found
    assert "STR002" not in found and "STR001" not in found


def test_lint_unknown_citekey_and_unlisted_source(repo):
    cfg = load_wiki_config(repo)
    body = "\n# X\n\nLede text here.\n\n## Why it matters\n\nSee [@nobody_1999_Nothing] and [@sirota_2003_CommunicationNeocortex].\n"
    page = write(cfg.wiki_root / "concepts" / "x.md", body=body)
    found = codes(lint(cfg, [page]))
    assert "CIT001" in found and "CIT002" in found
    assert "STR002" in found                                   # missing Key facts, Related


def test_reviewed_page_needs_reviewer_and_is_strict(repo):
    cfg = load_wiki_config(repo)
    page = write(cfg.wiki_root / "concepts" / "done.md", status="reviewed",
                 body="\n# Done\n\nLede.\n\n## Why it matters\n\n[[nowhere]]\n\n## Key facts\n\n## Related\n")
    findings = lint(cfg, [page])
    assert ("error", "FM004") in [(f.severity, f.code) for f in findings]
    assert ("error", "LNK001") in [(f.severity, f.code) for f in findings]


def test_frontmatter_and_tag_checks(repo):
    cfg = load_wiki_config(repo)
    page = write(cfg.wiki_root / "methods" / "odd.md", type="concept", status="final", tags="event/unknown",
                 extra="colour: blue\nrelated: ['[[ghost]]']\n", body="\n# Odd\n\nLede.\n")
    found = codes(lint(cfg, [page]))
    for code in ("FM003", "FM005", "FM006", "FM008", "TAG001"):
        assert code in found, code


def test_duplicate_basenames_and_embeds(repo):
    cfg = load_wiki_config(repo)
    write(cfg.wiki_root / "concepts" / "same.md", body="\n# A\n\nLede.\n\n![[other]]\n")
    write(cfg.wiki_root / "pitfalls" / "same.md", type="pitfall", body="\n# B\n\nLede.\n")
    found = codes(lint(cfg))
    assert found.count("LNK002") == 2 and "LNK003" in found


def test_status_block_is_not_a_quote(repo):
    cfg = load_wiki_config(repo)
    page = parse_page(write(cfg.wiki_root / "concepts" / "c.md", body=CONCEPT_BODY), cfg.wiki_root)
    assert not any("reverse order" in q.text for q in page.quotes)
    assert len(page.quotes) == 4


def test_hubs_regenerate_and_lint_detects_stale(repo):
    cfg = load_wiki_config(repo)
    hub = stub(cfg, "ripples", "hub", tags=["event/ripple"])
    stub(cfg, "ripple-detection", "method", tags=["event/ripple"])
    stub(cfg, "up-state", "concept", tags=["event/up-state"])
    assert "HUB001" in codes(lint(cfg))
    written = regenerate(cfg)
    assert hub in written and cfg.wiki_root / "index.md" in written
    text = hub.read_text()
    assert "[Ripple detection](../methods/ripple-detection.md) (stub)" in text and "up-state" not in text
    assert "[Ripples](hubs/hub-ripples.md)" in (cfg.wiki_root / "index.md").read_text()
    assert stale_views(cfg) == {} and regenerate(cfg) == []
    assert "HUB001" not in codes(lint(cfg))


def test_wikilink_style_is_opt_in(repo):
    cfg = load_wiki_config(repo)
    (cfg.wiki_root / "wiki.yml").write_text("link_style: wikilink\n")
    cfg = load_wiki_config(repo)
    hub = stub(cfg, "ripples", "hub", tags=["event/ripple"])
    stub(cfg, "ripple-detection", "method", tags=["event/ripple"])
    regenerate(cfg)
    assert "[[ripple-detection|Ripple detection]]" in hub.read_text()
    assert "LNK001" not in codes(lint(cfg))


def test_fresh_wiki_with_tags_passes_lint(tmp_path):
    """Laptop test 2026-10-22: init --tag and stub --tag gave TAG001 on the first lint."""
    cfg = load_wiki_config(tmp_path)
    init(cfg, subject="ripples", tags=["event/ripple"])
    stub(cfg, "sharp-wave-ripple", "concept", tags=["event/ripple", "region/ca1"])
    vocab = (cfg.wiki_root / "vocab.yml").read_text()
    assert "event: {description: Physiological event, values: [ripple]}" in vocab
    assert "region: {description: Anatomical region, values: [ca1]}" in vocab
    assert vocab.startswith("# Faceted tag vocabulary")           # comments kept
    assert "TAG001" not in codes(lint(cfg))
    assert "added event/ripple" in (cfg.wiki_root / "log.md").read_text()


def test_stub_tag_rules(repo):
    cfg = load_wiki_config(repo)
    before = (cfg.wiki_root / "vocab.yml").read_text()
    stub(cfg, "a", "concept", tags=["event/ripple"])                # already known: no change
    assert (cfg.wiki_root / "vocab.yml").read_text() == before
    with pytest.raises(ValueError, match="unknown facet 'evnt'"):
        stub(cfg, "b", "concept", tags=["evnt/ripple"])
    with pytest.raises(ValueError, match="facet/value"):
        stub(cfg, "c", "concept", tags=["ripple"])
    assert not (cfg.wiki_root / "concepts" / "b.md").exists()

    (cfg.wiki_root / "vocab.yml").write_text(
        "namespaces:\n  event:\n    description: Event\n    values: [ripple]\n  region:\n    values: []\n")
    stub(cfg, "d", "concept", tags=["event/spindle"])
    assert "    values: [ripple, spindle]\n  region:\n    values: []" in (cfg.wiki_root / "vocab.yml").read_text()


def test_status_review_queue(repo):
    cfg = load_wiki_config(repo)
    write(cfg.wiki_root / "concepts" / "drafted.md", body="\n# D\n\nLede.\n")
    report = status(cfg)
    assert report["review_queue"] == ["concepts/drafted.md"]
    assert report["by_type"]["concept"]["draft"] == 1


def test_quote_checker_tolerates_hyphenation(tmp_path):
    f = tmp_path / "p.md"
    f.write_text("The slow oscil-\nlation drives ripples in the hippo-\ncampus.")
    checker = QuoteChecker(lambda key: f)
    assert checker.check("k", "The slow oscillation drives ripples in the hippocampus") == "exact"
    assert checker.check("k", "Gamma bursts dominate the neocortex during waking hours") == "missing"


def test_cli_lint_exit_code_and_skills_install(repo, capsys, tmp_path):
    cfg = load_wiki_config(repo)
    write(cfg.wiki_root / "concepts" / "bad.md", status="reviewed", body="\n# Bad\n\nLede.\n")
    with pytest.raises(SystemExit) as exc:
        main(["wiki", "lint", "--root", str(repo), "--min-severity", "error"])
    assert exc.value.code == 1
    assert "FM004" in capsys.readouterr().out
    names = [n for n, _ in list_skills()]
    assert {"wiki-ingest", "wiki-maintain"} <= set(names)
    results = install(tmp_path / "skills")
    assert all(action == "installed" for _, action in results)
    assert (tmp_path / "skills" / "wiki-maintain" / "SKILL.md").is_file()


POOL_PAPER = """# Ripple heterogeneity

## Results

Sharp-wave ripples differed in their laminar current sinks across sessions.
"""


def test_lint_resolves_citekeys_and_quotes_in_pools(repo, tmp_path):
    pool_project = tmp_path / "poolproject"
    (pool_project / "bib" / "articles").mkdir(parents=True)
    (pool_project / "bib" / "main.bib").write_text(
        "@article{pool_2025_RippleHeterogeneity,\n  title = {Ripples},\n  doi = {10.1000/pool}\n}\n")
    paper = pool_project / "bib" / "derivatives" / "docling" / "pool_2025_RippleHeterogeneity"
    paper.mkdir(parents=True)
    (paper / "pool_2025_RippleHeterogeneity.md").write_text(POOL_PAPER)
    cfg_file = repo / ".projio" / "biblio" / "biblio.yml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(f"pool:\n  search:\n    - {pool_project / 'bib' / 'articles'}\n")

    cfg = load_wiki_config(repo)
    body = """
# Ripple types

Ripples are not all alike [@pool_2025_RippleHeterogeneity].

## Why it matters

> "Sharp-wave ripples differed in their laminar current sinks across sessions" [@pool_2025_RippleHeterogeneity]

> "Every ripple originates in the dentate gyrus" [@pool_2025_RippleHeterogeneity]

See also [@ghost_1999_Nothing].

## Key facts

## Related
"""
    page = write(cfg.wiki_root / "concepts" / "ripple-types.md",
                 sources="pool_2025_RippleHeterogeneity, ghost_1999_Nothing", body=body)
    findings = lint(cfg, [page])
    by_code = {}
    for f in findings:
        by_code.setdefault(f.code, []).append(f)
    assert "CIT003" in by_code and "pool" in by_code["CIT003"][0].message      # known, but only in a pool
    assert [f.message for f in by_code["CIT001"]] == ["@ghost_1999_Nothing is not in the bibliography or any pool"]
    assert len(by_code.get("FID001", [])) == 1 and "dentate" in by_code["FID001"][0].message
    assert "FID002" not in by_code                                               # pool full text was found


# --- W17: embedded figures -------------------------------------------------

import shutil  # noqa: E402
import subprocess  # noqa: E402

from biblio.wiki.embeds import figure_embed, file_state, find_embeds, apply  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048
FIG_KEY = "sirota_2003_CommunicationNeocortex"


def _figures(repo: Path) -> Path:
    d = repo / "bib" / "derivatives" / "figures" / FIG_KEY
    d.mkdir(parents=True, exist_ok=True)
    (d / "fig-2.png").write_bytes(PNG)
    (d / "manifest.yml").write_text(
        f"citekey: {FIG_KEY}\nfigures:\n"
        "- {index: 3, number: 2, kind: figure, caption: \"Figure 2. Hippocampal  ripples\\n follow up-states.\", "
        "page: 4, file: fig-2.png}\n")
    return d


def test_figure_snippet(repo):
    cfg = load_wiki_config(repo)
    _figures(repo)
    snippet = figure_embed(cfg, FIG_KEY, "2")
    assert snippet == (f"![Figure 2 of {FIG_KEY}](../../../bib/derivatives/figures/{FIG_KEY}/fig-2.png)\n\n"
                       f"*Figure 2. Hippocampal ripples follow up-states.* [@{FIG_KEY}]\n")
    page = cfg.wiki_root / "concepts" / "x.md"
    assert f"(../../../bib/derivatives/figures/{FIG_KEY}/fig-2.png)" in figure_embed(cfg, FIG_KEY, "fig-2", page)
    with pytest.raises(LookupError, match="known: 2"):
        figure_embed(cfg, FIG_KEY, "9")
    with pytest.raises(FileNotFoundError, match="biblio figures run"):
        figure_embed(cfg, "nobody_2000_X", "1")


def test_figure_needs_credit(repo):
    cfg = load_wiki_config(repo)
    _figures(repo)
    rel = f"../../../bib/derivatives/figures/{FIG_KEY}/fig-2.png"
    write(cfg.wiki_root / "concepts" / "uncredited.md", body=f"\n# U\n\nLede.\n\n![Figure 2]({rel})\n")
    write(cfg.wiki_root / "concepts" / "credited.md", sources=f"'@{FIG_KEY}'",
          body="\n# C\n\nLede.\n\n" + figure_embed(cfg, FIG_KEY, "2", cfg.wiki_root / "concepts" / "credited.md"))
    found = lint(cfg)
    assert "IMG003" in codes(found, "concepts/uncredited.md")
    assert not {"IMG003", "LNK004", "IMG001", "IMG002"} & set(codes(found, "concepts/credited.md"))


@pytest.mark.skipif(shutil.which("git-annex") is None, reason="needs git-annex")
def test_annexed_figure_states_and_embeds_command(repo, capsys):
    git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "annex", "init", "test")
    fig = _figures(repo) / "fig-2.png"
    git("annex", "add", str(fig))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fig")
    cfg = load_wiki_config(repo)
    page = cfg.wiki_root / "concepts" / "embeds.md"
    write(page, sources=f"'@{FIG_KEY}'", body="\n# E\n\nLede.\n\n" + figure_embed(cfg, FIG_KEY, "2", page))

    assert file_state(fig) == "locked"
    assert "IMG002" in codes(lint(cfg), "concepts/embeds.md")

    backup = repo / "fig-2.backup"
    backup.write_bytes(fig.read_bytes())
    git("annex", "drop", "--force", str(fig))
    assert file_state(fig) == "absent"
    found = lint(cfg)
    assert "IMG001" in codes(found, "concepts/embeds.md") and "LNK004" not in codes(found, "concepts/embeds.md")

    git("annex", "reinject", str(backup), str(fig))  # the content is back, still locked
    embeds = find_embeds(cfg)
    [(action, paths, code)] = apply(cfg, embeds, get=False, unlock=True)
    assert (action, code) == ("unlock", 0) and file_state(fig) == "file" and embeds[0].state == "file"
    assert not {"IMG001", "IMG002"} & set(codes(lint(cfg), "concepts/embeds.md"))

    with pytest.raises(SystemExit) as exc:
        main(["wiki", "embeds", "--root", str(repo)])
    assert exc.value.code == 0 and "file     bib/derivatives/figures" in capsys.readouterr().out
