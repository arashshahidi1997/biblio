"""Shared test configuration for biblio tests.

Ensures ``src/`` is on sys.path so ``from biblio import ...`` works regardless
of how pytest is invoked (Makefile, IDE runner, bare ``pytest`` command).
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


import pytest


@pytest.fixture(autouse=True)
def _llm_backend_api(monkeypatch):
    """Tests mock the Anthropic SDK; never shell out to the `claude` CLI from a test run."""
    monkeypatch.setenv("BIBLIO_LLM_BACKEND", "api")
