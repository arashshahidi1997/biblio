"""Reading by section (D01), the digest store (D02) and claims mode (D05, journal-club R06)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from biblio import digest as dg
from biblio.config import default_config_path, load_biblio_config
from biblio.sections import read_sections, split_markdown, split_tei

KEY = "aleman_2026_Deltas"
PAPER = """# Deltas and spindles

## Abstract

Ripples come in three types.

## Results

<!-- image -->

C2 ripples were less affected by the cortical plasticity manipulation and became more numerous.
C3 ripples occurred within spindles in both the hippocampus and the prefrontal cortex (n = 3 rats).

## Discussion

Small ripples after deltas may reflect a cortical query of the hippocampus.

## Author contr ibutions

A wrote it.

## References

1. Someone 2020.
"""


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


@pytest.fixture
def cfg(tmp_path: Path):
    d = tmp_path / "bib" / "derivatives" / "docling" / KEY
    d.mkdir(parents=True)
    (d / f"{KEY}.md").write_text(PAPER)
    return load_biblio_config(default_config_path(root=tmp_path), root=tmp_path)


def test_split_markdown_drops_references_and_admin():
    secs = split_markdown(PAPER)
    assert [s.title for s in secs] == ["Abstract", "Results", "Discussion"]   # the title heading has no body
    results = next(s for s in secs if s.title == "Results")
    assert results.id.startswith("S") and "<!-- image -->" not in results.text and results.line == 7


def test_split_tei_and_fallback(cfg, tmp_path):
    tei = """<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><profileDesc><abstract><p>Short.</p></abstract>
    </profileDesc></teiHeader><text><body><div><head>Results</head><p>C3 ripples sit in spindles.</p></div>
    <div><head>Acknowledgements</head><p>Thanks.</p></div></body></text></TEI>"""
    assert [s.title for s in split_tei(tei)] == ["Abstract", "Results"]
    other = "other_2020_X"
    g = tmp_path / "bib" / "derivatives" / "grobid" / other
    g.mkdir(parents=True)
    (g / f"{other}.tei.xml").write_text(tei)
    secs, source, kind = read_sections(cfg, other)
    assert kind == "grobid" and source.name.endswith(".tei.xml") and secs[1].title == "Results"
    with pytest.raises(FileNotFoundError, match="docling"):
        read_sections(cfg, "nobody_2000_Nothing")


def _fake_llm(responses):
    calls = []

    def llm(*, system, prompt, model, max_tokens):
        calls.append(prompt)
        return {"text": responses[len(calls) - 1], "error": None}
    llm.calls = calls
    return llm


def _secs(cfg):
    return {s.title: s.id for s in read_sections(cfg, KEY)[0]}


def test_claims_digest_verifies_and_repairs_quotes(cfg):
    ids = _secs(cfg)
    first = json.dumps({
        "question": "Do ripple types differ?",
        "setup": ["8 rats, tetrodes"],
        "claims": [
            {"id": "C1", "claim": "C3 ripples sit in spindles.", "kind": "finding", "evidence": "Fig 2, n = 3 rats",
             "caveats": "reader: 3 animals", "section": ids["Results"],
             "quote": "C3 ripples occurred within spindles in both the hippocampus and the prefrontal cortex"},
            {"id": "C2", "claim": "C2 ripples are robust to plasticity.", "kind": "finding", "evidence": "Fig 6",
             "caveats": "", "section": ids["Results"],
             "quote": "C2 ripples were more affected by the cortical plasticity manipulation"},
            {"id": "C3", "claim": "Cortex queries the hippocampus.", "kind": "interpretation", "evidence": "",
             "caveats": "authors: speculative", "section": ids["Discussion"],
             "quote": "the cortex sends a query to the hippocampus during deltas"},
        ],
        "one_line": "Ripple types map onto different cortical dialogues.",
    })
    repair = json.dumps({"quotes": {
        "C2": "C2 ripples were less affected by the cortical plasticity manipulation",
        "C3": "Small ripples after deltas may reflect a cortical querying",       # still not exact
    }})
    llm = _fake_llm([first, "```json\n" + repair + "\n```"])
    d = dg.digest_claims(cfg, KEY, llm=llm, model="test-model")

    claims = {c["id"]: c for c in d["claims"]}
    assert claims["C1"]["quote_status"] == "exact"
    assert claims["C2"]["quote_status"] == "exact" and "less affected" in claims["C2"]["quote"]   # repaired
    assert claims["C3"]["quote_status"] in ("missing", "approximate")                            # stays flagged
    assert d["meta"]["repaired"] == 1 and d["meta"]["quotes"]["exact"] == 2
    assert claims["C1"]["section_title"] == "Results" and claims["C1"]["section_line"] == 7
    assert "[S" in llm.calls[0] and "Author contr" not in llm.calls[0] and "Someone 2020" not in llm.calls[0]
    assert "C1: C3 ripples" not in llm.calls[1] and "C2: C2 ripples" in llm.calls[1]           # repair: bad ones only

    json_path, md_path = dg.digest_paths(cfg, KEY, "claims", "wiki")
    assert json_path.is_file() and json.loads(json_path.read_text())["meta"]["prompt_version"] == dg.PROMPT_VERSION
    md = md_path.read_text()
    assert f'> "C3 ripples occurred within spindles in both the hippocampus and the prefrontal cortex" [@{KEY}]' in md
    assert "quote exact" in md and "## In one line" in md and "Rigor notes" not in md

    # stored digests are reused; --force redoes them
    assert dg.digest_claims(cfg, KEY, llm=_fake_llm([])) == json.loads(json_path.read_text())
    assert [r["context"] for r in dg.list_digests(cfg)] == ["wiki"]


def test_talk_context_adds_rigor_and_figure_roles(cfg):
    ids = _secs(cfg)
    resp = json.dumps({
        "question": "q", "setup": [], "one_line": "x",
        "claims": [{"id": "C1", "claim": "c", "kind": "finding", "evidence": "e", "caveats": "",
                    "section": ids["Results"], "quote": "C3 ripples occurred within spindles"}],
        "rigor_notes": [{"note": "events as samples inflate the df", "claims": ["C1"], "section": ids["Results"],
                         "quote": "C3 ripples occurred within spindles in both the hippocampus"},
                        {"note": "only 3 vehicle rats but 8 animals in the Methods", "claims": ["C1"],
                         "section": ids["Results"], "quote": "eight vehicle rats were recorded for the analysis"}],
        "figure_roles": [{"figure": "Figure 1", "role": "the three ripple types"}],
    })
    llm = _fake_llm([resp])
    d = dg.digest_claims(cfg, KEY, context="talk", llm=llm)
    assert "rigor_notes" in llm.calls[0]
    good, wrong = d["rigor_notes"]
    assert good["quote_status"] == "exact" and wrong["quote_status"] != "exact"   # a misread note shows up
    md = dg.digest_paths(cfg, KEY, "claims", "talk")[1].read_text()
    assert "## Rigor notes for discussion" in md and "**Figure 1**: the three ripple types" in md
    assert "rests on" in md and "quote MISSING" in md


def test_llm_errors_and_bad_json(cfg):
    with pytest.raises(RuntimeError, match="LLM call failed"):
        dg.digest_claims(cfg, KEY, llm=lambda **kw: {"text": None, "error": "quota"})
    with pytest.raises(ValueError, match="no JSON"):
        dg.digest_claims(cfg, KEY, llm=_fake_llm(["sorry, I cannot"]))
    with pytest.raises(ValueError, match="unknown context"):
        dg.digest_claims(cfg, KEY, context="poster")


def test_claude_cli_errors_on_stdout_are_reported(monkeypatch):
    """An expired login is printed on stdout; it must reach the user, with the fix."""
    import subprocess
    from biblio import llm
    monkeypatch.setattr(llm, "_find_claude_cli", lambda: "/usr/bin/claude")
    seen = {}

    def run(cmd, **kw):
        seen["cwd"] = kw.get("cwd")
        return subprocess.CompletedProcess(cmd, 1, stdout="Failed to authenticate: OAuth session expired", stderr="")
    monkeypatch.setattr(llm.subprocess, "run", run)
    out = llm._call_claude_cli(system="s", prompt="p", model="sonnet", max_tokens=10)
    assert "OAuth session expired" in out["error"] and "/login" in out["error"]
    assert seen["cwd"] and "biblio-llm-" in seen["cwd"]          # never the user's project


def test_claims2_verifies_caveats_terms_and_inconsistencies(cfg):
    ids = _secs(cfg)
    resp = json.dumps({
        "question": "q", "setup": [], "one_line": "x",
        "claims": [{"id": "C1", "claim": "c", "kind": "finding", "evidence": "e", "section": ids["Results"],
                    "quote": "C3 ripples occurred within spindles",
                    "caveats": [{"by": "authors", "text": "speculative", "section": ids["Discussion"],
                                 "quote": "Small ripples after deltas may reflect a cortical query"},
                                {"by": "reader", "text": "3 animals"}]}],
        "terms": [{"term": "C2 ripple", "layer": "derived", "definition": "less affected cluster", "differs": "",
                   "section": ids["Results"], "quote": "C2 ripples were less affected by the cortical plasticity"}],
        "inconsistencies": [{"what": "abstract vs results", "passages": [
            {"section": ids["Abstract"], "quote": "Ripples come in three types."},
            {"section": ids["Results"], "quote": "Ripples come in seven types everywhere."}]}],
    })
    d = dg.digest_claims(cfg, KEY, llm=_fake_llm([resp]))
    cav = d["claims"][0]["caveats"]
    assert cav[0]["quote_status"] == "exact" and "quote_status" not in cav[1]     # reader caveats: no quote
    assert d["terms"][0]["quote_status"] == "exact"
    assert [p["quote_status"] for p in d["inconsistencies"][0]["passages"]] == ["exact", "missing"]
    assert d["meta"]["prompt_version"] == "claims-2"
    md = dg.digest_paths(cfg, KEY, "claims", "wiki")[1].read_text()
    assert "## Terms" in md and "**C2 ripple**" in md and "## Internal inconsistencies" in md
    assert "authors: speculative (exact)" in md and "reader: 3 animals" in md


def test_claims_batch_skips_redoes_stale_and_reports(cfg):
    ids = _secs(cfg)
    reply = json.dumps({"claims": [{"id": "C1", "claim": "C3 in spindles.", "kind": "finding", "section": ids["Results"],
                                    "quote": "C3 ripples occurred within spindles in both the hippocampus"}],
                        "terms": [{"term": "C3", "quote": "C3 ripples occurred within spindles"}]})
    llm = _fake_llm([reply] * 4)
    s = dg.digest_claims_batch(cfg, [KEY, "nobody_2000_Nothing"], llm=llm, model="m")
    assert [r["status"] for r in s["rows"]] == ["done", "failed"] and s["failed"] == 1
    assert s["claims"] == 1 and s["quotes"] == 2 and s["quotes_exact"] == 2
    assert Path(s["path"]).is_file() and "| aleman_2026_Deltas | done |" in Path(s["path"]).read_text()
    assert len(dg.list_digests(cfg)) == 1                 # the run summary is not listed as a digest

    s = dg.digest_claims_batch(cfg, [KEY], llm=llm, model="m")
    assert s["rows"][0]["status"] == "skipped (exists)" and len(llm.calls) == 1
    json_path, _ = dg.digest_paths(cfg, KEY, "claims", "wiki")
    d = json.loads(json_path.read_text())
    d["meta"]["prompt_version"] = "claims-1"
    json_path.write_text(json.dumps(d))
    s = dg.digest_claims_batch(cfg, [KEY], llm=llm, model="m", stale=True)
    assert s["rows"][0]["status"] == "done" and len(llm.calls) == 2


def test_claims_table_filters_across_digests(cfg):
    for ctx, key, claims in (
        ("wiki", "a_2020_X", [{"id": "C1", "claim": "Spindles follow ripples.", "kind": "finding",
                               "section_title": "Results", "quote": "q1", "quote_status": "exact"},
                              {"id": "C2", "claim": "Deltas precede spindles.", "kind": "interpretation",
                               "section_title": "Discussion", "quote": "q2", "quote_status": "missing"}]),
        ("talk", "b_2021_Y", [{"id": "C1", "claim": "Ripples | spindles couple.", "kind": "finding",
                               "section_title": "Results", "section_line": 40, "quote": "q3", "quote_status": "exact",
                               "caveats": [{"text": "only 3 rats", "quote": "n = 3"}]}]),
    ):
        path, _ = dg.digest_paths(cfg, key, "claims", ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"meta": {}, "claims": claims}))
    rows = dg.claims_table(cfg, grep="spindle")
    assert [(r["citekey"], r["id"]) for r in rows] == [("a_2020_X", "C1"), ("a_2020_X", "C2"), ("b_2021_Y", "C1")]
    assert [r["id"] for r in dg.claims_table(cfg, kind="interpretation")] == ["C2"]
    assert [r["citekey"] for r in dg.claims_table(cfg, section="result", exact_only=True)] == ["a_2020_X", "b_2021_Y"]
    assert dg.claims_table(cfg, grep="3 rats")[0]["caveats"] == "only 3 rats"
    md = dg.claims_table_markdown(dg.claims_table(cfg, ["b_2021_Y", "nobody_2000_Z"]), quotes=True)
    assert "| b_2021_Y | C1 | finding | Ripples / spindles couple. | Results (L40) | \"q3\" (exact) |" in md
    assert "1 claims from 1 papers. No claims digest: nobody_2000_Z." in md
