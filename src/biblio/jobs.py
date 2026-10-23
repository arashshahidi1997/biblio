"""Background job management for long-running biblio operations."""
from __future__ import annotations

import json
import re
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
    progress: dict[str, Any] | None = None


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
        progress=data.get("progress"),
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


def launch_docling_batch_background(
    root: Path,
    *,
    concurrency: int = 1,
    force: bool = False,
    filter_glob: str | None = None,
    keys: list[str] | None = None,
) -> tuple[str, int]:
    """Spawn a background subprocess that runs batch docling (only ``keys`` when given).

    Returns ``(job_id, total_pending)`` immediately.
    The ``total_pending`` is determined before the subprocess starts so the
    caller can report it; the actual execution happens in the background.
    """
    # Pre-scan to get the count (fast — only stat calls).
    from .batch import find_pending_docling
    from .config import default_config_path, load_biblio_config

    cfg_path = default_config_path(root=root)
    cfg = load_biblio_config(cfg_path, root=root)
    pending, _done = find_pending_docling(cfg, filter_glob=filter_glob, force=force, keys=keys)
    total = len(pending)

    job_id = new_run_id("docling_batch")
    job_file = _job_path(root, job_id)
    job_file.parent.mkdir(parents=True, exist_ok=True)

    worker_code = _build_batch_worker_script(
        root=str(root),
        concurrency=concurrency,
        force=force,
        filter_glob=filter_glob,
        job_id=job_id,
        job_file=str(job_file),
        keys=keys,
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", worker_code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    _write_job(root, job_id, {
        "job_id": job_id,
        "type": "batch",
        "status": "running",
        "citekey": "(batch)",
        "pid": proc.pid,
        "started": utc_now_iso(),
        "finished": None,
        "result": None,
        "error": None,
        "progress": {"total": total, "done": 0, "failed": 0},
    })

    return job_id, total


def launch_pdf_fetch_oa_background(
    root: Path,
    *,
    force: bool = False,
    citekey_filter: set[str] | None = None,
) -> tuple[str, int]:
    """Spawn a background subprocess that runs open-access PDF fetching.

    Returns ``(job_id, total_papers)`` immediately.
    """
    from .config import default_config_path, load_biblio_config

    cfg_path = default_config_path(root=root)
    cfg = load_biblio_config(cfg_path, root=root)

    # Count papers to process (fast — reads resolved.jsonl line count)
    total = 0
    if cfg.openalex.out_jsonl.exists():
        total = sum(1 for line in cfg.openalex.out_jsonl.open(encoding="utf-8") if line.strip())
    if citekey_filter:
        total = min(total, len(citekey_filter))

    job_id = new_run_id("pdf_fetch_oa")
    job_file = _job_path(root, job_id)
    job_file.parent.mkdir(parents=True, exist_ok=True)

    worker_code = _build_pdf_fetch_oa_worker_script(
        root=str(root),
        force=force,
        citekey_filter=sorted(citekey_filter) if citekey_filter else None,
        job_id=job_id,
        job_file=str(job_file),
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", worker_code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    _write_job(root, job_id, {
        "job_id": job_id,
        "type": "pdf_fetch_oa",
        "status": "running",
        "citekey": "(batch)",
        "pid": proc.pid,
        "started": utc_now_iso(),
        "finished": None,
        "result": None,
        "error": None,
        "progress": {"total": total, "done": 0, "failed": 0},
    })

    return job_id, total


