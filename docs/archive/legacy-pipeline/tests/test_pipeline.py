"""Pytest integration checks for the pipeline harness."""

from __future__ import print_function

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


if sys.version_info[0] < 3:
    pytest.skip("pipeline tests require Python 3", allow_module_level=True)


def require_tool(name):
    if shutil.which(name) is None:
        pytest.skip("missing required tool: {0}".format(name))


def require_env_flag():
    if os.environ.get("RUN_PIPELINE_TESTS") != "1":
        pytest.skip("set RUN_PIPELINE_TESTS=1 to run integration pipeline tests")


def resolve_default_work_id():
    registry = Path("data/01_bronze/registry.json")
    if not registry.exists():
        pytest.skip("missing data/01_bronze/registry.json; run ingest_bronze first")
    payload = json.loads(registry.read_text(encoding="utf-8"))
    works = payload.get("works", [])
    if not works:
        pytest.skip("registry has no works")
    return works[0]["work_id"]


@pytest.mark.integration
def test_pipeline_smoke():
    require_env_flag()
    require_tool("snakemake")
    require_tool("mkdocs")
    work_id = resolve_default_work_id()
    work_ids_arg = '["{0}"]'.format(work_id)

    subprocess.run(
        [
            "snakemake",
            "-j1",
            "compile_project_bib",
            "validate_project_bib",
            "internalize_pdfs",
            "link_pdfs",
            "build_manifest",
        ],
        check=True,
    )

    subprocess.run(
        [
            sys.executable,
            "src/scripts/ingest_bronze.py",
            "--bib",
            "data/01_bronze/project.bib",
            "--bronze-root",
            "data/01_bronze",
            "--pdf-map",
            "data/01_bronze/pdf_map.json",
            "--objects-dir",
            "data/01_bronze/objects",
            "--registry",
            "data/01_bronze/registry.json",
            "--manifest",
            "manifest.ingest.jsonl",
        ],
        check=True,
    )

    subprocess.run(
        ["snakemake", "-j1", "extract_docling", "extract_grobid", "--config", "work_ids={0}".format(work_ids_arg)],
        check=True,
    )
    subprocess.run(
        ["snakemake", "-j1", "reconcile_silver", "--config", "work_ids={0}".format(work_ids_arg)],
        check=True,
    )
    subprocess.run(
        ["snakemake", "-j1", "validate", "--config", "work_ids={0}".format(work_ids_arg)],
        check=True,
    )
    subprocess.run(
        ["snakemake", "-j1", "build_gold", "--config", "work_ids={0}".format(work_ids_arg)],
        check=True,
    )
    subprocess.run(["mkdocs", "build"], check=True)
