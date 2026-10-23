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
