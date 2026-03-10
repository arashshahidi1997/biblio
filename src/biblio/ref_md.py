from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import BiblioConfig
from .grobid import _normalize_title, build_corpus_for_match, grobid_outputs_for_key
from .docling import outputs_for_key
from .ledger import utc_now_iso, write_json

_TEI = "http://www.tei-c.org/ns/1.0"
_T = f"{{{_TEI}}}"
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

# Fallback regex for purely numeric citation groups: (1), (1, 2), (1-3), (1–3)
_NUMERIC_CITE_RE = re.compile(
    r"\((\d+(?:\s*[-\u2013]\s*\d+|\s*[,;]\s*\d+)*)\)"
)


@dataclass(frozen=True)
class RefMdOutputs:
    outdir: Path
    md_path: Path    # <key>_ref_resolved.md
    meta_path: Path  # _ref_md_biblio.json


def ref_md_outputs_for_key(cfg: BiblioConfig, citekey: str) -> RefMdOutputs:
    key = citekey.lstrip("@")
    outdir = (cfg.out_root / key).resolve()
    return RefMdOutputs(
        outdir=outdir,
        md_path=outdir / f"{key}_ref_resolved.md",
        meta_path=outdir / "_ref_md_biblio.json",
    )


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def parse_tei_biblstructs(tei_xml: str) -> dict[str, dict[str, Any]]:
    """Extract xml_id -> {title, authors, year, doi, display_num} from listBibl.

    xml:id is 'bN' (0-based); display_num = N + 1 (citation number in paper text).
    """
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for bib in root.findall(f".//{_T}listBibl/{_T}biblStruct"):
        xml_id = bib.get(_XML_ID) or bib.get("xml:id") or ""
        if not xml_id:
            continue

        # display_num from xml:id format 'bN'
        display_num: int | None = None
        if re.match(r"^b\d+$", xml_id):
            display_num = int(xml_id[1:]) + 1

        # Title: analytic first (article), then monogr (book/proceedings)
        title: str | None = None
        for container in (f"{_T}analytic", f"{_T}monogr"):
            t_el = bib.find(f"{container}/{_T}title")
            if t_el is not None:
                title = _text(t_el) or None
                break

        # Authors
        authors: list[str] = []
        for author_el in bib.findall(f".//{_T}author"):
            persname = author_el.find(f"{_T}persName")
            if persname is None:
                continue
            forenames = " ".join(_text(f) for f in persname.findall(f"{_T}forename")).strip()
            surname = _text(persname.find(f"{_T}surname"))
            full = f"{forenames} {surname}".strip() if forenames else surname
            if full:
                authors.append(full)

        # Year
        year: str | None = None
        for date_el in bib.findall(f".//{_T}date"):
            when = date_el.get("when") or date_el.get("year")
            if when:
                year = when[:4]
                break

        # DOI
        doi: str | None = None
        for idno in bib.findall(f".//{_T}idno"):
            if idno.get("type", "").upper() == "DOI":
                doi = _text(idno) or None
                break

        result[xml_id] = {
            "title": title,
            "authors": authors,
            "year": year,
            "doi": doi,
            "display_num": display_num,
        }

    return result


