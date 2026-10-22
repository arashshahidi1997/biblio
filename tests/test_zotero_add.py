"""One-paper ingest from Zotero (backlog I04). pyzotero is replaced by a fake with Zotero's JSON shapes."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from biblio import zotero_add
from biblio.config import default_config_path, load_biblio_config
from biblio.zotero_add import ZoteroLookupError, add_from_zotero, find_item, local_config

PDF = b"%PDF-1.7\n fake pdf body"

PAPER = {"key": "ABCD1234", "data": {
    "key": "ABCD1234", "itemType": "journalArticle",
    "title": "Deltas' and spindles' cross-area synchronization and ripple subtypes",
    "creators": [{"creatorType": "author", "firstName": "Adrian", "lastName": "Aleman-Zapata"},
                 {"creatorType": "author", "firstName": "Lisa", "lastName": "Genzel"}],
    "date": "2026-03-01", "DOI": "10.1093/sleep/zsag001", "publicationTitle": "SLEEP",
    "extra": "Citation Key: aleman-zapata_2026_DeltasSpindles",
}}
OTHER = {"key": "ZZZZ9999", "data": {
    "key": "ZZZZ9999", "itemType": "journalArticle", "title": "Something else by the same author",
    "creators": [{"creatorType": "author", "firstName": "Adrian", "lastName": "Aleman-Zapata"}],
    "date": "2022", "DOI": "10.1073/pnas.2123424119",
}}
CHILDREN = [
    {"key": "NOTE0001", "data": {"key": "NOTE0001", "itemType": "note"}},
    {"key": "LINK0001", "data": {"key": "LINK0001", "itemType": "attachment", "linkMode": "linked_file",
                                 "contentType": "application/pdf"}},
    {"key": "FILE0001", "data": {"key": "FILE0001", "itemType": "attachment", "linkMode": "imported_file",
                                 "contentType": "application/pdf", "parentItem": "ABCD1234"}},
]


class FakeZot:
    def __init__(self, items=(PAPER, OTHER), children=CHILDREN, files=None):
        self._items = {it["key"]: it for it in items}
        self._children = list(children)
        self.files = files if files is not None else {"FILE0001": PDF}
        self.queries: list[tuple] = []

    def item(self, key):
        if key in self._items:
            return self._items[key]
        for c in self._children:
            if c["key"] == key:
                return c
        raise KeyError(key)

    def items(self, q="", qmode="titleCreatorYear", limit=25):
        self.queries.append((q, qmode))
        # Zotero's quick search: every word must occur in title, creators or year
        words = q.lower().split()

        def text(it):
            d = it["data"]
            base = d["title"] + " " + " ".join(c["lastName"] for c in d["creators"]) + " " + d.get("date", "")
            return (str(d) if qmode == "everything" else base).lower()
        return [it for it in self._items.values() if all(w in text(it) for w in words)]

    def children(self, key):
        return self._children if key == "ABCD1234" else []

    def file(self, key):
        if key not in self.files:
            raise RuntimeError("404 file not found")
        return self.files[key]


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch):
    monkeypatch.setattr("biblio.profile.load_user_config", lambda: {})


@pytest.fixture
def cfg(tmp_path: Path):
    (tmp_path / "bib" / "srcbib").mkdir(parents=True)
    return load_biblio_config(default_config_path(root=tmp_path), root=tmp_path)


def _client(zot):
    return SimpleNamespace(_zot=zot)


ZCFG = local_config(None, Path("/nonexistent"))
KEY = "alemanzapata_2026_DeltasSpindles"


@pytest.mark.parametrize("ref", ["ABCD1234", "1:ABCD1234", "FILE0001", "10.1093/SLEEP/zsag001",
                                 "https://doi.org/10.1093/sleep/zsag001", "aleman-zapata_2026_DeltasSpindles",
                                 KEY, "@" + KEY])
def test_find_item_by_any_reference(ref):
    assert find_item(FakeZot(), ref)["key"] == "ABCD1234"


def test_find_item_errors():
    with pytest.raises(ZoteroLookupError, match="no Zotero item"):
        find_item(FakeZot(), "nobody_1999_Nothing")
    twin = {"key": "TWIN0001", "data": {**PAPER["data"], "key": "TWIN0001"}}
    with pytest.raises(ZoteroLookupError, match="matches 2 items"):
        find_item(FakeZot(items=(PAPER, twin)), "10.1093/sleep/zsag001")


def test_add_writes_entry_and_pdf(cfg):
    res = add_from_zotero(cfg, ZCFG, "aleman-zapata_2026_DeltasSpindles", client=_client(FakeZot()))

    assert res.citekey == KEY and not res.existing
    assert res.notes == [f"Zotero calls it aleman-zapata_2026_DeltasSpindles; biblio uses {KEY}"]
    bib = (cfg.repo_root / "bib" / "srcbib" / "zotero.bib").read_text()
    assert bib.startswith("@article{" + KEY + ",\n  zotero = {ABCD1234},")
    assert "doi = {10.1093/sleep/zsag001}" in bib
    assert res.pdf_status == "copied"  # the stored file, not the linked one listed first
    assert (cfg.repo_root / "bib" / "articles" / KEY / f"{KEY}.pdf").read_bytes() == PDF
    assert (cfg.repo_root / ".projio" / "biblio" / "logs" / "runs" / "zotero_sync.jsonl").is_file()


def test_add_keeps_existing_key_and_other_entries(cfg):
    zbib = cfg.repo_root / "bib" / "srcbib" / "zotero.bib"
    zbib.write_text("@article{keep_2000_Me,\n  title = {Keep {Me}}\n}\n")
    (cfg.repo_root / "bib" / "srcbib" / "main.bib").write_text(
        "@article{AlemanZapata2026,\n  title = {Deltas},\n  doi = {10.1093/sleep/zsag001}\n}\n")

    res = add_from_zotero(cfg, ZCFG, "ABCD1234", client=_client(FakeZot()))
    assert res.existing and res.citekey == "AlemanZapata2026"
    assert zbib.read_text() == "@article{keep_2000_Me,\n  title = {Keep {Me}}\n}\n"  # no duplicate entry
    assert res.pdf_path.name == "AlemanZapata2026.pdf" and res.pdf_status == "copied"

    again = add_from_zotero(cfg, ZCFG, "ABCD1234", client=_client(FakeZot()))
    assert again.pdf_status == "present"


def test_upsert_replaces_in_place(cfg):
    zbib = cfg.repo_root / "bib" / "srcbib" / "zotero.bib"
    zbib.write_text(f"@article{{keep_2000_Me,\n  title = {{x}}\n}}\n\n@article{{{KEY},\n  title = {{old}}\n}}\n")
    add_from_zotero(cfg, ZCFG, "ABCD1234", client=_client(FakeZot()))
    text = zbib.read_text()
    assert text.count(KEY + ",") == 1 and "old" not in text and text.startswith("@article{keep_2000_Me")


def test_refresh_keeps_key_pull_gave(cfg):
    zbib = cfg.repo_root / "bib" / "srcbib" / "zotero.bib"
    zbib.write_text("@article{Aleman-Zapata_2026_Deltas,\n  title = {old},\n  doi = {10.1093/sleep/zsag001}\n}\n")
    res = add_from_zotero(cfg, ZCFG, "ABCD1234", client=_client(FakeZot()))
    text = zbib.read_text()
    assert res.citekey == "Aleman-Zapata_2026_Deltas" and text.count("@article") == 1 and "old" not in text


@pytest.mark.parametrize("children,files,status", [
    ([], {}, "none"),
    (CHILDREN, {}, "failed"),
    (CHILDREN, {"FILE0001": b"<html>login</html>"}, "not-pdf"),
])
def test_pdf_problems_are_reported(cfg, children, files, status):
    res = add_from_zotero(cfg, ZCFG, "ABCD1234", client=_client(FakeZot(children=children, files=files)))
    assert res.pdf_status == status and len(res.notes) == 2
    assert (cfg.repo_root / "bib" / "srcbib" / "zotero.bib").is_file()  # the entry is still added


def test_dry_run_writes_nothing(cfg):
    res = add_from_zotero(cfg, ZCFG, "ABCD1234", dry_run=True, client=_client(FakeZot()))
    assert res.citekey == KEY and res.pdf_status == "dry-run"
    assert not (cfg.repo_root / "bib" / "srcbib" / "zotero.bib").exists()
    assert not (cfg.repo_root / "bib" / "articles").exists()


def test_local_config():
    assert (ZCFG.library_id, ZCFG.library_type, ZCFG.local, ZCFG.api_key) == ("0", "user", True, None)
    group = local_config(ZCFG.__class__(library_id="123", library_type="group", api_key="k", local=False,
                                        collection="C", tags_filter=None, citekey_mode="zotero",
                                        sync_state_path=Path("s")), Path("."))
    assert (group.library_id, group.local, group.api_key, group.collection) == ("123", True, None, None)


def test_client_uses_local_api(monkeypatch):
    calls = []
    monkeypatch.setattr("biblio.zotero.pyzotero_client",
                        SimpleNamespace(Zotero=lambda *a, **kw: calls.append((a, kw))))
    from biblio.zotero import ZoteroClient
    ZoteroClient(ZCFG)
    assert calls == [(("0", "user"), {"local": True})]


def test_cli(cfg, monkeypatch, capsys):
    from biblio.cli import main
    monkeypatch.setattr(zotero_add, "ZoteroClient", lambda zcfg: _client(FakeZot()))
    main(["add", "zotero", "ABCD1234", "--local", "--root", str(cfg.repo_root)])
    out = capsys.readouterr().out
    assert f"[OK] {KEY} (added) <- Zotero ABCD1234" in out and "next: biblio grobid run" in out

    with pytest.raises(SystemExit, match="No zotero section"):
        main(["add", "zotero", "ABCD1234", "--root", str(cfg.repo_root)])
