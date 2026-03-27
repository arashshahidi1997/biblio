"""Background job management for long-running biblio operations."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ledger import new_run_id, utc_now_iso


JOBS_DIR_NAME = ".projio/biblio/jobs"


@dataclass(frozen=True)
class JobInfo:
    job_id: str
    status: str  # "running", "completed", "failed"
    citekey: str
    pid: int | None
    started: str
    finished: str | None
    result: dict[str, Any] | None
    error: str | None


def _jobs_dir(root: Path) -> Path:
    return root / JOBS_DIR_NAME


def _job_path(root: Path, job_id: str) -> Path:
    return _jobs_dir(root) / f"{job_id}.json"


def _write_job(root: Path, job_id: str, payload: dict[str, Any]) -> Path:
    path = _job_path(root, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_job(root: Path, job_id: str) -> dict[str, Any] | None:
    path = _job_path(root, job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        import os
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def launch_docling_background(
    root: Path,
    citekey: str,
    force: bool = False,
) -> str:
    """Spawn a background subprocess that runs docling and writes results to a job file.

    Returns the job_id immediately.
    """
    job_id = new_run_id("docling_bg")
    job_file = _job_path(root, job_id)
    job_file.parent.mkdir(parents=True, exist_ok=True)

    # The worker script runs as a subprocess using the same Python interpreter.
    # It imports biblio, runs docling, and writes results to the job file.
    worker_code = _build_worker_script(
        root=str(root),
        citekey=citekey,
        force=force,
        job_id=job_id,
        job_file=str(job_file),
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", worker_code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach from parent
    )

    # Write initial "running" state
    _write_job(root, job_id, {
        "job_id": job_id,
        "status": "running",
        "citekey": citekey.lstrip("@"),
        "force": force,
        "pid": proc.pid,
        "started": utc_now_iso(),
        "finished": None,
        "result": None,
        "error": None,
    })

    return job_id


def get_job_status(root: Path, job_id: str) -> JobInfo | None:
    """Read job state from disk. If process exited without writing completion, mark failed."""
    data = _read_job(root, job_id)
    if data is None:
        return None

    status = data.get("status", "unknown")
    pid = data.get("pid")

    # If still marked running but process is dead, it crashed without writing results
    if status == "running" and pid is not None and not _pid_alive(pid):
        data["status"] = "failed"
        data["error"] = "Process exited without writing results (likely crashed)"
        data["finished"] = utc_now_iso()
        _write_job(root, job_id, data)
        status = "failed"

    return JobInfo(
        job_id=data["job_id"],
        status=data["status"],
        citekey=data.get("citekey", ""),
        pid=pid,
        started=data.get("started", ""),
        finished=data.get("finished"),
        result=data.get("result"),
        error=data.get("error"),
    )


def list_jobs(root: Path, status_filter: str | None = None) -> list[dict[str, Any]]:
    """List all jobs, optionally filtered by status."""
    jobs_dir = _jobs_dir(root)
    if not jobs_dir.exists():
        return []
    results = []
    for path in sorted(jobs_dir.glob("*.json"), key=lambda p: p.name):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if status_filter and data.get("status") != status_filter:
            continue
        results.append(data)
    return results


def _build_worker_script(
    root: str,
    citekey: str,
    force: bool,
    job_id: str,
    job_file: str,
) -> str:
    """Build the Python code that runs in the background subprocess."""
    # Use repr() for safe string embedding
    return f"""\
import json, sys, traceback
from pathlib import Path

def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def _write(data):
    p = Path({job_file!r})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\\n", encoding="utf-8")

try:
    from biblio.config import default_config_path, load_biblio_config
    root = Path({root!r})
    config_path = default_config_path(root=root)
    cfg = load_biblio_config(config_path, root=root)

    from biblio.docling import run_docling_for_key
    out = run_docling_for_key(cfg, {citekey!r}, force={force!r})

    result = {{
        "citekey": {citekey!r}.lstrip("@"),
        "md_path": str(out.md_path),
        "json_path": str(out.json_path),
        "outdir": str(out.outdir),
    }}

    # Auto-chain ref-md if GROBID TEI already exists
    try:
        from biblio.grobid import grobid_outputs_for_key
        from biblio.ref_md import run_ref_md_for_key
        grobid_out = grobid_outputs_for_key(cfg, {citekey!r})
        if grobid_out.tei_path.exists():
            ref_out = run_ref_md_for_key(cfg, {citekey!r}, force={force!r})
            result["ref_md_path"] = str(ref_out.md_path)
            result["ref_md"] = "resolved"
        else:
            result["ref_md"] = "skipped (GROBID TEI not yet available)"
    except Exception as ref_exc:
        result["ref_md"] = f"failed: {{ref_exc}}"

    # Read existing job data to preserve fields, then update
    existing = json.loads(Path({job_file!r}).read_text(encoding="utf-8"))
    existing["status"] = "completed"
    existing["finished"] = _utc_now_iso()
    existing["result"] = result
    _write(existing)

except Exception:
    tb = traceback.format_exc()
    try:
        existing = json.loads(Path({job_file!r}).read_text(encoding="utf-8"))
    except Exception:
        existing = {{"job_id": {job_id!r}, "citekey": {citekey!r}.lstrip("@"), "started": _utc_now_iso()}}
    existing["status"] = "failed"
    existing["finished"] = _utc_now_iso()
    existing["error"] = tb
    _write(existing)
"""
