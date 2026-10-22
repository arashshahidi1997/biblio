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
    changed = [f.message for f in findings if f.code == "FID004"]
    # exact quotes and formatting noise pass; a fabricated quote is not found; a changed direction word
    # ("increased" -> "rose") is an error of its own
    assert len(fid) == 1 and "moon" in fid[0]
    assert len(changed) == 1 and "'increased' -> 'rose'" in changed[0]
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


def test_observed_in_section_may_name_sessions(repo):
    """SPEC: a pitfall's 'Observed in' points at project cases (found in pixecog W02)."""
    cfg = load_wiki_config(repo)
    write(cfg.wiki_root / "pitfalls" / "edge.md", type="pitfall", body=(
        "\n# Edge\n\nLede.\n\n## Symptom\n\nx\n\n## Cause\n\nx\n\n## How to detect\n\nx\n\n"
        "## Mitigation\n\nx\n\n## Observed in\n\nsub-03 ses-08 hit the window ceiling.\n"))
    assert "SCOPE001" not in codes(lint(cfg), "pitfalls/edge.md")


# --- W02 findings (pixecog layer identification, 2026-10-22) ---------------

def test_code_anchors_in_body_and_snakemake_rules(repo):
    cfg = load_wiki_config(repo)
    (repo / "code").mkdir()
    (repo / "code" / "layers.py").write_text("def identify(x):\n    return x\n")
    (repo / "code" / "Snakefile").write_text("rule hpclayers_identify:\n    input: 'a'\n")
    write(cfg.wiki_root / "tools" / "t.md", type="tool", extra="code: [code/Snakefile::hpclayers_identify]\n",
          body="\n# T\n\nLede uses `code/layers.py::identify` and `code/layers.py::identifyXX`.\n")
    found = [f for f in lint(cfg) if f.page == "tools/t.md" and f.code.startswith("CODE")]
    assert [(f.code, f.line) for f in found] == [("CODE002", found[0].line)]
    assert "identifyXX" in found[0].message and found[0].line > 1


def test_stub_status_keys_and_placeholder_lede(repo):
    cfg = load_wiki_config(repo)
    page = stub(cfg, "x", "concept", status="draft", tags=["event/ripple"])
    text = page.read_text()
    assert "status: draft\n" in text and "evidence: []\n" in text and "code: []\n" in text
    assert "STR003" in codes(lint(cfg), "concepts/x.md")
    page.write_text(text.replace("One-paragraph definition: what this is and why a reader would come here.",
                                 "X is a thing."))
    assert "STR003" not in codes(lint(cfg), "concepts/x.md")


def test_inverse_relations_accepted(repo):
    cfg = load_wiki_config(repo)
    write(cfg.wiki_root / "pitfalls" / "p.md", type="pitfall", status="stub", extra="affects: [m]\n")
    write(cfg.wiki_root / "tools" / "t2.md", type="tool", status="stub", extra="implements: [m]\n")
    write(cfg.wiki_root / "markers" / "m.md", type="marker", status="stub")
    assert not [f for f in lint(cfg) if f.code.startswith("FM") and f.page in ("pitfalls/p.md", "tools/t2.md")]


def test_no_hub_suggestion_for_pages_a_hub_already_lists(repo):
    cfg = load_wiki_config(repo)
    stub(cfg, "ripples", "hub", tags=["event/ripple"])
    for i in range(6):
        stub(cfg, f"c{i}", "concept", tags=["event/ripple", "region/ca1"] if i < 5 else ["region/ca1"])
    sugg = [f.message for f in lint(cfg) if f.code == "SUG003"]
    assert not any("region/ca1" in m for m in sugg)                 # 5 of 6 are under the ripple hub
    for i in range(6, 11):
        stub(cfg, f"c{i}", "concept", tags=["region/ca1"])
    assert any("region/ca1" in f.message for f in lint(cfg) if f.code == "SUG003")


# --- review (W11 part 1) -----------------------------------------------------

from biblio.wiki import review as rv  # noqa: E402


REVIEW_BODY = """
# Ripple coupling

Sharp-wave ripples are coupled to cortical up-states during sleep.

## Why it matters

It links memory replay to cortical state.

## Key facts

> "Neocortical up-states precede hippocampal sharp-wave ripples by about 50 ms" [@sirota_2003_CommunicationNeocortex]

## Related

None yet.
"""


def _reviewable(cfg, name="coupling", flags="[]", body=REVIEW_BODY):
    return write(cfg.wiki_root / "concepts" / f"{name}.md", sources="'@sirota_2003_CommunicationNeocortex'",
                 extra=f"review_flags: {flags}\n", body=body)


