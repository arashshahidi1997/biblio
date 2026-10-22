"""Every command resolves .projio/biblio/biblio.yml first, then the legacy bib/config/biblio.yml."""
from __future__ import annotations

from pathlib import Path

import pytest

import biblio.cli as cli

COMMANDS = [
    ["docling", "run", "--key", "x"],
    ["docling", "batch"],
    ["grobid", "check"],
    ["library", "list"],
    ["bibtex", "merge"],
    ["openalex", "resolve"],
    ["queue", "list"],
    ["site", "doctor"],
    ["ref-md", "run", "--key", "x"],
    ["summarize", "x"],
]


class _Loaded(Exception):
    def __init__(self, path):
        self.path = Path(path)


def _capture(monkeypatch):
    def fake_load(path, *, root=None):
        raise _Loaded(path)
    monkeypatch.setattr(cli, "load_biblio_config", fake_load)


@pytest.mark.parametrize("argv", COMMANDS, ids=lambda a: " ".join(a[:2]))
def test_projio_layout_is_used(tmp_path, monkeypatch, argv):
    cfg = tmp_path / ".projio" / "biblio" / "biblio.yml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("pdf_root: bib/articles\n")
    _capture(monkeypatch)
    with pytest.raises(_Loaded) as exc:
        cli.main([*argv, "--root", str(tmp_path)])
    assert exc.value.path.resolve() == cfg.resolve()


@pytest.mark.parametrize("argv", COMMANDS[:3], ids=lambda a: " ".join(a[:2]))
def test_legacy_layout_still_works(tmp_path, monkeypatch, argv):
    cfg = tmp_path / "bib" / "config" / "biblio.yml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("pdf_root: bib/articles\n")
    _capture(monkeypatch)
    with pytest.raises(_Loaded) as exc:
        cli.main([*argv, "--root", str(tmp_path)])
    assert exc.value.path.resolve() == cfg.resolve()


def test_no_hardcoded_legacy_path_in_commands():
    src = Path(cli.__file__).parent
    for name in ("cli.py", "ui.py", "site.py", "pool.py"):
        text = (src / name).read_text(encoding="utf-8")
        assert '"bib" / "config" / "biblio.yml"' not in text, name