def _build_pdf_fetch_oa_worker_script(
    root: str,
    force: bool,
    citekey_filter: list[str] | None,
    job_id: str,
    job_file: str,
) -> str:
    """Build the Python code for the background PDF fetch subprocess."""
    return f"""\
import json, sys, time, traceback
from pathlib import Path

def _utc_now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def _write(data):
    p = Path({job_file!r})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\\n", encoding="utf-8")

def _read():
    p = Path({job_file!r})
    return json.loads(p.read_text(encoding="utf-8"))

try:
    from biblio.config import default_config_path, load_biblio_config
    from biblio.pdf_fetch_oa import fetch_pdfs_oa, ALL_STATUSES

    root = Path({root!r})
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    ck_filter = set({citekey_filter!r}) if {citekey_filter!r} else None

    _start = time.monotonic()

    def _progress_cb(prog):
        try:
            elapsed = time.monotonic() - _start
            done = int(prog.get("completed") or 0)
            total = int(prog.get("total") or 0)
            eta = None
            if done > 0 and total > done:
                eta = round((elapsed / done) * (total - done), 1)
            existing = _read()
            existing["progress"] = {{
                "total": total,
                "done": done,
                "failed": 0,
                "current_key": prog.get("citekey") or "",
                "elapsed_s": round(elapsed, 1),
                "eta_s": eta,
            }}
            _write(existing)
        except Exception:
            pass

    results = fetch_pdfs_oa(
        cfg,
        force={force!r},
        citekey_filter=ck_filter,
        progress_cb=_progress_cb,
    )

    elapsed = round(time.monotonic() - _start, 1)
    counts = {{s: sum(1 for r in results if r.status == s) for s in ALL_STATUSES}}
    errors = [
        {{"citekey": r.citekey, "error": r.error}}
        for r in results if r.error
    ]

    existing = _read()
    existing["status"] = "completed"
    existing["finished"] = _utc_now_iso()
    existing["result"] = {{
        "total": len(results),
        **counts,
        "elapsed_s": elapsed,
        "errors": errors[:20],
    }}
    existing["progress"] = {{
        "total": len(results),
        "done": len(results),
        "failed": counts.get("error", 0),
    }}
    _write(existing)

except Exception:
    tb = traceback.format_exc()
    try:
        existing = _read()
    except Exception:
        existing = {{"job_id": {job_id!r}, "type": "pdf_fetch_oa", "started": _utc_now_iso()}}
    existing["status"] = "failed"
    existing["finished"] = _utc_now_iso()
    existing["error"] = tb
    _write(existing)
"""


def _build_batch_worker_script(
    root: str,
    concurrency: int,
    force: bool,
    filter_glob: str | None,
    job_id: str,
    job_file: str,
    keys: list[str] | None = None,
) -> str:
    """Build the Python code for the background batch subprocess."""
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

def _read():
    p = Path({job_file!r})
    return json.loads(p.read_text(encoding="utf-8"))

try:
    from biblio.config import default_config_path, load_biblio_config
    from biblio.batch import find_pending_docling, run_docling_batch

    root = Path({root!r})
    cfg = load_biblio_config(default_config_path(root=root), root=root)
    pending, already_done = find_pending_docling(
        cfg,
        filter_glob={filter_glob!r},
        force={force!r},
        keys={keys!r},
    )

    def _progress_cb(prog):
        try:
            existing = _read()
            existing["progress"] = {{
                "total": prog.total,
                "done": prog.done,
                "failed": prog.failed,
                "current_key": prog.current_key,
                "elapsed_s": round(prog.elapsed_s, 1),
                "eta_s": round(prog.eta_s, 1) if prog.eta_s is not None else None,
            }}
            _write(existing)
        except Exception:
            pass

    result = run_docling_batch(
        cfg,
        pending,
        concurrency={concurrency!r},
        force={force!r},
        progress_cb=_progress_cb,
    )

    existing = _read()
    existing["status"] = "completed"
    existing["finished"] = _utc_now_iso()
    existing["result"] = {{
        "total": result.total,
        "processed": result.processed,
        "failed": result.failed,
        "skipped": len(already_done),
        "elapsed_s": round(result.elapsed_s, 1),
        "successes": result.successes,
        "failures": result.failures,
    }}
    existing["progress"] = {{
        "total": result.total,
        "done": result.processed + result.failed,
        "failed": result.failed,
    }}
    _write(existing)

except Exception:
    tb = traceback.format_exc()
    try:
        existing = _read()
    except Exception:
        existing = {{"job_id": {job_id!r}, "type": "batch", "started": _utc_now_iso()}}
    existing["status"] = "failed"
    existing["finished"] = _utc_now_iso()
    existing["error"] = tb
    _write(existing)
"""


# ---------------------------------------------------------------------------
# CLI jobs: one biblio command run in the background (the MCP job handle)
# ---------------------------------------------------------------------------

CLI_JOB_KINDS = ("docling", "grobid", "oa_fetch", "digest")


def cli_job_argv(kind: str, keys: list[str] | None = None, *, force: bool = False, concurrency: int = 1,
                 context: str = "wiki", stale: bool = False) -> list[str]:
    """The biblio CLI arguments a job of ``kind`` runs (the same command a person would type)."""
    keys = [k.lstrip("@") for k in keys or [] if k.strip()]
    joined = ",".join(keys)
    if kind == "docling":
        argv = ["docling", "batch"] + (["--keys", joined] if keys else [])
        argv += ["--concurrency", str(concurrency)] if concurrency > 1 else []
    elif kind == "grobid":
        argv = ["grobid", "run"] + (["--keys", joined] if keys else ["--all"])
    elif kind == "oa_fetch":
        argv = ["bibtex", "fetch-pdfs-oa"] + (["--citekeys", *keys] if keys else [])
    elif kind == "digest":
        if not keys:
            raise ValueError("a digest job needs keys")
        argv = ["digest", "claims", "--keys", joined, "--context", context]
        argv += ["--concurrency", str(concurrency)] if concurrency > 1 else []
        argv += ["--stale"] if stale else []
    else:
        raise ValueError(f"unknown job kind {kind!r}; known: {', '.join(CLI_JOB_KINDS)}")
    return argv + (["--force"] if force else [])


_CLI_WORKER = """\
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
job = Path({job_file!r})
with open({log!r}, "ab") as log:
    rc = subprocess.run({cmd!r}, cwd={root!r}, stdout=log, stderr=subprocess.STDOUT).returncode
