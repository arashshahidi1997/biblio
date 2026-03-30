"""Tests for biblio.author_search — ORCID-based author lookup and works listing."""
from __future__ import annotations

import pytest

from biblio.author_search import (
    AuthorRecord,
    WorkRecord,
    _extract_author,
    _extract_work,
    get_author_works,
    search_by_orcid,
)
from biblio.openalex.openalex_client import OpenAlexClientConfig


# ── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_AUTHOR_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/A5023888391",
            "orcid": "https://orcid.org/0000-0002-1234-5678",
            "display_name": "Jane Doe",
            "last_known_institutions": [
                {"display_name": "MIT", "type": "education"}
            ],
            "works_count": 42,
            "cited_by_count": 1500,
            "summary_stats": {"h_index": 18, "i10_index": 25},
        }
    ]
}

SAMPLE_WORKS_PAGE1 = {
    "results": [
        {
            "id": "https://openalex.org/W111",
            "display_name": "Paper Alpha",
            "publication_year": 2023,
            "cited_by_count": 50,
            "ids": {"doi": "https://doi.org/10.1000/alpha"},
            "primary_location": {
                "source": {"display_name": "Nature Neuroscience"}
            },
            "open_access": {"is_oa": True},
        },
        {
            "id": "https://openalex.org/W222",
            "display_name": "Paper Beta",
            "publication_year": 2021,
            "cited_by_count": 5,
            "ids": {"doi": "https://doi.org/10.1000/beta"},
            "primary_location": {
                "source": {"display_name": "PLOS ONE"}
            },
            "open_access": {"is_oa": False},
        },
    ],
    "meta": {"next_cursor": None},
}

SAMPLE_WORKS_PAGINATED_P1 = {
    "results": [
        {
            "id": "https://openalex.org/W111",
            "display_name": "Paper Alpha",
            "publication_year": 2023,
            "cited_by_count": 50,
            "ids": {"doi": "https://doi.org/10.1000/alpha"},
            "primary_location": None,
            "open_access": {"is_oa": True},
        },
    ],
    "meta": {"next_cursor": "cursor2"},
}

SAMPLE_WORKS_PAGINATED_P2 = {
    "results": [
        {
            "id": "https://openalex.org/W222",
            "display_name": "Paper Beta",
            "publication_year": 2021,
            "cited_by_count": 3,
            "ids": {},
            "primary_location": None,
            "open_access": {"is_oa": False},
        },
    ],
    "meta": {"next_cursor": None},
}


def _make_cfg() -> OpenAlexClientConfig:
    return OpenAlexClientConfig(
        base_url="https://api.openalex.org",
        email=None,
        api_key=None,
        timeout_s=30,
        max_retries=0,
        per_page=25,
        select=("id", "display_name", "publication_year", "cited_by_count", "ids", "open_access", "primary_location"),
    )


class _FakeClient:
    """Minimal stand-in for OpenAlexClient._get_json."""

    def __init__(self, responses: dict[str, dict]):
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    def _get_json(self, path: str, *, params: dict | None = None) -> dict:
        self.calls.append((path, params or {}))
        key = path
        if params:
            if "cursor" in params and params["cursor"] != "*":
                key = f"{path}?cursor={params['cursor']}"
        return self._responses[key]

    def close(self) -> None:
        pass


# ── Unit tests for extraction helpers ────────────────────────────────────────

def test_extract_author_basic():
    author = _extract_author(SAMPLE_AUTHOR_RESPONSE["results"][0])
    assert author.openalex_id == "A5023888391"
    assert author.orcid == "https://orcid.org/0000-0002-1234-5678"
    assert author.display_name == "Jane Doe"
    assert author.affiliation == "MIT"
    assert author.works_count == 42
    assert author.cited_by_count == 1500
    assert author.h_index == 18


def test_extract_author_missing_fields():
    author = _extract_author({"id": "A1", "display_name": ""})
    assert author.display_name == "Unknown"
    assert author.affiliation is None
    assert author.h_index is None


def test_extract_work_basic():
    w = _extract_work(SAMPLE_WORKS_PAGE1["results"][0])
    assert w.openalex_id == "W111"
    assert w.doi == "10.1000/alpha"
    assert w.title == "Paper Alpha"
    assert w.year == 2023
    assert w.journal == "Nature Neuroscience"
    assert w.cited_by_count == 50
    assert w.is_oa is True


def test_extract_work_no_doi():
    w = _extract_work({"id": "W999", "display_name": "No DOI Paper", "ids": {}})
    assert w.doi is None
    assert w.title == "No DOI Paper"


def test_extract_work_no_title():
    w = _extract_work({"id": "W888"})
    assert w.title == "Untitled"


# ── Integration tests with mocked client ─────────────────────────────────────

def test_search_by_orcid(monkeypatch):
    import biblio.author_search as mod

    fake = _FakeClient({"authors": SAMPLE_AUTHOR_RESPONSE})
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    author = search_by_orcid(_make_cfg(), "0000-0002-1234-5678")
    assert author.display_name == "Jane Doe"
    assert author.openalex_id == "A5023888391"
    assert len(fake.calls) == 1


def test_search_by_orcid_not_found(monkeypatch):
    import biblio.author_search as mod

    fake = _FakeClient({"authors": {"results": []}})
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    with pytest.raises(ValueError, match="No author found"):
        search_by_orcid(_make_cfg(), "0000-0000-0000-0000")


def test_search_by_orcid_empty():
    with pytest.raises(ValueError, match="Empty ORCID"):
        search_by_orcid(_make_cfg(), "")


def test_get_author_works_single_page(monkeypatch):
    import biblio.author_search as mod

    fake = _FakeClient({"works": SAMPLE_WORKS_PAGE1})
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    works = get_author_works(_make_cfg(), "A5023888391")
    assert len(works) == 2
    assert works[0].title == "Paper Alpha"
    assert works[1].title == "Paper Beta"


def test_get_author_works_pagination(monkeypatch):
    import biblio.author_search as mod

    fake = _FakeClient({
        "works": SAMPLE_WORKS_PAGINATED_P1,
        "works?cursor=cursor2": SAMPLE_WORKS_PAGINATED_P2,
    })
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    works = get_author_works(_make_cfg(), "A5023888391")
    assert len(works) == 2
    assert len(fake.calls) == 2  # two pages


def test_get_author_works_min_citations_filter(monkeypatch):
    import biblio.author_search as mod

    fake = _FakeClient({"works": SAMPLE_WORKS_PAGE1})
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    works = get_author_works(_make_cfg(), "A5023888391", min_citations=10)
    assert len(works) == 1
    assert works[0].title == "Paper Alpha"


def test_get_author_works_empty_id():
    with pytest.raises(ValueError, match="Empty author_id"):
        get_author_works(_make_cfg(), "")


def test_get_author_works_normalizes_url(monkeypatch):
    import biblio.author_search as mod

    fake = _FakeClient({"works": SAMPLE_WORKS_PAGE1})
    monkeypatch.setattr(mod, "OpenAlexClient", lambda cfg: fake)

    works = get_author_works(_make_cfg(), "https://openalex.org/A5023888391")
    assert len(works) == 2
    # The filter should use the normalized ID (without URL prefix)
    _, params = fake.calls[0]
    assert "A5023888391" in params.get("filter", "")
