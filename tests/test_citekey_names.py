"""Family-name handling in canonical citekeys (H02)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from biblio.citekey import canonical_citekey_str, family_name
from biblio.ingest import canonical_citekey as ingest_citekey


def key(author: str, title: str = "Facet analysis", year: str = "2010") -> str:
    return canonical_citekey_str(SimpleNamespace(authors=[author], title=title, year=year, doi=None))


@pytest.mark.parametrize("author, expected", [
    ("Kathryn La Barre", "labarre"),          # capitalized particle belongs to the family name
    ("La Barre, Kathryn", "labarre"),
    ("Anita de Waard", "waard"),              # lowercase particle dropped (biblatex useprefix=false)
    ("de Waard, Anita", "waard"),
    ("Enny H. van Beest", "beest"),
    ("Ludwig van der Waals", "waals"),
    ("Frank M. Shipman III", "shipman"),      # generational suffix dropped
    ("Shipman III, Frank M.", "shipman"),
    ("Shipman, III, Frank M.", "shipman"),
    ("Martin Luther King Jr.", "king"),
    ("Birger Hjørland", "hjorland"),          # letters NFKD does not decompose
    ("Søren Kierkegaard", "kierkegaard"),
    ("Buckingham Shum, Simon", "buckinghamshum"),
    ("Mohamed Aleman-Zapata", "alemanzapata"),
    ("Mölle, Matthias", "molle"),
])
def test_author_token(author, expected):
    assert key(author).split("_")[0] == expected


def test_same_person_same_key_in_both_name_forms():
    assert key("Anita de Waard") == key("de Waard, Anita")
    assert key("Kathryn La Barre") == key("La Barre, Kathryn")


def test_family_name_keeps_single_token_names():
    assert family_name("Plato") == "Plato"
    assert family_name("III") == "III"


def test_ingest_uses_the_same_generator():
    rec = SimpleNamespace(authors=["Frank M. Shipman III"], title="Formality considered harmful", year="1999", doi=None)
    assert ingest_citekey(rec) == canonical_citekey_str(rec) == "shipman_1999_FormalityConsidered"