data = json.loads(job.read_text(encoding="utf-8"))
if data.get("status") == "running":
    data["status"] = "completed" if rc == 0 else "failed"
data["exit_code"] = rc
data["finished"] = datetime.now(timezone.utc).isoformat()
job.write_text(json.dumps(data, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
"""


def launch_cli_job(root: Path, kind: str, keys: list[str] | None = None, **opts: Any) -> dict[str, Any]:
    """Start ``biblio <argv for kind>`` detached; returns the job record (``job_id``, ``argv``, ``log``)."""
    argv = cli_job_argv(kind, keys, **opts)
    job_id = new_run_id(f"job_{kind}")
    job_file = _job_path(root, job_id)
    log = _jobs_dir(root) / f"{job_id}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "biblio.cli", *argv[:2], "--root", str(root), *argv[2:]]
    record = {"job_id": job_id, "type": "cli", "kind": kind, "argv": ["biblio", *argv], "status": "running",
              "citekey": ",".join(keys or []) or "(all)", "started": utc_now_iso(), "finished": None,
              "log": str(log), "exit_code": None, "pid": None, "result": None, "error": None}
    _write_job(root, job_id, record)
    proc = subprocess.Popen([sys.executable, "-c", _CLI_WORKER.format(job_file=str(job_file), log=str(log),
                                                                      cmd=cmd, root=str(root))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    record["pid"] = proc.pid
    _write_job(root, job_id, record)
    return record


_PROGRESS = re.compile(r"^\s*\[(?:RUN |OK |FAIL )?(\d+)/(\d+)\]")
_SUMMARY = re.compile(r"^\s*\[(DONE|OK|FAIL|ERROR|SKIP|MISS|failed|done)\b|^\s*(?:\d+ papers|\[INFO\] pending)")


def cli_job_status(root: Path, job_id: str, *, lines: int = 15) -> dict[str, Any] | None:
    """A CLI job's state, progress (the last "[n/total]" line) and its summary lines; None if unknown.

    Jobs started by the older launchers (docling, batch, OA fetch) are read too.
    """
    data = _read_job(root, job_id)
    if data is None:
        return None
    if data.get("type") != "cli":
        info = get_job_status(root, job_id)
        return {k: v for k, v in info.__dict__.items() if v is not None} if info else None
    if data["status"] == "running" and data.get("pid") and not _pid_alive(data["pid"]):
        data = _read_job(root, job_id) or data            # the worker may have just finished
        if data["status"] == "running":
            data.update(status="failed", error="process ended without recording an exit code",
                        finished=utc_now_iso())
            _write_job(root, job_id, data)
    text = Path(data["log"]).read_text(encoding="utf-8", errors="replace") if Path(data["log"]).is_file() else ""
    log_lines = text.splitlines()
    progress = None
    for ln in reversed(log_lines):
        m = _PROGRESS.match(ln)
        if m:
            progress = {"done": int(m.group(1)), "total": int(m.group(2)), "line": ln.strip()[:200]}
            break
    summary = [ln.strip()[:300] for ln in log_lines if _SUMMARY.match(ln)][-lines:]
    out = {k: data.get(k) for k in ("job_id", "kind", "argv", "status", "exit_code", "started", "finished",
                                    "log", "error")}
    out["progress"] = progress
    out["summary"] = summary
    if data["status"] != "running" and not summary:
        out["tail"] = [ln[:300] for ln in log_lines[-lines:]]
    return out


def kill_cli_job(root: Path, job_id: str) -> dict[str, Any]:
    """Stop a running job (its whole process group)."""
    import os
    import signal
    data = _read_job(root, job_id)
    if data is None:
        return {"error": f"no job {job_id}"}
    if data.get("status") != "running" or not data.get("pid"):
        return {"job_id": job_id, "status": data.get("status"), "note": "not running"}
    try:
        os.killpg(os.getpgid(int(data["pid"])), signal.SIGTERM)
    except (OSError, ProcessLookupError) as exc:
        return {"job_id": job_id, "error": str(exc)}
    data.update(status="killed", finished=utc_now_iso())
    _write_job(root, job_id, data)
    return {"job_id": job_id, "status": "killed"}
