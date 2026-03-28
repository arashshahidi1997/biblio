"""Tests for the query DSL, evaluator, and smart collections."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from biblio.query import (
    AndExpr,
    NotExpr,
    OrExpr,
    ParseError,
    Predicate,
    evaluate,
    parse_query,
    query_citekeys,
)


# ── Parser tests ─────────────────────────────────────────────────────────────

class TestParser:
    def test_single_predicate(self):
        expr = parse_query("tag:method:transformer")
        assert isinstance(expr, Predicate)
        assert expr.field == "tag"
        assert expr.value == "method:transformer"

    def test_and(self):
        expr = parse_query("status:unread AND priority:high")
        assert isinstance(expr, AndExpr)
        assert len(expr.children) == 2

    def test_or(self):
        expr = parse_query("tag:review OR tag:survey")
        assert isinstance(expr, OrExpr)
        assert len(expr.children) == 2

    def test_not(self):
        expr = parse_query("NOT status:archived")
        assert isinstance(expr, NotExpr)
        assert isinstance(expr.child, Predicate)

    def test_parentheses(self):
        expr = parse_query("(tag:ml OR tag:dl) AND status:unread")
        assert isinstance(expr, AndExpr)
        assert isinstance(expr.children[0], OrExpr)

    def test_nested_not(self):
        expr = parse_query("NOT NOT status:unread")
        assert isinstance(expr, NotExpr)
        assert isinstance(expr.child, NotExpr)

    def test_case_insensitive_operators(self):
        expr = parse_query("status:unread and priority:high")
        assert isinstance(expr, AndExpr)

    def test_complex_query(self):
        expr = parse_query("(tag:method:transformer OR tag:method:rnn) AND year:>2020 AND NOT status:archived")
        assert isinstance(expr, AndExpr)
        assert len(expr.children) == 3

    def test_empty_query_raises(self):
        with pytest.raises(ParseError):
            parse_query("")

    def test_bad_predicate_raises(self):
        with pytest.raises(ParseError):
            parse_query("badtoken")

    def test_unbalanced_parens_raises(self):
        with pytest.raises(ParseError):
            parse_query("(tag:ml")

    def test_unexpected_close_paren(self):
        with pytest.raises(ParseError):
            parse_query(") tag:ml")

    def test_year_comparison(self):
        expr = parse_query("year:>2022")
        assert isinstance(expr, Predicate)
        assert expr.value == ">2022"


# ── Evaluator tests ──────────────────────────────────────────────────────────

class TestEvaluator:
    def _lib(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def _bib(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def test_tag_match(self):
        expr = parse_query("tag:method:transformer")
        assert evaluate(expr, self._lib(tags=["method:transformer", "topic:nlp"]), {})
        assert not evaluate(expr, self._lib(tags=["method:cnn"]), {})

    def test_tag_case_insensitive(self):
        expr = parse_query("tag:Method:Transformer")
        assert evaluate(expr, self._lib(tags=["method:transformer"]), {})

    def test_status_match(self):
        expr = parse_query("status:unread")
        assert evaluate(expr, self._lib(status="unread"), {})
        assert not evaluate(expr, self._lib(status="reading"), {})

    def test_priority_match(self):
        expr = parse_query("priority:high")
        assert evaluate(expr, self._lib(priority="high"), {})
        assert not evaluate(expr, self._lib(priority="low"), {})

    def test_author_match(self):
        expr = parse_query("author:Smith")
        assert evaluate(expr, {}, self._bib(authors=["John Smith", "Jane Doe"]))
        assert not evaluate(expr, {}, self._bib(authors=["Jane Doe"]))

    def test_year_exact(self):
        expr = parse_query("year:2024")
        assert evaluate(expr, {}, self._bib(year="2024"))
        assert not evaluate(expr, {}, self._bib(year="2023"))

    def test_year_gt(self):
        expr = parse_query("year:>2022")
        assert evaluate(expr, {}, self._bib(year="2023"))
        assert not evaluate(expr, {}, self._bib(year="2022"))

    def test_year_gte(self):
        expr = parse_query("year:>=2022")
        assert evaluate(expr, {}, self._bib(year="2022"))

    def test_year_lt(self):
        expr = parse_query("year:<2020")
        assert evaluate(expr, {}, self._bib(year="2019"))
        assert not evaluate(expr, {}, self._bib(year="2020"))

    def test_year_lte(self):
        expr = parse_query("year:<=2020")
        assert evaluate(expr, {}, self._bib(year="2020"))

    def test_type_match(self):
        expr = parse_query("type:article")
        assert evaluate(expr, {}, self._bib(type="article"))
        assert not evaluate(expr, {}, self._bib(type="inproceedings"))

    def test_keyword_match(self):
        expr = parse_query("keyword:neural")
        assert evaluate(expr, {}, self._bib(keywords="neural networks, deep learning"))
        assert not evaluate(expr, {}, self._bib(keywords="regression"))

    def test_and_eval(self):
        expr = parse_query("status:unread AND priority:high")
        assert evaluate(expr, self._lib(status="unread", priority="high"), {})
        assert not evaluate(expr, self._lib(status="unread", priority="low"), {})

    def test_or_eval(self):
        expr = parse_query("status:unread OR status:reading")
        assert evaluate(expr, self._lib(status="unread"), {})
        assert evaluate(expr, self._lib(status="reading"), {})
        assert not evaluate(expr, self._lib(status="archived"), {})

    def test_not_eval(self):
        expr = parse_query("NOT status:archived")
        assert evaluate(expr, self._lib(status="unread"), {})
        assert not evaluate(expr, self._lib(status="archived"), {})

    def test_complex_eval(self):
        expr = parse_query("(tag:ml OR tag:dl) AND NOT status:archived")
        assert evaluate(expr, self._lib(tags=["ml"], status="unread"), {})
        assert not evaluate(expr, self._lib(tags=["ml"], status="archived"), {})
        assert not evaluate(expr, self._lib(tags=["bio"], status="unread"), {})

    def test_missing_year_no_crash(self):
        expr = parse_query("year:2024")
        assert not evaluate(expr, {}, {})

    def test_missing_tags_no_crash(self):
        expr = parse_query("tag:ml")
        assert not evaluate(expr, {}, {})

    def test_has_predicate(self):
        expr = parse_query("has:pdf")
        assert evaluate(expr, {"_artifacts": {"pdf": True}}, {})
        assert not evaluate(expr, {"_artifacts": {"pdf": False}}, {})
        assert not evaluate(expr, {}, {})


# ── query_citekeys tests ────────────────────────────────────────────────────

class TestQueryCitekeys:
    def test_basic_filter(self):
        library = {
            "smith2024": {"status": "unread", "tags": ["ml"]},
            "doe2023": {"status": "reading", "tags": ["bio"]},
            "jones2024": {"status": "unread", "tags": ["ml", "dl"]},
        }
        result = query_citekeys("status:unread", library)
        assert result == ["jones2024", "smith2024"]

    def test_filter_with_bib(self):
        library = {
            "smith2024": {"status": "unread"},
            "doe2023": {"status": "unread"},
        }
        bib = {
            "smith2024": {"year": "2024", "authors": ["Smith"]},
            "doe2023": {"year": "2023", "authors": ["Doe"]},
        }
        result = query_citekeys("year:>2023", library, bib)
        assert result == ["smith2024"]

    def test_combined_sources(self):
        library = {"a": {"status": "unread"}}
        bib = {"b": {"year": "2024"}}
        # Both keys should be considered
        result = query_citekeys("status:unread OR year:2024", library, bib)
        assert result == ["a", "b"]


# ── Smart collection integration tests ───────────────────────────────────────

class TestSmartCollections:
    @pytest.fixture()
    def bib_root(self, tmp_path: Path) -> Path:
        """Set up a minimal biblio workspace for collection tests."""
        config_dir = tmp_path / "bib" / "config"
        config_dir.mkdir(parents=True)

        # Minimal biblio.yml
        import yaml
        config = {
            "pdf_root": str(tmp_path / "bib" / "articles"),
            "citekeys_path": str(config_dir / "citekeys.md"),
        }
        (config_dir / "biblio.yml").write_text(yaml.safe_dump(config), encoding="utf-8")

        # Library with test data
        library = {
            "papers": {
                "smith2024_transformers": {"status": "unread", "tags": ["method:transformer", "topic:nlp"], "priority": "high"},
                "doe2023_rnns": {"status": "reading", "tags": ["method:rnn", "topic:nlp"], "priority": "normal"},
                "jones2022_cnns": {"status": "archived", "tags": ["method:cnn", "topic:cv"], "priority": "low"},
                "lee2024_diffusion": {"status": "unread", "tags": ["method:diffusion", "topic:cv"], "priority": "high"},
            }
        }
        (config_dir / "library.yml").write_text(yaml.safe_dump(library), encoding="utf-8")
        return tmp_path

    @pytest.fixture()
    def cfg(self, bib_root: Path):
        from biblio.config import load_biblio_config
        return load_biblio_config(bib_root / "bib" / "config" / "biblio.yml", root=bib_root)

    def test_create_smart_collection(self, cfg):
        from biblio.collections import create_collection, is_smart
        col = create_collection(cfg, "Unread Papers", query="status:unread")
        assert is_smart(col)
        assert col["query"] == "status:unread"
        assert "citekeys" not in col

    def test_create_manual_collection(self, cfg):
        from biblio.collections import create_collection, is_smart
        col = create_collection(cfg, "My Reads")
        assert not is_smart(col)
        assert col["citekeys"] == []

    def test_resolve_smart_collection(self, cfg):
        from biblio.collections import create_collection, resolve_smart
        col = create_collection(cfg, "Unread", query="status:unread")
        citekeys = resolve_smart(cfg, col["id"])
        assert sorted(citekeys) == ["lee2024_diffusion", "smith2024_transformers"]

    def test_resolve_smart_complex_query(self, cfg):
        from biblio.collections import create_collection, resolve_smart
        col = create_collection(cfg, "NLP Unread", query="tag:topic:nlp AND status:unread")
        citekeys = resolve_smart(cfg, col["id"])
        assert citekeys == ["smith2024_transformers"]

    def test_resolve_smart_not_query(self, cfg):
        from biblio.collections import create_collection, resolve_smart
        col = create_collection(cfg, "Active", query="NOT status:archived")
        citekeys = resolve_smart(cfg, col["id"])
        assert "jones2022_cnns" not in citekeys
        assert len(citekeys) == 3

    def test_resolve_manual_collection(self, cfg):
        from biblio.collections import add_papers, create_collection, resolve_smart
        col = create_collection(cfg, "Favorites")
        add_papers(cfg, col["id"], ["smith2024_transformers", "doe2023_rnns"])
        citekeys = resolve_smart(cfg, col["id"])
        assert citekeys == ["smith2024_transformers", "doe2023_rnns"]

    def test_update_query(self, cfg):
        from biblio.collections import create_collection, resolve_smart, update_query
        col = create_collection(cfg, "High Priority", query="priority:high")
        citekeys = resolve_smart(cfg, col["id"])
        assert len(citekeys) == 2
        # Change query
        update_query(cfg, col["id"], "priority:low")
        citekeys = resolve_smart(cfg, col["id"])
        assert citekeys == ["jones2022_cnns"]

    def test_invalid_query_rejected(self, cfg):
        from biblio.collections import create_collection
        from biblio.query import ParseError
        with pytest.raises(ParseError):
            create_collection(cfg, "Bad", query="(unclosed")

    def test_list_collections_summary(self, cfg):
        from biblio.collections import create_collection, list_collections_summary
        create_collection(cfg, "Smart Unread", query="status:unread")
        create_collection(cfg, "Manual")
        summaries = list_collections_summary(cfg)
        assert len(summaries) == 2
        smart = next(s for s in summaries if s["smart"])
        manual = next(s for s in summaries if not s["smart"])
        assert smart["count"] == 2
        assert manual["count"] == 0

    def test_smart_collection_with_description(self, cfg):
        from biblio.collections import create_collection, load_collections
        col = create_collection(cfg, "NLP Papers", query="tag:topic:nlp",
                                description="All NLP-related papers")
        data = load_collections(cfg)
        stored = next(c for c in data["collections"] if c["id"] == col["id"])
        assert stored["description"] == "All NLP-related papers"
