"""Citekey aliases across pools (lit-studio R66)."""
from __future__ import annotations

from pathlib import Path

import pytest

from biblio.aliases import add_alias, load_aliases
from biblio.bibtex import BibtexMergeConfig, merge_srcbib
from biblio.cli import main

PAPER = """# Coordinated memory replay

## Results

Replay in the visual cortex was coordinated with hippocampal replay during slow-wave sleep.
"""

OLD, NEW = "ji_2006_CoordinatedMemory", "ji_2007_CoordinatedMemory"


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


def test_alias_file_roundtrip_and_rules(tmp_path: Path) -> None:
    assert not load_aliases(tmp_path)
    add_alias(tmp_path, NEW, OLD)
    al = load_aliases(tmp_path)
    assert al.canonical(OLD) == NEW and al.canonical(NEW) == NEW and al.canonical("x") == "x"
    assert al.equivalents(OLD) == [OLD, NEW]
    assert al.equivalents(NEW) == [NEW, OLD]
    with pytest.raises(ValueError):
        add_alias(tmp_path, OLD, "z_2000_Z")          # an alias cannot become canonical
    with pytest.raises(ValueError):
        add_alias(tmp_path, "z_2000_Z", NEW)          # nor a canonical key an alias


def _pool_repo(tmp_path: Path) -> Path:
    """lit-studio cites ji_2007; the pixecog pool holds the paper as ji_2006."""
    pool = tmp_path / "pixecog"
    (pool / "bib" / "articles").mkdir(parents=True)
    (pool / "bib" / "main.bib").write_text(f"@article{{{OLD},\n  title = {{Replay}},\n  doi = {{10.1038/nn1825}}\n}}\n")
    d = pool / "bib" / "derivatives" / "docling" / OLD
    d.mkdir(parents=True)
    (d / f"{OLD}.md").write_text(PAPER)
    repo = tmp_path / "lit"
    (repo / "bib").mkdir(parents=True)
    (repo / "bib" / "main.bib").write_text(f"@article{{{NEW},\n  title = {{Replay}},\n  year = {{2007}}\n}}\n")
    cfg_file = repo / ".projio" / "biblio" / "biblio.yml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(f"pool:\n  search:\n    - {pool / 'bib' / 'articles'}\n")
    return repo


def test_fulltext_and_quotes_resolve_through_an_alias(tmp_path: Path) -> None:
    from biblio.config import default_config_path, load_biblio_config
    from biblio.quotes import check_quotes, parse_quotes
    from biblio.sections import fulltext_path

    repo = _pool_repo(tmp_path)
    cfg = load_biblio_config(default_config_path(root=repo), root=repo)
    assert fulltext_path(cfg, NEW) is None
    add_alias(repo, NEW, OLD)
    assert fulltext_path(cfg, NEW).name == f"{OLD}.md"
    items, _ = parse_quotes(f'- q1, {NEW}, results, L5: "Replay in the visual cortex was coordinated"\n')
    assert check_quotes(cfg, items)[0].status == "exact"


def test_wiki_lint_treats_alias_and_canonical_as_one_paper(tmp_path: Path) -> None:
    from biblio.wiki.lint import lint
    from biblio.wiki.scaffold import init
    from biblio.wiki.schema import load_wiki_config

    repo = _pool_repo(tmp_path)
    add_alias(repo, NEW, OLD)
    cfg = load_wiki_config(repo)
    init(cfg)
    page = cfg.wiki_root / "concepts" / "replay.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: Replay\ntype: concept\nscope: general\nstatus: draft\nauthor: llm\nupdated: 2026-11-10\n"
        f"tags: []\nsources: [{NEW}]\n---\n\n# Replay\n\nCortex replays with the hippocampus [@{OLD}].\n\n"
        f'> "Replay in the visual cortex was coordinated with hippocampal replay" [@{NEW}]\n')
    found = {f.code: f for f in lint(cfg, [page])}
    assert "CIT001" not in found and "CIT002" not in found and "CIT004" not in found
    assert not any(c.startswith("FID") and found[c].severity == "error" for c in found)
    assert NEW in found["CIT006"].message


def _merge_cfg(root: Path) -> BibtexMergeConfig:
    src = root / "bib" / "srcbib"
    src.mkdir(parents=True)
    (src / "zotero.bib").write_text(f"@article{{{NEW}, title={{Replay}}, doi={{10.1038/nn1825}}}}\n")
    (src / "src-pixecog.bib").write_text(
        f"@article{{{OLD}, title={{Replay}}, doi={{https://doi.org/10.1038/NN1825}}}}\n"
        "@article{other_2020_X, title={X}, doi={10.1/x}}\n")
    return BibtexMergeConfig(
        repo_root=root, src_dir=src, src_glob="*.bib", out_bib=root / "bib" / "main.bib",
        file_field_mode="drop", file_field_template="", duplicates_log=root / "bib" / "logs" / "dup.txt")


def test_merge_collapses_aliases_only_when_asked(tmp_path: Path) -> None:
    cfg = _merge_cfg(tmp_path)
    add_alias(tmp_path, NEW, OLD)
    kept = merge_srcbib(cfg)
    assert kept[1] == 3 and len(kept.doi_duplicates) == 1 and kept.collapsed == {}

    res = merge_srcbib(cfg, collapse_aliases=True)
    assert res[1] == 2 and res.doi_duplicates == [] and res.collapsed == {OLD: NEW}
    assert OLD not in cfg.out_bib.read_text() and NEW in cfg.out_bib.read_text()


def test_merge_keeps_an_alias_with_another_doi(tmp_path: Path) -> None:
    cfg = _merge_cfg(tmp_path)
    add_alias(tmp_path, NEW, "other_2020_X")
    res = merge_srcbib(cfg, collapse_aliases=True)
    assert res.collapsed == {} and "other_2020_X kept" in res.alias_warnings[0]


def test_cli_citekey_alias(tmp_path: Path, capsys) -> None:
    main(["citekey", "alias", "--root", str(tmp_path), NEW, OLD])
    main(["citekey", "alias", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert f"{OLD} -> {NEW}" in out.splitlines()[-1]
    with pytest.raises(SystemExit):
        main(["citekey", "alias", "--root", str(tmp_path), OLD, "z_2000_Z"])
