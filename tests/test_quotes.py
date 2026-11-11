"""`biblio quotes check` and one line numbering for full texts (journal-club R29)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from biblio import cli
from biblio.config import default_config_path, load_biblio_config
from biblio.quotes import check_file, parse_quotes
from biblio.sections import read_fulltext, text_lines
from biblio.wiki.fidelity import QuoteChecker

A, B = "smith_2020_Ripples", "jones_2019_Spindles"
# a stray carriage return on line 2: universal newlines would count it as a line break
PAPER_A = ("# Ripples\n\nIntro text with a stray\rcarriage return.\n\n## Results\n\n"
           "Ripples were less frequent after the lesion in all rats.\n\n"
           "Spindles followed ripples by about 200 ms.\n")
PAPER_B = "# Spindles\n\n## Discussion\n\nSpindles are generated in the thalamus.\n"

SOURCE = f"""# Sources

**Ripples.**
- R1, {A}, Results, L7: "Ripples were less frequent after the lesion" — exact (rat)
- R2, same, L9: "Spindles followed ripples by about 200 ms." — exact
- R3, same, "Results, again", L3: "Ripples were more frequent after the lesion" — exact

Physiology ({B}, a review):
- R4, Discussion, L5: "Spindles are generated in the thalamus." — exact
- R5 (above), L5 (model): "Spindles are generated in the thalamus" — exact
- R6: "a quote from a paper with no docling text" — exact
"""


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


@pytest.fixture
def cfg(tmp_path: Path):
    for key, text in ((A, PAPER_A), (B, PAPER_B)):
        d = tmp_path / "bib" / "derivatives" / "docling" / key
        d.mkdir(parents=True)
        (d / f"{key}.md").write_bytes(text.encode())
    return load_biblio_config(default_config_path(root=tmp_path), root=tmp_path)


def test_line_numbering_ignores_carriage_returns(cfg):
    md = cfg.out_root / A / f"{A}.md"
    lines = text_lines(read_fulltext(md))
    assert lines[6].startswith("Ripples were less")            # grep -n line 7
    qc = QuoteChecker(lambda k: md)
    assert qc.locate(A, "Ripples were less frequent after the lesion") == (7, "Results")


def test_parse(tmp_path):
    items, unchecked = parse_quotes(SOURCE)
    assert [(i.id, i.citekey, i.section, i.line) for i in items] == [
        ("R1", A, "Results", 7), ("R2", A, "", 9), ("R3", A, "Results, again", 3),
        ("R4", B, "Discussion", 5), ("R5 (above)", B, "", 5)]
    assert items[0].claimed == "exact" and unchecked == [11]


def test_check_file_and_fix_lines(cfg, tmp_path, capsys):
    src = tmp_path / "sources.md"
    src.write_text(SOURCE)
    results, _ = check_file(cfg, src)
    by = {r.id: r for r in results}
    assert by["R1"].status == "exact" and by["R1"].line == 7 and by["R1"].where == "project"
    assert by["R3"].status == "changed" and "more" in by["R3"].diff and by["R3"].line == 7
    assert by["R4"].line == 5 and by["R4"].heading == "Discussion"
    out = tmp_path / "r.json"
    with pytest.raises(SystemExit) as exc:
        cli.main(["quotes", "check", str(src), "--json", str(out), "--fix-lines", "--root", str(tmp_path)])
    assert exc.value.code == 1                                   # R3 is not exact
    assert json.loads(out.read_text())[str(src)][2]["status"] == "changed"
    assert 'R3, same, "Results, again", L7:' in src.read_text()  # L3 rewritten to the located line
    assert "not checked (no L<n>)" in capsys.readouterr().out


def test_a_second_version_of_a_paper_is_checked_too(cfg, tmp_path):
    """R38: <key>@published beside <key>; a quote found in either passes, and says where."""
    pub = cfg.out_root / f"{A}@published"
    pub.mkdir()
    (pub / f"{A}@published.md").write_text("# Ripples (published)\n\n## Conditions\n\n"
                                            "Under the new conditions ripples doubled in every rat.\n")
    src = tmp_path / "v.md"
    src.write_text(f'- V1, {A}, L7: "Ripples were less frequent after the lesion" — exact\n'
                   f'- V2, same, L5: "Under the new conditions ripples doubled in every rat." — exact\n')
    results, _ = check_file(cfg, src)
    by = {r.id: r for r in results}
    assert by["V1"].status == "exact" and by["V1"].version == "" and by["V1"].line == 7
    assert by["V2"].status == "exact" and by["V2"].version == "published" and by["V2"].line == 5
    from biblio.wiki.fidelity import QuoteChecker
    qc = QuoteChecker(lambda k: cfg.out_root / k / f"{k}.md")
    assert qc.versions(A) == ["", "published"]
    from biblio.sections import read_sections
    assert [s.title for s in read_sections(cfg, f"{A}@published")[0]] == ["Conditions"]


# ── --text: any quoted string against named texts (the claim format of an answer or digest) ──

ANSWER = f"""---
paper: {A}
note: "a frontmatter value that is not checked"
---
- **measured** — Ripples dropped after the lesion (rat, n = 4). "Ripples were less frequent after the lesion in all rats" (Results)
- **derived** — Timing. "Spindles followed ripples … about 200 ms" (Results)
- **interpreted** — "Spindles followed ripples by about 900 ms" (Results)
- short "too short" quotes are not checked
"""


def test_text_mode_checks_every_quote_against_a_path_and_a_key(cfg, tmp_path):
    from biblio.quotes import check_against, free_quotes
    page = tmp_path / "answer.md"
    page.write_text(ANSWER, encoding="utf-8")
    assert [n for n, _ in free_quotes(ANSWER)] == [5, 6, 7]       # frontmatter and short quotes skipped
    paper = cfg.out_root / A / f"{A}.md"
    for source in (str(paper), A):                                   # a path or a held citekey
        results = check_against(cfg, page, [source])
        assert [r.status for r in results][:2] == ["exact", "exact"]
        assert results[2].status != "exact"                          # one changed number fails
        assert results[0].line == 7                                  # located as grep -n counts


def test_text_mode_cli_exit_status(cfg, tmp_path, capsys):
    page = tmp_path / "answer.md"
    page.write_text(ANSWER, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli.main(["quotes", "check", str(page), "--text", A, "--root", str(tmp_path)])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "3 quotes; 2 exact" in out and "900 ms" in out
    page.write_text(ANSWER.replace("900 ms", "200 ms"), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cli.main(["quotes", "check", str(page), "--text", A, "--text", B, "--root", str(tmp_path)])
    assert exc.value.code == 0


def test_text_mode_unknown_source(cfg, tmp_path):
    page = tmp_path / "answer.md"
    page.write_text(ANSWER, encoding="utf-8")
    with pytest.raises(SystemExit, match="no text for: nobody_2000_Missing"):
        cli.main(["quotes", "check", str(page), "--text", "nobody_2000_Missing", "--root", str(tmp_path)])
