"""Docling text artefacts cleaned line for line (journal-club R32)."""
from __future__ import annotations

from pathlib import Path

from biblio.sections import read_fulltext, text_lines
from biblio.textclean import clean_text, describe
from biblio.wiki.fidelity import QuoteChecker

FILLER = ("Ripples in the hippocampus are brief. The hippocampus generates ripples during sleep. "
          "Sharp-wave ripples occur in the hippocampus and are followed by spindles. ") * 3

TEXT = "\n".join([
    "# Paper",
    "Sharp-waveripples(SPW-Rs)inthehippocampusare implied in memory.",
    "a short latency ( /C24 5 ms) negative wave; r = /C0 0.64, 62.9 /C14 ± 4 /C14 , 3 /C2 10, P /C20 0.01",
    "the hippocampal /uniFB01 bers are signi /uniFB01 cant in the /uniFB01 rst place /uniFB01 elds of Grif /uniFB01 n",
    "(Buzs /C19 aki, 2015; Dole /C20 zalov /C19 a) with p &gt; 0.05 and an unknown /C138 glyph",
    "WAKESPW-Rs and designations, housekeeping, drawbridge, author(s), (re)constructive stay as written.",
    FILLER,
])


def test_clean_text_line_for_line():
    clean, subs = clean_text(TEXT)
    lines = text_lines(clean)
    assert len(lines) == len(text_lines(TEXT))
    assert lines[1].startswith("Sharp-wave ripples (SPW-Rs) in the hippocampus are implied")
    assert "(~5 ms)" in lines[2] and "r = −0.64" in lines[2] and "62.9° ± 4°" in lines[2]
    assert "3 × 10" in lines[2] and "P ≤ 0.01" in lines[2]
    assert lines[3] == "the hippocampal fibers are significant in the first place fields of Griffin"
    assert "(Buzsáki, 2015; Doležalová)" in lines[4] and "p > 0.05" in lines[4] and "/C138" in lines[4]
    assert lines[5] == TEXT.split("\n")[5]                      # real words and acronyms untouched
    rules = {s.rule for s in subs}
    assert {"spacing", "symbol", "ligature", "accent", "entity", "unknown-glyph"} <= rules
    assert any("'signi /uniFB01 cant'" in describe(s) or "signi" in describe(s) for s in subs if s.rule == "ligature")


def test_quotes_check_against_clean_and_raw(tmp_path: Path):
    md = tmp_path / "k.md"
    md.write_text(TEXT)
    assert read_fulltext(md, clean=True).split("\n")[3].endswith("Griffin")
    qc = QuoteChecker(lambda k: md)
    assert qc.check("k", "a short latency (~5 ms) negative wave") == "exact"            # as on the slide
    assert qc.check("k", "a short latency ( /C24 5 ms) negative wave") == "exact"       # as docling wrote it
    assert qc.check("k", "the hippocampal fibers are significant in the first") == "exact"
    assert qc.check("k", "the hippocampal /uniFB01 bers are signi /uniFB01 cant") == "exact"
    assert qc.locate("k", "Sharp-wave ripples (SPW-Rs) in the hippocampus are implied")[0] == 2
