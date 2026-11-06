from __future__ import annotations

import pytest

from biblio.extract import parse_llm_mapping


def test_parses_json() -> None:
    out = parse_llm_mapping('{"citekey": "k", "key_findings": ["a: b"]}')
    assert out["key_findings"] == ["a: b"]


def test_parses_fenced_json_with_prose_around() -> None:
    out = parse_llm_mapping('```json\n{"citekey": "k"}\n```')
    assert out == {"citekey": "k"}


def test_repairs_yaml_with_colons_in_values() -> None:
    # The failure from pixecog (peyrache_2011): an unquoted colon inside a summary.
    text = (
        "citekey: peyrache_2011_InhibitionRecruitment\n"
        "relevance:\n"
        "  - question_id: q1\n"
        "    relevance: high\n"
        "    summary: characterizes the temporal sequence: SPWRs cluster before δ-waves\n"
        "    supports: true\n"
        "key_findings:\n"
        "  - SPWR-spindle coupling (ratio 2: 1) in all animals\n"
        "  - plain finding\n"
    )
    out = parse_llm_mapping(text)
    rel = out["relevance"][0]
    assert rel["summary"] == "characterizes the temporal sequence: SPWRs cluster before δ-waves"
    assert rel["supports"] is True
    assert out["key_findings"] == ["SPWR-spindle coupling (ratio 2: 1) in all animals", "plain finding"]


def test_plain_yaml_unchanged() -> None:
    assert parse_llm_mapping("citekey: k\nmethods:\n  - LFP\n") == {"citekey": "k", "methods": ["LFP"]}


def test_not_a_mapping_raises() -> None:
    with pytest.raises(ValueError):
        parse_llm_mapping("just prose, no structure")
