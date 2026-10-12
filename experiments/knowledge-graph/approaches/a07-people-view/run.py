"""a07 people view: build Person / Institution nodes and a co-author graph.

    python approaches/a07-people-view/run.py --set extended
    python approaches/a07-people-view/run.py --set extended --offline   # cache only

Writes runs/a07-people-view/<run-id>/ with run.yml, nodes.jsonl, edges.jsonl,
stats.yml, people.json, people.html and cq/CQ11.md, cq/CQ12.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "common"))

from corpus import EXP_ROOT, papers as corpus_papers  # noqa: E402
import people as ppl  # noqa: E402

APPROACH = "a07-people-view"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", default="extended")
    ap.add_argument("--root", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--offline", action="store_true", help="use cached API responses only")
    args = ap.parse_args(argv)

    started = datetime.now()
    run_id = started.strftime("%Y%m%d-%H%M") + (f"-{args.tag}" if args.tag else "")
    out = EXP_ROOT / "runs" / APPROACH / run_id
    out.mkdir(parents=True, exist_ok=True)
    cache = ppl.Cache(EXP_ROOT / "runs" / APPROACH / "_cache")

    corpus = corpus_papers(args.set, args.root)
    records = {p.citekey: p.openalex() for p in corpus if p.openalex()}
    people = ppl.aggregate(records)

    enrich = {}
    t0 = time.time()
    if args.offline:
        ppl._http_json = _offline  # type: ignore[assignment]
    enrich["openalex_profiles"] = ppl.enrich_openalex(people, cache)
    enrich["wikidata_matches"] = ppl.enrich_wikidata(people, cache)
    enrich["photos"] = ppl.enrich_commons(people, cache)
    api_s = round(time.time() - t0, 1)
    # people.html sits in runs/<approach>/<run-id>/, three levels below EXP_ROOT
    enrich["local_photos"] = ppl.apply_local_photos(people, EXP_ROOT / "people", "../../../people")

    nodes, edges = to_interchange(people, run_id)
    write_jsonl(out / "nodes.jsonl", nodes)
    write_jsonl(out / "edges.jsonl", edges)

    stats = compute_stats(people, enrich, len(corpus))
    (out / "stats.yml").write_text(yaml.safe_dump(stats, sort_keys=False, allow_unicode=True))
    data = export_people(people)
    (out / "people.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))

    cq = out / "cq"
    cq.mkdir(exist_ok=True)
    (cq / "CQ11.md").write_text(answer_cq11(people))
    (cq / "CQ12.md").write_text(answer_cq12(people))

    import render  # noqa: E402
    (out / "people.html").write_text(render.page(data, stats, run_id), encoding="utf-8")

    run = {
        "approach": APPROACH, "run_id": run_id, "corpus_set": args.set, "model": None,
        "started": started.isoformat(timespec="seconds"),
        "wall_time_s": round((datetime.now() - started).total_seconds(), 1),
        "api_time_s": api_s, "cost_usd": 0.0, "tokens": None,
        "notes": "OpenAlex + Wikidata + Commons; no LLM",
    }
    (out / "run.yml").write_text(yaml.safe_dump(run, sort_keys=False))

    print(yaml.safe_dump(stats, sort_keys=False, allow_unicode=True))
    print(f"-> {out}")
    return 0


def _offline(url, data=None, retries=3):
    raise RuntimeError(f"--offline: not in cache: {url[:80]}")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def to_interchange(people: ppl.People, run_id: str) -> tuple[list[dict], list[dict]]:
    prov = {"method": APPROACH, "model": None, "run_id": run_id, "status": "candidate"}
    nodes, edges = [], []
    for ck, paper in people.papers.items():
        nodes.append({"id": f"paper:{ck}", "type": "Paper", "label": paper["title"],
                      "attrs": {"year": paper["year"], "doi": paper["doi"], "on_topic": paper["on_topic"]},
                      "provenance": prov})
    for iid, inst in people.institutions.items():
        nodes.append({"id": f"inst:{iid}", "type": "Institution", "label": inst["name"],
                      "attrs": {k: inst[k] for k in ("ror", "country", "type")}, "provenance": prov})
    for p in people.persons.values():
        prof = p.profile or {}
        nodes.append({
            "id": p.id, "type": "Person", "label": p.name,
            "attrs": {
                "openalex": p.openalex, "orcid": p.orcid,
                "wikidata": (p.wikidata or {}).get("item"),
                "works_count": prof.get("works_count"),
                "h_index": (prof.get("summary_stats") or {}).get("h_index"),
                "topics": [t["display_name"] for t in (prof.get("topics") or [])[:5]],
                "photo": p.photo,
            },
            "provenance": prov,
        })
        for row in p.papers:
            edges.append({"src": f"paper:{row['citekey']}", "dst": p.id, "type": "authored_by",
                          "attrs": {"position": row["position"], "corresponding": row["corresponding"]},
                          "provenance": prov})
        for iid, years in p.institutions.items():
            edges.append({"src": p.id, "dst": f"inst:{iid}", "type": "affiliated_with",
                          "attrs": {"years": sorted(years)}, "provenance": prov})
    for (a, b), cks in people.coauthors.items():
        edges.append({"src": a, "dst": b, "type": "coauthor",
                      "attrs": {"weight": len(cks), "papers": cks}, "provenance": prov})
    return nodes, edges


def compute_stats(people: ppl.People, enrich: dict, n_corpus: int) -> dict:
    persons = list(people.persons.values())
    n = len(persons)
    licenses = Counter((p.photo or {}).get("license") for p in persons if p.photo)
    by_name = defaultdict(set)
    for p in persons:
        by_name[ppl.slug(p.name)].add(p.id)
    split = {name: sorted(ids) for name, ids in by_name.items() if len(ids) > 1}
    top20 = sorted(persons, key=lambda p: -p.score(True))[:20]

    def pct(k):
        return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "0"

    return {
        "papers_in_set": n_corpus,
        "papers_with_openalex": len(people.papers),
        "papers_on_topic": sum(p["on_topic"] for p in people.papers.values()),
        "authorships": sum(len(p.papers) for p in persons),
        "persons": n,
        "persons_without_openalex_id": sum(1 for p in persons if not p.openalex),
        "with_orcid": pct(sum(1 for p in persons if p.orcid)),
        "with_institution_in_corpus": pct(sum(1 for p in persons if p.institutions)),
        "with_openalex_profile": pct(enrich["openalex_profiles"]),
        "with_wikidata_item": pct(sum(1 for p in persons if p.wikidata)),
        "wikidata_matched_by": enrich["wikidata_matches"],
        "with_photo": pct(enrich["photos"]),
        "with_local_photo": enrich["local_photos"],
        "top20_contributors_with_open_photo": sum(
            1 for p in top20 if p.photo and p.photo.get("origin") == "commons"),
        "top20_contributors_in_wikidata": sum(1 for p in top20 if p.wikidata),
        "photo_licenses": dict(licenses),
        "with_doctoral_advisor": pct(sum(1 for p in persons if (p.wikidata or {}).get("advisors"))),
        "institutions": len(people.institutions),
        "institutions_with_ror": sum(1 for i in people.institutions.values() if i["ror"]),
        "countries": len({i["country"] for i in people.institutions.values() if i["country"]}),
        "coauthor_pairs": len(people.coauthors),
        "repeat_coauthor_pairs": sum(1 for v in people.coauthors.values() if len(v) > 1),
        "same_name_multiple_ids": split,
    }


def export_people(people: ppl.People) -> dict:
    neighbors = defaultdict(list)
    for (a, b), cks in people.coauthors.items():
        neighbors[a].append({"id": b, "papers": cks})
        neighbors[b].append({"id": a, "papers": cks})
    persons = []
    for p in people.persons.values():
        prof = p.profile or {}
        last = [
            {"name": i.get("display_name"), "country": i.get("country_code")}
            for i in prof.get("last_known_institutions") or []
        ]
        affiliations = [
            {"name": a["institution"].get("display_name"), "country": a["institution"].get("country_code"),
             "years": [min(a["years"]), max(a["years"])] if a.get("years") else None}
            for a in prof.get("affiliations") or []
        ]
        persons.append({
            "id": p.id, "name": p.name, "openalex": p.openalex, "orcid": p.orcid,
            "score_topic": round(p.score(True), 2), "score_all": round(p.score(False), 2),
            "papers": p.papers,
            "institutions": {iid: sorted(y) for iid, y in p.institutions.items()},
            "last_known": last, "affiliations": affiliations,
            "works_count": prof.get("works_count"), "cited_by_count": prof.get("cited_by_count"),
            "h_index": (prof.get("summary_stats") or {}).get("h_index"),
            "topics": [t["display_name"] for t in (prof.get("topics") or [])[:5]],
            "wikidata": p.wikidata or None, "photo": p.photo,
            "coauthors": sorted(neighbors[p.id], key=lambda x: -len(x["papers"])),
        })
    persons.sort(key=lambda x: (-x["score_topic"], -x["score_all"], x["name"]))
    return {"papers": people.papers, "institutions": people.institutions, "persons": persons}


def _paper_ref(people: ppl.People, row: dict) -> str:
    tags = [row["position"]] + (["corr."] if row["corresponding"] else [])
    return f"{row['citekey']} ({', '.join(tags)})"


def answer_cq11(people: ppl.People, top: int = 15) -> str:
    ranked = sorted(people.persons.values(), key=lambda p: -p.score(True))
    lines = [
        "# CQ11: main contributors to spindle-ripple coupling research",
        "",
        f"Topic papers: {sum(p['on_topic'] for p in people.papers.values())} of {len(people.papers)} "
        "(matched on title, OpenAlex keywords and topics).",
        "Score per topic paper: first or last author 1.0, middle 0.25, corresponding +0.5.",
        "",
        "Contributions are listed as papers only. Claims and methods per person need a01.",
        "",
        "| # | Person | Score | Topic papers | Co-authors in corpus |",
        "|---|--------|-------|--------------|----------------------|",
    ]
    for i, p in enumerate(ranked[:top], 1):
        co = Counter()
        for (a, b), cks in people.coauthors.items():
            if p.id in (a, b):
                other = b if a == p.id else a
                co[people.persons[other].name] += len(cks)
        co_txt = ", ".join(f"{name} ({k})" for name, k in co.most_common(4))
        papers = "; ".join(_paper_ref(people, r) for r in p.topic_papers)
        lines.append(f"| {i} | {p.name} | {p.score(True):.2f} | {papers} | {co_txt} |")
    return "\n".join(lines) + "\n"


def answer_cq12(people: ppl.People) -> str:
    by_inst = defaultdict(lambda: {"papers": set(), "years": set()})
    by_country_decade = defaultdict(Counter)
    for p in people.persons.values():
        for row in p.papers:
            for iid in row["institutions"]:
                by_inst[iid]["papers"].add(row["citekey"])
                if row["year"]:
                    by_inst[iid]["years"].add(row["year"])
    for ck, paper in people.papers.items():
        countries = set()
        for p in people.persons.values():
            for row in p.papers:
                if row["citekey"] == ck:
                    countries |= {people.institutions[i]["country"] for i in row["institutions"]}
        decade = f"{(paper['year'] // 10) * 10}s" if paper["year"] else "?"
        for c in countries - {None}:
            by_country_decade[decade][c] += 1

    lines = ["# CQ12: research groups and institutions over time", "",
             "Institutions by number of corpus papers (an institution counts once per paper).", "",
             "| Institution | Country | Papers | Years |", "|---|---|---|---|"]
    ranked = sorted(by_inst.items(), key=lambda kv: -len(kv[1]["papers"]))
    for iid, row in ranked[:20]:
        inst = people.institutions[iid]
        years = sorted(row["years"])
        span = f"{years[0]}-{years[-1]}" if years else ""
        lines.append(f"| {inst['name']} | {inst['country']} | {len(row['papers'])} | {span} |")
    lines += ["", "Countries per decade (papers with at least one author from that country):", ""]
    for decade in sorted(by_country_decade):
        txt = ", ".join(f"{c} {k}" for c, k in by_country_decade[decade].most_common())
        lines.append(f"- **{decade}**: {txt}")
    lines += ["", "## Groups", "",
              "Research groups (labs) are not in OpenAlex. Two proxies:", "",
              "**Academic lineage** (Wikidata P184, doctoral advisor):", ""]
    students = defaultdict(list)
    for p in people.persons.values():
        for adv in (p.wikidata or {}).get("advisors", []):
            students[adv["label"]].append(p.name)
    for adv, names in sorted(students.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- {adv} → {', '.join(sorted(names))}")
    lines += ["", "**Last-author groups** (people who appear on papers whose last author is X):", ""]
    groups = defaultdict(set)
    for ck in people.papers:
        rows = [(p, r) for p in people.persons.values() for r in p.papers if r["citekey"] == ck]
        lasts = [p for p, r in rows if r["position"] == "last"]
        if lasts and len(rows) <= 15:                 # skip consortium papers
            groups[lasts[0].name] |= {p.name for p, r in rows if p is not lasts[0]}
    for pi, members in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:10]:
        lines.append(f"- {pi}: {len(members)} people ({', '.join(sorted(members)[:6])}{', ...' if len(members) > 6 else ''})")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
