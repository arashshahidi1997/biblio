"""Named keys for the extraction batch, and papers added since the last merge (journal-club R28)."""
from __future__ import annotations

from pathlib import Path

import pytest

from biblio import cli
from biblio.batch import plan_docling_batch
from biblio.citekeys import load_active_citekeys, read_key_list
from biblio.config import default_config_path, load_biblio_config


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


def _entry(key: str) -> str:
    return f"@article{{{key},\n  title = {{T {key}}},\n  year = {{2020}}\n}}\n"


@pytest.fixture
def cfg(tmp_path: Path):
    cfg = load_biblio_config(default_config_path(root=tmp_path), root=tmp_path)
    cfg.bibtex_merge.src_dir.mkdir(parents=True)
    (cfg.bibtex_merge.src_dir / "main.bib").write_text(_entry("old_2020_A") + _entry("mine_2021_B"))
    cfg.bibtex_merge.out_bib.parent.mkdir(parents=True, exist_ok=True)
    cfg.bibtex_merge.out_bib.write_text(_entry("old_2020_A"))  # merged before mine_2021_B was added
    (cfg.bibtex_merge.src_dir / "zotero.bib").write_text(_entry("other_2019_C") + "@comment{x,\n}\n")
    for key in ("old_2020_A", "mine_2021_B", "other_2019_C"):
        pdf = cfg.pdf_root / cfg.pdf_pattern.format(citekey=key)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4")
    done = cfg.out_root / "old_2020_A"
    done.mkdir(parents=True)
    (done / "old_2020_A.md").write_text("# done\n\ntext\n")
    return cfg


def test_srcbib_keys_are_active_before_merge(cfg):
    assert load_active_citekeys(cfg) == ["mine_2021_B", "old_2020_A", "other_2019_C"]


def test_named_keys_only(cfg, monkeypatch):
    monkeypatch.setattr("biblio.docling.resolve_docling_outputs",
                        lambda c, k, doi=None: (None, "local" if k == "old_2020_A" else "missing"))
    pending, skipped = plan_docling_batch(cfg, keys=["mine_2021_B", "old_2020_A", "ghost_2000_X"])
    assert pending == ["mine_2021_B"]          # other_2019_C is someone else's: not touched
    assert skipped == [("old_2020_A", "done"), ("ghost_2000_X", "not in the bibliography, no PDF")]
    pending, _ = plan_docling_batch(cfg)
    assert pending == ["mine_2021_B", "other_2019_C"]


def test_read_key_list(tmp_path):
    f = tmp_path / "keys.txt"
    f.write_text("# the new ones\n@a_2020_X\n- b_2021_Y, c_2022_Z  # two\n\na_2020_X\n")
    assert read_key_list("d_1,  e_2", f) == ["d_1", "e_2", "a_2020_X", "b_2021_Y", "c_2022_Z"]


def test_cli_batch_reports_skips(cfg, monkeypatch, capsys):
    monkeypatch.setattr("biblio.docling.resolve_docling_outputs",
                        lambda c, k, doi=None: (None, "local" if k == "old_2020_A" else "missing"))
    ran = []
    monkeypatch.setattr("biblio.batch.run_docling_for_key", lambda c, k, force=False: ran.append(k))
    with pytest.raises(SystemExit) as exc:
        cli.main(["docling", "batch", "--root", str(cfg.repo_root), "--keys", "mine_2021_B,old_2020_A,ghost_2000_X"])
    assert exc.value.code == 1                 # a named key could not be converted
    assert ran == ["mine_2021_B"]
    err = capsys.readouterr().err
    assert "[SKIP] old_2020_A: done" in err and "[SKIP] ghost_2000_X: not in the bibliography, no PDF" in err
