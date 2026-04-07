#!/usr/bin/env python3
"""Fetch missing PDFs and ingest them into Bronze CAS storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pyalex import Works
from sutil.repo_root import repo_abs


HEADERS = {
    "User-Agent": "Bibliography-Intelligence-Bot/0.9 (Research Project)"
}


def sha256sum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_pdf_map(path: Path) -> dict[str, str]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_pdf_map(path: Path, mapping: dict[str, str]) -> None:
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    shutil.move(str(temp_path), str(path))


def ingest_to_cas(content: bytes, objects_dir: Path, extension: str = "pdf") -> str:
    file_hash = sha256sum(content)
    filename = "{0}.{1}".format(file_hash, extension)
    target_path = objects_dir / filename
    if not target_path.exists():
        target_path.write_bytes(content)
    return filename


def fetch_url(url: str) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
    except Exception as exc:
        print("fetch: request failed for {0}: {1}".format(url, exc))
        return None
    content_type = resp.headers.get("Content-Type", "")
    print(
        "fetch: {0} -> {1} ({2}) final={3}".format(
            url, resp.status_code, content_type, resp.url
        )
    )
    if resp.status_code != 200:
        return None
    return resp


def find_pdf_in_html(html: str, base_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
    if meta and meta.get("content"):
        print("fetch: citation_pdf_url found on {0}".format(base_url))
        return meta["content"]

    if "pmc.ncbi.nlm.nih.gov" in base_url:
        pdf_link = soup.find("a", href=re.compile(r"/pdf/.*\\.pdf$"))
        if pdf_link:
            print("fetch: PMC PDF link found on {0}".format(base_url))
            return urllib.parse.urljoin(base_url, pdf_link["href"])
    return None


def process_work(work_id: str, meta: dict[str, str], pdf_map: dict[str, str], objects_dir: Path) -> bool:
    candidates: list[str] = []
    doi = meta.get("doi") or meta.get("DOI")
    if doi:
        candidates.append("https://doi.org/{0}".format(doi))
    print("fetch: work_id={0} candidates={1}".format(work_id, len(candidates)))

    found_pdf: bytes | None = None

    for url in candidates:
        print("fetch: trying {0}".format(url))
        resp = fetch_url(url)
        if not resp:
            continue
        content_type = resp.headers.get("Content-Type", "").lower()
        if "application/pdf" in content_type:
            print("fetch: direct PDF from {0}".format(resp.url))
            found_pdf = resp.content
            break
        if "html" in content_type:
            pdf_url = find_pdf_in_html(resp.text, resp.url)
            if pdf_url:
                print("fetch: downloading PDF from {0}".format(pdf_url))
                pdf_resp = fetch_url(pdf_url)
                if pdf_resp and "application/pdf" in pdf_resp.headers.get("Content-Type", "").lower():
                    found_pdf = pdf_resp.content
                    break

    if not found_pdf:
        print("fetch: no PDF found for {0}".format(work_id))
        return False

    filename = ingest_to_cas(found_pdf, objects_dir, "pdf")
    pdf_map[work_id] = filename
    print("fetch: stored {0} -> {1}".format(work_id, filename))
    return True


def iter_missing_work_ids(manifest_path: Path) -> list[dict[str, str]]:
    missing = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") != "missing_pdf":
                continue
            if record.get("stage") and record.get("stage") != "bronze":
                continue
            missing.append(record)
    return missing


def load_candidates(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def enrich_from_openalex(record: dict) -> dict:
    openalex_id = record.get("openalex_id")
    if not openalex_id:
        return record
    try:
        work = Works()[openalex_id]
    except Exception as exc:
        print("fetch: openalex lookup failed for {0}: {1}".format(openalex_id, exc))
        return record
    meta = record.get("meta", {})
    doi = work.get("doi")
    if doi:
        meta["doi"] = doi.replace("https://doi.org/", "")
    title = work.get("title")
    if title and not meta.get("title"):
        meta["title"] = title
    record["meta"] = meta
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch missing PDFs into Bronze CAS.")
    parser.add_argument("--manifest", type=Path, default=repo_abs("manifest.jsonl"))
    parser.add_argument(
        "--candidates",
        type=Path,
        default=repo_abs("data/graph/expansion_candidates.json"),
    )
    parser.add_argument("--objects-dir", type=Path, default=repo_abs("data/01_bronze/objects"))
    parser.add_argument("--pdf-map", type=Path, default=repo_abs("data/01_bronze/pdf_map.json"))
    parser.add_argument("--sleep", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.manifest.exists():
        print("manifest.jsonl not found; run build_manifest first.")
        sys.exit(1)

    args.objects_dir.mkdir(parents=True, exist_ok=True)
    pdf_map = load_pdf_map(args.pdf_map)

    missing_records = iter_missing_work_ids(args.manifest)
    discovered_records = [
        enrich_from_openalex(rec)
        for rec in load_candidates(args.candidates)
        if rec.get("status") == "discovered"
    ]
    records = missing_records + discovered_records
    print(
        "fetch: missing={0} discovered={1}".format(
            len(missing_records), len(discovered_records)
        )
    )
    updates = 0

    for record in records:
        work_id = record.get("work_id")
        if not work_id:
            continue
        if work_id in pdf_map:
            print("fetch: already mapped {0}".format(work_id))
            continue
        meta = record.get("meta", {})
        if process_work(work_id, meta, pdf_map, args.objects_dir):
            updates += 1
            if updates % 5 == 0:
                save_pdf_map(args.pdf_map, pdf_map)
        time.sleep(args.sleep)

    save_pdf_map(args.pdf_map, pdf_map)
    print("fetched {0} new PDFs".format(updates))


if __name__ == "__main__":
    main()
