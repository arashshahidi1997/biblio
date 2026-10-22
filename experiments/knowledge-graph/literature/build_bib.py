"""Build foundations.bib from dois.txt (CSL-JSON via doi.org) plus manual.bib.

    python experiments/knowledge-graph/literature/build_bib.py

Metadata comes from Crossref / DataCite content negotiation, not from
OpenAlex: OpenAlex mis-resolves several arXiv DOIs and drops book authors.
Citekeys use biblio's own ``canonical_citekey`` on structured family names,
so multi-word family names (La Barre), lowercase particles (de Waard -> waard)
and suffixes (Shipman III) follow one rule.
Responses are cached in .cache/ (gitignored).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))
from biblio.citekey import canonical_citekey  # noqa: E402

CACHE = HERE / ".cache"
USER_AGENT = "biblio-kg-experiments/0.1 (https://github.com/arashshahidi1997/biblio)"

CSL_TO_BIBTEX = {
    "article-journal": "article", "article": "article", "article-magazine": "article",
    "book": "book", "monograph": "book", "edited-book": "book",
    "chapter": "incollection", "entry": "incollection",
    "paper-conference": "inproceedings", "proceedings-article": "inproceedings",
    "report": "techreport", "posted-content": "misc",
    # Crossref content negotiation returns Crossref type names
    "journal-article": "article", "book-chapter": "incollection", "book-section": "incollection",
    "reference-entry": "incollection", "book-part": "incollection",
}

# Container metadata that Crossref does not hold as such
TITLE_FIXES = {
    # Crossref lists the 3rd edition as a collection title only
    "10.1145/3382097": {"edition": "3"},
}


def fetch_csl(doi: str) -> dict:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / (re.sub(r"[^A-Za-z0-9._-]+", "_", doi) + ".json")
    if path.is_file():
        return json.loads(path.read_text())
    req = urllib.request.Request(
        "https://doi.org/" + urllib.parse.quote(doi, safe="/"),
        headers={"Accept": "application/vnd.citationstyles.csl+json", "User-Agent": USER_AGENT},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            break
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(f"{doi}: {exc}") from exc
            time.sleep(2 ** attempt)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return data


def family(person: dict) -> str:
    parts = [person.get("non-dropping-particle"), person.get("family") or person.get("literal")]
    return " ".join(p for p in parts if p)


def bib_name(person: dict) -> str:
    fam = family(person)
    given = person.get("given")
    suffix = person.get("suffix")
    if suffix:
        return f"{fam}, {suffix}, {given}" if given else fam
    return f"{fam}, {given}" if given else fam


def year_of(csl: dict) -> str | None:
    for field in ("issued", "published-print", "published-online", "created"):
        parts = (csl.get(field) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return str(parts[0][0])
    return None


def esc(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)           # JATS tags in titles
    return value.replace("&", r"\&").replace("%", r"\%").replace("#", r"\#").strip()


def first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def to_bibtex(doi: str, csl: dict, theme: str) -> tuple[str, str]:
    authors = [p for p in csl.get("author") or [] if family(p)]
    editors = [p for p in csl.get("editor") or [] if family(p)]
    people = authors or editors
    title = first(csl.get("title")) or ""
    year = year_of(csl)
    # "Family," keeps multi-word family names whole in canonical_citekey
    record = SimpleNamespace(
        authors=[family(p) + "," for p in people], year=year, title=title, doi=doi)
    key = canonical_citekey(record, strict=False).key
    etype = CSL_TO_BIBTEX.get(csl.get("type"), "misc")
    fields = {
        "title": title,
        "author": " and ".join(bib_name(p) for p in authors) or None,
        "editor": " and ".join(bib_name(p) for p in editors) if editors and (not authors or etype == "incollection") else None,
        "year": year,
        "doi": doi,
        "publisher": csl.get("publisher") if etype in ("book", "incollection", "techreport") else None,
        "volume": csl.get("volume") if etype == "article" else None,
        "number": csl.get("issue") if etype == "article" else None,
        "pages": csl.get("page"),
        "keywords": f"kg-foundations, {theme}",
        **TITLE_FIXES.get(doi, {}),
    }
    if doi.lower().startswith("10.48550/arxiv."):
        etype = "misc"
        fields.update({"eprint": doi.split("arXiv.", 1)[-1], "archiveprefix": "arXiv",
                       "howpublished": "arXiv preprint"})
    container = first(csl.get("container-title"))
    if container and etype != "misc":
        fields[{"article": "journal", "incollection": "booktitle", "inproceedings": "booktitle"}.get(etype, "howpublished")] = container
    if csl.get("URL") and etype == "misc":
        fields["url"] = csl["URL"]
    body = ",\n".join(f"  {k} = {{{esc(str(v))}}}" for k, v in fields.items() if v)
    return key, f"@{etype}{{{key},\n{body}\n}}\n"


def main() -> int:
    entries, seen = [], {}
    theme = "uncategorized"
    for line in (HERE / "dois.txt").read_text().splitlines():
        line = line.strip()
        if line.startswith("# ") and len(line) > 3 and line[2].isupper() and line[3] == ".":
            theme = "theme-" + line[2].lower()
            continue
        if not line or line.startswith("#"):
            continue
        key, bib = to_bibtex(line, fetch_csl(line), theme)
        if key in seen:
            raise SystemExit(f"duplicate citekey {key}: {seen[key]} and {line}")
        seen[key] = line
        entries.append(bib)
    manual = (HERE / "manual.bib").read_text()
    manual_keys = re.findall(r"^@\w+\{([^,]+),", manual, re.M)
    clash = set(manual_keys) & set(seen)
    if clash:
        raise SystemExit(f"manual.bib keys clash with DOI keys: {sorted(clash)}")
    header = ("% Foundations for biblio's knowledge-graph and wiki design.\n"
              "% GENERATED by build_bib.py from dois.txt (Crossref/DataCite) + manual.bib. Do not edit.\n\n")
    (HERE / "foundations.bib").write_text(header + "\n".join(entries) + "\n" + manual)
    print(f"{len(entries)} DOI entries + {len(manual_keys)} manual entries -> foundations.bib")
    for key in sorted(seen):
        print(f"  {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
