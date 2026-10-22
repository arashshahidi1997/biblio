"""Reference triage for one paper (backlog I05)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from biblio import refs
from biblio.config import default_config_path, load_biblio_config

KEY = "aleman_2026_Deltas"


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


def _bib(path: Path, entries: list[tuple[str, dict[str, str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ""
    for key, fields in entries:
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items())
        text += f"@article{{{key},\n{body}\n}}\n\n"
    path.write_text(text)


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


REFERENCES = [
    # 1: in the pool with docling, matched by DOI
    {"title": "Selective suppression of hippocampal ripples", "authors": ["G Girardeau"], "year": "2009",
     "doi": "10.1038/NN.2384"},
    # 2: project PDF, no DOI from GROBID, title with the venue glued on
    {"title": "Biasing the content of hippocampal replay during sleep. Nat Neurosci", "authors": ["D Bendor"],
     "year": "2012", "doi": None},
    # 3: pool entry without PDF -> metadata; OCR noise in the title
    {"title": "Hippocampal CA2 sharp-wave ripples reactivate and promote socia1 memory", "authors": ["A Oliva"],
     "year": "2020"},
    # 4: same title, wrong year -> not a match
    {"title": "Long-duration hippocampal sharp wave ripples improve memory", "authors": ["A Fernandez-Ruiz"],
     "year": "1999"},
    # 5: nowhere
    {"title": "A paper nobody holds at all", "authors": ["N Body"], "year": "2001"},
]


@pytest.fixture
def project(tmp_path: Path):
    root = tmp_path / "proj"
    _bib(root / "bib" / "srcbib" / "main.bib", [
        (KEY, {"title": "Deltas and spindles", "year": "2026", "doi": "10.1093/sleep/x"}),
        ("bendor_2012_Biasing", {"title": "Biasing the content of hippocampal replay during sleep",
                                 "year": "2012"}),
        ("fernandezruiz_2019_Long", {"title": "Long-duration hippocampal sharp wave ripples improve memory",
                                     "year": "2019"}),
    ])
    _touch(root / "bib" / "articles" / "bendor_2012_Biasing" / "bendor_2012_Biasing.pdf")
    grobid = root / "bib" / "derivatives" / "grobid" / KEY
    _touch(grobid / "references.json", json.dumps(REFERENCES))
    _touch(grobid / "header.json", json.dumps({"doi": "10.1093/sleep/x"}))

    pool = tmp_path / "sirocampus"
    _bib(pool / ".projio" / "biblio" / "merged.bib", [
        ("girardeau_2009_Selective", {"title": "Selective suppression of hippocampal ripples impairs spatial memory",
                                      "year": "2009", "doi": "10.1038/nn.2384"}),
        ("oliva_2020_CA2", {"title": "Hippocampal CA2 sharp-wave ripples reactivate and promote social memory",
                            "year": "2020"}),
    ])
    _touch(pool / "bib" / "articles" / "girardeau_2009_Selective" / "girardeau_2009_Selective.pdf")
    _touch(pool / "bib" / "derivatives" / "docling" / "girardeau_2009_Selective" / "girardeau_2009_Selective.md")
    (pool / "bib" / "articles" / "oliva_2020_CA2").mkdir(parents=True)

    _touch(root / ".projio" / "biblio" / "biblio.yml", f"pool:\n  search:\n    - {pool / 'bib' / 'articles'}\n")
    return load_biblio_config(default_config_path(root=root), root=root)


def test_triage_statuses_and_matching(project):
    result = refs.triage(project, KEY)
    rows = {r["n"]: r for r in result["references"]}

    assert rows[1]["status"] == "fulltext" and rows[1]["via"] == "doi"
    assert rows[1]["held"] == [{"where": "pool:sirocampus", "key": "girardeau_2009_Selective",
                                "status": "fulltext"}]
    assert rows[2]["status"] == "pdf" and rows[2]["via"] == "title"
    assert rows[3]["status"] == "metadata" and rows[3]["held"][0]["key"] == "oliva_2020_CA2"
    assert rows[4]["status"] == "absent"  # title matches, year is 20 years off
    assert rows[5]["status"] == "absent"
    assert result["counts"] == {"fulltext": 1, "pdf": 1, "metadata": 1, "absent": 2}
    assert result["doi"] == "10.1093/sleep/x"
    assert result["searched"] == ["pool:sirocampus", "project"]


def test_zotero_sqlite_and_bib_export(project, tmp_path):
    db = tmp_path / "zotero.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE items (itemID INTEGER PRIMARY KEY, libraryID INT, key TEXT);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INT, fieldID INT, valueID INT);
        CREATE TABLE itemAttachments (itemID INT, parentItemID INT, contentType TEXT);
        CREATE TABLE deletedItems (itemID INT);
        INSERT INTO fields VALUES (1, 'title'), (2, 'DOI'), (3, 'date'), (4, 'extra');
        INSERT INTO items VALUES (10, 1, 'NOBODY01'), (11, 1, 'PDFATT01'), (12, 1, 'TRASHED1');
        INSERT INTO itemDataValues VALUES (1, 'A paper nobody holds at all'), (2, '2001-03-01'),
                                          (3, 'unrelated'), (4, 'DOI: 10.9/trashed');
        INSERT INTO itemData VALUES (10, 1, 1), (10, 3, 2), (12, 1, 3), (12, 4, 4);
        INSERT INTO itemAttachments VALUES (11, 10, 'application/pdf');
        INSERT INTO deletedItems VALUES (12);
    """)
    con.commit()
    con.close()

    rows = refs.triage(project, KEY, zotero=db)["references"]
    assert rows[4]["status"] == "pdf"
    assert rows[4]["held"] == [{"where": "zotero", "key": "1:NOBODY01", "status": "pdf"}]

    export = tmp_path / "zotero.bib"
    _bib(export, [("nobody2001", {"title": "A paper nobody holds at all", "year": "2001",
                                  "file": "Body - 2001.pdf:/home/x/Body - 2001.pdf:application/pdf"})])
    assert refs.triage(project, KEY, zotero=export)["references"][4]["status"] == "pdf"