def test_set_fields_keeps_other_lines(repo):
    cfg = load_wiki_config(repo)
    page = _reviewable(cfg)
    before = page.read_text()
    rv.set_fields(page, {"status": "reviewed", "reviewed": {"by": "Arash", "date": "2026-10-22"}})
    after = page.read_text()
    assert "..." not in after and "status: reviewed\n" in after and "reviewed: {by: Arash, date: '2026-10-22'}" in after
    kept = [ln for ln in before.split("---", 2)[1].splitlines() if not ln.startswith("status:")]
    assert all(ln in after.split("---", 2)[1].splitlines() for ln in kept)          # other keys byte for byte
    assert after.split("---", 2)[2] == before.split("---", 2)[2]                       # body untouched


def test_accept_rules_and_lint(repo):
    cfg = load_wiki_config(repo)
    page = _reviewable(cfg, flags="['check the n']")
    with pytest.raises(rv.ReviewError, match="reviewer's name"):
        rv.accept(cfg, page, "  ")
    with pytest.raises(rv.ReviewError, match="1 open review flag"):
        rv.accept(cfg, page, "Arash")
    with pytest.raises(rv.ReviewError, match="review it before marking it stable"):
        rv.accept(cfg, page, "Arash", stable=True, resolve_flags=True)
    assert rv.accept(cfg, page, "Arash", resolve_flags=True, on="2026-10-23") == "reviewed by Arash; 1 flag(s) resolved"
    fm = parse_page(page, cfg.wiki_root).frontmatter
    assert fm["status"] == "reviewed" and fm["reviewed"] == {"by": "Arash", "date": "2026-10-23"}
    assert fm["review_flags"] == []
    assert not {"FM004", "FM005"} & set(codes(lint(cfg), "concepts/coupling.md"))
    assert rv.accept(cfg, page, "Arash", stable=True) == "stable by Arash"
    assert "review · concepts/coupling.md · stable by Arash" in (cfg.wiki_root / "log.md").read_text()

    rv.reopen(cfg, page, "rewrote the lede")
    fm = parse_page(page, cfg.wiki_root).frontmatter
    assert fm["status"] == "draft" and fm["reviewed"] is None


def test_accept_refuses_stub_and_lint_errors(repo):
    cfg = load_wiki_config(repo)
    stubbed = stub(cfg, "s", "concept", tags=["event/ripple"])
    with pytest.raises(rv.ReviewError, match="stub"):
        rv.accept(cfg, stubbed, "Arash")
    bad = _reviewable(cfg, "bad", body=REVIEW_BODY + "\n> \"Every ripple originates in the dentate gyrus\" "
                                                      "[@sirota_2003_CommunicationNeocortex]\n")
    with pytest.raises(rv.ReviewError, match="lint error"):
        rv.accept(cfg, bad, "Arash")


def test_flag_and_packet(repo, capsys):
    cfg = load_wiki_config(repo)
    page = _reviewable(cfg, body=REVIEW_BODY + "\n> \"Every ripple originates in the dentate gyrus\" "
                                                "[@sirota_2003_CommunicationNeocortex]\n")
    rv.flag(cfg, page, "  number   of sessions? ")
    assert parse_page(page, cfg.wiki_root).list_field("review_flags") == ["number of sessions?"]
    text = rv.packet(cfg, page)
    assert "- [ ] number of sessions?" in text and "NOT FOUND in source" in text
    assert "@sirota_2003_CommunicationNeocortex: project" in text
    assert [p.name for p in rv.queue(cfg)] == ["coupling.md"]

    main(["wiki", "review", "packet", "--root", str(repo)])
    assert "## " in capsys.readouterr().out
    main(["wiki", "review", "flag", "coupling", "second", "--root", str(repo)])
    with pytest.raises(SystemExit):
        main(["wiki", "review", "accept", "coupling", "--by", "Arash", "--root", str(repo)])
    assert "lint error" in capsys.readouterr().err                   # the bad quote blocks acceptance first
    page.write_text(page.read_text().replace('> "Every ripple originates in the dentate gyrus"', "Removed."))
    with pytest.raises(SystemExit):
        main(["wiki", "review", "accept", "coupling", "--by", "Arash", "--root", str(repo)])
    assert "2 open review flag" in capsys.readouterr().err


def test_skills_dir_entry_point_target():
    """projio finds biblio's skills through [project.entry-points."projio.skills"] (W15)."""
    import tomllib
    from biblio.skills_bundle import skills_dir
    pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert pyproject["project"]["entry-points"]["projio.skills"]["biblio"] == "biblio.skills_bundle:skills_dir"
    assert {p.parent.name for p in skills_dir().glob("*/SKILL.md")} >= {"wiki-ingest", "wiki-review", "zotero-add"}


