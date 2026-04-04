from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import BiblioConfig
from .ledger import append_jsonl, file_sha256, new_run_id, utc_now_iso, write_json


@dataclass(frozen=True)
class DoclingOutputs:
    outdir: Path
    md_path: Path
    json_path: Path
    meta_path: Path


def pdf_path_for_key(cfg: BiblioConfig, citekey: str) -> Path:
    key = citekey.lstrip("@")
    rel = Path(cfg.pdf_pattern.format(citekey=key))
    return (cfg.pdf_root / rel).resolve()


def outputs_for_key(cfg: BiblioConfig, citekey: str) -> DoclingOutputs:
    key = citekey.lstrip("@")
    outdir = (cfg.out_root / key).resolve()
    return DoclingOutputs(
        outdir=outdir,
        md_path=outdir / f"{key}.md",
        json_path=outdir / f"{key}.json",
        meta_path=outdir / "_biblio.json",
    )


def resolve_docling_outputs(
    cfg: BiblioConfig, citekey: str, doi: str | None = None,
) -> tuple[DoclingOutputs, str]:
    """Resolve docling outputs, checking pool first then local.

    Returns ``(outputs, source)`` where source is "pool", "local", or "missing".
    Pool outputs are read-only — the returned paths point into the pool directory.
    Uses DOI for matching when citekeys differ between project and pool.
    """
    key = citekey.lstrip("@")

    # Check pool first (by citekey, then by DOI)
    try:
        from .pool import resolve_pool_derivative
        pool_dir = resolve_pool_derivative(cfg, key, "docling", doi=doi)
        if pool_dir is not None:
            # The pool citekey may differ — find the .md file by listing
            md_files = list(pool_dir.glob("*.md"))
            md = md_files[0] if md_files else pool_dir / f"{key}.md"
            json_files = list(pool_dir.glob("*.json"))
            json_ = next((f for f in json_files if f.name != "_biblio.json"), pool_dir / f"{key}.json")
            if md.exists() and md.stat().st_size > 0:
                return DoclingOutputs(
                    outdir=pool_dir,
                    md_path=md,
                    json_path=json_,
                    meta_path=pool_dir / "_biblio.json",
                ), "pool"
    except Exception:
        pass

    # Fall back to local
    local = outputs_for_key(cfg, key)
    if local.md_path.exists() and local.md_path.stat().st_size > 0:
        return local, "local"
    return local, "missing"


