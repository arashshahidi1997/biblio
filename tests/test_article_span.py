"""Neighbouring articles in a reprint's docling text (lit-studio R69)."""
from __future__ import annotations

from pathlib import Path

import pytest

from biblio.article_span import article_span

TITLE = "The Human K-Complex Represents an Isolated Cortical Down-State"

# cash_2009_HumanK in the pixecog pool, shortened: cover page, the previous article's tail and
# references, Cash et al., its references, then the next article of the issue.
REPRINT = """\
## The Human K-Complex Represents an Isolated Cortical Down-State

This copy is for your personal, non-commercial use only.

ficed to establish place preference in the absence of other reward. These results establish a causal role.

## References and Notes

1. R. A. Wise, Nat. Rev. Neurosci. 5 , 483 (2004).

## The Human K-Complex Represents an Isolated Cortical Down-State

Sydney S. Cash, Eric Halgren, Nima Dehghani

The K-complex is a large evoked slow wave of the human sleep electroencephalogram. """ + "word " * 300 + """

## Supporting Online Material

www.sciencemag.org/cgi/content/full/324/5930/1084/DC1

## References and Notes

1. M. Steriade, Neuroscience 101, 243 (2000).

## Crystal Structure of the Nuclear Export Receptor CRM1 in Complex with Snurportin1 and RanGTP

Thomas Monecke, 1 * Thomas Güttler, 2 * Piotr Neumann, 1 Achim Dickmanns, 1 Dirk Görlich, 2 † Ralf Ficner 1

CRM1 mediates nuclear export of numerous unrelated cargoes.
"""

# A Cell paper: STAR Methods after the references, then the paper's own supplement.
CELL = """\
## Brain-Wide Dynamics Linking Sensation and Action

Alice Smith, Bob Jones

""" + "word " * 300 + """

## References

Smith, A. (2020). A paper. Neuron 1, 1-2.

## STAR METHODS

## Unit Classification Based on Physiological Features

Units recorded by medial shanks penetrating granule cell layers were classified as dentate units.

## Supplemental Information

## Brain-Wide Dynamics Linking

## Sensation and Action in the Behaving Mouse Brain

Alice Smith, Bob Jones, Carol White

Supplemental Figure S1.
"""


def _lines(text: str) -> list[str]:
    return text.split("\n")


def test_reprint_neighbours_are_found():
    span = article_span(_lines(REPRINT), TITLE)
    lines = _lines(REPRINT)
    assert lines[span.start - 1] == "## The Human K-Complex Represents an Isolated Cortical Down-State"
    assert span.start == 11                                     # the second copy of the title, not the cover
    assert span.previous_references == 7
    assert span.next_article[1].startswith("Crystal Structure")
    assert span.end == span.next_article[0] - 1
    assert span.mixed and not span.contains(5) and span.contains(15)
    assert any("previous article" in r for r in span.reasons())


def test_methods_and_own_supplement_are_not_other_articles():
    span = article_span(_lines(CELL), "Brain-Wide Dynamics Linking Sensation and Action in the Behaving Mouse Brain")
    assert span.start == 1 and span.next_article is None and span.previous_references is None
    assert not span.mixed


def test_without_the_title_nothing_is_flagged():
    span = article_span(_lines(REPRINT), None)
    assert span.start is None and not span.mixed and span.contains(5)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})
    (tmp_path / "bib" / "srcbib").mkdir(parents=True)
    (tmp_path / "bib" / "srcbib" / "main.bib").write_text(
        "@article{cash_2009_HumanK,\n  title = {The Human {K}-Complex Represents an Isolated Cortical Down-State},\n"
        "  year = {2009}\n}\n")
    d = tmp_path / "bib" / "derivatives" / "docling" / "cash_2009_HumanK"
    d.mkdir(parents=True)
    (d / "cash_2009_HumanK.md").write_text(REPRINT)
    return tmp_path


def test_quotes_check_warns_outside_the_article(project, capsys):
    from biblio.cli import main

    q = project / "q.md"
    q.write_text('- q1, cash_2009_HumanK, intro, L5: "ficed to establish place preference in the absence"\n'
                 '- q2, cash_2009_HumanK, abstract, L15: "The K-complex is a large evoked slow wave"\n')
    with pytest.raises(SystemExit) as exc:
        main(["quotes", "check", str(q), "--root", str(project)])
    assert exc.value.code == 0                                  # a warning, not a failure
    out = capsys.readouterr().out
    assert "[WARN] L5 is outside the article (lines 11-" in out
    assert "q2" not in out and "1 outside the cited article" in out


def test_fulltext_span_and_survey(project, capsys):
    from biblio.cli import main

    main(["fulltext", "cash_2009_HumanK", "--span", "--root", str(project)])
    assert "(other articles mixed in)" in capsys.readouterr().out
    main(["fulltext", "--survey", "--format", "tsv", "--root", str(project)])
    rows = capsys.readouterr().out.splitlines()
    assert rows[0].startswith("citekey\t") and rows[1].startswith("cash_2009_HumanK\t11\t")
