"""Tests for Unpaywall client, EZProxy rewriting, fetch cascade, and config loading."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from biblio.unpaywall import best_pdf_url, query_unpaywall, batch_query, _doi_slug
from biblio.ezproxy import rewrite_url, download_via_proxy
from biblio.config import load_biblio_config, PdfFetchCascadeConfig, DEFAULT_CASCADE_SOURCES


# ── Unpaywall response parsing ───────────────────────────────────────────────


class TestBestPdfUrl:
    def test_best_oa_location_url_for_pdf(self):
        resp = {"best_oa_location": {"url_for_pdf": "https://example.com/paper.pdf", "url": "https://example.com/page"}}
        assert best_pdf_url(resp) == "https://example.com/paper.pdf"

    def test_best_oa_location_url_fallback(self):
        resp = {"best_oa_location": {"url": "https://example.com/page"}}
        assert best_pdf_url(resp) == "https://example.com/page"

    def test_oa_locations_fallback(self):
        resp = {
            "best_oa_location": {},
            "oa_locations": [
                {"url_for_pdf": None, "url": "https://x.com"},
                {"url_for_pdf": "https://repo.org/paper.pdf", "url": "https://repo.org"},
            ],
        }
        assert best_pdf_url(resp) == "https://repo.org/paper.pdf"

    def test_none_response(self):
        assert best_pdf_url(None) is None

    def test_empty_response(self):
        assert best_pdf_url({}) is None

    def test_no_pdf_anywhere(self):
        resp = {"best_oa_location": {}, "oa_locations": [{"url": "https://x.com"}]}
        assert best_pdf_url(resp) is None


class TestDoiSlug:
    def test_basic(self):
        assert _doi_slug("10.1234/foo.bar") == "10.1234_foo.bar"

    def test_slashes(self):
        assert _doi_slug("10.1234/foo/bar") == "10.1234_foo_bar"


class TestQueryUnpaywall:
    def test_empty_doi_returns_none(self):
        assert query_unpaywall("", "test@example.com") is None

    def test_empty_email_returns_none(self):
        assert query_unpaywall("10.1234/test", "") is None

    def test_cached_response(self, tmp_path: Path):
        cache_dir = tmp_path / "bib" / "derivatives" / "unpaywall"
        cache_dir.mkdir(parents=True)
        data = {"doi": "10.1234/test", "best_oa_location": {"url_for_pdf": "https://x.com/test.pdf"}}
        slug = _doi_slug("10.1234/test")
        (cache_dir / f"{slug}.json").write_text(json.dumps(data), encoding="utf-8")

        result = query_unpaywall("10.1234/test", "test@example.com", repo_root=tmp_path)
        assert result == data

    @patch("biblio.unpaywall.urllib.request.urlopen")
    def test_network_call_and_caching(self, mock_urlopen, tmp_path: Path):
        data = {"doi": "10.1234/new", "best_oa_location": {"url_for_pdf": "https://x.com/new.pdf"}}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = query_unpaywall("10.1234/new", "test@example.com", repo_root=tmp_path)
        assert result == data
        # Check cache was written
        slug = _doi_slug("10.1234/new")
        cached = tmp_path / "bib" / "derivatives" / "unpaywall" / f"{slug}.json"
        assert cached.exists()

    @patch("biblio.unpaywall.urllib.request.urlopen", side_effect=Exception("network error"))
    def test_network_error_returns_none(self, mock_urlopen):
        assert query_unpaywall("10.1234/fail", "test@example.com") is None


class TestBatchQuery:
    @patch("biblio.unpaywall.query_unpaywall")
    def test_batch_returns_urls(self, mock_query):
        mock_query.side_effect = [
            {"best_oa_location": {"url_for_pdf": "https://a.com/1.pdf"}},
            {"best_oa_location": {}},
            None,
        ]
        results = batch_query(["10.1/a", "10.1/b", "10.1/c"], "x@y.com", delay=0)
        assert results["10.1/a"] == "https://a.com/1.pdf"
        assert results["10.1/b"] is None
        assert results["10.1/c"] is None


# ── EZProxy URL rewriting ────────────────────────────────────────────────────


class TestRewriteUrl:
    def test_prefix_mode(self):
        result = rewrite_url(
            "https://doi.org/10.1234/test",
            "https://emedien.ub.uni-muenchen.de",
            mode="prefix",
        )
        assert result.startswith("https://emedien.ub.uni-muenchen.de/login?url=")
        assert "10.1234" in result

    def test_prefix_mode_url_encoding(self):
        result = rewrite_url(
            "https://doi.org/10.1234/test",
            "https://proxy.example.edu",
        )
        # The original URL should be URL-encoded in the query parameter
        assert "https%3A%2F%2Fdoi.org" in result

    def test_suffix_mode(self):
        result = rewrite_url(
            "https://www.nature.com/articles/s41586-023-12345-6",
            "https://emedien.ub.uni-muenchen.de",
            mode="suffix",
        )
        assert "www.nature.com.emedien.ub.uni-muenchen.de" in result

    def test_trailing_slash_stripped(self):
        result = rewrite_url(
            "https://doi.org/10.1234/test",
            "https://proxy.example.edu/",
            mode="prefix",
        )
        assert result.startswith("https://proxy.example.edu/login?url=")


class TestDownloadViaProxy:
    @patch("biblio.ezproxy.urllib.request.urlopen")
    def test_html_response_returns_false(self, mock_urlopen, tmp_path: Path):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        dest = tmp_path / "paper.pdf"
        result = download_via_proxy(
            "https://doi.org/10.1234/test", "https://proxy.example.edu",
            dest, mode="prefix",
        )
        assert result is False

    @patch("biblio.ezproxy.urllib.request.urlopen", side_effect=Exception("connection refused"))
    def test_network_error_returns_false(self, mock_urlopen, tmp_path: Path):
        dest = tmp_path / "paper.pdf"
        result = download_via_proxy(
            "https://doi.org/10.1234/test", "https://proxy.example.edu",
            dest, mode="prefix",
        )
        assert result is False


# ── Config loading ───────────────────────────────────────────────────────────


class TestPdfFetchCascadeConfig:
    def test_default_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Isolate from real ~/.config/biblio/config.yml
        monkeypatch.setenv("BIBLIO_USER_CONFIG", str(tmp_path / "empty_user.yml"))
        (tmp_path / "bib" / "config").mkdir(parents=True)
        (tmp_path / "bib" / "config" / "biblio.yml").write_text("{}", encoding="utf-8")
        (tmp_path / "bib" / "config" / "citekeys.md").write_text("", encoding="utf-8")

        cfg = load_biblio_config("bib/config/biblio.yml", root=tmp_path)
        assert cfg.pdf_fetch_cascade.unpaywall_email is None
        assert cfg.pdf_fetch_cascade.ezproxy_base is None
        assert cfg.pdf_fetch_cascade.ezproxy_mode == "prefix"
        assert cfg.pdf_fetch_cascade.ezproxy_cookie is None
        assert cfg.pdf_fetch_cascade.sources == DEFAULT_CASCADE_SOURCES
        assert cfg.pdf_fetch_cascade.delay == 1.0

    def test_custom_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Isolate from real ~/.config/biblio/config.yml
        monkeypatch.setenv("BIBLIO_USER_CONFIG", str(tmp_path / "empty_user.yml"))
        (tmp_path / "bib" / "config").mkdir(parents=True)
        (tmp_path / "bib" / "config" / "citekeys.md").write_text("", encoding="utf-8")
        config = {
            "pdf_fetch": {
                "unpaywall_email": "user@uni.de",
                "ezproxy_base": "https://proxy.uni.de",
                "ezproxy_mode": "suffix",
                "ezproxy_cookie": "ezproxy=abc123",
                "sources": ["pool", "unpaywall"],
                "delay": 2.0,
            }
        }
        import yaml
        (tmp_path / "bib" / "config" / "biblio.yml").write_text(yaml.safe_dump(config), encoding="utf-8")

        cfg = load_biblio_config("bib/config/biblio.yml", root=tmp_path)
        assert cfg.pdf_fetch_cascade.unpaywall_email == "user@uni.de"
        assert cfg.pdf_fetch_cascade.ezproxy_base == "https://proxy.uni.de"
        assert cfg.pdf_fetch_cascade.ezproxy_mode == "suffix"
        assert cfg.pdf_fetch_cascade.ezproxy_cookie == "ezproxy=abc123"
        assert cfg.pdf_fetch_cascade.sources == ("pool", "unpaywall")
        assert cfg.pdf_fetch_cascade.delay == 2.0


# ── Fetch cascade order ─────────────────────────────────────────────────────


class TestFetchCascade:
    """Test fetch_pdfs_oa cascade logic with mocked network."""

    def _make_cfg(self, tmp_path: Path, sources: list[str] | None = None, email: str | None = None) -> Any:
        """Build a minimal BiblioConfig for testing cascade."""
        from biblio.scaffold import init_bib_scaffold
        init_bib_scaffold(tmp_path, force=True)
        import yaml
        config: dict[str, Any] = {}
        pf: dict[str, Any] = {}
        if sources is not None:
            pf["sources"] = sources
        if email:
            pf["unpaywall_email"] = email
        if pf:
            config["pdf_fetch"] = pf
        (tmp_path / "bib" / "config" / "biblio.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
        return load_biblio_config("bib/config/biblio.yml", root=tmp_path)

    def _write_openalex_jsonl(self, cfg: Any, records: list[dict[str, Any]]) -> None:
        cfg.openalex.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with cfg.openalex.out_jsonl.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_openalex_source_success(self, tmp_path: Path):
        cfg = self._make_cfg(tmp_path, sources=["openalex"])
        self._write_openalex_jsonl(cfg, [
            {"citekey": "smith_2020_Test", "best_oa_location": {"pdf_url": "https://oa.com/test.pdf"}},
        ])

        from biblio.pdf_fetch_oa import fetch_pdfs_oa
        with patch("biblio.pdf_fetch_oa._download") as mock_dl:
            results = fetch_pdfs_oa(cfg, delay=0, queue=False)

        assert len(results) == 1
        assert results[0].status == "openalex"
        mock_dl.assert_called_once()

    def test_unpaywall_fallback(self, tmp_path: Path):
        cfg = self._make_cfg(tmp_path, sources=["openalex", "unpaywall"], email="test@uni.de")
        self._write_openalex_jsonl(cfg, [
            {"citekey": "jones_2021_Demo", "doi": "10.1234/demo"},
        ])

        from biblio.pdf_fetch_oa import fetch_pdfs_oa
        with patch("biblio.pdf_fetch_oa._try_unpaywall", return_value="https://unpaywall.org/demo.pdf") as mock_up:
            results = fetch_pdfs_oa(cfg, delay=0, queue=False)

        assert len(results) == 1
        assert results[0].status == "unpaywall"
        mock_up.assert_called_once()

    def test_all_sources_exhausted_queues(self, tmp_path: Path):
        cfg = self._make_cfg(tmp_path, sources=["openalex"])
        self._write_openalex_jsonl(cfg, [
            {"citekey": "nope_2022_None", "doi": "10.1234/nope"},
        ])

        from biblio.pdf_fetch_oa import fetch_pdfs_oa
        results = fetch_pdfs_oa(cfg, delay=0, queue=True)

        assert len(results) == 1
        assert results[0].status == "no_url"

    def test_cascade_order_respects_config(self, tmp_path: Path):
        """If sources=[unpaywall, openalex] and unpaywall succeeds, openalex should not be tried."""
        cfg = self._make_cfg(tmp_path, sources=["unpaywall", "openalex"], email="x@y.com")
        self._write_openalex_jsonl(cfg, [
            {"citekey": "first_2023_X", "doi": "10.1234/first", "best_oa_location": {"pdf_url": "https://oa.com/first.pdf"}},
        ])

        from biblio.pdf_fetch_oa import fetch_pdfs_oa
        with patch("biblio.pdf_fetch_oa._try_unpaywall", return_value="https://unpaywall.org/first.pdf") as mock_up, \
             patch("biblio.pdf_fetch_oa._download") as mock_dl:
            results = fetch_pdfs_oa(cfg, delay=0, queue=False)

        assert results[0].status == "unpaywall"
        mock_dl.assert_not_called()  # openalex was never reached

    def test_skips_existing_pdf(self, tmp_path: Path):
        cfg = self._make_cfg(tmp_path, sources=["openalex"])
        self._write_openalex_jsonl(cfg, [
            {"citekey": "exist_2023_Y", "best_oa_location": {"pdf_url": "https://oa.com/y.pdf"}},
        ])
        dest = cfg.pdf_root / cfg.pdf_pattern.format(citekey="exist_2023_Y")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("fake pdf")

        from biblio.pdf_fetch_oa import fetch_pdfs_oa
        results = fetch_pdfs_oa(cfg, delay=0, queue=False)
        assert results[0].status == "skipped"
