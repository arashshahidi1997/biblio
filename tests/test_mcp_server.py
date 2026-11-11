"""`biblio mcp`: the small server over the stable commands (needs the mcp extra)."""
from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("mcp")

from biblio.mcp_server import build_server  # noqa: E402

KEY = "smith_2020_Ripples"
PAPER = "# Ripples\n\n## Results\n\nRipples were less frequent after the lesion in all rats.\n"


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


def _call(server, name, args):
    res = asyncio.run(server.call_tool(name, args))
    content = res[0] if isinstance(res, tuple) else res
    return json.loads(content[0].text)


def test_tools_and_quote_check(tmp_path):
    d = tmp_path / "bib" / "derivatives" / "docling" / KEY
    d.mkdir(parents=True)
    (d / f"{KEY}.md").write_text(PAPER)
    answer = tmp_path / "answer.md"
    answer.write_text('- **measured** — fewer. "Ripples were less frequent after the lesion" (Results)\n')
    server = build_server(tmp_path)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"paper_lookup", "paper_text", "quotes_check", "paper_add", "paper_job", "pipeline_status"}
    res = _call(server, "quotes_check", {"file": str(answer), "texts": [KEY]})
    assert res["exit"] == 0 and res["results"][str(answer)][0]["status"] == "exact"
    res = _call(server, "paper_text", {"citekey": KEY, "grep": "lesion"})
    assert res["exit"] == 0 and "5:" in res["output"]
