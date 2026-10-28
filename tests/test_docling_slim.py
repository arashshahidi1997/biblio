"""lit-studio R47: docling JSON without page images; R48: docling version in _biblio.json."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

from biblio.cli import main as biblio_main
from biblio.config import load_biblio_config
from biblio.docling import (
    docling_json_in,
    outputs_for_key,
    run_docling_for_key,
    slim_docling_json,
    strip_page_images,
)
from biblio.scaffold import init_bib_scaffold

PNG = "data:image/png;base64," + "A" * 20000


def _doc(n_pages: int = 3, images: bool = True) -> dict:
    pages = {}
    for i in range(1, n_pages + 1):
        page = {"size": {"width": 595.0, "height": 785.0}, "page_no": i}
        if images:
            page["image"] = {"mimetype": "image/png", "dpi": 144, "size": {"width": 1190.0, "height": 1570.0},
                             "uri": PNG}
        pages[str(i)] = page
    return {
        "schema_name": "DoclingDocument",
        "texts": [{"self_ref": "#/texts/0", "text": "Figure 1. Ripples", "prov": [{"page_no": 1, "bbox": {}}]}],
        "pictures": [{"prov": [{"page_no": 1}], "captions": [{"$ref": "#/texts/0"}],
                      "image": {"uri": "x_artifacts/image_000000_abc.png"}}],
        "pages": pages,
    }


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")


def test_strip_keeps_what_biblio_reads() -> None:
    doc = _doc()
    assert strip_page_images(doc) == 3
    assert all("image" not in p and p["size"]["height"] == 785.0 for p in doc["pages"].values())
    assert doc["pictures"][0]["image"]["uri"].endswith(".png")      # picture refs stay
    assert doc["texts"][0]["text"] == "Figure 1. Ripples"
    assert strip_page_images(doc) == 0


def test_slim_in_place_reports_bytes(tmp_path: Path) -> None:
    path = tmp_path / "k" / "k.json"
    _write(path, _doc())
    before = path.stat().st_size
    r = slim_docling_json(path)
    assert r.status == "slimmed" and r.pages == 3
    assert r.bytes_before == before and r.bytes_after == path.stat().st_size < before / 10
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "image" not in doc["pages"]["1"] and doc["pages"]["2"]["size"]["width"] == 595.0
    assert slim_docling_json(path).status == "already slim"
    assert [p.name for p in path.parent.iterdir()] == ["k.json"]    # no temp file left


def test_slim_dry_run_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "k" / "k.json"
    _write(path, _doc())
    text = path.read_text(encoding="utf-8")
    r = slim_docling_json(path, dry_run=True)
    assert r.status == "would slim" and r.saved > 0
    assert path.read_text(encoding="utf-8") == text


def test_slim_replaces_locked_annex_symlink(tmp_path: Path) -> None:
    """A locked annex file: a symlink to read-only content. The link becomes a regular file."""
    obj = tmp_path / "annex" / "objects" / "SHA256-k.json"
    _write(obj, _doc())
    obj.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    original = obj.read_bytes()
    path = tmp_path / "docling" / "k" / "k.json"
    path.parent.mkdir(parents=True)
    path.symlink_to(os.path.relpath(obj, path.parent))
    assert slim_docling_json(path).status == "slimmed"
    assert not path.is_symlink() and "image" not in json.loads(path.read_text())["pages"]["1"]
    assert obj.read_bytes() == original                              # the annex object is untouched


def test_slim_annexed_without_content(tmp_path: Path) -> None:
    path = tmp_path / "k" / "k.json"
    path.parent.mkdir()
    path.symlink_to("../.git/annex/objects/missing")
    assert slim_docling_json(path).status == "no content"


def test_docling_json_in_pool_folder_with_other_name(tmp_path: Path) -> None:
    folder = tmp_path / "poolkey"
    _write(folder / "otherkey.json", _doc())
    (folder / "_biblio.json").write_text("{}", encoding="utf-8")
    assert docling_json_in(folder) == folder / "otherkey.json"


def _project(tmp_path: Path, **docling: object) -> Path:
    init_bib_scaffold(tmp_path, force=False)
    cfg_path = tmp_path / ".projio" / "biblio" / "biblio.yml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    data.setdefault("docling", {}).update(docling)
    cfg_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return cfg_path


@pytest.mark.parametrize("settings, expected", [
    ({}, False),
    ({"image_export_mode": "embedded"}, True),
    ({"page_images": True}, True),
    ({"image_export_mode": "embedded", "page_images": False}, False),
    ({"page_images": "embedded"}, True),
])
def test_page_images_config(tmp_path: Path, settings: dict, expected: bool) -> None:
    cfg = load_biblio_config(_project(tmp_path, **settings), root=tmp_path)
    assert cfg.docling_page_images is expected


FAKE_DOCLING = r'''
import json, sys
from pathlib import Path
if "--version" in sys.argv:
    print("Docling version: 9.9.9\nDocling Core version: 1.0.0")
    sys.exit(0)
pdf = Path(sys.argv[-1])
Path(pdf.stem + ".md").write_text("# text\n")
Path(pdf.stem + ".json").write_text(json.dumps(DOC, indent=2))
'''


@pytest.mark.parametrize("keep", [False, True])
def test_run_drops_page_images_and_records_version(tmp_path: Path, keep: bool) -> None:
    script = tmp_path / "fake_docling.py"
    script.write_text(f"DOC = {json.dumps(_doc())!r}\nimport json as _j; DOC = _j.loads(DOC)\n" + FAKE_DOCLING,
                      encoding="utf-8")
    from biblio import docling as docling_mod
    docling_mod._VERSIONS.clear()
    cfg = load_biblio_config(_project(tmp_path, cmd=[sys.executable, str(script)], page_images=keep), root=tmp_path)
    pdf = tmp_path / "bib" / "articles" / "smith2020" / "smith2020.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 fake\n")
    out = run_docling_for_key(cfg, "smith2020")
    doc = json.loads(out.json_path.read_text(encoding="utf-8"))
    assert ("image" in doc["pages"]["1"]) is keep
    meta = json.loads(out.meta_path.read_text(encoding="utf-8"))["docling"]
    assert meta["version"] == "9.9.9" and meta["page_images"] is keep
    # a later reuse keeps what the converting run recorded
    run_docling_for_key(cfg, "smith2020")
    meta = json.loads(out.meta_path.read_text(encoding="utf-8"))["docling"]
    assert meta["version"] == "9.9.9" and meta["page_images"] is keep


def test_cli_slim_all_and_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = load_biblio_config(_project(tmp_path), root=tmp_path)
    for key in ("a2020", "b2021"):
        _write(outputs_for_key(cfg, key).json_path, _doc())
    _write(outputs_for_key(cfg, "c2022").json_path, _doc(images=False))
    a = outputs_for_key(cfg, "a2020").json_path
    before = a.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        biblio_main(["docling", "slim", "--all", "--dry-run", "--root", str(tmp_path)])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "2 of 3 JSON files to slim" in out and "would save" in out
    assert a.read_text(encoding="utf-8") == before

    with pytest.raises(SystemExit) as exc:
        biblio_main(["docling", "slim", "--key", "a2020", "--root", str(tmp_path)])
    assert exc.value.code == 0
    assert "1 of 1 JSON files slimmed" in capsys.readouterr().out
    assert "image" not in json.loads(a.read_text(encoding="utf-8"))["pages"]["1"]

    with pytest.raises(SystemExit) as exc:
        biblio_main(["docling", "slim", "--dir", str(cfg.out_root)])
    assert exc.value.code == 0
    assert "1 of 3 JSON files slimmed" in capsys.readouterr().out

    with pytest.raises(SystemExit) as exc:
        biblio_main(["docling", "slim", "--key", "nope", "--root", str(tmp_path)])
    assert exc.value.code == 1
