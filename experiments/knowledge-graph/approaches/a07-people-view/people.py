"""Build the people layer: aggregate authorships, then enrich from open sources.

Steps:
  1. aggregate()          authorships in OpenAlex resolved.jsonl -> people, institutions, co-authors
  2. enrich_openalex()    OpenAlex author profiles (works, h-index, topics, affiliations over time)
  3. enrich_wikidata()    Wikidata items by ORCID (P496) or OpenAlex ID (P10283): image (P18), advisor (P184)
  4. enrich_commons()     Wikimedia Commons license and author for each image

All API responses are cached under runs/a07-people-view/_cache/.
Images are never downloaded; pages hotlink Commons thumbnails with attribution.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html import unescape
from itertools import combinations
from pathlib import Path

USER_AGENT = "biblio-kg-experiments/0.1 (https://github.com/arashshahidi1997/biblio)"

# Papers about the hippocampal-cortical coupling topic of CQ11
TOPIC_RE = re.compile(
    r"ripple|sharp[- ]?wave|spindle|up[- ]?state|down[- ]?state|slow[- ]oscillation|"
    r"hippocampo[- ]?cortical|neocortical|memory consolidation|nrem",
    re.IGNORECASE,
)

# Contribution weight per author position (CQ11 ranking)
POSITION_WEIGHT = {"first": 1.0, "last": 1.0, "middle": 0.25}
CORRESPONDING_BONUS = 0.5


def short_id(url: str | None) -> str | None:
    return url.rsplit("/", 1)[-1] if url else None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Person:
    id: str
    name: str
    openalex: str | None = None
    orcid: str | None = None
    papers: list[dict] = field(default_factory=list)
    institutions: dict[str, set] = field(default_factory=lambda: defaultdict(set))  # inst id -> years
    profile: dict = field(default_factory=dict)      # OpenAlex author profile
    wikidata: dict = field(default_factory=dict)     # item, label, description, image, advisors
    photo: dict | None = None                        # thumb, page, license, artist

    @property
    def topic_papers(self) -> list[dict]:
        return [p for p in self.papers if p["on_topic"]]

    def score(self, on_topic: bool = True) -> float:
        rows = self.topic_papers if on_topic else self.papers
        return sum(
            POSITION_WEIGHT.get(p["position"], 0.25) + (CORRESPONDING_BONUS if p["corresponding"] else 0)
            for p in rows
        )


@dataclass
class People:
    papers: dict[str, dict]
    persons: dict[str, Person]
    institutions: dict[str, dict]
    coauthors: dict[tuple[str, str], list[str]]      # (pid, pid) -> citekeys


def aggregate(records: dict[str, dict]) -> People:
    """records: citekey -> OpenAlex resolved.jsonl record."""
    papers: dict[str, dict] = {}
    persons: dict[str, Person] = {}
    institutions: dict[str, dict] = {}
    coauthors: dict[tuple[str, str], list[str]] = defaultdict(list)

    for ck, rec in records.items():
        title = rec.get("display_name") or rec.get("title_bib") or ck
        year = rec.get("publication_year")
        topic_text = " ".join(
            [title]
            + [k.get("display_name", "") for k in rec.get("keywords") or []]
            + [t.get("display_name", "") for t in rec.get("topics") or []]
        )
        on_topic = bool(TOPIC_RE.search(topic_text))
        papers[ck] = {
            "citekey": ck, "title": title, "year": year, "doi": rec.get("doi"),
            "on_topic": on_topic, "n_authors": len(rec.get("authorships") or []),
            "primary_topic": (rec.get("primary_topic") or {}).get("display_name"),
        }
        pids = []
        for a in rec.get("authorships") or []:
            author = a.get("author") or {}
            oa = short_id(author.get("id"))
            name = author.get("display_name") or a.get("raw_author_name") or "?"
            pid = f"person:{oa}" if oa else f"person:name:{slug(name)}"
            person = persons.setdefault(pid, Person(id=pid, name=name, openalex=oa))
            if author.get("orcid") and not person.orcid:
                person.orcid = short_id(author["orcid"])
            inst_ids = []
            for inst in a.get("institutions") or []:
                iid = short_id(inst.get("id"))
                if not iid:
                    continue
                inst_ids.append(iid)
                institutions.setdefault(iid, {
                    "id": iid, "name": inst.get("display_name"), "ror": short_id(inst.get("ror")),
                    "country": inst.get("country_code"), "type": inst.get("type"),
                })
                if year:
                    person.institutions[iid].add(year)
            person.papers.append({
                "citekey": ck, "year": year, "position": a.get("author_position") or "middle",
                "corresponding": bool(a.get("is_corresponding")), "institutions": inst_ids,
                "on_topic": on_topic,
            })
            pids.append(pid)
        for p, q in combinations(sorted(set(pids)), 2):
            coauthors[(p, q)].append(ck)

    return People(papers, persons, institutions, dict(coauthors))


# --- HTTP with cache ---------------------------------------------------------

class Cache:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def get(self, name: str):
        path = self.root / f"{name}.json"
        return json.loads(path.read_text()) if path.is_file() else None

    def put(self, name: str, data) -> None:
        (self.root / f"{name}.json").write_text(json.dumps(data, indent=1, sort_keys=True))


def _http_json(url: str, data: dict | None = None, retries: int = 3) -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": USER_AGENT, "Accept": "application/sparql-results+json, application/json",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# --- OpenAlex ----------------------------------------------------------------

def enrich_openalex(people: People, cache: Cache) -> int:
    profiles: dict = cache.get("openalex_authors") or {}
    missing = sorted({p.openalex for p in people.persons.values() if p.openalex} - set(profiles))
    select = "id,display_name,orcid,works_count,cited_by_count,summary_stats,topics,last_known_institutions,affiliations,counts_by_year"
    mailto = os.environ.get("OPENALEX_MAILTO")
    for batch in _batches(missing, 50):
        params = {"filter": "openalex:" + "|".join(batch), "select": select, "per_page": 100}
        if mailto:
            params["mailto"] = mailto
        data = _http_json("https://api.openalex.org/authors?" + urllib.parse.urlencode(params))
        for a in data.get("results", []):
            profiles[short_id(a["id"])] = a
        for oa in batch:                       # remember misses too
            profiles.setdefault(oa, None)
        cache.put("openalex_authors", profiles)
    found = 0
    for p in people.persons.values():
        prof = profiles.get(p.openalex) if p.openalex else None
        if prof:
            p.profile = prof
            if not p.orcid and prof.get("orcid"):
                p.orcid = short_id(prof["orcid"])
            found += 1
    return found


# --- Wikidata ----------------------------------------------------------------

_SPARQL = """
SELECT ?item ?key ?itemLabel ?itemDescription ?image ?advisor ?advisorLabel WHERE {{
  VALUES ?key {{ {values} }}
  ?item wdt:{prop} ?key .
  OPTIONAL {{ ?item wdt:P18 ?image }}
  OPTIONAL {{ ?item wdt:P184 ?advisor }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def _wikidata_lookup(keys: list[str], prop: str, cache: Cache, cache_name: str) -> dict[str, dict]:
    hits: dict = cache.get(cache_name) or {}
    todo = [k for k in keys if k not in hits]
    for batch in _batches(todo, 80):
        query = _SPARQL.format(values=" ".join(f'"{k}"' for k in batch), prop=prop)
        data = _http_json("https://query.wikidata.org/sparql", {"query": query, "format": "json"})
        found: dict[str, dict] = {}
        for b in data["results"]["bindings"]:
            key = b["key"]["value"]
            row = found.setdefault(key, {
                "item": short_id(b["item"]["value"]),
                "label": b.get("itemLabel", {}).get("value"),
                "description": b.get("itemDescription", {}).get("value"),
                "image": None, "advisors": [],
            })
            if "image" in b and not row["image"]:
                row["image"] = b["image"]["value"]
            if "advisor" in b:
                adv = {"item": short_id(b["advisor"]["value"]), "label": b.get("advisorLabel", {}).get("value")}
                if adv not in row["advisors"]:
                    row["advisors"].append(adv)
        for k in batch:
            hits[k] = found.get(k)
        cache.put(cache_name, hits)
        time.sleep(1)
    return hits


def enrich_wikidata(people: People, cache: Cache) -> dict[str, int]:
    by_orcid = _wikidata_lookup(
        sorted({p.orcid for p in people.persons.values() if p.orcid}), "P496", cache, "wikidata_by_orcid")
    by_oa = _wikidata_lookup(
        sorted({p.openalex for p in people.persons.values() if p.openalex}), "P10283", cache, "wikidata_by_openalex")
    counts = Counter()
    for p in people.persons.values():
        hit = (by_orcid.get(p.orcid) if p.orcid else None)
        how = "orcid"
        if not hit and p.openalex:
            hit, how = by_oa.get(p.openalex), "openalex"
        if hit:
            p.wikidata = {**hit, "matched_by": how}
            counts[how] += 1
    return dict(counts)


# --- Commons -----------------------------------------------------------------

def _strip_html(text: str | None) -> str | None:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", text))).strip() if text else None


def enrich_commons(people: People, cache: Cache, width: int = 240) -> int:
    meta: dict = cache.get("commons_imageinfo") or {}
    files = {}
    for p in people.persons.values():
        url = p.wikidata.get("image") if p.wikidata else None
        if url:
            files[p.id] = "File:" + urllib.parse.unquote(url.rsplit("/", 1)[-1])
    todo = sorted(set(files.values()) - set(meta))
    for batch in _batches(todo, 40):
        params = {
            "action": "query", "format": "json", "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": width, "titles": "|".join(batch),
        }
        data = _http_json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
        pages = data.get("query", {}).get("pages", {})
        normalized = {n["to"]: n["from"] for n in data.get("query", {}).get("normalized", [])}
        for page in pages.values():
            title = normalized.get(page.get("title"), page.get("title"))
            info = (page.get("imageinfo") or [{}])[0]
            ext = info.get("extmetadata") or {}
            meta[title] = {
                "thumb": info.get("thumburl"), "page": info.get("descriptionurl"),
                "license": (ext.get("LicenseShortName") or {}).get("value"),
                "license_url": (ext.get("LicenseUrl") or {}).get("value"),
                "artist": _strip_html((ext.get("Artist") or {}).get("value")),
            }
        cache.put("commons_imageinfo", meta)
    n = 0
    for pid, title in files.items():
        info = meta.get(title)
        if info and info.get("thumb"):
            people.persons[pid].photo = {**info, "file": title, "origin": "commons"}
            n += 1
    return n


PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def apply_local_photos(people: People, folder: Path, href_prefix: str) -> int:
    """Use <folder>/<orcid or openalex id>.<ext> when no open photo was found.

    The folder is gitignored; local photos are for private viewing only.
    """
    if not folder.is_dir():
        return 0
    files = {f.stem: f.name for f in folder.iterdir() if f.suffix.lower() in PHOTO_EXTS}
    n = 0
    for p in people.persons.values():
        if p.photo:
            continue
        name = files.get(p.orcid or "") or files.get(p.openalex or "")
        if name:
            p.photo = {"thumb": f"{href_prefix}/{name}", "page": None, "license": "local, private",
                       "artist": None, "file": name, "origin": "local"}
            n += 1
    return n