def test_openalex_recovers_dois_and_missed_references(project, monkeypatch):
    oa_refs = [
        {"openalex": "W1", "doi": "10.1038/nn.2384", "title": "Selective suppression ...", "year": 2009},
        {"openalex": "W3", "doi": "10.1038/s41586-020-2758-y",
         "title": "Hippocampal CA2 sharp-wave ripples reactivate and promote social memory", "year": 2020},
        {"openalex": "W9", "doi": "10.1/missed", "title": "A reference GROBID never saw", "year": 2015},
    ]
    monkeypatch.setattr(refs, "openalex_references", lambda cfg, doi, fetch=True: oa_refs)
    result = refs.triage(project, KEY, use_openalex=True)
    rows = result["references"]

    assert rows[2]["doi"] == "10.1038/s41586-020-2758-y" and rows[2]["openalex"] == "W3"
    assert [r["openalex"] for r in rows if r["source"] == "openalex"] == ["W9"]
    assert len(rows) == 6
    assert "OpenAlex: 3 referenced works" in result["notes"][0]


def test_openalex_references_reads_cache(project):
    cache = project.openalex_cache
    cache.save_json(cache.path_for_doi("10.1093/sleep/x"),
                    {"id": "https://openalex.org/W0", "referenced_works": ["https://openalex.org/W1"]})
    cache.save_json(cache.path_for_work_id("W1"), {"id": "https://openalex.org/W1",
                                                   "doi": "https://doi.org/10.1038/NN.2384",
                                                   "display_name": "Selective suppression", "publication_year": 2009})
    assert refs.openalex_references(project, "10.1093/sleep/x", fetch=False) == [
        {"openalex": "W1", "doi": "10.1038/nn.2384", "title": "Selective suppression", "year": 2009}]
    assert refs.openalex_references(project, "10.1/uncached", fetch=False) is None


def test_outputs_and_missing_grobid(project, tmp_path):
    result = refs.triage(project, KEY)
    jp, mp = refs.write_outputs(project, result)
    assert jp == project.repo_root / "bib" / "derivatives" / "refs" / KEY / "triage.json"
    assert json.loads(jp.read_text())["counts"]["absent"] == 2
    md = mp.read_text()
    assert "## Full text (docling) (1)" in md and "pool:sirocampus:girardeau_2009_Selective" in md

    empty = refs.triage(project, "nobody_2000_Nothing")
    assert empty["references"] == [] and "no GROBID references.json" in empty["notes"][0]


def test_cli(project, capsys):
    from biblio.cli import main
    main(["refs", "triage", KEY, "--root", str(project.repo_root)])
    out = capsys.readouterr().out
    assert "5 references: 1 fulltext, 1 pdf, 1 metadata, 2 absent" in out


# --- journal-club follow-ups on R03 ----------------------------------------------

@pytest.mark.parametrize("raw,clean", [
    ("10.1152/physrev.00032.2012.-over", "10.1152/physrev.00032.2012"),
    ("https://doi.org/10.1038/NN.2384.", "10.1038/nn.2384"),
    ("doi:10.1523/jneurosci.4288-13.2014)", "10.1523/jneurosci.4288-13.2014"),
    ("see 10.7554/elife.84911 online", "10.7554/elife.84911"),
])
def test_normalize_doi_strips_grobid_junk(raw, clean):
    assert refs.normalize_doi(raw) == clean


def test_duplicates_openalex_titles_and_counts(project, monkeypatch):
    grobid = project.repo_root / "bib" / "derivatives" / "grobid" / KEY / "references.json"
    data = json.loads(grobid.read_text())
    data.append({"title": "", "authors": [], "year": "2009", "doi": "10.1038/nn.2384"})   # same DOI as #1
    grobid.write_text(json.dumps(data))
    oa_refs = [{"openalex": "W1", "doi": "10.1038/nn.2384",
                "title": "Selective suppression of hippocampal ripples impairs spatial memory", "year": 2009},
               {"openalex": "W9", "doi": "10.1/missed", "title": "A reference GROBID never saw", "year": 2015}]
    monkeypatch.setattr(refs, "openalex_references", lambda cfg, doi, fetch=True: oa_refs)
    result = refs.triage(project, KEY, use_openalex=True)
    rows = {r["n"]: r for r in result["references"]}
    assert rows[6]["duplicate_of"] == 1
    assert rows[1]["title_openalex"].endswith("impairs spatial memory") and rows[1]["title"].endswith("ripples")
    note = next(n for n in result["notes"] if n.startswith("OpenAlex"))
    assert "1 works GROBID missed" in note and "GROBID references not among them" in note
    assert any("same DOI as #1" in n for n in result["notes"])
    md = refs.to_markdown(result)
    assert "impairs spatial memory" in md and "*(OpenAlex only)*" in md and "*(same DOI as #1)*" in md


def test_pool_duplicate_keys_are_noted(project, tmp_path):
    bib = tmp_path / "sirocampus" / ".projio" / "biblio" / "merged.bib"
    bib.write_text(bib.read_text() + "\n@article{Girardeau_2009_SelectiveSuppression,\n  title = {Selective suppression of "
                   "hippocampal ripples impairs spatial memory},\n  year = {2009},\n  doi = {10.1038/nn.2384}\n}\n")
    notes = refs.triage(project, KEY)["notes"]
    assert any("pool:sirocampus holds one paper under 2 keys" in n for n in notes)