def match_biblstructs_to_corpus(
    cfg: BiblioConfig,
    biblstructs: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Match bib xml_ids to local citekeys. Returns {xml_id: citekey}.

    DOI match takes priority over title match.
    """
    corpus = build_corpus_for_match(cfg)

    doi_index: dict[str, str] = {}
    title_index: dict[str, str] = {}
    grobid_root = cfg.repo_root / "bib" / "derivatives" / "grobid"

    for record in corpus:
        ck = str(record.get("citekey") or "").strip()
        if not ck:
            continue
        doi = str(record.get("doi") or "").strip().lower()
        if doi:
            doi_index.setdefault(doi, ck)
        title = str(record.get("title") or "").strip()
        if title:
            norm = _normalize_title(title)
            if norm:
                title_index.setdefault(norm, ck)
        # Enrich from GROBID header (paper may have DOI/title not in srcbib)
        header_path = grobid_root / ck / "header.json"
        if header_path.exists():
            try:
                header = json.loads(header_path.read_text(encoding="utf-8"))
                h_doi = str(header.get("doi") or "").strip().lower()
                if h_doi:
                    doi_index.setdefault(h_doi, ck)
                h_title = str(header.get("title") or "").strip()
                if h_title:
                    norm = _normalize_title(h_title)
                    if norm:
                        title_index.setdefault(norm, ck)
            except Exception:  # noqa: BLE001
                pass

    result: dict[str, str] = {}
    for xml_id, bib_data in biblstructs.items():
        ref_doi = str(bib_data.get("doi") or "").strip().lower()
        ref_title = str(bib_data.get("title") or "").strip()

        if ref_doi and ref_doi in doi_index:
            result[xml_id] = doi_index[ref_doi]
        elif ref_title:
            norm = _normalize_title(ref_title)
            if norm and norm in title_index:
                result[xml_id] = title_index[norm]

    return result


def build_number_to_citekey(
    biblstructs: dict[str, dict[str, Any]],
    bib_id_to_citekey: dict[str, str],
) -> dict[int, str]:
    """Map citation display numbers to local citekeys (for numeric-style papers).

    Uses xml_id format 'bN' -> display_num = N+1.
    """
    result: dict[int, str] = {}
    for xml_id, citekey in bib_id_to_citekey.items():
        bib_data = biblstructs.get(xml_id, {})
        display_num = bib_data.get("display_num")
        if display_num is not None:
            result[display_num] = citekey
    return result


def extract_citation_clusters_from_body(
    tei_xml: str,
    bib_id_to_citekey: dict[str, str],
) -> list[tuple[str, list[str]]]:
    """Extract (display_text, [citekeys]) for fully-resolved citation groups.

    Parses the TEI body to find consecutive <ref type="bibr"> element groups.
    A group is a sequence of adjacent bibr refs where all but the last have an
    empty/None tail (meaning no intervening prose text).

    The closing ')' is appended when the last ref's tail starts with ')'.
    Only groups starting with '(' and fully resolved to local citekeys are returned.
    """
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return []

    clusters: list[tuple[str, list[str]]] = []
    seen_displays: set[str] = set()

    for para in root.findall(f".//{_T}body//{_T}p"):
        children = list(para)
        i = 0
        while i < len(children):
            child = children[i]
            if child.tag != f"{_T}ref" or child.get("type") != "bibr":
                i += 1
                continue

            # Collect a group of consecutive bibr refs
            group: list[ET.Element] = []
            j = i
            while j < len(children):
                c = children[j]
                if c.tag == f"{_T}ref" and c.get("type") == "bibr":
                    group.append(c)
                    j += 1
                    # A non-empty tail on any ref (other than pure whitespace) ends the group
                    if c.tail and c.tail.strip():
                        break
                else:
                    break

            # Build display text from concatenated ref text content
            display = "".join("".join(c.itertext()) for c in group)

            # Append ')' if the last ref's tail opens with ')' but isn't already in the text
            last = group[-1]
            if last.tail and last.tail.startswith(")") and not display.endswith(")"):
                display += ")"

            # Only handle citations that form a parenthesized group starting with '('
            if display.startswith("("):
                bib_ids = [c.get("target", "").lstrip("#") for c in group]
                bib_ids = [b for b in bib_ids if b]
                citekeys = [bib_id_to_citekey.get(b) for b in bib_ids]

                if bib_ids and all(ck is not None for ck in citekeys) and display not in seen_displays:
                    seen_displays.add(display)
                    clusters.append((display, citekeys))  # type: ignore[arg-type]

            i = j

    return clusters


def _display_to_pattern(display: str) -> re.Pattern:  # type: ignore[type-arg]
    """Build a whitespace-tolerant regex pattern from a GROBID citation display text.

    GROBID omits spaces after separators (';', ',') when concatenating consecutive
    ref elements. The source document (docling markdown) may include these spaces.
    """
    esc = re.escape(display)
    # Allow optional whitespace after ; and , (inter-citation separator gaps)
    esc = esc.replace(";", r";\s*").replace(",", r",\s*")
    return re.compile(esc)


def resolve_citations_in_markdown(
    md_text: str,
    number_to_citekey: dict[int, str],
    clusters: list[tuple[str, list[str]]],
) -> str:
    """Replace citation markers in markdown with pandoc [@citekey] syntax.

    Two-pass approach:
    1. Text-based: replace GROBID-extracted display strings (handles all styles:
       author-year, numbered, mixed). Longest matches applied first.
    2. Numeric fallback: replace remaining parenthesized numeric groups using
       the bN -> display_num mapping.
    """
    result = md_text

    # Pass 1: text-based substitution using GROBID body ref clusters
    if clusters:
        # Longest display text first to avoid substring conflicts
        for display, citekeys in sorted(clusters, key=lambda x: len(x[0]), reverse=True):
            pandoc = "[" + "; ".join(f"@{ck}" for ck in citekeys) + "]"
            try:
                result = _display_to_pattern(display).sub(pandoc, result)
            except re.error:
                pass  # skip malformed patterns

    # Pass 2: numeric fallback for numbered-citation papers
    if number_to_citekey:
        def _replace_numeric(m: re.Match) -> str:  # type: ignore[type-arg]
            start = m.start()
            if start > 0 and result[start - 1] == "[":
                return m.group(0)
            nums = _expand_numbers(m.group(1))
            if not nums:
                return m.group(0)
            citekeys_list = [number_to_citekey.get(n) for n in nums]
            if any(ck is None for ck in citekeys_list):
                return m.group(0)
            return "[" + "; ".join(f"@{ck}" for ck in citekeys_list) + "]"  # type: ignore[arg-type]

        result = _NUMERIC_CITE_RE.sub(_replace_numeric, result)

    return result


def _expand_numbers(group_str: str) -> list[int]:
    """Parse '1, 3-5, 7' -> [1, 3, 4, 5, 7]. Also handles en-dash ranges."""
    nums: list[int] = []
    for token in re.split(r"[,;]", group_str):
        token = token.strip()
        range_m = re.match(r"(\d+)\s*[-\u2013]\s*(\d+)$", token)
        if range_m:
            nums.extend(range(int(range_m.group(1)), int(range_m.group(2)) + 1))
        elif re.match(r"^\d+$", token):
            nums.append(int(token))
    return nums


def run_ref_md_for_key(
    cfg: BiblioConfig,
    citekey: str,
    *,
    force: bool = False,
) -> RefMdOutputs:
    """Produce reference-resolved markdown for a single citekey.

    Requires existing docling MD and GROBID TEI artifacts.
    Raises FileNotFoundError if either is missing.
    """
    key = citekey.lstrip("@")
    out = ref_md_outputs_for_key(cfg, key)

    if out.md_path.exists() and not force:
        return out

    docling_out = outputs_for_key(cfg, key)
    if not docling_out.md_path.exists():
        raise FileNotFoundError(f"Docling markdown not found for {key}: {docling_out.md_path}")

    grobid_out = grobid_outputs_for_key(cfg, key)
    if not grobid_out.tei_path.exists():
        raise FileNotFoundError(f"GROBID TEI not found for {key}: {grobid_out.tei_path}")

    tei_xml = grobid_out.tei_path.read_text(encoding="utf-8")
    md_text = docling_out.md_path.read_text(encoding="utf-8")

    biblstructs = parse_tei_biblstructs(tei_xml)
    bib_id_to_citekey = match_biblstructs_to_corpus(cfg, biblstructs)
    number_to_citekey = build_number_to_citekey(biblstructs, bib_id_to_citekey)
    clusters = extract_citation_clusters_from_body(tei_xml, bib_id_to_citekey)
    resolved_md = resolve_citations_in_markdown(md_text, number_to_citekey, clusters)

    out.outdir.mkdir(parents=True, exist_ok=True)
    out.md_path.write_text(resolved_md, encoding="utf-8")

    meta: dict[str, Any] = {
        "citekey": key,
        "timestamp": utc_now_iso(),
        "source_docling_md": str(docling_out.md_path),
        "source_tei": str(grobid_out.tei_path),
        "total_biblstructs": len(biblstructs),
        "matched_biblstructs": len(bib_id_to_citekey),
        "resolved_clusters": len(clusters),
        "bib_id_to_citekey": bib_id_to_citekey,
        "number_to_citekey": {str(k): v for k, v in number_to_citekey.items()},
        "forced": force,
    }
    write_json(out.meta_path, meta)

    return out
