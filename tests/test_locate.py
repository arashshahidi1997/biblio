"""`biblio locate`: where is each paper of a list? (journal-club R30)"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from biblio import cli
from biblio.config import default_config_path, load_biblio_config
from biblio.locate import locate, parse_item, to_markdown


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


@pytest.fixture
def cfg(tmp_path: Path):
    src = tmp_path / "bib" / "srcbib"
    src.mkdir(parents=True)
    (src / "main.bib").write_text(
        "@article{buzsaki_2015_HippocampalSharp,\n  author = {Buzsáki, György},\n"
        "  title = {Hippocampal sharp wave-ripple: A cognitive biomarker for episodic memory and planning},\n"
        "  year = {2015},\n  doi = {10.1002/hipo.22488}\n}\n"
        "@article{navarrolobato_2023_IncreasedCortical,\n  author = {Navarro Lobato, Irene and Genzel, Lisa},\n"
        "  title = {Increased cortical plasticity leads to memory interference},\n  year = {2023}\n}\n")
    d = tmp_path / "bib" / "derivatives" / "docling" / "buzsaki_2015_HippocampalSharp"
    d.mkdir(parents=True)
    (d / "buzsaki_2015_HippocampalSharp.md").write_text("# text\n")
    pdf = tmp_path / "bib" / "articles" / "navarrolobato_2023_IncreasedCortical" / "navarrolobato_2023_IncreasedCortical.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4")
    return load_biblio_config(default_config_path(root=tmp_path), root=tmp_path)


def test_parse_item():
    assert parse_item("https://doi.org/10.1038/NN.2344").doi == "10.1038/nn.2344"
    it = parse_item("Pfeiffer & Foster 2013, Hippocampal place-cell sequences")
    assert (it.author, it.year, it.title) == ("pfeiffer", 2013, "Hippocampal place-cell sequences")


def _zotero_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, libraryID INT, key TEXT);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
        CREATE TABLE itemAttachments (itemID INT, parentItemID INT, contentType TEXT);
        CREATE TABLE deletedItems (itemID INT);
        CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, lastName TEXT);
        CREATE TABLE itemCreators (itemID INT, creatorID INT, orderIndex INT);
        CREATE TABLE groups (libraryID INT, name TEXT);
        INSERT INTO fields VALUES (1, 'title'), (2, 'DOI'), (3, 'date');
        INSERT INTO items VALUES (1, 2, '7AP9TICH'), (2, 1, 'KIMA0001'), (3, 1, 'KIMB0002');
        INSERT INTO itemDataValues VALUES (1, 'Hippocampal place-cell sequences depict future paths to remembered goals'),
            (2, '10.1038/nature12112'), (3, '2013'), (4, 'Spindle waves are propagating synchronized oscillations'),
            (5, '1995');
        INSERT INTO itemData VALUES (1, 1, 1), (1, 2, 2), (1, 3, 3), (2, 1, 4), (2, 3, 5), (3, 1, 4), (3, 3, 5);
        INSERT INTO itemAttachments VALUES (10, 1, 'application/pdf'), (11, 2, 'application/pdf');
        INSERT INTO creators VALUES (1, 'Pfeiffer'), (2, 'Kim');
        INSERT INTO itemCreators VALUES (1, 1, 0), (2, 2, 0), (3, 2, 0);
        INSERT INTO groups VALUES (2, 'SirotaLab');
    """)
    con.commit()
    con.close()
    return path


def test_locate_project_zotero_groups_duplicates_and_absent(cfg, tmp_path):
    db = _zotero_db(tmp_path / "zotero.sqlite")
    rows = locate(cfg, ["Buzsaki 2015 Hippocampal sharp wave-ripple", "Navarro-Lobato 2023",
                        "10.1038/nature12112", "Kim 1995 Spindle waves", "Nobody 2001 Nothing here"],
                  zotero=db)
    by = {r.item.raw.split()[0]: r for r in rows}
    assert by["Buzsaki"].status == "project: full text" and by["Buzsaki"].via == "author-year"
    assert by["Navarro-Lobato"].status == "project: PDF only"
    assert by["10.1038/nature12112"].status == "zotero (SirotaLab): PDF only"
    assert by["Kim"].note == "2 Zotero items" and {h["status"] for h in by["Kim"].holdings} == {"pdf", "metadata"}
    assert by["Nobody"].status == "not held"
    md = to_markdown(rows)
    assert "https://doi.org/10.1002/hipo.22488" in md and "zotero SirotaLab `2:7AP9TICH` PDF" in md
    assert md.rstrip().endswith("5 papers: 3 PDF only, 1 full text, 1 not held.")


def test_cli(cfg, capsys, tmp_path):
    f = tmp_path / "list.txt"
    f.write_text("# capture list\n- 10.1002/hipo.22488\n")
    out = tmp_path / "loc.json"
    cli.main(["locate", "--from", str(f), "--json", str(out), "--root", str(cfg.repo_root)])
    text = capsys.readouterr().out
    assert "| 1 | 10.1002/hipo.22488" in text and "Zotero not searched" in text
    assert '"status": "project: full text"' in out.read_text()
