#!/usr/bin/env python
import sys
import json
from pathlib import Path
import urllib.parse

import requests
from bs4 import BeautifulSoup
from pybtex.database import parse_file

PROJECT = Path(__file__).resolve().parents[1]
BIB = PROJECT / "pixecog.bib"
bib_db = parse_file(str(BIB))


def get_entry(key: str):
    return bib_db.entries[key]


def get_field(entry, name: str):
    return entry.fields.get(name)


def fetch_html(url: str, headers, timeout: int = 15):
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as e:
        print(f"[fulltext-online] request failed for {url}: {e}")
        return None, None, None

    ctype = resp.headers.get("Content-Type", "").lower()
    print(f"[fulltext-online] GET {url} -> {resp.status_code}, type={ctype}, final={resp.url}")

    if resp.status_code != 200 or "html" not in ctype:
        return None, None, None

    return resp.url, resp.text, ctype


def candidate_urls_for_entry(entry):
    urls = []
    pmcid = get_field(entry, "pmcid")
    doi = get_field(entry, "doi")

    if pmcid:
        pmcid_clean = pmcid.replace("PMC", "").strip()
        urls.append(f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid_clean}/")

    if doi:
        urls.append(f"https://doi.org/{doi}")
        urls.append(f"https://pubmed.ncbi.nlm.nih.gov/?term={doi}")

    # dedupe
    seen = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    return urls


def find_pmc_links_in_pubmed(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    pmc_urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "pmc.ncbi.nlm.nih.gov" in href:
            pmc_urls.append(requests.compat.urljoin(base_url, href))
    return list(dict.fromkeys(pmc_urls))


def extract_main_text_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")

    # Prefer main article container if it exists (PMC-style)
    main = soup.find(id="main-content") or soup.find("article")
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    return text


def main():
    if len(sys.argv) != 3:
        print("Usage: download_fulltext.py <citekey> <outdir>")
        sys.exit(1)

    citekey = sys.argv[1]
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    entry = get_entry(citekey)
    doi = get_field(entry, "doi")
    pmcid = get_field(entry, "pmcid")

    print(f"[fulltext-online] citekey={citekey}, doi={doi}, pmcid={pmcid}")

    headers = {"User-Agent": "pixecog-fulltext-bot/0.1 (personal research)"}

    url_queue = candidate_urls_for_entry(entry)
    visited = set()
    tried = []

    full_html = None
    final_used_url = None

    idx = 0
    while idx < len(url_queue) and not full_html:
        url = url_queue[idx]
        idx += 1
        if url in visited:
            continue
        visited.add(url)

        final_url, html, ctype = fetch_html(url, headers)
        tried.append({"url": url, "final_url": final_url, "ctype": ctype or "unknown"})

        if not html:
            continue

        parsed = urllib.parse.urlparse(final_url or url)
        host = parsed.netloc.lower()

        # If this is a PubMed search page, look for PMC links
        if "pubmed.ncbi.nlm.nih.gov" in host and "/?term=" in (final_url or url):
            soup = BeautifulSoup(html, "html.parser")
            first = soup.select_one("a.docsum-title")
            if first and first.get("href"):
                art_url = requests.compat.urljoin(final_url, first["href"])
                if art_url not in visited and art_url not in url_queue:
                    url_queue.append(art_url)
            continue

        # If this is a PubMed article page, follow PMC full-text links
        if "pubmed.ncbi.nlm.nih.gov" in host:
            pmc_urls = find_pmc_links_in_pubmed(final_url, html)
            for pu in pmc_urls:
                if pu not in visited and pu not in url_queue:
                    url_queue.append(pu)
            continue

        # If this is PMC or publisher HTML, we can try to use it as full text
        if "pmc.ncbi.nlm.nih.gov" in host or "learnmem.cshlp.org" in host:
            full_html = html
            final_used_url = final_url
            break

    if not full_html:
        print(f"[fulltext-online] no usable HTML full text for {citekey}")
        return

    # Save HTML and plain text
    html_path = outdir / "full.html"
    txt_path = outdir / "full.txt"
    html_path.write_text(full_html, encoding="utf-8")
    txt_path.write_text(extract_main_text_from_html(full_html), encoding="utf-8")

    meta = {
        "source": "online",
        "doi": doi,
        "pmcid": pmcid,
        "used_url": final_used_url,
        "tried_urls": url_queue,
        "trace": tried,
    }
    (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[fulltext-online] saved HTML + text for {citekey} at {html_path} / {txt_path}")


if __name__ == "__main__":
    main()