# --- R13: only exact quotes are verified (journal-club trial) -------------------

SOURCE_TEXT = ("Results. C2 ripples were less affected by the cortical plasticity manipulation and became "
               "more numerous, while C4 ripples had the longest duration of all identif ied classes "
               "(n = 12 rats). The ref lected wave was not detected in sham animals.")


@pytest.mark.parametrize("quote,status", [
    ("C2 ripples were less affected by the cortical plasticity manipulation", "exact"),
    ("C4 ripples had the longest duration of all identified classes", "exact"),        # ligature split
    ("The reflected wave was not detected in sham animals", "exact"),
    ("C2 ripples were more affected by the cortical plasticity manipulation", "changed"),
    ("C2 ripples were not affected by the cortical plasticity manipulation", "changed"),
    ("C4 ripples had the longest duration of all identified classes (n = 14 rats)", "changed"),
    ("The reflected wave was detected in sham animals", "changed"),                     # dropped 'not'
    ("C2 ripples were less influenced by the cortical plasticity manipulation", "approximate"),
    ("Gamma bursts dominate the neocortex during waking hours", "missing"),
    ("ripples were less", "exact"),
])
def test_quote_statuses(tmp_path, quote, status):
    f = tmp_path / "p.md"
    f.write_text(SOURCE_TEXT)
    m = QuoteChecker(lambda key: f).match("k", quote)
    assert m.status == status, m


def test_approximate_quote_reports_diff_and_scattered_words_do_not_match(tmp_path):
    f = tmp_path / "p.md"
    f.write_text(SOURCE_TEXT)
    checker = QuoteChecker(lambda key: f)
    m = checker.match("k", "C2 ripples were less influenced by the cortical plasticity manipulation")
    assert "'affected' -> 'influenced'" in m.diff
    # every 3-word chunk exists somewhere, but not as one passage: the old check passed this
    assert checker.check("k", "C4 ripples were less affected by the cortical plasticity manipulation and "
                              "became more numerous") in ("changed", "approximate", "missing")
    assert checker.check("k", "were less affected by the longest duration of all identified classes") == "missing"


def test_lint_and_packet_mark_fidelity(repo):
    cfg = load_wiki_config(repo)
    body = REVIEW_BODY + ('\n> "Neocortical up-states precede hippocampal sharp-wave ripples by about 60 ms" '
                          '[@sirota_2003_CommunicationNeocortex]\n'
                          '\n> "Neocortical up-states precede hippocampal sharp-wave ripples by roughly 50 ms" '
                          '[@sirota_2003_CommunicationNeocortex]\n')
    page = _reviewable(cfg, body=body)
    found = {f.code: f for f in lint(cfg, [page])}
    assert "FID004" in found and "'50' -> '60'" in found["FID004"].message
    assert "FID003" in found and found["FID003"].severity == "warning"
    text = rv.packet(cfg, page)
    assert "verified exact" in text and "MEANING CHANGED" in text and "APPROXIMATE" in text


# --- journal-club trial: R09 R10 R11 R12 ------------------------------------------

def test_init_tag_ignores_bibliography_tag_vocab(tmp_path):
    """R09: .projio/biblio/tag_vocab.yml (namespace:value) must not shadow the new wiki's vocab.yml."""
    tv = tmp_path / ".projio" / "biblio" / "tag_vocab.yml"
    tv.parent.mkdir(parents=True)
    tv.write_text("namespaces:\n  task: {values: [x]}\n  corpus: {values: [y]}\n")
    cfg = load_wiki_config(tmp_path)
    assert cfg.vocab == tv                                  # the fallback, before the skeleton exists
    init(cfg, subject="sleep-coupling", tags=["event/spindle", "state/nrem-sleep"])
    assert "values: [spindle]" in (cfg.wiki_root / "vocab.yml").read_text()
    assert "spindle" not in tv.read_text()


def test_stub_quotes_titles_and_tags(repo):
    """R10: a colon in a title must not break the frontmatter."""
    cfg = load_wiki_config(repo)
    page = stub(cfg, "aleman-2026", "source", title="Aleman-Zapata et al. 2026: ripple subtypes",
                tags=["event/ripple"], status="draft")
    assert "title: 'Aleman-Zapata et al. 2026: ripple subtypes'" in page.read_text()
    assert parse_page(page, cfg.wiki_root).title == "Aleman-Zapata et al. 2026: ripple subtypes"
    assert "FM001" not in codes(lint(cfg, [page]), "sources/aleman-2026.md")