def _require_nonempty(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Not a file ({label}): {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Empty {label}: {path}")


def _parse_docling_progress(line: str) -> dict[str, Any] | None:
    """Parse a docling stderr/stdout line for page-level progress."""
    # Docling typically logs lines like "Processing page 3/12" or percentage patterns
    m = re.search(r"[Pp]age\s+(\d+)\s*/\s*(\d+)", line)
    if m:
        return {"done": int(m.group(1)), "total": int(m.group(2))}
    m = re.search(r"(\d+)\s*%", line)
    if m:
        pct = int(m.group(1))
        return {"done": pct, "total": 100}
    return None


def run_docling_for_key(
    cfg: BiblioConfig,
    citekey: str,
    *,
    force: bool = False,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> DoclingOutputs:
    key = citekey.lstrip("@")
    pdf_path = pdf_path_for_key(cfg, key)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found for {key}: {pdf_path}")

    run_id = new_run_id("docling")
    source_hash = file_sha256(pdf_path)

    out = outputs_for_key(cfg, key)
    if out.outdir.exists():
        if not force:
            # If artifacts look good, don't do work.
            try:
                _require_nonempty(out.md_path, "Docling Markdown output")
                _require_nonempty(out.json_path, "Docling JSON output")
                _write_docling_meta(
                    cfg,
                    out,
                    citekey=key,
                    run_id=run_id,
                    source_pdf=pdf_path,
                    source_hash=source_hash,
                    forced=False,
                    reused=True,
                )
                _append_docling_run(
                    cfg,
                    citekey=key,
                    run_id=run_id,
                    source_pdf=pdf_path,
                    source_hash=source_hash,
                    out=out,
                    status="reused",
                    forced=False,
                )
                return out
            except Exception:
                pass
        shutil.rmtree(out.outdir)
    out.outdir.mkdir(parents=True, exist_ok=True)

    # Fail early if Docling isn't runnable (prevents creating empty outdirs).
    exe = cfg.docling_cmd[0] if cfg.docling_cmd else "docling"
    if exe and ("/" not in exe):
        resolved = shutil.which(exe)
        if resolved is None:
            raise FileNotFoundError(
                f"Docling command not found on PATH: {exe!r}. "
                "Install Docling or set `docling.cmd` in bib/config/biblio.yml "
                '(e.g. ["conda","run","-n","docling","docling"] or "docling").'
            )

    # Work inside OUTDIR so Docling doesn't mirror paths under it.
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        tmp_pdf = tmpdir / f"{key}.pdf"
        try:
            tmp_pdf.symlink_to(pdf_path.resolve())
        except Exception:
            shutil.copy2(pdf_path, tmp_pdf)

        cmd: list[str] = list(cfg.docling_cmd)
        for to in cfg.docling_to:
            cmd.extend(["--to", to])
        cmd.extend(
            [
                "--image-export-mode",
                cfg.docling_image_export_mode,
                "--output",
                ".",
                str(tmp_pdf),
            ]
        )

        if progress_cb is not None:
            # Stream stderr line-by-line for progress reporting
            proc = subprocess.Popen(
                cmd, cwd=str(out.outdir),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            # Notify caller of PID so it can be killed on cancel
            progress_cb({"pid": proc.pid, "message": f"Docling started (PID {proc.pid})"})
            accumulated_stderr: list[str] = []
            accumulated_stdout: list[str] = []
            assert proc.stderr is not None  # for type checker
            assert proc.stdout is not None
            for line in proc.stderr:
                accumulated_stderr.append(line)
                stripped = line.rstrip()
                if not stripped:
                    continue
                parsed = _parse_docling_progress(stripped)
                cb_payload: dict[str, Any] = {"line": stripped, "logs": "".join(accumulated_stderr)}
                if parsed:
                    cb_payload["progress"] = parsed
                    cb_payload["message"] = f"Processing page {parsed['done']}/{parsed['total']}"
                else:
                    cb_payload["message"] = stripped[:120]
                progress_cb(cb_payload)
            stdout_data = proc.stdout.read()
            accumulated_stdout.append(stdout_data)
            proc.wait()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(
                    proc.returncode, cmd,
                    "".join(accumulated_stdout),
                    "".join(accumulated_stderr),
                )
        else:
            proc_result = subprocess.run(cmd, cwd=str(out.outdir), capture_output=True, text=True)
            if proc_result.returncode != 0:
                raise subprocess.CalledProcessError(proc_result.returncode, cmd, proc_result.stdout, proc_result.stderr)

    _require_nonempty(out.md_path, "Docling Markdown output")
    _require_nonempty(out.json_path, "Docling JSON output")
    _write_docling_meta(
        cfg,
        out,
        citekey=key,
        run_id=run_id,
        source_pdf=pdf_path,
        source_hash=source_hash,
        forced=force,
        reused=False,
    )
    _append_docling_run(
        cfg,
        citekey=key,
        run_id=run_id,
        source_pdf=pdf_path,
        source_hash=source_hash,
        out=out,
        status="success",
        forced=force,
    )
    return out


def _write_docling_meta(
    cfg: BiblioConfig,
    out: DoclingOutputs,
    *,
    citekey: str,
    run_id: str,
    source_pdf: Path,
    source_hash: str,
    forced: bool,
    reused: bool,
) -> None:
    payload: dict[str, Any] = {
        "citekey": citekey,
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "source": {
            "citekey": citekey,
            "source_pdf": str(source_pdf),
            "pdf_sha256": source_hash,
        },
        "docling": {
            "cmd": list(cfg.docling_cmd),
            "formats": list(cfg.docling_to),
            "image_export_mode": cfg.docling_image_export_mode,
        },
        "outputs": {
            "md_path": str(out.md_path),
            "json_path": str(out.json_path),
        },
        "status": "reused" if reused else "success",
        "forced": forced,
    }
    write_json(out.meta_path, payload)


def _append_docling_run(
    cfg: BiblioConfig,
    *,
    citekey: str,
    run_id: str,
    source_pdf: Path,
    source_hash: str,
    out: DoclingOutputs,
    status: str,
    forced: bool,
) -> None:
    append_jsonl(
        cfg.ledger.docling_runs,
        {
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "stage": "docling",
            "status": status,
            "citekey": citekey,
            "source_bib": None,
            "source_pdf": str(source_pdf),
            "source_pdf_sha256": source_hash,
            "md_path": str(out.md_path),
            "json_path": str(out.json_path),
            "meta_path": str(out.meta_path),
            "forced": forced,
        },
    )
