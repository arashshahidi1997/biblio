from __future__ import annotations

from pathlib import Path

from .ledger import utc_now_iso

_TIMESTAMP_RE_CHARS = "".join(c if c.isalnum() else "_" for c in "")


def _safe_filename(name: str) -> str:
    """Return a filesystem-safe version of a filename."""
    import re
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200]


def create_pool_app(inbox_dir: Path):
    """Create a FastAPI app that accepts PDF drops into inbox_dir."""
    try:
        import fastapi
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as e:
        raise ImportError(
            "FastAPI is required for biblio pool serve. Install with: pip install biblio-tools[ui]"
        ) from e

    inbox_dir = inbox_dir.expanduser().resolve()
    inbox_dir.mkdir(parents=True, exist_ok=True)

    app = fastapi.FastAPI(title="biblio pool server", version="0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "inbox": str(inbox_dir)}

    @app.post("/drop")
    async def drop_pdf(
        file: fastapi.UploadFile = fastapi.File(...),
        doi: str | None = fastapi.Form(default=None),
        url: str | None = fastapi.Form(default=None),
    ):
        """Accept a PDF file upload and save it to the inbox directory."""
        ts = utc_now_iso().replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
        orig_name = _safe_filename(file.filename or "paper.pdf")
        if not orig_name.lower().endswith(".pdf"):
            orig_name += ".pdf"
        dest_name = f"{ts}_{orig_name}"
        dest = inbox_dir / dest_name
        content = await file.read()
        dest.write_bytes(content)
        meta_path = dest.with_suffix(".meta.txt")
        lines = []
        if doi:
            lines.append(f"doi: {doi}")
        if url:
            lines.append(f"url: {url}")
        if lines:
            meta_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {
            "status": "received",
            "filename": dest_name,
            "size_bytes": len(content),
            "doi": doi,
            "url": url,
        }

    @app.post("/drop-doi")
    async def drop_doi(
        doi: str = fastapi.Form(...),
        url: str | None = fastapi.Form(default=None),
    ):
        """Record a DOI (no PDF) for later queue drain."""
        ts = utc_now_iso().replace(":", "").replace("-", "").replace("T", "_").replace("Z", "")
        safe_doi = _safe_filename(doi.replace("/", "_"))
        meta_path = inbox_dir / f"{ts}_{safe_doi}.doi.txt"
        lines = [f"doi: {doi}"]
        if url:
            lines.append(f"url: {url}")
        meta_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"status": "queued", "doi": doi, "url": url}

    return app


def serve_pool(
    inbox_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 7171,
) -> None:
    """Start the pool HTTP server (blocks until interrupted)."""
    try:
        import uvicorn
    except ImportError as e:
        raise ImportError(
            "uvicorn is required for biblio pool serve. Install with: pip install biblio-tools[ui]"
        ) from e

    app = create_pool_app(inbox_dir)
    print(f"biblio pool server listening on http://{host}:{port}")
    print(f"Inbox: {inbox_dir.expanduser().resolve()}")
    uvicorn.run(app, host=host, port=port)
