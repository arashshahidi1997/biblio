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
    """
    Fetch a URL, return (final_url, text, content_type) or (None, None, None) on failure.
    Skips non-HTML content (e.g. direct PDFs).
    """
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as e:
        print(f"[online] request failed for {url}: {e}")
        return None, None, None

    ctype = resp.headers.get("Content-Type", "").lower()
    print(f"[online] GET {url} -> {resp.status_code}, content-type={ctype}, final={resp.url}")

    if resp.status_code != 200:
        return None, None, None

    if "html" not in ctype:
        print(f"[online] non-HTML content at {resp.url}, skipping")
        return None, None, None

    return resp.url, resp.text, ctype


def extract_img_urls_from_html(base_url: str, html: str):
    """
    Generic figure scraping: collect image URLs from common figure containers.
    Works well on PMC and many journal sites.
    """
    soup = BeautifulSoup(html, "html.parser")
    img_urls = []

    # 1) <figure> tags
    for fig in soup.find_all("figure"):
        for img in fig.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if src:
                img_urls.append(requests.compat.urljoin(base_url, src))

    # 2) Common figure/fig container selectors
    for selector in ['div.figures', 'div.figure', 'div.fig', 'li.fig', 'li.figure']:
        for container in soup.select(selector):
            for img in container.find_all("img"):
                src = img.get("data-src") or img.get("src")
                if src:
                    img_urls.append(requests.compat.urljoin(base_url, src))

    # 3) Fallback: any <img> with "fig"/"figure" mentioned in alt/title
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").lower()
        title = (img.get("title") or "").lower()
        if any(tok in alt or tok in title for tok in ("fig", "figure")):
            src = img.get("data-src") or img.get("src")
            if src:
                img_urls.append(requests.compat.urljoin(base_url, src))

    # dedupe while preserving order
    seen = set()
    uniq = []
    for u in img_urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    return uniq


def find_pmc_links_in_html(base_url: str, html: str):
    """
    From a PubMed article page, find links to PMC full text.
    Returns a list of absolute PMC URLs.
    """
    soup = BeautifulSoup(html, "html.parser")
    pmc_urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "pmc.ncbi.nlm.nih.gov" in href:
            pmc_urls.append(requests.compat.urljoin(base_url, href))

    # dedupe
    pmc_urls = list(dict.fromkeys(pmc_urls))
    if pmc_urls:
        print(f"[online] found PMC links on {base_url}:")
        for u in pmc_urls:
            print(f"        {u}")
    return pmc_urls


def try_download_from_url(url: str, figs_dir: Path, headers, visited: set, url_queue: list, tried_meta: list):
    """
    Try one URL:
      - fetch HTML
      - if pubmed: discover PMC links and push onto queue
      - try to extract <img> figure URLs and download them
    Returns list of {url, file} for downloaded images.
    """
    visited.add(url)
    final_url, html, ctype = fetch_html(url, headers)
    if not html:
        tried_meta.append({"url": url, "final_url": final_url, "status": "no_html"})
        return []

    tried_meta.append({"url": url, "final_url": final_url, "status": "html"})

    parsed = urllib.parse.urlparse(final_url or url)
    host = parsed.netloc.lower()

    # If this is a PubMed article page, look for PMC links and enqueue them
    if "pubmed.ncbi.nlm.nih.gov" in host:
        pmc_candidates = find_pmc_links_in_html(final_url, html)
        for pmc_url in pmc_candidates:
            if pmc_url not in visited and pmc_url not in url_queue:
                url_queue.append(pmc_url)

    # Extract and download figure images
    img_urls = extract_img_urls_from_html(final_url, html)
    print(f"[online] {len(img_urls)} candidate image URLs from {final_url}")

    downloaded = []
    for i, img_url in enumerate(img_urls, start=1):
        try:
            r = requests.get(img_url, headers=headers, timeout=15)
        except Exception as e:
            print(f"[online] download failed {img_url}: {e}")
            continue
        if r.status_code != 200 or not r.content:
            continue

        ext = ".png"
        lower = img_url.lower()
        for cand in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".gif"):
            if cand in lower:
                ext = cand
                break

        fname = figs_dir / f"figure_{i}{ext}"
        fname.write_bytes(r.content)
        downloaded.append({"url": img_url, "file": fname.name})
        print(f"[online] {img_url} -> {fname}")

    return downloaded


def main():
    if len(sys.argv) != 3:
        print("Usage: download_figures.py <citekey> <outdir>")
        sys.exit(1)

    citekey = sys.argv[1]
    outdir = Path(sys.argv[2])
    figs_dir = outdir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    entry = get_entry(citekey)
    doi = get_field(entry, "doi")
    pmcid = get_field(entry, "pmcid")  # optional, if you add it later

    print(f"[online] citekey={citekey}, doi={doi}, pmcid={pmcid}")

    headers = {"User-Agent": "pixecog-figures-bot/0.1 (personal research)"}

    url_queue = []
    visited = set()
    tried_meta = []

    # 1) If we ever add pmcid to entries, try PMC directly first
    if pmcid:
        pmcid_clean = pmcid.replace("PMC", "").strip()
        url_queue.append(f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid_clean}/")

    # 2) DOI landing page
    if doi:
        url_queue.append(f"https://doi.org/{doi}")
        # 3) PubMed search by DOI (will redirect to article page)
        url_queue.append(f"https://pubmed.ncbi.nlm.nih.gov/?term={doi}")

    # dedupe while preserving order
    seen = set()
    url_queue = [u for u in url_queue if not (u in seen or seen.add(u))]

    print("[online] initial URL candidates:")
    for u in url_queue:
        print(f"  - {u}")

    downloaded_all = []

    # Breadth-first-ish: pop from the front, append PMC links at the end
    idx = 0
    while idx < len(url_queue) and not downloaded_all:
        url = url_queue[idx]
        idx += 1

        if url in visited:
            continue

        new_downloads = try_download_from_url(url, figs_dir, headers, visited, url_queue, tried_meta)
        downloaded_all.extend(new_downloads)

    if downloaded_all:
        meta = {
            "source": "online",
            "doi": doi,
            "pmcid": pmcid,
            "figures": downloaded_all,
            "tried_urls": url_queue,
            "trace": tried_meta,
        }
        (outdir / "meta.json").write_text(json.dumps(meta, indent=2))
        print(f"[online] total figures downloaded for {citekey}: {len(downloaded_all)}")
    else:
        print(f"[online] no usable figures found for {citekey}")


if __name__ == "__main__":
    main()