def test_lint_folder_arguments_expand_and_unmatched_fail(repo, capsys):
    """R11: a folder used to check nothing and report 0 errors."""
    cfg = load_wiki_config(repo)
    write(cfg.wiki_root / "concepts" / "bad.md", status="reviewed", body="\n# Bad\n\nLede.\n")
    with pytest.raises(SystemExit) as exc:
        main(["wiki", "lint", "concepts", "--root", str(repo)])
    out = capsys.readouterr().out
    assert exc.value.code == 1 and "FM004" in out and "1 pages:" in out
    with pytest.raises(SystemExit) as exc:
        main(["wiki", "lint", "no/such/folder", "--root", str(repo)])
    assert exc.value.code == 2 and "no wiki page matches" in capsys.readouterr().err


def test_lint_reads_srcbib_without_merged_bib(tmp_path):
    """R12: before `biblio bibtex merge`, the project's own papers are known from bib/srcbib."""
    src = tmp_path / "bib" / "srcbib"
    src.mkdir(parents=True)
    (src / "jc.bib").write_text("@article{aleman_2026_Deltas,\n  title = {Deltas},\n  year = {2026}\n}\n")
    cfg = load_wiki_config(tmp_path)
    init(cfg)
    write(cfg.wiki_root / "concepts" / "c.md", sources="aleman_2026_Deltas", tags="",
          body="\n# C\n\nCites [@aleman_2026_Deltas].\n")
    found = lint(cfg)
    assert "CIT001" not in codes(found, "concepts/c.md") and "CIT005" not in codes(found)


# --- R15: what a reviewer needs in the packet ------------------------------------

PACKET_BODY = """
# Ripple coupling

Sharp-wave ripples are coupled to cortical up-states during sleep.

## Why it matters

It links memory replay to cortical state.

## Key facts

- **Order**: cortical up-states come first, by about 50 ms, in
  sleeping rats.

> "Neocortical up-states precede hippocampal sharp-wave ripples by about 50 ms" [@sirota_2003_CommunicationNeocortex]

- The coupling holds in 80 % of sessions [@sirota_2003_CommunicationNeocortex].

## Our experience

We saw a 120 ms lag (result-20260611-163058).

## Related

None yet.
"""


def test_packet_has_claims_locations_unbacked_and_numbers(repo):
    cfg = load_wiki_config(repo)
    stub(cfg, "ripples", "hub", tags=["event/ripple"])
    page = _reviewable(cfg, body=PACKET_BODY)
    text = rv.packet(cfg, page)
    claims = text.split("### Claims and their quotes")[1].split("###")[0]
    # 1: the whole wrapped bullet is the claim; 2: section and line of the quote in the paper
    assert "claim: - **Order**: cortical up-states come first, by about 50 ms, in sleeping rats." in claims
    assert "verified exact in Results, `bib/derivatives/docling/sirota_2003_CommunicationNeocortex/" \
           "sirota_2003_CommunicationNeocortex.md:5`" in claims
    # 4: a citation with no quote behind it
    unbacked = text.split("### Citations without a quote")[1].split("###")[0]
    assert "(1)" in unbacked and "80 % of sessions" in unbacked
    # 5: numbers: 80 is not in the paper; 50 is; project numbers are labeled
    numbers = text.split("### Numbers")[1].split("###")[0]
    assert "**80** not in the cited papers" in numbers
    assert "120 (project result" in numbers and "every number found" in numbers
    # 7, 8: placement and history
    assert "hubs: hubs/hub-ripples.md" in text and "### History" in text


def test_packet_pool_only_citation_and_figure(repo, tmp_path):
    cfg = load_wiki_config(repo)
    pool_project = tmp_path / "poolproject"
    (pool_project / "bib" / "articles").mkdir(parents=True)
    (pool_project / "bib" / "main.bib").write_text("@article{pool_2025_X,\n  title = {X},\n  doi = {10.1/x}\n}\n")
    cfg_file = repo / ".projio" / "biblio" / "biblio.yml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(f"pool:\n  search:\n    - {pool_project / 'bib' / 'articles'}\n")
    _figures(repo)
    page = _reviewable(cfg, body=REVIEW_BODY + "\nAlso [@pool_2025_X].\n\n"
                       + figure_embed(cfg, FIG_KEY, "2", cfg.wiki_root / "concepts" / "coupling.md"))
    text = rv.packet(cfg, page)
    assert "@pool_2025_X: pool only (" in text and "add to the project bibliography" in text
    assert "### Figures (1)" in text and "fig-2.png` (file)" in text
