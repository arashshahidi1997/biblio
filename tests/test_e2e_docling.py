"""End to end: init -> PDF -> docling -> quotes check, with the real docling (R55 item 5).

Runs only with ``BIBLIO_E2E=1`` and a docling command (the ``docling`` extra, or ``BIBLIO_E2E_DOCLING``
naming one). The PDF is made here, so no journal text enters the repository. CI runs it in the
``e2e-docling`` job.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from biblio import cli

KEY = "doe_2024_RippleTest"
SENTENCES = [
    "Ripples were detected in 12 of 14 recording sessions.",
    "The mean ripple frequency was 180 Hz across all animals.",
    "Spindles followed ripples within one second in most cases.",
]


def _docling_cmd() -> str | None:
    named = os.environ.get("BIBLIO_E2E_DOCLING")
    if named:
        return named
    beside = Path(sys.executable).parent / "docling"
    return str(beside) if beside.exists() else shutil.which("docling")


pytestmark = pytest.mark.skipif(
    os.environ.get("BIBLIO_E2E") != "1" or _docling_cmd() is None,
    reason="end-to-end docling test: set BIBLIO_E2E=1 and install the docling extra")


def make_pdf(path: Path, title: str, lines: list[str]) -> None:
    """A one-page PDF with real text (Helvetica), written by hand."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    body = ["BT", "/F1 18 Tf", "72 720 Td", f"({esc(title)}) Tj", "/F1 11 Tf", "0 -36 Td"]
    for line in lines:
        body += [f"({esc(line)}) Tj", "0 -18 Td"]
    body.append("ET")
    stream = "\n".join(body).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


def test_init_docling_quotes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})
    cli.main(["init"])
    cfg = tmp_path / ".projio" / "biblio" / "biblio.yml"
    cfg.write_text(cfg.read_text() + f"\ndocling:\n  cmd: {_docling_cmd()!r}\n")
    pdf = tmp_path / "bib" / "articles" / KEY / f"{KEY}.pdf"
    pdf.parent.mkdir(parents=True)
    make_pdf(pdf, "A Test Of Ripples", SENTENCES)

    cli.main(["docling", "run", "--key", KEY])
    md = tmp_path / "bib" / "derivatives" / "docling" / KEY / f"{KEY}.md"
    assert md.is_file() and "180 Hz" in md.read_text()

    answer = tmp_path / "answers" / f"{KEY}-ripples.md"
    answer.parent.mkdir()
    answer.write_text(
        f'- **measured** — Ripples in most sessions. "{SENTENCES[0][:-1]}" (p. 1)\n'
        f'- **measured** — Frequency. "{SENTENCES[1][:-1]}" (p. 1)\n')
    with pytest.raises(SystemExit) as exc:
        cli.main(["quotes", "check", str(answer), "--text", KEY])
    assert exc.value.code == 0, capsys.readouterr().out
    answer.write_text(answer.read_text().replace("180 Hz", "150 Hz"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["quotes", "check", str(answer), "--text", KEY])
    assert exc.value.code == 1
