"""Agent-facing MCP functions: paper_lookup and the background job handle (projio spec: agent interface layers)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from biblio import jobs
from biblio.mcp import job, paper_lookup


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


@pytest.fixture
def root(tmp_path: Path) -> Path:
    src = tmp_path / "bib" / "srcbib"
    src.mkdir(parents=True)
    (src / "main.bib").write_text("@article{smith_2020_Ripples,\n  author = {Smith, Ann},\n"
                                  "  title = {Ripples in sleep},\n  year = {2020},\n  doi = {10.1234/abc}\n}\n")
    merged = tmp_path / ".projio" / "biblio" / "merged.bib"
    merged.parent.mkdir(parents=True)
    merged.write_text((src / "main.bib").read_text())
    d = tmp_path / "bib" / "derivatives" / "docling" / "smith_2020_Ripples"
    d.mkdir(parents=True)
    (d / "smith_2020_Ripples.md").write_text("# Ripples in sleep\n\n## Results\n\nRipples were frequent.\n")
    dg = tmp_path / "bib" / "derivatives" / "digest" / "claims" / "wiki"
    dg.mkdir(parents=True)
    (dg / "smith_2020_Ripples.json").write_text(json.dumps({"meta": {"prompt_version": "claims-2",
                                                                     "quotes": {"exact": 3}}, "claims": []}))
    return tmp_path


def test_paper_lookup(root):
    r = paper_lookup(["@smith_2020_Ripples", "10.1234/abc", "Smith 2020 Ripples in sleep", "nobody_2000_X"],
                     root=root, detail="context")
    a, b, c, d = r["papers"]
    assert a["where"] == "project" and a["bib"]["title"] == "Ripples in sleep"
    assert a["held"]["fulltext"] == "project" and a["held"]["digests"][0]["prompt_version"] == "claims-2"
    assert [s["title"] for s in a["sections"]] == ["Results"]
    assert b["citekey"] == c["citekey"] == "smith_2020_Ripples" and b["link"] == "https://doi.org/10.1234/abc"
    assert d["where"] == "not held" and r["not_held"] == ["nobody_2000_X"]


def test_job_runs_the_cli_and_reports(root):
    started = job("start", root=root, kind="grobid", keys=["smith_2020_Ripples"])
    assert started["started"] and started["argv"] == ["biblio", "grobid", "run", "--keys", "smith_2020_Ripples"]
    for _ in range(100):
        st = job("status", root=root, job_id=started["job_id"])
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "failed" and st["exit_code"] == 1          # no PDF: grobid fails for that key
    assert any("smith_2020_Ripples" in ln for ln in st["summary"] + st.get("tail", []))
    assert job("list", root=root)["jobs"][-1]["job_id"] == started["job_id"]


def test_docling_job_plans_first_and_kill(root):
    plan = job("start", root=root, kind="docling", keys=["smith_2020_Ripples", "ghost_2000_X"])
    assert plan["started"] is False and {s["reason"] for s in plan["plan"]["skipped"]} == {
        "no PDF", "not in the bibliography, no PDF"}
    with pytest.raises(ValueError):
        jobs.cli_job_argv("digest", [])
    assert job("start", root=root, kind="nonsense")["error"].startswith("kind must be")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    jobs._write_job(root, "job_x", {"job_id": "job_x", "type": "cli", "status": "running", "pid": proc.pid,
                                    "log": str(root / "none.log")})
    assert job("kill", root=root, job_id="job_x")["status"] == "killed"
    assert proc.wait(timeout=5) != 0
