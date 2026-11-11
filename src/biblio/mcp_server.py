"""``biblio mcp``: a small MCP server over the stable commands (beta; needs ``biblio-tools[mcp]``).

Six tools, each a thin wrapper over what the CLI and projio's biblio tools already run
(:mod:`biblio.mcp`), so the two servers share one implementation. The skills do not need it;
it is for clients that prefer tools to a shell. Stdio transport.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from .paths import find_repo_root


def _run_cli(argv: list[str]) -> dict[str, Any]:
    """Run ``biblio <argv>`` in process; return its exit code and output."""
    from . import cli

    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cli.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
            if not isinstance(exc.code, int) and exc.code:
                err.write(str(exc.code))
    return {"exit": code, "output": out.getvalue(), **({"error": err.getvalue()} if err.getvalue() else {})}


def build_server(root: Path | None = None):
    """The FastMCP server, with every tool bound to ``root`` (default: the workspace around cwd)."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:   # pragma: no cover - depends on the extra
        from ._extras import install_hint
        raise SystemExit("[ERROR] biblio mcp needs " + install_hint("mcp")) from exc
    from . import mcp as api

    root = (root or find_repo_root()).resolve()
    server = FastMCP("biblio", instructions=(
        "biblio: papers into checkable full text. Look papers up (project and shared pools), read their "
        "text by section, line or search, check quotes against them, add papers, and convert them "
        "(docling, GROBID) as background jobs. Quote only from paper_text output, and check every "
        f"quote with quotes_check before showing it. Workspace: {root}"))

    @server.tool()
    def paper_lookup(refs: list[str], detail: str = "summary") -> dict[str, Any]:
        """Papers by citekey, DOI or "Author Year Title", in the project or a shared pool: the
        bibliographic record and where the PDF, full text, GROBID output and figures are; for papers
        not held, a doi.org link. detail="context" adds the full text's sections."""
        return api.paper_lookup(refs, root=root, detail=detail)

    @server.tool()
    def paper_text(citekey: str, section: str = "", grep: str = "", lines: str = "") -> dict[str, Any]:
        """A held paper's full text (project or pool), as `biblio fulltext` prints it: without
        options the list of sections; `section` (id like S3, or title) one section; `grep` a
        case-insensitive regex, with section and line per hit; `lines` "A-B"."""
        argv = ["fulltext", citekey, "--root", str(root)]
        for flag, value in (("--section", section), ("--grep", grep), ("--lines", lines)):
            if value:
                argv += [flag, value]
        return _run_cli(argv)

    @server.tool()
    def quotes_check(file: str, texts: list[str] | None = None) -> dict[str, Any]:
        """Check the quotes in a markdown file. With `texts` (citekeys or .md/.txt/.pdf paths),
        every "quoted string" of 12+ characters must be in those texts; without, the file's
        `- id, citekey, section, L<n>: "quote"` items are checked. exit 0 means all exact."""
        argv = ["quotes", "check", file, "--root", str(root), "--json", "-"]
        for t in texts or []:
            argv += ["--text", t]
        res = _run_cli(argv)
        text = res["output"]
        start = text.find("\n{")
        if start != -1 or text.startswith("{"):
            body = text[start + 1:] if start != -1 else text
            with contextlib.suppress(json.JSONDecodeError):
                res["results"] = json.loads(body)
                res["output"] = text[:start] if start != -1 else ""
        return res

    @server.tool()
    def paper_add(refs: list[str], source: str = "doi") -> dict[str, Any]:
        """Add papers to the bibliography. source="doi": DOIs, metadata from the DOI registry;
        source="zotero": item keys, DOIs or titles from the Zotero app on this machine (local API),
        PDFs copied. Never bulk-download papers from publishers."""
        if source == "doi":
            return api.ingest_dois(refs, root=root)
        if source == "zotero":
            return _run_cli(["add", "zotero", *refs, "--local", "--root", str(root)])
        return {"error": 'source must be "doi" or "zotero"'}

    @server.tool()
    def paper_job(action: str, kind: str = "", keys: list[str] | None = None, job_id: str = "",
                  force: bool = False) -> dict[str, Any]:
        """Background conversion: action="start" with kind docling or grobid (or oa_fetch, digest)
        and the citekeys to touch; "status" with job_id; "list"; "kill". Always name the keys."""
        return api.job(action, root=root, kind=kind, keys=keys, job_id=job_id, force=force)

    @server.tool()
    def pipeline_status(citekeys: list[str] | None = None) -> dict[str, Any]:
        """Per paper: whether the PDF, docling text, GROBID output and figures exist."""
        return api.pipeline_status(root=root, citekeys=citekeys)

    return server


def serve(root: Path | None = None) -> None:
    build_server(root).run()
