from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _require_nonempty(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Not a file ({label}): {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Empty {label}: {path}")


def run_docling_for_key(cfg: BiblioConfig, citekey: str, *, force: bool = False) -> DoclingOutputs:
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
                '(e.g. ["conda","run","-n","rag","docling"]).'
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

        subprocess.run(cmd, cwd=str(out.outdir), check=True)

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
